"""Pipeline persistence and lifecycle services."""

from __future__ import annotations

import datetime
import shutil
import uuid
from pathlib import Path

from pipeline_artifacts import (
    basename_only,
    downstream_output_keys,
    auxiliary_step_data_keys,
    keys_to_clear_from_step,
    locate_workspace_file,
    validate_step_data_patch,
    workspace_dir_for,
)
from shared import _pipelines_lock, load_pipelines, save_pipelines


def get_pipeline(pipeline_id: str) -> dict | None:
    """Get a single pipeline by ID (under lock)."""
    if not pipeline_id:
        return None
    with _pipelines_lock:
        pipelines = load_pipelines()
        for p in pipelines:
            if p.get("id") == pipeline_id:
                return p
    return None


def list_pipelines() -> list[dict]:
    with _pipelines_lock:
        pipelines = load_pipelines()
    pipelines.sort(key=lambda p: p.get("updated_at", ""), reverse=True)
    return pipelines


def create_pipeline(data: dict, workspace: Path) -> dict:
    name = (data.get("name") or "").strip()
    scenario = (data.get("scenario") or "").strip()
    domain = (data.get("domain") or "").strip()

    if not name:
        return {"status": "error", "error": "流水线名称不能为空"}

    now = datetime.datetime.now().isoformat()
    pipeline_id = uuid.uuid4().hex[:12]
    pipeline_stub = {"id": pipeline_id, "name": name}
    workspace_dir = workspace_dir_for(pipeline_stub, workspace=workspace)
    pipeline = {
        "id": pipeline_id,
        "name": name,
        "scenario": scenario,
        "domain": domain or scenario,
        "workspace_dir": workspace_dir,
        "current_step": 1,
        "step_status": {"1": "pending", "2": "pending", "3": "pending", "4": "pending", "5": "pending"},
        "step_data": {},
        "created_at": now,
        "updated_at": now,
    }

    with _pipelines_lock:
        pipelines = load_pipelines()
        pipelines.append(pipeline)
        save_pipelines(pipelines)

    return {"status": "ok", "pipeline": pipeline}


def update_pipeline(pipeline_id: str, data: dict, workspace: Path) -> dict:
    with _pipelines_lock:
        pipelines = load_pipelines()
        target = None
        for p in pipelines:
            if p["id"] == pipeline_id:
                target = p
                break
        if not target:
            return {"status": "error", "error": "流水线不存在"}

        if "current_step" in data:
            target["current_step"] = max(target.get("current_step", 1), data["current_step"])
        if "step_status" in data:
            for k, v in data["step_status"].items():
                if v == "done" or target["step_status"].get(k) != "done":
                    target["step_status"][k] = v
        if "step_data" in data:
            patch = data["step_data"]
            if not isinstance(patch, dict):
                return {"status": "error", "error": "step_data 格式错误"}
            err = validate_step_data_patch(patch)
            if err:
                return {"status": "error", "error": err}
            target["step_data"].update(patch)
        if "name" in data:
            old_name = target.get("name", "")
            new_name = data["name"]
            if new_name != old_name:
                target["name"] = new_name
                old_dir = workspace / (target.get("workspace_dir") or target["id"])
                target["workspace_dir"] = workspace_dir_for(target, workspace=workspace)
                new_dir = workspace / target["workspace_dir"]
                if old_dir.is_dir() and not new_dir.exists():
                    try:
                        old_dir.rename(new_dir)
                    except Exception:
                        pass

        target["updated_at"] = datetime.datetime.now().isoformat()
        save_pipelines(pipelines)

    return {"status": "ok", "pipeline": target}


def delete_pipeline(pipeline_id: str, workspace: Path) -> dict:
    removed_pipeline = None
    with _pipelines_lock:
        pipelines = load_pipelines()
        before = len(pipelines)
        removed_pipeline = next((p for p in pipelines if p["id"] == pipeline_id), None)
        pipelines = [p for p in pipelines if p["id"] != pipeline_id]
        if len(pipelines) == before:
            return {"status": "error", "error": "流水线不存在"}
        save_pipelines(pipelines)

    if removed_pipeline:
        pipeline_dir = workspace / (removed_pipeline.get("workspace_dir") or removed_pipeline["id"])
        if pipeline_dir.is_dir():
            try:
                shutil.rmtree(pipeline_dir)
            except Exception:
                pass

    return {"status": "ok"}


def clear_pipeline(pipeline_id: str) -> dict:
    with _pipelines_lock:
        pipelines = load_pipelines()
        pipeline = next((p for p in pipelines if p["id"] == pipeline_id), None)
        if not pipeline:
            return {"status": "error", "error": "流水线不存在"}
        pipeline["step_data"] = {}
        pipeline["step_status"] = {str(i): "pending" for i in range(1, 6)}
        pipeline["current_step"] = 1
        pipeline["updated_at"] = datetime.datetime.now().isoformat()
        save_pipelines(pipelines)
    return {"status": "ok"}


def rollback_pipeline(pipeline_id: str, step: int, workspace: Path) -> dict:
    if step < 1 or step > 5:
        return {"status": "error", "error": "步骤号必须在 1-5 之间"}

    with _pipelines_lock:
        pipelines = load_pipelines()
        pipeline = next((p for p in pipelines if p["id"] == pipeline_id), None)
        if not pipeline:
            return {"status": "error", "error": "流水线不存在"}

        for s in range(step, 6):
            pipeline["step_status"][str(s)] = "pending"

        sd = pipeline.setdefault("step_data", {})

        _trash_dir = workspace / "_trash"
        for key in downstream_output_keys(step):
            filename = str(sd.get(key, "")).strip()
            if not filename:
                continue
            file_path = locate_workspace_file(workspace, filename, pipeline_id=pipeline_id)
            if file_path and file_path.exists():
                try:
                    _trash_dir.mkdir(parents=True, exist_ok=True)
                    dest = _trash_dir / file_path.name
                    if dest.exists():
                        dest = _trash_dir / f"{file_path.stem}_{uuid.uuid4().hex[:6]}{file_path.suffix}"
                    shutil.move(str(file_path), str(dest))
                except Exception:
                    pass
            sd.pop(key, None)

        for key in auxiliary_step_data_keys(step):
            sd.pop(key, None)

        pipeline["current_step"] = step
        pipeline["updated_at"] = datetime.datetime.now().isoformat()
        save_pipelines(pipelines)

    return {"status": "ok", "pipeline": pipeline}

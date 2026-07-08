"""Step1 场景锚定业务服务."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from pipeline_artifacts import (
    basename_only,
    infer_file_step,
    keys_to_clear_from_step,
    workspace_path_for,
)
from shared import (
    _pipelines_lock,
    _safe_workbook,
    load_pipelines,
    save_pipelines,
    SCHEMA_PATH,
    SAMPLES_DIR,
    _excel_to_markdown_file,
    _pipeline_prefers_markdown,
)


def generate_step1(data: dict, request_form: dict, request_files: dict, workspace: Path) -> dict:
    """Step1: 将场景四项填入萃取模板前四列，保留模板表结构（无 LLM）."""
    from step1_template import (
        fill_scenario_skeleton,
        find_default_step1_template,
        list_default_step1_templates,
    )
    from scenario_schema import (
        enrich_knowledge_columns_for_markdown,
        load_scenario_schema,
        normalize_knowledge_columns,
        resolve_knowledge_columns_for_request,
    )
    from step1_markdown_builder import generate_markdown_skeleton
    from step1_schema_builder import generate_skeleton_from_schema

    scenario_name = request_form.get("scenario_name", "").strip()
    scenario_content = request_form.get("scenario_content", "").strip()
    sub_scenarios_json = request_form.get("sub_scenarios", "[]")
    pipeline_id = request_form.get("pipeline_id", "") or data.get("pipeline_id", "")
    template_mode = (request_form.get("template_mode", "") or "").strip().lower()
    output_format = (request_form.get("output_format", "excel") or "excel").strip().lower()
    if output_format not in {"excel", "markdown"}:
        output_format = "excel"
    knowledge_columns_json = request_form.get("knowledge_columns", "[]")

    if not scenario_name:
        return {"status": "error", "error": "场景名称不能为空"}

    try:
        sub_scenarios = json.loads(sub_scenarios_json) if sub_scenarios_json else []
    except json.JSONDecodeError:
        sub_scenarios = []

    try:
        user_columns_raw = json.loads(knowledge_columns_json) if knowledge_columns_json else []
        if not isinstance(user_columns_raw, list):
            user_columns_raw = []
    except json.JSONDecodeError:
        user_columns_raw = []

    schema = load_scenario_schema(SCHEMA_PATH) if SCHEMA_PATH.exists() else {}
    knowledge_columns = resolve_knowledge_columns_for_request(schema, user_columns_raw)
    has_custom_columns = bool(normalize_knowledge_columns(user_columns_raw))
    columns_enriched = False
    user_knowledge_columns = list(knowledge_columns)
    if output_format == "markdown":
        knowledge_columns, columns_enriched, _substantive = enrich_knowledge_columns_for_markdown(
            user_columns_raw, schema
        )
    if not knowledge_columns and output_format != "upload":
        return {"status": "error", "error": "请至少定义一列知识字段"}

    template_path = None
    selected_default_template = request_form.get("default_template", "").strip()
    template_source = "schema"
    template_name = ""
    schema_meta = None
    md_name = ""
    md_download_url = ""
    upload = request_files.get("template")
    if upload and upload.filename:
        ext = os.path.splitext(upload.filename)[1].lower()
        if ext not in (".xlsx", ".xls"):
            return {"status": "error", "error": "模板仅支持 .xlsx / .xls 格式"}
        temp_name = f"upload_tpl_{uuid.uuid4().hex[:8]}{ext}"
        template_path_obj = workspace_path_for(workspace, pipeline_id, infer_file_step(temp_name) or "uploads", temp_name)
        template_path_obj.parent.mkdir(parents=True, exist_ok=True)
        template_path = str(template_path_obj)
        upload.save(template_path)
        template_source = "upload"
        template_name = upload.filename
    elif template_mode == "legacy" and not has_custom_columns:
        step1_tpl_dir = SAMPLES_DIR / "step1-场景锚定"
        default_tpl = None
        if selected_default_template and selected_default_template != "__schema__":
            candidates = {p.name: p for p in list_default_step1_templates(step1_tpl_dir)}
            default_tpl = candidates.get(selected_default_template)
            if not default_tpl:
                return {"status": "error", "error": "所选 Excel 模板不存在，请刷新后重试"}
        else:
            default_tpl = find_default_step1_template(step1_tpl_dir)

        if default_tpl:
            template_path = str(default_tpl)
            template_source = "legacy"
            template_name = default_tpl.name

    uid = uuid.uuid4().hex[:8]
    output_name = f"template_{uid}.xlsx"
    output_path_obj = workspace_path_for(workspace, pipeline_id, "step1", output_name)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    output_path = str(output_path_obj)
    primary_download_name = output_name
    primary_download_url = "/downloads/" + output_name

    try:
        if template_path and os.path.exists(template_path):
            fill_result = fill_scenario_skeleton(
                template_path, output_path, scenario_name, scenario_content, sub_scenarios
            )
            knowledge_columns = knowledge_columns or []
            if output_format == "markdown":
                md_name = f"template_{uid}.md"
                md_path = workspace_path_for(workspace, pipeline_id, "step1", md_name)
                md_path.parent.mkdir(parents=True, exist_ok=True)
                _excel_to_markdown_file(output_path, md_path, title=f"场景锚定骨架 · {scenario_name}")
                primary_download_name = md_name
                primary_download_url = "/downloads/" + md_name
                md_download_url = primary_download_url
                if template_source == "upload":
                    template_source = "upload_markdown"
                elif template_source == "legacy":
                    template_source = "legacy_markdown"
        elif output_format == "markdown":
            if not SCHEMA_PATH.exists():
                return {"status": "error", "error": "未找到 config/scenario-schema.yaml，无法生成骨架"}
            md_name = f"template_{uid}.md"
            md_path_obj = workspace_path_for(workspace, pipeline_id, "step1", md_name)
            md_path_obj.parent.mkdir(parents=True, exist_ok=True)
            md_path = str(md_path_obj)
            generate_markdown_skeleton(
                md_path,
                scenario_name,
                scenario_content,
                sub_scenarios,
                knowledge_columns,
            )
            fill_result = generate_skeleton_from_schema(
                SCHEMA_PATH,
                output_path,
                scenario_name,
                scenario_content,
                sub_scenarios,
                knowledge_columns=knowledge_columns,
            )
            schema_meta = fill_result.get("schema") or {}
            template_source = "schema_markdown"
            template_name = "自定义列 · Markdown + Excel"
            primary_download_name = md_name
            primary_download_url = "/downloads/" + md_name
            md_download_url = primary_download_url
        else:
            if not SCHEMA_PATH.exists():
                return {"status": "error", "error": "未找到 config/scenario-schema.yaml，无法按结构方案生成模板"}
            fill_result = generate_skeleton_from_schema(
                SCHEMA_PATH,
                output_path,
                scenario_name,
                scenario_content,
                sub_scenarios,
                knowledge_columns=knowledge_columns,
            )
            schema_meta = fill_result.get("schema") or {}
            template_source = "schema"
            template_name = (
                f"{schema_meta.get('display_name', '自定义结构')} "
                f"({schema_meta.get('version', 'v1.0')})"
            ).strip()
    except ValueError as e:
        return {"status": "error", "error": str(e)}
    except Exception as e:
        return {"status": "error", "error": f"生成场景骨架失败: {str(e)}"}

    if schema_meta is None and SCHEMA_PATH.exists():
        from scenario_schema import schema_summary
        schema_meta = schema_summary(schema, schema_path=SCHEMA_PATH)
        schema_meta["knowledge_columns"] = knowledge_columns

    result = {
        "status": "ok",
        "scenario": scenario_name,
        "download_url": primary_download_url,
        "file_name": primary_download_name,
        "excel_file": output_name,
        "excel_download_url": "/downloads/" + output_name,
        "output_format": output_format,
        "knowledge_columns": knowledge_columns,
        "user_knowledge_columns": user_knowledge_columns,
        "columns_enriched": columns_enriched,
        "version": (schema_meta or {}).get("version", "v0.1"),
        "fields_info": fill_result.get("fields_info", []),
        "sub_scenario_count": fill_result.get("sub_scenario_count", len(sub_scenarios)),
        "template_source": template_source,
        "template_name": template_name,
        "schema": schema_meta,
    }
    if md_name:
        result["markdown_file"] = md_name
        result["markdown_download_url"] = md_download_url

    saved_pipeline = None
    if pipeline_id:
        with _pipelines_lock:
            pipelines = load_pipelines()
            for p in pipelines:
                if p["id"] == pipeline_id:
                    sd = p.setdefault("step_data", {})
                    for key in keys_to_clear_from_step(1):
                        sd.pop(key, None)
                    sd["step1_output_file"] = output_name
                    sd["step1_download_url"] = "/downloads/" + output_name
                    sd["step1_template_source"] = template_source
                    sd["step1_template_name"] = template_name
                    sd["step1_output_format"] = output_format
                    sd["step1_knowledge_columns"] = knowledge_columns
                    sd["step1_user_knowledge_columns"] = user_knowledge_columns
                    sd["step1_columns_enriched"] = columns_enriched
                    if md_name:
                        sd["step1_md_file"] = md_name
                        sd["step1_md_download_url"] = md_download_url
                    else:
                        sd.pop("step1_md_file", None)
                        sd.pop("step1_md_download_url", None)
                    p["scenario"] = scenario_name
                    p["domain"] = p.get("domain", "") or scenario_name
                    p.setdefault("step_status", {})
                    p["step_status"]["1"] = "done"
                    if "2" not in p["step_status"] or p["step_status"]["2"] == "pending":
                        p["step_status"]["2"] = "active"
                    p["current_step"] = max(p.get("current_step", 1), 2)
                    p["updated_at"] = __import__("datetime").datetime.now().isoformat()
                    save_pipelines(pipelines)
                    saved_pipeline = dict(p)
                    saved_pipeline["step_data"] = dict(p.get("step_data", {}))
                    break

    if saved_pipeline:
        result["pipeline"] = saved_pipeline
    return result


def step1_schema() -> dict:
    """返回当前知识结构方案（scenario-schema.yaml）摘要."""
    from scenario_schema import load_scenario_schema, schema_summary
    if not SCHEMA_PATH.exists():
        return {"status": "error", "error": "未找到 scenario-schema.yaml"}
    schema = load_scenario_schema(SCHEMA_PATH)
    return {"status": "ok", "schema": schema_summary(schema, schema_path=SCHEMA_PATH)}


def step1_templates() -> dict:
    """列出 Step1 模板来源：默认 schema + 可选 legacy Excel 模板."""
    from scenario_schema import load_scenario_schema, schema_summary
    from step1_template import list_default_step1_templates, find_default_step1_template

    schema_info = {}
    if SCHEMA_PATH.exists():
        schema_info = schema_summary(load_scenario_schema(SCHEMA_PATH), schema_path=SCHEMA_PATH)

    step1_tpl_dir = SAMPLES_DIR / "step1-场景锚定"
    all_templates = list_default_step1_templates(step1_tpl_dir)
    templates = all_templates
    default_tpl = find_default_step1_template(step1_tpl_dir)
    legacy_default = default_tpl.name if default_tpl else ""

    return {
        "status": "ok",
        "schema": schema_info,
        "default_mode": "schema",
        "templates": [
            {"name": p.name, "label": p.stem, "kind": "legacy"}
            for p in templates
        ],
        "default_template": "__schema__",
        "legacy_default_template": legacy_default,
    }

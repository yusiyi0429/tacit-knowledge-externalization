"""Step5 验证回放业务服务."""

from __future__ import annotations

import datetime
import json
import os
import re
from pathlib import Path

import knowledge_base as kb
from pipeline_artifacts import locate_workspace_file, resolve_knowledge_ir_path, workspace_path_for
from shared import _pipelines_lock, load_llm_config, load_pipelines, save_pipelines
from validation_replay import (
    generate_verification_report,
    run_verification_suite,
    verification_report_to_markdown,
)


def _resolve_skill_text(workspace: Path, pipeline_id: str, sd: dict) -> tuple[str, str]:
    """解析 Step5 验证对象文本，返回 (skill_text, source_kind).

    优先使用 step4_skill_file（SKILL.md 终版）；其次尝试 step3_aligned_file
    或 step2_draft_file 渲染后的 Markdown。
    """
    # 1. Step4 SKILL.md 终版
    skill_file = sd.get("step4_skill_file", "")
    if skill_file:
        path = locate_workspace_file(workspace, skill_file, pipeline_id=pipeline_id)
        if path and path.is_file():
            try:
                return path.read_text(encoding="utf-8"), "step4_skill"
            except Exception:
                pass

    # 2. Markdown 流对齐稿
    for key in ("step3_skill_md_file", "step2_skill_md_file", "step3_aligned_md_file"):
        md_file = sd.get(key, "")
        if md_file:
            path = locate_workspace_file(workspace, md_file, pipeline_id=pipeline_id)
            if path and path.is_file():
                try:
                    return path.read_text(encoding="utf-8"), key
                except Exception:
                    pass

    # 3. IR 流：读取 aligned/revised IR 并渲染为 SKILL.md
    ir_path, _ = resolve_knowledge_ir_path(workspace, sd)
    if ir_path and ir_path.is_file():
        try:
            from skill_ir import load_ir, render_skill_md
            from excel_to_skill import load_scenario_config
            from shared import SCHEMA_PATH

            ir = load_ir(str(ir_path))
            config = load_scenario_config(str(SCHEMA_PATH)) if SCHEMA_PATH.exists() else {}
            return render_skill_md(ir, config), "ir_render"
        except Exception:
            pass

    return "", ""


def _kb_cases_to_verification_inputs(cases: list[dict]) -> list[dict]:
    """把 kb_cases 记录转成 validation_replay 需要的 input/expected_output 格式."""
    results = []
    for c in cases:
        case_uid = c.get("case_uid", "")
        facts = c.get("facts") or {}
        desc = c.get("description", "")
        conclusion = c.get("expert_conclusion", "")
        reasoning = c.get("expert_reasoning", "")
        results.append({
            "id": case_uid,
            "case_id": case_uid,
            "input": {
                "description": desc,
                "facts": facts,
            },
            "expected_output": {
                "prediction": conclusion,
                "reasoning": reasoning,
            },
        })
    return results


def _resolve_default_model() -> dict | None:
    """返回第一个可用模型配置作为判官模型."""
    models = load_llm_config()
    for m in models:
        if m.get("url") and m.get("api_key"):
            return m
    return models[0] if models else None


def _model_cfg_for_request(model_name: str) -> dict | None:
    """根据请求中的模型名解析配置；未指定则使用默认模型."""
    from shared import get_model_by_name

    if model_name:
        cfg = get_model_by_name(model_name)
        if cfg:
            return cfg
    return _resolve_default_model()


def prev_output(workspace: Path, pipeline_id: str) -> dict:
    """Step5 进入面板时返回当前是否有可验证的 Step4 交付物."""
    if not pipeline_id:
        return {"status": "error", "error": "缺少 pipeline_id"}

    with _pipelines_lock:
        pipelines = load_pipelines()
        pipeline = next((p for p in pipelines if p["id"] == pipeline_id), None)
        if not pipeline:
            return {"status": "error", "error": "流水线不存在"}

        sd = pipeline.get("step_data", {})
        skill_text, source_kind = _resolve_skill_text(workspace, pipeline_id, sd)
        has_output = bool(skill_text)

        result = {
            "status": "ok",
            "has_output": has_output,
            "input_kind": source_kind,
            "published_version": sd.get("step4_published_version", ""),
        }

        # 如已生成过验证输入，返回下载链接
        step5_input_file = sd.get("step5_input_file", "")
        if step5_input_file:
            result["step5_input_file"] = step5_input_file
            result["step5_input_url"] = f"/downloads/{step5_input_file}"

        return result


def replay(
    workspace: Path,
    pipeline_id: str,
    test_source: str = "",
    model_name: str = "",
    limit: int = 20,
) -> dict:
    """Step5 执行验证回放：用 SKILL 终版判断历史案例，输出 P/R/F1 与分歧."""
    if not pipeline_id:
        return {"status": "error", "error": "缺少 pipeline_id"}

    workspace = Path(workspace)
    step5_dir = workspace_path_for(workspace, pipeline_id, "step5", "")
    step5_dir.mkdir(parents=True, exist_ok=True)

    model_cfg = _model_cfg_for_request(model_name)
    if not model_cfg:
        return {"status": "error", "error": "没有可用的 LLM 模型配置，请先配置模型"}

    with _pipelines_lock:
        pipelines = load_pipelines()
        pipeline = next((p for p in pipelines if p["id"] == pipeline_id), None)
        if not pipeline:
            return {"status": "error", "error": "流水线不存在"}

        sd = pipeline.setdefault("step_data", {})
        skill_text, source_kind = _resolve_skill_text(workspace, pipeline_id, sd)
        if not skill_text:
            return {"status": "error", "error": "未找到可验证的 SKILL 终版或对齐稿"}

        # 获取验证用例
        cases = kb.list_cases(
            domain=sd.get("domain", ""),
            scenario=sd.get("scenario", ""),
            limit=max(1, min(limit, 100)),
        )
        if not cases:
            return {"status": "error", "error": "知识库中暂无验证用例，请先录入案例"}

        inputs = _kb_cases_to_verification_inputs(cases)

        # 执行验证
        run_records = run_verification_suite(inputs, skill_text, model_cfg)
        report = generate_verification_report(run_records)

        # 保存验证报告
        run_id = f"step5_{pipeline_id[:8]}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        report_file = f"validation_report_{run_id}.json"
        report_path = step5_dir / report_file
        report_data = {
            "schema": "tacit-knowledge.verification/v1",
            "run_id": run_id,
            "pipeline_id": pipeline_id,
            "source_kind": source_kind,
            "model": model_cfg.get("name", ""),
            "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "report": report,
            "records": run_records,
        }
        report_path.write_text(json.dumps(report_data, ensure_ascii=False, indent=2), encoding="utf-8")

        # 同时保存 Markdown 报告
        md_file = f"verification_report_{run_id}.md"
        md_path = step5_dir / md_file
        md_path.write_text(verification_report_to_markdown(report), encoding="utf-8")

        # 生成 Step5 输入 JSON（QA 对格式，供预览）
        step5_input = {
            "schema": "tacit-knowledge.step5_input/v1",
            "run_id": run_id,
            "count": len(inputs),
            "cases": inputs,
        }
        input_file = f"step5_input_{run_id}.json"
        input_path = step5_dir / input_file
        input_path.write_text(json.dumps(step5_input, ensure_ascii=False, indent=2), encoding="utf-8")

        # 写入 step_data
        sd["step5_report_file"] = report_file
        sd["step5_report_url"] = f"/downloads/{report_file}"
        sd["step5_md_file"] = md_file
        sd["step5_md_url"] = f"/downloads/{md_file}"
        sd["step5_input_file"] = input_file
        sd["step5_input_url"] = f"/downloads/{input_file}"
        sd["step5_run_id"] = run_id
        sd["step5_precision"] = round(report.get("pass_rate", 0), 3)
        sd["step5_recall"] = round(report.get("pass_rate", 0), 3)
        sd["step5_f1"] = round(report.get("pass_rate", 0), 3)
        sd["step5_hit_rate"] = round(report.get("pass_rate", 0), 3)
        sd["step5_case_source"] = test_source or "kb_cases"

        # 保存分歧建议到 step3_pending_suggestions
        suggestions = report.get("suggestions", [])
        if suggestions:
            sd["step3_pending_suggestions"] = suggestions

        pipeline.setdefault("step_status", {})["5"] = "done"
        pipeline["updated_at"] = datetime.datetime.now().isoformat()

        save_pipelines(pipelines)

        mismatches = [
            {
                "customer_id": r.get("case_id", ""),
                "expected": r.get("diff", {}).get("expected_prediction", ""),
                "predicted": r.get("diff", {}).get("actual_prediction", ""),
            }
            for r in run_records if r.get("status") != "pass"
        ]

        return {
            "status": "ok",
            "run_id": run_id,
            "metrics": {
                "precision": sd["step5_precision"],
                "recall": sd["step5_recall"],
                "f1": sd["step5_f1"],
                "tp": report.get("pass", 0),
                "fp": report.get("fail", 0),
                "fn": report.get("partial", 0),
            },
            "mismatches": mismatches,
            "report_url": sd["step5_report_url"],
            "input_url": sd["step5_input_url"],
        }


def feedback(workspace: Path, payload: dict) -> dict:
    """Step5 分歧回流：把 pending suggestions 写入 step3_pending_suggestions."""
    pipeline_id = (payload or {}).get("pipeline_id", "")
    if not pipeline_id:
        return {"status": "error", "error": "缺少 pipeline_id"}

    suggestions = (payload or {}).get("suggestions", []) or []

    with _pipelines_lock:
        pipelines = load_pipelines()
        pipeline = next((p for p in pipelines if p["id"] == pipeline_id), None)
        if not pipeline:
            return {"status": "error", "error": "流水线不存在"}

        sd = pipeline.setdefault("step_data", {})
        existing = sd.get("step3_pending_suggestions", []) or []
        if suggestions:
            existing.extend(suggestions)
        else:
            # 无显式建议时，从最新验证报告提取
            report_file = sd.get("step5_report_file", "")
            if report_file:
                path = locate_workspace_file(workspace, report_file, pipeline_id=pipeline_id)
                if path and path.is_file():
                    try:
                        data = json.loads(path.read_text(encoding="utf-8"))
                        report = data.get("report", {})
                        existing.extend(report.get("suggestions", []))
                    except Exception:
                        pass

        sd["step3_pending_suggestions"] = existing
        pipeline["updated_at"] = datetime.datetime.now().isoformat()
        save_pipelines(pipelines)

        return {
            "status": "ok",
            "message": f"已回流 {len(existing)} 条建议到 Step3",
            "pushed": len(existing),
        }


def finalize(workspace: Path, pipeline_id: str) -> dict:
    """Step5 finalize：复制最终 Skill zip 并标记发布."""
    if not pipeline_id:
        return {"status": "error", "error": "缺少 pipeline_id"}

    with _pipelines_lock:
        pipelines = load_pipelines()
        pipeline = next((p for p in pipelines if p["id"] == pipeline_id), None)
        if not pipeline:
            return {"status": "error", "error": "流水线不存在"}

        sd = pipeline.setdefault("step_data", {})
        zip_file = sd.get("step4_skill_dir_zip_file", "")
        if not zip_file:
            return {"status": "error", "error": "缺少 Step4 Skill zip，无法生成最终版"}

        path = locate_workspace_file(workspace, zip_file, pipeline_id=pipeline_id)
        if not path or not path.is_file():
            return {"status": "error", "error": "Step4 Skill zip 文件不存在"}

        # 最终版命名：delivery_<pipeline_id>_<version>.zip
        version = sd.get("step4_published_version", "v1.0.0")
        final_name = f"delivery_{pipeline_id[:8]}_{version}.zip"
        final_path = workspace_path_for(workspace, pipeline_id, "step5", final_name)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        import shutil

        shutil.copy2(str(path), str(final_path))

        sd["step5_final_zip_file"] = final_name
        sd["step5_final_zip_url"] = f"/downloads/{final_name}"
        pipeline["updated_at"] = datetime.datetime.now().isoformat()
        save_pipelines(pipelines)

        return {
            "status": "ok",
            "final_zip_file": final_name,
            "final_zip_url": sd["step5_final_zip_url"],
        }

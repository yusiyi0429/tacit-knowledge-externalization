"""Step2 知识萃取 Blueprint."""

from __future__ import annotations

from flask import Blueprint, request, jsonify

import shared
from services.step2_service import (
    extract_rules,
    extract_skill_md,
    extract_sql,
    step2_prev_output,
    step2_extract_unified,
)

bp = Blueprint("step2", __name__)


@bp.route("/prev_output", methods=["GET"])
def api_step2_prev_output():
    """获取当前流水线 Step1 的输出件信息，供 Step2 引用."""
    return jsonify(step2_prev_output(request.args.get("pipeline_id", ""), shared.WORKSPACE))


@bp.route("/extract_rules", methods=["POST"])
def api_step2_extract_rules():
    """Step2a: 从知识文档萃取业务规则 IR（无 SQL）."""
    return jsonify(extract_rules(
        request.form.get("pipeline_id", ""),
        request.form.get("model", ""),
        request.form.get("source_text", ""),
        request.files,
        shared.WORKSPACE,
    ))


@bp.route("/extract_sql", methods=["POST"])
def api_step2_extract_sql():
    """Step2b: 为规则 IR 生成取数逻辑 SQL."""
    return jsonify(extract_sql(
        request.form.get("pipeline_id", ""),
        request.form.get("model", ""),
        shared.WORKSPACE,
    ))


@bp.route("/extract", methods=["POST"])
def api_step2_extract():
    """统一知识萃取端点."""
    return jsonify(step2_extract_unified(request, shared.WORKSPACE))


@bp.route("/extract_skill_md", methods=["POST"])
def api_step2_extract_skill_md():
    """Step2: LLM 根据场景骨架+知识文档生成 SKILL.md."""
    return jsonify(extract_skill_md(
        request.form.get("pipeline_id", ""),
        request.form.get("model", ""),
        request.form,
        request.files,
        shared.WORKSPACE,
    ))


@bp.route("/multi_source_extract", methods=["POST"])
def step2_multi_source_extract():
    """[已废弃] 多源知识提取 — 内部委托到统一端点 /api/step2/extract."""
    return jsonify(step2_extract_unified(request, shared.WORKSPACE))


@bp.route("/fuse", methods=["POST"])
def step2_fuse():
    """[已废弃] 融合已有提取结果 — 内部委托到统一端点 /api/step2/extract."""
    return jsonify(step2_extract_unified(request, shared.WORKSPACE))


@bp.route("/interview/start", methods=["POST"])
def step2_interview_start():
    """[已废弃] 知识深挖 — 请使用 /api/step3/interview/start."""
    return jsonify({"status": "deprecated", "message": "请使用 /api/step3/interview/start"})


@bp.route("/interview/convert", methods=["POST"])
def step2_interview_convert():
    """[已废弃] 访谈转知识条目 — 请使用 /api/step3/interview/convert."""
    return jsonify({"status": "deprecated", "message": "请使用 /api/step3/interview/convert"})

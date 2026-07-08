"""Step4 智能转化 Blueprint."""

from __future__ import annotations

from flask import Blueprint, request, jsonify

import shared
from services.step4_service import compile_pipeline

bp = Blueprint("step4", __name__)


@bp.route("/build_skill", methods=["POST"])
def api_step4_build_skill():
    """旧端点，委托到 /compile（统一生成 SKILL + CoT + QA）。"""
    return jsonify(
        compile_pipeline(
            request.form.get("pipeline_id", ""),
            shared.WORKSPACE,
            formats=request.form.get("formats") or "skill,cot,qa",
        )
    )


@bp.route("/compile", methods=["POST"])
def api_step4_compile():
    """Step4 统一编译：从对齐 IR 生成 SKILL / CoT / QA 交付包。"""
    return jsonify(
        compile_pipeline(
            request.form.get("pipeline_id", ""),
            shared.WORKSPACE,
            formats=request.form.get("formats") or "skill,cot,qa",
        )
    )


@bp.route("/generate-executable-skill", methods=["POST"])
def api_step4_generate_executable_skill():
    return jsonify({"status": "error", "error": "Step4 generate-executable-skill 已合并到 /compile，请使用 /compile"})


@bp.route("/generate-cot", methods=["POST"])
def api_step4_generate_cot():
    return jsonify({"status": "error", "error": "Step4 generate-cot 已合并到 /compile，请使用 /compile"})


@bp.route("/generate-qa", methods=["POST"])
def api_step4_generate_qa():
    return jsonify({"status": "error", "error": "Step4 generate-qa 已合并到 /compile，请使用 /compile"})


@bp.route("/quality", methods=["POST"])
def api_step4_quality():
    return jsonify({"status": "error", "error": "Step4 quality 尚未在服务层实现"})

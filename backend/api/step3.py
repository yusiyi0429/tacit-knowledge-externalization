"""Step3 知识对齐 Blueprint."""

from __future__ import annotations

from flask import Blueprint, request, jsonify

import shared
from services.step3_service import (
    align_ir as _align_ir,
    align_output as _align_output,
    apply_suggestions as _apply_suggestions,
    confirm_as_is as _confirm_as_is,
    prev_output as _prev_output,
    revision_context as _revision_context,
    suggestions as _suggestions,
)

bp = Blueprint("step3", __name__)


@bp.route("/suggestions", methods=["GET"])
def api_step3_suggestions():
    """统一建议池."""
    return jsonify(_suggestions(shared.WORKSPACE, request.args.get("pipeline_id", "")))


@bp.route("/apply_suggestions", methods=["POST"])
def api_step3_apply_suggestions():
    """专家采纳建议池中的修订."""
    return jsonify(_apply_suggestions(shared.WORKSPACE, request.get_json(force=True) or {}))


@bp.route("/revision_context", methods=["GET"])
def api_step3_revision_context():
    """返回 Step3 修订上下文."""
    return jsonify(_revision_context(request.args.get("pipeline_id", "")))


@bp.route("/prev_output", methods=["GET"])
def api_step3_prev_output():
    """获取 Step2 知识萃取的输出件."""
    return jsonify(_prev_output(shared.WORKSPACE, request.args.get("pipeline_id", "")))


@bp.route("/align_output", methods=["GET"])
def api_step3_align_output():
    """获取知识对齐稿."""
    return jsonify(_align_output(shared.WORKSPACE, request.args.get("pipeline_id", "")))


@bp.route("/finalize", methods=["POST"])
def api_step3_finalize():
    """知识对齐：基于 Step3 修订稿（或 Step2 萃取稿）+专家意见，生成最终稿."""
    # TODO: migrate full finalize business logic from app_server.py
    return jsonify({"status": "error", "error": "Step3 finalize 尚未在服务层实现"})


@bp.route("/align_preview", methods=["POST"])
def api_step3_align_preview():
    """知识对齐 - 校正性：返回 AI 对齐建议列表."""
    return jsonify({"status": "error", "error": "Step3 align_preview 尚未在服务层实现"})


@bp.route("/align_chat", methods=["POST"])
def api_step3_align_chat():
    """知识对齐 - 校正性：对话式知识对齐."""
    return jsonify({"status": "error", "error": "Step3 align_chat 尚未在服务层实现"})


@bp.route("/apply_notes", methods=["POST"])
def api_step3_apply_notes():
    """交互式对齐 Phase 2."""
    return jsonify({"status": "error", "error": "Step3 apply_notes 尚未在服务层实现"})


@bp.route("/align_ir", methods=["POST"])
def api_step3_align_ir():
    """Step3 对齐 IR：专家修订规则/SQL."""
    return jsonify(_align_ir(shared.WORKSPACE, request.get_json(force=True) or {}))


@bp.route("/confirm_as_is", methods=["POST"])
def api_step3_confirm_as_is():
    """Markdown 无修订直通：直接复制 Step2 SKILL.md 作为对齐稿."""
    return jsonify(_confirm_as_is(shared.WORKSPACE, request.get_json(force=True) or {}))


@bp.route("/revision_with_expert", methods=["POST"])
def api_step3_revision_with_expert():
    """Step3: LLM 根据专家反馈修订 SKILL.md."""
    return jsonify({"status": "error", "error": "Step3 revision_with_expert 尚未在服务层实现"})


@bp.route("/interview/start", methods=["POST"])
def step3_interview_start():
    """知识深挖（Step3 访谈）."""
    return jsonify({"status": "error", "error": "Step3 interview/start 尚未在服务层实现"})


@bp.route("/interview/convert", methods=["POST"])
def step3_interview_convert():
    """知识深挖（Step3 访谈）：将已回答的访谈记录转换为知识条目."""
    return jsonify({"status": "error", "error": "Step3 interview/convert 尚未在服务层实现"})

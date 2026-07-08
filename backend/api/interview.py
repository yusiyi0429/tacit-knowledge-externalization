"""Interview API Blueprint."""

from __future__ import annotations

from flask import Blueprint, request, jsonify

from services.interview_service import probe

bp = Blueprint("interview", __name__)


@bp.route("/probe", methods=["POST"])
def api_interview_probe():
    """结构化访谈追问生成：输入一条知识 + 方法 → LLM 生成追问。"""
    data = request.get_json(force=True) if request.is_json else {}
    method = data.get("method", "case_reverse")
    knowledge_item = data.get("knowledge", {})
    model_name = data.get("model", "")
    return jsonify(probe(method, knowledge_item, model_name))

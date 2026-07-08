"""Step1 场景锚定 Blueprint."""

from __future__ import annotations

from flask import Blueprint, request, jsonify

import shared
from services.step1_service import generate_step1, step1_schema, step1_templates

bp = Blueprint("step1", __name__)


@bp.route("/schema", methods=["GET"])
def api_step1_schema():
    """返回当前知识结构方案（scenario-schema.yaml）摘要，供 Step1 界面展示。"""
    return jsonify(step1_schema())


@bp.route("/templates", methods=["GET"])
def api_step1_templates():
    """列出 Step1 模板来源：默认 schema + 可选 legacy Excel 模板。"""
    return jsonify(step1_templates())


@bp.route("/generate", methods=["POST"])
def api_step1_generate():
    """Step1: 将场景四项填入萃取模板前四列，保留模板表结构（无 LLM）。"""
    return jsonify(generate_step1(
        request.args.to_dict(),
        request.form.to_dict(),
        request.files.to_dict(),
        shared.WORKSPACE,
    ))

"""Step5 验证回放 Blueprint."""

from __future__ import annotations

from flask import Blueprint, request, jsonify

import shared
from services.step5_service import feedback as _feedback, finalize as _finalize, prev_output as _prev_output, replay as _replay

bp = Blueprint("step5", __name__)


@bp.route("/replay", methods=["POST"])
def api_step5_replay():
    """执行验证回放：用 SKILL 终版判断历史案例并输出 P/R/F1."""
    return jsonify(
        _replay(
            shared.WORKSPACE,
            request.form.get("pipeline_id", ""),
            test_source=request.form.get("test_source", ""),
            model_name=request.form.get("model", ""),
            limit=int(request.form.get("limit", 20)),
        )
    )


@bp.route("/prev_output", methods=["GET"])
def api_step5_prev_output():
    """获取 Step5 验证对象（Step4 交付物）信息."""
    return jsonify(_prev_output(shared.WORKSPACE, request.args.get("pipeline_id", "")))


@bp.route("/feedback", methods=["POST"])
def api_step5_feedback():
    """把验证分歧回流到 Step3 建议池."""
    payload = request.get_json(force=True) or {}
    if not payload:
        # 兼容 form 提交
        payload = {
            "pipeline_id": request.form.get("pipeline_id", ""),
            "suggestions": [],
        }
    return jsonify(_feedback(shared.WORKSPACE, payload))


@bp.route("/golden_verify", methods=["POST"])
def api_step5_golden_verify():
    """黄金数据集验证（当前委托到 /replay）。"""
    return jsonify(
        _replay(
            shared.WORKSPACE,
            request.form.get("pipeline_id", ""),
            test_source=request.form.get("test_source", ""),
            model_name=request.form.get("model", ""),
            limit=int(request.form.get("limit", 20)),
        )
    )


@bp.route("/finalize", methods=["POST"])
def api_step5_finalize():
    """生成最终版 Agent-Skill 交付 zip."""
    return jsonify(_finalize(shared.WORKSPACE, request.form.get("pipeline_id", "")))

"""Step5 验证回放 Blueprint."""

from __future__ import annotations

from flask import Blueprint, jsonify

bp = Blueprint("step5", __name__)


@bp.route("/replay", methods=["POST"])
def api_step5_replay():
    return jsonify({"status": "error", "error": "Step5 replay 尚未在服务层实现"})


@bp.route("/prev_output", methods=["GET"])
def api_step5_prev_output():
    return jsonify({"status": "error", "error": "Step5 prev_output 尚未在服务层实现"})


@bp.route("/feedback", methods=["POST"])
def api_step5_feedback():
    return jsonify({"status": "error", "error": "Step5 feedback 尚未在服务层实现"})


@bp.route("/golden_verify", methods=["POST"])
def api_step5_golden_verify():
    return jsonify({"status": "error", "error": "Step5 golden_verify 尚未在服务层实现"})


@bp.route("/finalize", methods=["POST"])
def api_step5_finalize():
    return jsonify({"status": "error", "error": "Step5 finalize 尚未在服务层实现"})

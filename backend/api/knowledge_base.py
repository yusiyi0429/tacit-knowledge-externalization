"""Knowledge base Blueprint."""

from __future__ import annotations

from flask import Blueprint, request, jsonify

import shared
from pipeline_artifacts import resolve_knowledge_ir_path, safe_workspace_path
from services.kb_service import (
    add_cases,
    delete_test_customers,
    deprecate,
    import_entries,
    insert_test_customers,
    list_cases,
    list_releases,
    list_test_customers,
    publish,
    search_entries,
    timeline,
)

bp = Blueprint("knowledge_base", __name__)


@bp.route("/entries", methods=["GET"])
def api_kb_entries():
    """检索知识库条目（Step1 继承预检 / 浏览）。"""
    try:
        return jsonify(search_entries(
            domain=request.args.get("domain", ""),
            scenario=request.args.get("scenario", ""),
            query=request.args.get("q", ""),
            top_k=int(request.args.get("top_k", "20") or 20),
            status=request.args.get("status", "active"),
        ))
    except Exception as e:
        return jsonify({"status": "error", "error": f"知识库检索失败: {str(e)}"})


@bp.route("/entries/import", methods=["POST"])
def api_kb_entries_import():
    """选中 KB 条目 → 标准 records（供前端注入流水线 / 调试）。"""
    data = request.get_json(force=True) or {}
    entry_uids = data.get("entry_uids") or []
    if not isinstance(entry_uids, list) or not entry_uids:
        return jsonify({"status": "error", "error": "请提供 entry_uids"})
    try:
        return jsonify(import_entries(entry_uids))
    except Exception as e:
        return jsonify({"status": "error", "error": f"导入失败: {str(e)}"})


@bp.route("/publish", methods=["POST"])
def api_kb_publish():
    """Step4 发布入库：当前流水线的最新 Skill IR → kb_entries + 发布登记。"""
    data = request.get_json(force=True) or {}
    pipeline_id = data.get("pipeline_id", "")
    by = data.get("by", "")
    if not pipeline_id:
        return jsonify({"status": "error", "error": "缺少 pipeline_id"})
    try:
        return jsonify(publish(
            pipeline_id,
            by,
            shared.WORKSPACE,
            resolve_knowledge_ir_path,
            safe_workspace_path,
        ))
    except Exception as e:
        return jsonify({"status": "error", "error": f"发布失败: {str(e)}"})


@bp.route("/entries/<entry_uid>/deprecate", methods=["POST"])
def api_kb_deprecate(entry_uid):
    data = request.get_json(force=True) or {}
    try:
        return jsonify(deprecate(entry_uid, note=data.get("note", ""), by=data.get("by", "")))
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)})


@bp.route("/entries/<entry_uid>/timeline", methods=["GET"])
def api_kb_timeline(entry_uid):
    try:
        return jsonify(timeline(entry_uid))
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)})


@bp.route("/cases", methods=["GET"])
def api_kb_list_cases():
    try:
        return jsonify(list_cases(
            domain=request.args.get("domain", ""),
            scenario=request.args.get("scenario", ""),
            difficulty=request.args.get("difficulty", ""),
            limit=int(request.args.get("limit", "20") or 20),
        ))
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)})


@bp.route("/cases", methods=["POST"])
def api_kb_add_cases():
    """录入案例（单条或批量）。"""
    data = request.get_json(force=True) or {}
    raw_cases = data.get("cases")
    if not isinstance(raw_cases, list):
        raw_cases = [data]
    try:
        return jsonify(add_cases(raw_cases))
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)})


@bp.route("/skills", methods=["GET"])
def api_kb_skills():
    try:
        return jsonify(list_releases(
            skill_slug=request.args.get("skill_slug", ""),
            limit=int(request.args.get("limit", "20") or 20),
        ))
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)})


@bp.route("/test_customers", methods=["GET"])
def api_list_test_customers():
    try:
        return jsonify(list_test_customers(
            source=request.args.get("source"),
            limit=int(request.args.get("limit", "100") or 100),
        ))
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)})


@bp.route("/test_customers", methods=["POST"])
def api_insert_test_customers():
    try:
        data = request.get_json(force=True) or {}
        customers = data.get("customers", [])
        if not isinstance(customers, list):
            return jsonify({"status": "error", "error": "customers 必须是数组"})
        return jsonify(insert_test_customers(customers))
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)})


@bp.route("/test_customers", methods=["DELETE"])
def api_delete_test_customers():
    try:
        source = request.args.get("source")
        if not source:
            return jsonify({"status": "error", "error": "缺少 source 参数"})
        return jsonify(delete_test_customers(source))
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)})

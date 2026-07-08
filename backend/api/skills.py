"""Skill registry Blueprint."""

from __future__ import annotations

from flask import Blueprint, request, jsonify

from services.skill_service import get_skill, list_skills, update_skill

bp = Blueprint("skills", __name__)


@bp.route("", methods=["GET"])
def api_skills_list():
    """返回所有已注册 Skill 的简要信息"""
    return jsonify(list_skills())


@bp.route("/<path:skill_id>", methods=["GET"])
def api_skill_detail(skill_id):
    """返回指定 Skill 的详细信息"""
    return jsonify(get_skill(skill_id))


@bp.route("/<path:skill_id>", methods=["PUT"])
def api_skill_update(skill_id):
    """更新 Skill 配置（如启用/禁用）"""
    data = request.get_json(force=True)
    return jsonify(update_skill(skill_id, data))


@bp.route("/execute", methods=["POST"])
def api_skill_execute():
    """通用 Skill 执行入口，根据 skill_id 路由到对应处理器"""
    from skill_registry import SKILL_REGISTRY

    skill_id = request.form.get("skill_id", "").strip()
    if not skill_id:
        return jsonify({"status": "error", "error": "缺少 skill_id 参数"})

    info = SKILL_REGISTRY.get(skill_id)
    if not info or not info.get("enabled"):
        return jsonify({"status": "error", "error": f"Skill '{skill_id}' 不存在或未启用"})

    # Route based on skill_id; business logic lives in step service modules.
    if skill_id == "knowledge-extraction":
        from services.step2_service import execute_knowledge_extraction
        return jsonify(execute_knowledge_extraction(request))
    elif skill_id == "knowledge-revision":
        from services.step3_service import execute_knowledge_revision
        return jsonify(execute_knowledge_revision(request))
    else:
        return jsonify({"status": "error", "error": f"Skill '{skill_id}' 暂无执行处理器"})

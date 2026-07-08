"""Skill registry business services."""

from __future__ import annotations

from skill_registry import SKILL_REGISTRY


def list_skills() -> dict:
    skills = []
    for sid, info in SKILL_REGISTRY.items():
        skills.append({
            "id": sid,
            "name": info["name"],
            "version": info["version"],
            "description": info["description"],
            "enabled": info["enabled"],
        })
    return {"status": "ok", "skills": skills}


def get_skill(skill_id: str) -> dict:
    info = SKILL_REGISTRY.get(skill_id)
    if not info:
        return {"status": "error", "error": "Skill 不存在"}
    return {"status": "ok", "skill": info}


def update_skill(skill_id: str, data: dict) -> dict:
    info = SKILL_REGISTRY.get(skill_id)
    if not info:
        return {"status": "error", "error": "Skill 不存在"}
    if "enabled" in data:
        info["enabled"] = bool(data["enabled"])
    return {"status": "ok", "skill": info}

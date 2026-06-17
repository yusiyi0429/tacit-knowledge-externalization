"""Skill registry — extracted from app_server.py."""

SKILL_REGISTRY = {
    "knowledge-extraction": {
        "id": "knowledge-extraction",
        "name": "知识萃取",
        "version": "2.0.0",
        "description": "基于场景骨架和知识文档，通过LLM生成 Agent SKILL.md 初稿。",
        "prompt_template": "step2_generate_skill_md.txt",
        "related_step": 2,
        "enabled": True,
    },
    "knowledge-revision": {
        "id": "knowledge-revision",
        "name": "知识对齐",
        "version": "2.0.0",
        "description": "基于专家自然语言反馈，通过LLM对 SKILL.md 进行修订对齐。",
        "prompt_template": "step3_align_with_expert.txt",
        "related_step": 3,
        "enabled": True,
    },
    "skill-generator": {
        "id": "skill-generator",
        "name": "Skill生成器",
        "version": "1.0.0",
        "description": "基于修订后的 SKILL.md，通过LLM生成 QA对、思维链和待验证 Agent-Skill。",
        "prompt_template": "step4_build_deliverables.txt",
        "related_step": 4,
        "enabled": True,
    },
}

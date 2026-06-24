"""Lightweight backend i18n."""
from __future__ import annotations

import os
from typing import Any

DEFAULT_LANG = os.environ.get("DEFAULT_LANG", "zh-CN")
SUPPORTED_LANGS = {"zh-CN", "en"}

_MESSAGES: dict[str, dict[str, str]] = {
    "zh-CN": {
        "pipeline_name_required": "流水线名称不能为空",
        "file_not_found": "文件不存在",
        "download_not_allowed": "不允许下载该文件",
        "read_not_allowed": "不允许读取该文件",
        "write_not_allowed": "不允许写入该文件",
        "missing_upload_file": "缺少上传文件",
        "pipeline_not_found": "流水线不存在",
        "invalid_step": "步骤号必须在 1-5 之间",
        "scenario_name_required": "场景名称不能为空",
        "need_at_least_one_knowledge_column": "请至少定义一列知识字段",
        "template_format_error": "模板仅支持 .xlsx / .xls 格式",
        "need_scenario_skeleton_first": "请先在「场景锚定」生成场景骨架",
        "skill_md_not_found": "未找到 SKILL.md（请先完成 Step2/Step3）",
        "skill_generation_failed": "Skill生成失败: {error}",
        "need_extraction_first": "未找到可转化的知识稿。请先完成「知识萃取」",
        "delivery_failed": "智能转化失败: {error}",
        "suggestion_pool_empty": "建议池为空",
        "need_adopt_or_reject": "请至少采纳或驳回一条建议",
        "markdown_use_editor": "当前为 Markdown 流程，请使用知识对齐节点的编辑器手动修订",
        "need_preextract_first": "未找到可对齐的知识稿。请先完成「知识萃取」生成 preextract_*.xlsx",
        "llm_parse_failed": "LLM输出解析失败: {error}",
        "need_step4_first": "请先完成 Step4 智能转化",
        "validation_not_passed": "验证未通过 (precision={precision})，请先完成验证回流",
        "customers_must_be_array": "customers 必须是数组",
    },
    "en": {
        "pipeline_name_required": "Pipeline name is required",
        "file_not_found": "File not found",
        "download_not_allowed": "Download not allowed for this file",
        "read_not_allowed": "Read not allowed for this file",
        "write_not_allowed": "Write not allowed for this file",
        "missing_upload_file": "Missing upload file",
        "pipeline_not_found": "Pipeline not found",
        "invalid_step": "Step number must be between 1 and 5",
        "scenario_name_required": "Scenario name is required",
        "need_at_least_one_knowledge_column": "Please define at least one knowledge column",
        "template_format_error": "Template must be .xlsx / .xls",
        "need_scenario_skeleton_first": "Please generate the scenario skeleton in Scenario Anchoring first",
        "skill_md_not_found": "SKILL.md not found (please complete Step 2 / Step 3 first)",
        "skill_generation_failed": "Skill generation failed: {error}",
        "need_extraction_first": "No knowledge draft found. Please complete Knowledge Extraction first",
        "delivery_failed": "Delivery generation failed: {error}",
        "suggestion_pool_empty": "Suggestion pool is empty",
        "need_adopt_or_reject": "Please adopt or reject at least one suggestion",
        "markdown_use_editor": "Current pipeline uses Markdown flow; please revise using the Knowledge Alignment editor",
        "need_preextract_first": "No alignable draft found. Please complete Knowledge Extraction to generate preextract_*.xlsx",
        "llm_parse_failed": "LLM output parsing failed: {error}",
        "need_step4_first": "Please complete Step 4 Delivery first",
        "validation_not_passed": "Validation not passed (precision={precision}); please complete validation feedback",
        "customers_must_be_array": "customers must be an array",
    },
}


def resolve_locale(
    *,
    query_lang: str | None = None,
    header_lang: str | None = None,
    pipeline_locale: str | None = None,
) -> str:
    for candidate in (query_lang, pipeline_locale, header_lang):
        if candidate:
            normalized = candidate.split(",")[0].strip().lower()
            if normalized in SUPPORTED_LANGS:
                return normalized
            if normalized.startswith("en"):
                return "en"
            if normalized.startswith("zh"):
                return "zh-CN"
    return DEFAULT_LANG


def t(key: str, lang: str = DEFAULT_LANG, **kwargs: Any) -> str:
    lang = lang if lang in SUPPORTED_LANGS else DEFAULT_LANG
    message = _MESSAGES.get(lang, _MESSAGES[DEFAULT_LANG]).get(key, key)
    if kwargs:
        try:
            return message.format(**kwargs)
        except KeyError:
            return message
    return message


def add_messages(lang: str, messages: dict[str, str]) -> None:
    if lang not in _MESSAGES:
        _MESSAGES[lang] = {}
    _MESSAGES[lang].update(messages)


def get_messages(lang: str) -> dict[str, str]:
    return dict(_MESSAGES.get(lang, {}))

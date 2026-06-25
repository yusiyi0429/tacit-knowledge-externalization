"""Lightweight backend i18n."""
from __future__ import annotations

import os
from typing import Any

DEFAULT_LANG = os.environ.get("DEFAULT_LANG", "zh-CN")
SUPPORTED_LANGS = {"zh-CN", "en"}
FORCED_LANG = os.environ.get("FORCED_LANG")

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
        # Report / artifact labels
        "report_quality_title": "# 知识萃取质量报告",
        "report_validation_title": "# 显性化校验报告 · 决策回放",
        "report_skill_execution": "## 执行说明",
        "report_skill_rules": "## 知识规则",
        "report_glossary": "## 附录：术语表",
        "report_confidence_high": "高",
        "report_confidence_medium": "中",
        "report_confidence_low": "低",
        "report_entry_id": "条目编号",
        "report_source_doc": "来源文档",
        "report_replay_result": "回放结果",
        "report_hit": "命中",
        "report_miss": "未命中",
        "report_precision": "Precision",
        "report_recall": "Recall",
        "report_f1": "F1",
        # Extended report / artifact labels
        "report_cot_title": "# {display_name} · 思维链知识库",
        "report_cot_intro": "> 由知识对齐稿确定性转化。每条知识拆为：情境识别 → 推理步骤 → 结论与校验。",
        "report_cot_situation": "### 1. 情境识别",
        "report_cot_reasoning": "### 2. 推理步骤",
        "report_cot_conclusion": "### 3. 结论与校验",
        "report_cot_expert_correction": "### 4. 专家经验校正",
        "report_cot_risk_check": "**风险校验**：",
        "report_generated_at": "生成时间",
        "report_item_count": "条目数",
        "report_trigger_condition": "触发条件",
        "report_sub_scenario_context": "子场景上下文",
        "report_check_condition": "核对是否满足适用条件",
        "report_apply_logic": "应用判断逻辑",
        "report_formulate_plan": "结合知识描述形成执行方案",
        "report_confirm_publishability": "对照来源与专家署名，确认可发布性",
        "report_experience_judgment": "经验判断",
        "report_applicable_boundary": "适用边界",
        "report_exception_case": "例外情形",
        "report_confidence_label": "置信度",
        "report_category_label": "分类",
        "report_sub_scenario_label": "子场景",
        "report_uncategorized": "未分类",
        "report_qa_title": "# {scenario_name} · QA 对",
        "report_qa_intro": "共 **{count}** 组问答，可用于检索增强、评测集或微调样本。",
        "report_qa_question": "**问**：",
        "report_qa_answer": "**答**：",
        "report_qa_category": "分类",
        "report_qa_sub_scenario": "子场景",
        "report_qa_type": "类型",
        "report_cot_artifact_label": "思维链",
        "report_qa_artifact_label": "QA 对",
        "report_skill_artifact_label": "Skill (OpenClaw / Hermes)",
        "report_validation_cases": "# 验证用例",
        "report_case_scenario": "场景",
        "report_case_description": "描述",
        "report_case_facts": "事实",
        "report_case_conclusion": "专家结论",
        "report_case_reasoning": "推理",
        "report_quality_dimensions": "## 各维度得分",
        "report_quality_tacitness": "## 隐性化成效",
        "report_quality_suggestions": "## 改进建议",
        "report_quality_dimension": "维度",
        "report_quality_score": "得分",
        "report_quality_max": "满分",
        "report_quality_rate": "得分率",
        "report_quality_total": "总计",
        "report_quality_total_score": "总分",
        "report_quality_grade": "等级",
        "report_quality_scenario": "场景",
        "report_quality_item_count": "知识条目数",
        "report_hit_rate": "命中率",
        "report_case_count": "案例数",
        "report_total_cases": "用例总数",
        "report_mismatch_count": "分歧数",
        "report_all_cases_match": "所有案例判断与专家结论一致。",
        "report_check_rules_suggestion": "请检查上述规则是否需要更新或补充例外情形。",
        "report_mismatch_analysis": "## 不一致案例分析",
        "report_llm_prediction": "LLM 预测",
        "report_expert_conclusion": "专家结论",
        "report_reasoning_process": "推理过程",
        "report_referenced_rules": "引用的规则",
        "report_suggestion": "建议",
        "report_case": "案例",
        "report_verification_title": "# Agent-Skill 本地知识库验证报告",
        "report_verification_mismatches": "## 不一致用例",
        "report_pass_rate": "通过率",
        "report_all_cases_pass": "所有用例均通过。",
        "report_fail_count": "失败",
        "report_partial_count": "部分通过",
        "report_actual_conclusion": "实际结论",
        "report_expected_conclusion": "期望结论",
        "report_scenario_skeleton_title": "# 场景锚定骨架 · {scenario_name}",
        "report_scenario_description": "## 场景说明",
        "report_knowledge_columns": "## 知识列",
        "report_sub_scenario": "## 子场景：{sub_name}",
        "report_skeleton_footer": "> 可在下方继续追加知识条目行，或进入 Step2 使用同结构 Excel 萃取。",
        "step1_scenario_todo": "（待补充）",
        "step1_no_knowledge_columns": "（无）",
        "step1_sub_scenario_default": "子场景{index}",
        "cot_default_trigger": "（未显式填写，按业务默认场景处理）",
        "report_quality_tacit_ratio_label": "隐性度（tacit_ratio）",
        "report_quality_tacit_ratio_desc": "（有专家经验判断/适用边界/例外情形的条目占比）",
        "report_quality_case_ratio_label": "案例衍生占比",
        "report_quality_case_ratio_desc": "（来自案例复盘或已被案例支撑的条目占比）",
        "report_quality_avg_evidence_label": "平均证据数",
        "report_quality_avg_evidence_desc": "（每条知识被多少案例支撑）",
        "report_quality_breaks_label": "被突破条目",
        "report_quality_breaks_desc": "（专家实践中曾被突破的规则数）",
        "report_skill_frontmatter": "### 1. 元数据 (frontmatter)",
        "report_skill_trigger": "### 2. 触发规则 (TRIGGER)",
        "report_skill_matching": "### 3. 知识匹配引擎 (MATCHING)",
        "report_skill_decision_flow": "### 4. 决策链 (DECISION_FLOW)",
        "report_skill_output": "### 5. 评估输出模板 (OUTPUT)",
        "report_skill_example": "### 6. 使用示例 (EXAMPLE)",
        "report_skill_requirements": "## 要求",
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
        # Report / artifact labels
        "report_quality_title": "# Knowledge Extraction Quality Report",
        "report_validation_title": "# Explicit Validation Report · Decision Replay",
        "report_skill_execution": "## Execution Instructions",
        "report_skill_rules": "## Knowledge Rules",
        "report_glossary": "## Appendix: Glossary",
        "report_confidence_high": "High",
        "report_confidence_medium": "Medium",
        "report_confidence_low": "Low",
        "report_entry_id": "Entry ID",
        "report_source_doc": "Source Document",
        "report_replay_result": "Replay Result",
        "report_hit": "Hit",
        "report_miss": "Miss",
        "report_precision": "Precision",
        "report_recall": "Recall",
        "report_f1": "F1",
        # Extended report / artifact labels
        "report_cot_title": "# {display_name} · Chain-of-Thought Knowledge Base",
        "report_cot_intro": "> Deterministically converted from the aligned knowledge draft. Each item is split into: situation recognition → reasoning steps → conclusion and validation.",
        "report_cot_situation": "### 1. Situation Recognition",
        "report_cot_reasoning": "### 2. Reasoning Steps",
        "report_cot_conclusion": "### 3. Conclusion and Validation",
        "report_cot_expert_correction": "### 4. Expert Experience Calibration",
        "report_cot_risk_check": "**Risk Check**: ",
        "report_generated_at": "Generated at",
        "report_item_count": "Items",
        "report_trigger_condition": "Trigger condition",
        "report_sub_scenario_context": "Sub-scenario context",
        "report_check_condition": "Check whether the applicable condition is satisfied",
        "report_apply_logic": "Apply decision logic",
        "report_formulate_plan": "Formulate an execution plan based on the knowledge description",
        "report_confirm_publishability": "Verify publishability against sources and expert attribution",
        "report_experience_judgment": "Expert judgment",
        "report_applicable_boundary": "Applicable boundary",
        "report_exception_case": "Exception case",
        "report_confidence_label": "Confidence",
        "report_category_label": "Category",
        "report_sub_scenario_label": "Sub-scenario",
        "report_uncategorized": "Uncategorized",
        "report_qa_title": "# {scenario_name} · QA Pairs",
        "report_qa_intro": "A total of **{count}** Q&A pairs for retrieval augmentation, evaluation sets, or fine-tuning samples.",
        "report_qa_question": "**Q**: ",
        "report_qa_answer": "**A**: ",
        "report_qa_category": "Category",
        "report_qa_sub_scenario": "Sub-scenario",
        "report_qa_type": "Type",
        "report_cot_artifact_label": "Chain-of-Thought",
        "report_qa_artifact_label": "QA Pairs",
        "report_skill_artifact_label": "Skill (OpenClaw / Hermes)",
        "report_validation_cases": "# Validation Cases",
        "report_case_scenario": "Scenario",
        "report_case_description": "Description",
        "report_case_facts": "Facts",
        "report_case_conclusion": "Expert Conclusion",
        "report_case_reasoning": "Reasoning",
        "report_quality_dimensions": "## Dimension Scores",
        "report_quality_tacitness": "## Tacitness Effectiveness",
        "report_quality_suggestions": "## Improvement Suggestions",
        "report_quality_dimension": "Dimension",
        "report_quality_score": "Score",
        "report_quality_max": "Max",
        "report_quality_rate": "Rate",
        "report_quality_total": "Total",
        "report_quality_total_score": "Total Score",
        "report_quality_grade": "Grade",
        "report_quality_scenario": "Scenario",
        "report_quality_item_count": "Knowledge Items",
        "report_hit_rate": "Hit Rate",
        "report_case_count": "Cases",
        "report_total_cases": "Total Cases",
        "report_mismatch_count": "Mismatches",
        "report_all_cases_match": "All case predictions match the expert conclusions.",
        "report_check_rules_suggestion": "Please check whether the above rules need to be updated or whether exception cases need to be supplemented.",
        "report_mismatch_analysis": "## Mismatch Case Analysis",
        "report_llm_prediction": "LLM Prediction",
        "report_expert_conclusion": "Expert Conclusion",
        "report_reasoning_process": "Reasoning Process",
        "report_referenced_rules": "Referenced Rules",
        "report_suggestion": "Suggestion",
        "report_case": "Case",
        "report_verification_title": "# Agent-Skill Local Knowledge Base Verification Report",
        "report_verification_mismatches": "## Mismatch Cases",
        "report_pass_rate": "Pass Rate",
        "report_all_cases_pass": "All cases passed.",
        "report_fail_count": "Failed",
        "report_partial_count": "Partial",
        "report_actual_conclusion": "Actual Conclusion",
        "report_expected_conclusion": "Expected Conclusion",
        "report_scenario_skeleton_title": "# Scenario Anchoring Skeleton · {scenario_name}",
        "report_scenario_description": "## Scenario Description",
        "report_knowledge_columns": "## Knowledge Columns",
        "report_sub_scenario": "## Sub-scenario: {sub_name}",
        "report_skeleton_footer": "> You can append additional knowledge item rows below, or proceed to Step 2 to extract using the same Excel structure.",
        "step1_scenario_todo": "To be completed",
        "step1_no_knowledge_columns": "None",
        "step1_sub_scenario_default": "Sub-scenario {index}",
        "cot_default_trigger": "(Not explicitly specified; handled by business default scenario)",
        "report_quality_tacit_ratio_label": "Tacitness (tacit_ratio)",
        "report_quality_tacit_ratio_desc": "(percentage of items with expert judgment/applicable boundary/exception cases)",
        "report_quality_case_ratio_label": "Case-derived ratio",
        "report_quality_case_ratio_desc": "(percentage of items from case reviews or supported by cases)",
        "report_quality_avg_evidence_label": "Average evidence count",
        "report_quality_avg_evidence_desc": "(how many cases support each knowledge item)",
        "report_quality_breaks_label": "Items with breaks",
        "report_quality_breaks_desc": "(number of rules ever broken in expert practice)",
        "report_skill_frontmatter": "### 1. Metadata (frontmatter)",
        "report_skill_trigger": "### 2. Trigger Rules (TRIGGER)",
        "report_skill_matching": "### 3. Knowledge Matching Engine (MATCHING)",
        "report_skill_decision_flow": "### 4. Decision Flow (DECISION_FLOW)",
        "report_skill_output": "### 5. Output Template (OUTPUT)",
        "report_skill_example": "### 6. Usage Example (EXAMPLE)",
        "report_skill_requirements": "## Requirements",
    },
}


def resolve_locale(
    *,
    query_lang: str | None = None,
    header_lang: str | None = None,
    pipeline_locale: str | None = None,
) -> str:
    """Resolve the best-supported language from the provided candidates.

    If the ``FORCED_LANG`` environment variable is set to a supported language,
    it always takes precedence.

    Priority order: FORCED_LANG > query_lang > pipeline_locale > header_lang > DEFAULT_LANG.
    Candidates are normalized to lowercase before matching. Any prefix starting
    with "en" maps to "en", and any prefix starting with "zh" maps to "zh-CN".
    """
    forced = os.environ.get("FORCED_LANG")
    if forced in SUPPORTED_LANGS:
        return forced
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
    """Return the translation for ``key`` in ``lang``.

    Falls back to ``DEFAULT_LANG`` if ``lang`` is unsupported, and falls back to
    ``key`` itself if the key is missing. Keyword arguments are passed to
    ``str.format``; if a placeholder is missing, the unformatted template is
    returned.
    """
    lang = lang if lang in SUPPORTED_LANGS else DEFAULT_LANG
    message = _MESSAGES.get(lang, _MESSAGES[DEFAULT_LANG]).get(key, key)
    if kwargs:
        try:
            return message.format(**kwargs)
        except KeyError:
            return message
    return message


def add_messages(lang: str, messages: dict[str, str]) -> None:
    """Add or update translations for a supported language.

    Raises:
        ValueError: If ``lang`` is not in ``SUPPORTED_LANGS``.
    """
    if lang not in SUPPORTED_LANGS:
        raise ValueError(f"Unsupported language: {lang!r}")
    if lang not in _MESSAGES:
        _MESSAGES[lang] = {}
    _MESSAGES[lang].update(messages)


def get_messages(lang: str) -> dict[str, str]:
    """Return a shallow copy of the messages for ``lang``.

    Returns an empty dict if ``lang`` has no registered messages.
    """
    return dict(_MESSAGES.get(lang, {}))

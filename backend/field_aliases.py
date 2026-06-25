"""
Bilingual field alias table shared by quality_report.py and excel_to_skill.py.

Canonical keys are English; each accepts both Chinese and English aliases.
L1 explicit conclusion layer / L2 judgment context layer / L3 evidence layer
"""

FIELD_ALIASES = {
    # Anchor columns (Step1 scenario anchoring)
    "scenario": ["场景", "scenario"],
    "scenario_desc": ["场景说明", "场景内容", "scenario_desc", "scenario description"],
    "sub_scenario": ["子场景", "sub_scenario"],
    "sub_scenario_desc": ["子场景说明", "子场景内容", "sub_scenario_desc", "sub scenario description"],
    # L1 explicit conclusion layer
    "knowledge_id": ["知识编号", "编号", "KN编号", "知识ID", "knowledge_id", "id"],
    "category": ["知识分类", "分类", "类型", "知识要点", "知识", "category", "type"],
    "stage": ["环节", "stage", "Stage"],
    "interview_direction": ["访谈方向", "interview_direction", "Interview Direction"],
    "knowledge_desc": [
        "知识描述", "描述", "知识内容", "内容", "数据规则", "具体方案",
        "具体方法", "场景说明", "子场景说明", "知识说明",
        "knowledge_desc", "knowledge description", "description", "method", "Method",
    ],
    "knowledge_type": ["知识类型", "knowledge_type", "Knowledge Type"],
    "reference": ["知识引用", "reference", "Reference"],
    "applicable_condition": ["适用条件", "触发条件", "条件", "applicable_condition", "condition", "trigger", "Condition"],
    "judgment_logic": ["判断逻辑", "判断规则", "逻辑", "规则引用", "judgment_logic", "logic", "Logic"],
    "anti_pattern": ["反模式/踩坑提示", "反模式", "踩坑提示", "注意事项", "anti_pattern", "pitfall", "caveat", "Anti-pattern"],
    # L2 judgment context layer (targets for implicit annotation writes)
    "expert_judgment": ["经验判断", "专家经验判断", "expert_judgment", "expert_opinion", "experience_judgment", "Experience Judgment"],
    "applicable_boundary": ["适用边界", "适用边界/例外", "applicable_boundary", "boundary", "Boundary"],
    "exception_case": ["例外情形", "例外场景", "破例场景", "exception_case", "exception", "Exception"],
    # L3 evidence layer
    "source_doc": ["来源文档", "来源", "source_doc", "source", "source_document", "Source Doc"],
    "source_location": ["来源位置", "位置", "页码", "source_location", "location", "page", "Source Location"],
    "source_quote": ["原文摘录", "摘录", "source_quote", "quote", "excerpt"],
    "confidence": ["置信度", "可信度", "confidence", "credibility", "Confidence"],
    "contributor": ["贡献专家", "贡献人", "contributor", "contributing_expert", "Contributor"],
    "confirmer": ["确认专家", "确认人", "confirmer", "confirming_expert"],
    "evidence_count": ["证据数", "案例支撑数", "evidence_count", "evidences", "Evidence Count"],
    "break_count": ["突破数", "被突破数", "break_count", "breaks", "Break Count"],
    "breakthrough_count": ["突破数", "被突破数", "breakthrough_count", "breakthroughs", "Breakthrough Count"],
    "remark": ["备注", "说明", "修订说明", "remark", "note", "comment"],
}

# Chinese / English display labels for canonical keys (optional UI helper).
DISPLAY_NAMES = {
    "scenario": {"zh": "场景", "en": "Scenario"},
    "scenario_desc": {"zh": "场景说明", "en": "Scenario Description"},
    "sub_scenario": {"zh": "子场景", "en": "Sub-scenario"},
    "sub_scenario_desc": {"zh": "子场景说明", "en": "Sub-scenario Description"},
    "knowledge_id": {"zh": "知识编号", "en": "Knowledge ID"},
    "category": {"zh": "知识分类", "en": "Category"},
    "stage": {"zh": "环节", "en": "Stage"},
    "interview_direction": {"zh": "访谈方向", "en": "Interview Direction"},
    "knowledge_desc": {"zh": "知识描述", "en": "Knowledge Description"},
    "knowledge_type": {"zh": "知识类型", "en": "Knowledge Type"},
    "reference": {"zh": "知识引用", "en": "Reference"},
    "applicable_condition": {"zh": "适用条件", "en": "Applicable Condition"},
    "judgment_logic": {"zh": "判断逻辑", "en": "Judgment Logic"},
    "anti_pattern": {"zh": "反模式/踩坑提示", "en": "Anti-pattern / Pitfall"},
    "expert_judgment": {"zh": "经验判断", "en": "Expert Judgment"},
    "applicable_boundary": {"zh": "适用边界", "en": "Applicable Boundary"},
    "exception_case": {"zh": "例外情形", "en": "Exception Case"},
    "source_doc": {"zh": "来源文档", "en": "Source Document"},
    "source_location": {"zh": "来源位置", "en": "Source Location"},
    "source_quote": {"zh": "原文摘录", "en": "Source Quote"},
    "confidence": {"zh": "置信度", "en": "Confidence"},
    "contributor": {"zh": "贡献专家", "en": "Contributor"},
    "confirmer": {"zh": "确认专家", "en": "Confirmer"},
    "evidence_count": {"zh": "证据数", "en": "Evidence Count"},
    "break_count": {"zh": "突破数", "en": "Break Count"},
    "breakthrough_count": {"zh": "突破数", "en": "Breakthrough Count"},
    "remark": {"zh": "备注", "en": "Remark"},
}

REVISION_COLUMN_MARKERS = ("修订状态", "原始内容", "修订内容", "修订说明", "修订时间")


def resolve_header(raw_header: str) -> str:
    """Resolve an Excel header text to a canonical English field name."""
    if not raw_header:
        return ""
    raw = str(raw_header).strip()
    raw_lower = raw.lower()
    for canonical, aliases in FIELD_ALIASES.items():
        if raw in aliases:
            return canonical
        if raw_lower in [a.lower() for a in aliases]:
            return canonical
    return raw


def match_alias(header: str, canonical_key: str) -> bool:
    """Check whether header matches any alias of a canonical field."""
    if not header:
        return False
    h = str(header).strip()
    return h in FIELD_ALIASES.get(canonical_key, [])


def iter_knowledge_columns(header_map: dict) -> dict:
    """从 {表头: col} 中筛选出知识字段列。"""
    result = {}
    for h, col in header_map.items():
        canonical = resolve_header(h)
        if canonical and canonical not in result:
            result[canonical] = (h, col)
    return result

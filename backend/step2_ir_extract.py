#!/usr/bin/env python3
"""Step2 IR 萃取：规则萃取 + SQL 生成。"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from llm_client import call_llm_with_retry
from shared import get_model_by_name, _extract_json_from_text


_logger = logging.getLogger(__name__)


STEP_PHASES = ["客户筛选", "客户数据匹配", "原因归因", "决策建议"]


def _render_prompt(template_path: str, ctx: dict) -> str:
    text = Path(template_path).read_text(encoding="utf-8")
    for key, val in ctx.items():
        placeholder = "{{" + key + "}}"
        text = text.replace(placeholder, str(val))
    return text


def extract_rules_from_doc(
    scenario_meta: dict,
    source_text: str,
    model_name: str,
    prompt_template: str = "prompts/step2a_rules_extract.txt",
) -> list[dict]:
    """Step2a: 从知识文档萃取业务规则（无 SQL）。"""
    if not source_text or not str(source_text).strip():
        raise ValueError("source_text 不能为空")

    model_cfg = get_model_by_name(model_name)
    if not model_cfg:
        raise ValueError(f"Model {model_name} not configured")

    sub_list = scenario_meta.get("sub_scenarios") or []
    sub_text = "\n".join(f"- {s.get('name')}: {s.get('desc', '')}" for s in sub_list) or "- 默认子场景"

    prompt = _render_prompt(
        prompt_template,
        {
            "scenario_name": scenario_meta.get("scenario_name", ""),
            "scenario_desc": scenario_meta.get("scenario_content", ""),
            "sub_scenarios": sub_text,
            "source_text": source_text[:12000],
        },
    )

    result = call_llm_with_retry(
        model_cfg,
        [{"role": "user", "content": prompt}],
        stream=False,
        temperature=0.2,
        max_tokens=4096,
    )
    content = result.get("choices", [{}])[0].get("message", {}).get("content", "") if isinstance(result, dict) else str(result)
    return _parse_json_array(content)


def generate_sql_for_entry(
    entry: dict,
    table_schema: str,
    model_name: str,
    prompt_template: str = "prompts/step2b_sql_generate.txt",
) -> dict:
    """Step2b: 为单条 entry 生成 data_logic.sql。"""
    model_cfg = get_model_by_name(model_name)
    if not model_cfg:
        raise ValueError(f"Model {model_name} not configured")

    fields = entry.get("fields") or {}
    prompt = _render_prompt(
        prompt_template,
        {
            "table_schema": table_schema,
            "sub_scenario": entry.get("sub_scenario", ""),
            "step_phase": entry.get("step_phase", ""),
            "knowledge_desc": fields.get("knowledge_desc", ""),
            "knowledge_ref": fields.get("knowledge_ref", ""),
            "rule_ref": fields.get("rule_ref", ""),
            "output": fields.get("output", ""),
        },
    )

    result = call_llm_with_retry(
        model_cfg,
        [{"role": "user", "content": prompt}],
        stream=False,
        temperature=0.1,
        max_tokens=2048,
    )
    content = result.get("choices", [{}])[0].get("message", {}).get("content", "") if isinstance(result, dict) else str(result)
    parsed = _parse_json_object(content)
    return {
        "sql": parsed.get("sql", ""),
        "tables": parsed.get("tables", []),
        "fields": parsed.get("fields", []),
        "confidence": parsed.get("confidence", "medium"),
    }


def fill_sql_for_entries(
    entries: list[dict],
    table_schema: str,
    model_name: str,
) -> list[dict]:
    """为 entries 列表逐条生成 SQL。"""
    for entry in entries:
        data_logic = generate_sql_for_entry(entry, table_schema, model_name)
        entry.setdefault("fields", {})["data_logic"] = data_logic
    return entries


def _parse_json_array(text: str) -> list:
    text = _extract_json(text)
    try:
        data = json.loads(text)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError as exc:
        _logger.warning("_parse_json_array 解析失败: %s", exc)
        return []


def _parse_json_object(text: str) -> dict:
    raw = _extract_json(text)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError as e:
        _logger.warning("Failed to parse SQL generation JSON: %s (raw: %r)", e, raw[:200])
        return {}


def _extract_json(text: str) -> str:
    return _extract_json_from_text(text or "")

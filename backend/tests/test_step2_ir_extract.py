import pytest
from unittest.mock import patch
from step2_ir_extract import (
    extract_rules_from_doc,
    generate_sql_for_entry,
    fill_sql_for_entries,
    _extract_json,
    _parse_json_array,
    _parse_json_object,
)


def test_parse_json_array():
    text = '```json\n[{"step_phase": "客户筛选"}]\n```'
    assert _parse_json_array(text) == [{"step_phase": "客户筛选"}]


def test_parse_json_object():
    text = '```json\n{"sql": "SELECT 1"}\n```'
    assert _parse_json_object(text) == {"sql": "SELECT 1"}


def test_extract_json_preamble_and_markdown_blocks():
    assert _extract_json('preamble\n```json\n[{"a": 1}]\n```\nextra') == '[{"a": 1}]'
    assert _extract_json('```json\n{"b": 2}\n```') == '{"b": 2}'
    assert _extract_json('```\n[1, 2, 3]\n```') == '[1, 2, 3]'
    assert _extract_json('here is json: {"c": 3} end') == '{"c": 3}'


def test_parse_json_array_malformed_returns_empty():
    assert _parse_json_array("not json") == []
    assert _parse_json_array('```json\n[{bad}]\n```') == []


def test_parse_json_object_malformed_returns_defaults():
    assert _parse_json_object("not json") == {}
    assert _parse_json_object('```json\n{invalid}\n```') == {}


@patch("step2_ir_extract.get_model_by_name")
@patch("step2_ir_extract.call_llm_with_retry")
def test_fill_sql_for_entries(mock_call, mock_get_model):
    mock_get_model.return_value = {"name": "test"}
    mock_call.return_value = {
        "choices": [{"message": {"content": '{"sql": "SELECT 1"}'}}]
    }
    entries = [
        {"fields": {"knowledge_desc": "x", "knowledge_ref": "", "rule_ref": "", "output": ""}},
        {"fields": {"knowledge_desc": "y", "knowledge_ref": "", "rule_ref": "", "output": ""}},
    ]
    result = fill_sql_for_entries(entries, "schema", "test")
    assert len(result) == 2
    assert result[0]["fields"]["data_logic"]["sql"] == "SELECT 1"
    assert result[1]["fields"]["data_logic"]["sql"] == "SELECT 1"


@patch("step2_ir_extract.get_model_by_name")
@patch("step2_ir_extract.call_llm_with_retry")
def test_extract_rules_from_doc(mock_call, mock_get_model, tmp_path):
    mock_get_model.return_value = {"name": "test"}
    mock_call.return_value = {
        "choices": [{"message": {"content": '[{"step_phase": "客户筛选", "fields": {"knowledge_desc": "x", "knowledge_ref": "", "rule_ref": "", "output": ""}}]'}}]
    }
    # Create fake prompt file
    prompt_file = tmp_path / "step2a_rules_extract.txt"
    prompt_file.write_text("{{scenario_name}}\n{{scenario_desc}}\n{{sub_scenarios}}\n{{source_text}}")
    result = extract_rules_from_doc(
        {"scenario_name": "S", "sub_scenarios": []},
        "source",
        "test",
        prompt_template=str(prompt_file),
    )
    assert len(result) == 1
    assert result[0]["step_phase"] == "客户筛选"


@patch("step2_ir_extract.get_model_by_name")
def test_extract_rules_from_doc_empty_source_raises(mock_get_model, tmp_path):
    mock_get_model.return_value = {"name": "test"}
    prompt_file = tmp_path / "step2a_rules_extract.txt"
    prompt_file.write_text("{{scenario_name}}\n{{scenario_desc}}\n{{sub_scenarios}}\n{{source_text}}")
    with pytest.raises(ValueError):
        extract_rules_from_doc(
            {"scenario_name": "S", "sub_scenarios": []},
            "",
            "test",
            prompt_template=str(prompt_file),
        )


@patch("step2_ir_extract.get_model_by_name")
@patch("step2_ir_extract.call_llm_with_retry")
def test_generate_sql_for_entry(mock_call, mock_get_model, tmp_path):
    mock_get_model.return_value = {"name": "test"}
    mock_call.return_value = {
        "choices": [{"message": {"content": '```json\n{"sql": "SELECT id FROM customers", "tables": ["customers"], "fields": ["id"], "confidence": "high"}\n```'}}]
    }
    prompt_file = tmp_path / "step2b_sql_generate.txt"
    prompt_file.write_text("{{table_schema}}\n{{sub_scenario}}\n{{step_phase}}\n{{knowledge_desc}}\n{{knowledge_ref}}\n{{rule_ref}}\n{{output}}")
    result = generate_sql_for_entry(
        {"sub_scenario": "S", "step_phase": "客户筛选", "fields": {"knowledge_desc": "x", "knowledge_ref": "", "rule_ref": "", "output": ""}},
        "CREATE TABLE customers(id TEXT);",
        "test",
        prompt_template=str(prompt_file),
    )
    assert "SELECT id FROM customers" in result["sql"]


@patch("step2_ir_extract.get_model_by_name")
@patch("step2_ir_extract.call_llm_with_retry")
def test_generate_sql_for_entry_parse_failure(mock_call, mock_get_model, tmp_path):
    mock_get_model.return_value = {"name": "test"}
    mock_call.return_value = {
        "choices": [{"message": {"content": '```json\n{invalid json}\n```'}}]
    }
    prompt_file = tmp_path / "step2b_sql_generate.txt"
    prompt_file.write_text("{{table_schema}}\n{{sub_scenario}}\n{{step_phase}}\n{{knowledge_desc}}\n{{knowledge_ref}}\n{{rule_ref}}\n{{output}}")
    result = generate_sql_for_entry(
        {"sub_scenario": "S", "step_phase": "客户筛选", "fields": {"knowledge_desc": "x", "knowledge_ref": "", "rule_ref": "", "output": ""}},
        "schema",
        "test",
        prompt_template=str(prompt_file),
    )
    assert result == {"sql": "", "tables": [], "fields": [], "confidence": "medium"}

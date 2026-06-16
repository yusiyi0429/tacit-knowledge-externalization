from skill_ir import new_draft_v2, validate_ir_v2, push_sql_history, VALID_STEP_PHASES


def test_new_draft_v2_basic():
    ir = new_draft_v2(
        {
            "scenario_name": "科技型企业普惠贷款营销",
            "domain": "对公普惠",
            "sub_scenarios": [{"name": "科技型企业普惠贷款营销", "desc": "..."}],
        },
        [
            {
                "entry_id": "KN-001",
                "sub_scenario": "科技型企业普惠贷款营销",
                "step_phase": "客户筛选",
                "fields": {
                    "knowledge_desc": "筛选科技标签客户",
                    "knowledge_ref": "CRM标签",
                    "rule_ref": "标签 IN ('高企')",
                    "output": "科技标签客户清单",
                },
            }
        ],
        pipeline_id="p1",
    )
    assert ir["ir_version"] == "2.0"
    assert ir["skill_meta"]["scenario_name"] == "科技型企业普惠贷款营销"
    assert len(ir["entries"]) == 1
    assert ir["entries"][0]["step_phase"] == "客户筛选"
    assert ir["entries"][0]["fields"]["data_logic"]["sql"] == ""
    assert "confidence" not in ir["entries"][0]["fields"]["data_logic"]


def test_new_draft_v2_skips_non_dict_entries():
    ir = new_draft_v2(
        {"scenario_name": "S", "sub_scenarios": []},
        [
            "not-a-dict",
            {"entry_id": "KN-001", "step_phase": "客户筛选", "fields": {"knowledge_desc": "x", "knowledge_ref": "", "rule_ref": "", "output": ""}},
            None,
        ],
    )
    assert len(ir["entries"]) == 1
    assert ir["entries"][0]["entry_id"] == "KN-001"


def test_new_draft_v2_deduplicates_entry_ids():
    ir = new_draft_v2(
        {"scenario_name": "S", "sub_scenarios": []},
        [
            {"entry_id": "KN-001", "step_phase": "客户筛选", "fields": {"knowledge_desc": "a", "knowledge_ref": "", "rule_ref": "", "output": ""}},
            {"entry_id": "KN-001", "step_phase": "客户数据匹配", "fields": {"knowledge_desc": "b", "knowledge_ref": "", "rule_ref": "", "output": ""}},
            {"entry_id": "KN-003", "step_phase": "原因归因", "fields": {"knowledge_desc": "c", "knowledge_ref": "", "rule_ref": "", "output": ""}},
        ],
    )
    ids = [e["entry_id"] for e in ir["entries"]]
    assert len(ids) == len(set(ids))
    assert "KN-001" in ids
    assert "KN-003" in ids
    # _next_entry_id uses max+1 over all existing ids, so duplicate of KN-001
    # becomes KN-004 because KN-003 already exists.
    assert "KN-004" in ids


def test_new_draft_v2_ensures_data_logic_sql():
    ir = new_draft_v2(
        {"scenario_name": "S", "sub_scenarios": []},
        [
            {
                "entry_id": "KN-001",
                "step_phase": "客户筛选",
                "fields": {
                    "knowledge_desc": "x",
                    "knowledge_ref": "",
                    "rule_ref": "",
                    "output": "",
                    "data_logic": {"sql": "SELECT 1"},
                },
            },
            {
                "entry_id": "KN-002",
                "step_phase": "客户筛选",
                "fields": {
                    "knowledge_desc": "x",
                    "knowledge_ref": "",
                    "rule_ref": "",
                    "output": "",
                    "data_logic": {"other": "value"},
                },
            },
            {
                "entry_id": "KN-003",
                "step_phase": "客户筛选",
                "fields": {
                    "knowledge_desc": "x",
                    "knowledge_ref": "",
                    "rule_ref": "",
                    "output": "",
                    "data_logic": "invalid",
                },
            },
        ],
    )
    assert ir["entries"][0]["fields"]["data_logic"]["sql"] == "SELECT 1"
    assert ir["entries"][1]["fields"]["data_logic"]["sql"] == ""
    assert "other" not in ir["entries"][1]["fields"]["data_logic"]
    assert ir["entries"][2]["fields"]["data_logic"] == {"sql": ""}


def test_new_draft_v2_preserves_data_logic_schema_fields():
    ir = new_draft_v2(
        {"scenario_name": "S", "sub_scenarios": []},
        [
            {
                "entry_id": "KN-001",
                "step_phase": "客户筛选",
                "fields": {
                    "knowledge_desc": "x",
                    "knowledge_ref": "",
                    "rule_ref": "",
                    "output": "",
                    "data_logic": {
                        "sql": "SELECT * FROM t",
                        "tables": ["t", "u"],
                        "fields": ["a", "b"],
                        "confidence": "high",
                    },
                },
            }
        ],
    )
    data_logic = ir["entries"][0]["fields"]["data_logic"]
    assert data_logic["sql"] == "SELECT * FROM t"
    assert data_logic["tables"] == ["t", "u"]
    assert data_logic["fields"] == ["a", "b"]
    assert data_logic["confidence"] == "high"


def test_validate_ir_v2_well_formed():
    ir = new_draft_v2(
        {"scenario_name": "S", "sub_scenarios": []},
        [
            {
                "entry_id": "KN-001",
                "step_phase": "客户筛选",
                "fields": {
                    "knowledge_desc": "x",
                    "knowledge_ref": "",
                    "rule_ref": "",
                    "output": "",
                },
            }
        ],
    )
    errors = validate_ir_v2(ir)
    assert errors == []


def test_validate_ir_v2_invalid_phase():
    ir = new_draft_v2(
        {"scenario_name": "S", "sub_scenarios": []},
        [{"step_phase": "未知步骤", "fields": {"knowledge_desc": "x", "knowledge_ref": "", "rule_ref": "", "output": ""}}],
    )
    errors = validate_ir_v2(ir)
    assert errors
    assert any("step_phase" in e for e in errors)


def test_validate_ir_v2_missing_required_fields():
    ir = new_draft_v2(
        {"scenario_name": "S", "sub_scenarios": []},
        [{"entry_id": "KN-001", "step_phase": "客户筛选", "fields": {}}],
    )
    # new_draft_v2 normalizes missing fields into empty strings, so build an invalid IR manually
    ir["entries"][0]["fields"] = {"data_logic": {"sql": ""}}
    errors = validate_ir_v2(ir)
    for req in ("knowledge_desc", "knowledge_ref", "rule_ref", "output"):
        assert any(f"missing required field {req}" in e for e in errors)


def test_validate_ir_v2_invalid_entry_id():
    ir = new_draft_v2(
        {"scenario_name": "S", "sub_scenarios": []},
        [{"entry_id": "KN-001", "step_phase": "客户筛选", "fields": {"knowledge_desc": "x", "knowledge_ref": "", "rule_ref": "", "output": ""}}],
    )
    ir["entries"][0]["entry_id"] = "BAD-ID"
    errors = validate_ir_v2(ir)
    assert any("entry_id 格式非法" in e for e in errors)


def test_validate_ir_v2_missing_data_logic_sql():
    ir = new_draft_v2(
        {"scenario_name": "S", "sub_scenarios": []},
        [{"entry_id": "KN-001", "step_phase": "客户筛选", "fields": {"knowledge_desc": "x", "knowledge_ref": "", "rule_ref": "", "output": ""}}],
    )
    ir["entries"][0]["fields"]["data_logic"] = {}
    errors = validate_ir_v2(ir)
    assert any("data_logic.sql is required" in e for e in errors)


def test_validate_ir_v2_duplicate_entry_ids():
    ir = new_draft_v2(
        {"scenario_name": "S", "sub_scenarios": []},
        [
            {"entry_id": "KN-001", "step_phase": "客户筛选", "fields": {"knowledge_desc": "a", "knowledge_ref": "", "rule_ref": "", "output": ""}},
            {"entry_id": "KN-002", "step_phase": "客户数据匹配", "fields": {"knowledge_desc": "b", "knowledge_ref": "", "rule_ref": "", "output": ""}},
        ],
    )
    ir["entries"][1]["entry_id"] = "KN-001"
    errors = validate_ir_v2(ir)
    assert any("entry_id 重复" in e for e in errors)


def test_validate_ir_v2_no_duplicate_empty_entry_ids():
    ir = new_draft_v2(
        {"scenario_name": "S", "sub_scenarios": []},
        [
            {"entry_id": "KN-001", "step_phase": "客户筛选", "fields": {"knowledge_desc": "a", "knowledge_ref": "", "rule_ref": "", "output": ""}},
            {"entry_id": "KN-002", "step_phase": "客户数据匹配", "fields": {"knowledge_desc": "b", "knowledge_ref": "", "rule_ref": "", "output": ""}},
        ],
    )
    # Simulate empty entry_ids to verify duplicate detection is not triggered.
    ir["entries"][0]["entry_id"] = ""
    ir["entries"][1]["entry_id"] = ""
    errors = validate_ir_v2(ir)
    assert all("entry_id 重复" not in e for e in errors)
    assert sum("缺少 entry_id" in e for e in errors) == 2


def test_validate_ir_v2_empty_step_phase():
    ir = new_draft_v2(
        {"scenario_name": "S", "sub_scenarios": []},
        [{"entry_id": "KN-001", "step_phase": "", "fields": {"knowledge_desc": "x", "knowledge_ref": "", "rule_ref": "", "output": ""}}],
    )
    errors = validate_ir_v2(ir)
    assert any("invalid step_phase" in e for e in errors)


def test_validate_ir_v2_invalid_confidence():
    ir = new_draft_v2(
        {"scenario_name": "S", "sub_scenarios": []},
        [{
            "step_phase": "客户筛选",
            "fields": {
                "knowledge_desc": "x",
                "knowledge_ref": "",
                "rule_ref": "",
                "output": "",
                "data_logic": {"sql": "SELECT 1", "confidence": "invalid"},
            },
        }],
    )
    errors = validate_ir_v2(ir)
    assert any("confidence" in e for e in errors)


def test_push_sql_history():
    entry = {"flags": {"sql_history": []}}
    push_sql_history(entry, "SELECT 1", "llm")
    assert len(entry["flags"]["sql_history"]) == 1
    assert entry["flags"]["sql_history"][0]["sql"] == "SELECT 1"


def test_push_sql_history_creates_flags():
    entry = {}
    push_sql_history(entry, "SELECT 2", "llm")
    assert "flags" in entry
    assert len(entry["flags"]["sql_history"]) == 1
    assert entry["flags"]["sql_history"][0]["sql"] == "SELECT 2"


def test_push_sql_history_with_flags_none():
    entry = {"flags": None}
    push_sql_history(entry, "SELECT 3", "llm")
    assert isinstance(entry["flags"], dict)
    assert len(entry["flags"]["sql_history"]) == 1
    assert entry["flags"]["sql_history"][0]["sql"] == "SELECT 3"


def test_push_sql_history_with_non_list_history():
    entry = {"flags": {"sql_history": "not-a-list"}}
    push_sql_history(entry, "SELECT 4", "llm")
    assert isinstance(entry["flags"]["sql_history"], list)
    assert len(entry["flags"]["sql_history"]) == 1
    assert entry["flags"]["sql_history"][0]["sql"] == "SELECT 4"


def test_validate_ir_v2_non_dict():
    assert validate_ir_v2("not-a-dict")
    assert validate_ir_v2(None)


def test_validate_ir_v2_missing_top_level_keys():
    base = new_draft_v2(
        {"scenario_name": "S", "sub_scenarios": []},
        [{"entry_id": "KN-001", "step_phase": "客户筛选", "fields": {"knowledge_desc": "x", "knowledge_ref": "", "rule_ref": "", "output": ""}}],
    )
    for key in ("skill_meta", "anchors", "entries"):
        ir = dict(base)
        del ir[key]
        errors = validate_ir_v2(ir)
        assert any(key in e for e in errors)


def test_validate_ir_v2_top_level_wrong_types():
    assert any("skill_meta must be object" in e for e in validate_ir_v2({
        "ir_version": "2.0", "skill_meta": "bad", "anchors": {}, "entries": []
    }))
    assert any("anchors must be object" in e for e in validate_ir_v2({
        "ir_version": "2.0", "skill_meta": {}, "anchors": "bad", "entries": []
    }))
    assert any("entries must be array" in e for e in validate_ir_v2({
        "ir_version": "2.0", "skill_meta": {}, "anchors": {}, "entries": "bad"
    }))


def test_new_draft_v2_handles_non_dict_fields():
    ir = new_draft_v2(
        {"scenario_name": "S", "sub_scenarios": []},
        [
            {"entry_id": "KN-001", "step_phase": "客户筛选", "fields": None},
            {"entry_id": "KN-002", "step_phase": "客户筛选", "fields": ["not", "a", "dict"]},
        ],
    )
    for entry in ir["entries"]:
        assert isinstance(entry["fields"], dict)
        assert "data_logic" in entry["fields"]


def test_new_draft_v2_normalizes_data_logic_tables_fields():
    ir = new_draft_v2(
        {"scenario_name": "S", "sub_scenarios": []},
        [
            {
                "entry_id": "KN-001",
                "step_phase": "客户筛选",
                "fields": {
                    "knowledge_desc": "x",
                    "knowledge_ref": "",
                    "rule_ref": "",
                    "output": "",
                    "data_logic": {
                        "sql": "SELECT 1",
                        "tables": ["t", None, 1],
                        "fields": ["a", None, 2],
                    },
                },
            }
        ],
    )
    data_logic = ir["entries"][0]["fields"]["data_logic"]
    assert data_logic["tables"] == ["t", "1"]
    assert data_logic["fields"] == ["a", "2"]


def test_validate_ir_v2_data_logic_type_errors():
    base = new_draft_v2(
        {"scenario_name": "S", "sub_scenarios": []},
        [{"entry_id": "KN-001", "step_phase": "客户筛选", "fields": {"knowledge_desc": "x", "knowledge_ref": "", "rule_ref": "", "output": ""}}],
    )
    base["entries"][0]["fields"]["data_logic"]["sql"] = 123
    errors = validate_ir_v2(base)
    assert any("data_logic.sql must be string" in e for e in errors)

    base["entries"][0]["fields"]["data_logic"]["sql"] = ""
    base["entries"][0]["fields"]["data_logic"]["tables"] = "not-a-list"
    errors = validate_ir_v2(base)
    assert any("data_logic.tables must be array" in e for e in errors)

    base["entries"][0]["fields"]["data_logic"]["tables"] = ["t", 1]
    errors = validate_ir_v2(base)
    assert any("data_logic.tables must be string array" in e for e in errors)

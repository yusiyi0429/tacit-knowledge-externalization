import json
import sqlite3

from skill_executor import run_agent_skill


def _write_ir(skill_dir, ir):
    refs_dir = skill_dir / "references"
    refs_dir.mkdir(parents=True, exist_ok=True)
    (refs_dir / "ir_snapshot.json").write_text(json.dumps(ir), encoding="utf-8")


def _create_db(db_path, sql_and_data):
    conn = sqlite3.connect(str(db_path))
    for stmt in sql_and_data:
        conn.execute(stmt)
    conn.commit()
    conn.close()


def test_run_agent_skill(tmp_path):
    # Create fake skill dir with IR snapshot
    skill_dir = tmp_path / "skill"
    ir = {
        "ir_version": "2.0",
        "anchors": {"scenario": "测试场景"},
        "entries": [
            {
                "entry_id": "KN-001",
                "sub_scenario": "子场景",
                "step_phase": "客户筛选",
                "fields": {
                    "knowledge_desc": "筛选高资产客户",
                    "data_logic": {"sql": "SELECT customer_id FROM customers WHERE deposit_balance > 100"},
                },
            }
        ],
    }
    _write_ir(skill_dir, ir)

    # Create fake db
    db_path = tmp_path / "test.db"
    _create_db(
        db_path,
        [
            "CREATE TABLE customers (customer_id TEXT, deposit_balance REAL)",
            "INSERT INTO customers VALUES ('C001', 200)",
        ],
    )

    report = run_agent_skill(str(skill_dir), str(db_path))
    assert report["phase_results"][0]["count"] == 1
    assert report["phase_results"][0]["sample"][0]["customer_id"] == "C001"


def test_empty_ir_no_entries(tmp_path):
    skill_dir = tmp_path / "skill"
    _write_ir(skill_dir, {"ir_version": "2.0", "anchors": {"scenario": "空场景"}, "entries": []})

    db_path = tmp_path / "test.db"
    _create_db(db_path, ["CREATE TABLE customers (customer_id TEXT)"])

    report = run_agent_skill(str(skill_dir), str(db_path))
    assert report["phase_results"] == []
    assert report["scenario"] == "空场景"


def test_missing_sql(tmp_path):
    skill_dir = tmp_path / "skill"
    ir = {
        "ir_version": "2.0",
        "anchors": {"scenario": "测试场景"},
        "entries": [
            {
                "entry_id": "KN-001",
                "sub_scenario": "子场景",
                "step_phase": "客户筛选",
                "fields": {"knowledge_desc": "无 SQL", "data_logic": {}},
            }
        ],
    }
    _write_ir(skill_dir, ir)

    db_path = tmp_path / "test.db"
    _create_db(db_path, ["CREATE TABLE customers (customer_id TEXT)"])

    report = run_agent_skill(str(skill_dir), str(db_path))
    assert report["phase_results"][0]["error"] == "缺少 SQL"
    assert report["phase_results"][0]["count"] == 0


def test_sql_execution_error(tmp_path):
    skill_dir = tmp_path / "skill"
    ir = {
        "ir_version": "2.0",
        "anchors": {"scenario": "测试场景"},
        "entries": [
            {
                "entry_id": "KN-001",
                "sub_scenario": "子场景",
                "step_phase": "客户筛选",
                "fields": {
                    "knowledge_desc": "错误 SQL",
                    "data_logic": {"sql": "SELECT * FROM nonexistent_table"},
                },
            }
        ],
    }
    _write_ir(skill_dir, ir)

    db_path = tmp_path / "test.db"
    _create_db(db_path, ["CREATE TABLE customers (customer_id TEXT)"])

    report = run_agent_skill(str(skill_dir), str(db_path))
    assert report["phase_results"][0]["error"]
    assert "nonexistent_table" in report["phase_results"][0]["error"]


def test_scope_injection(tmp_path):
    skill_dir = tmp_path / "skill"
    ir = {
        "ir_version": "2.0",
        "anchors": {"scenario": "测试场景"},
        "entries": [
            {
                "entry_id": "KN-001",
                "sub_scenario": "子场景",
                "step_phase": "客户筛选",
                "fields": {
                    "knowledge_desc": "使用 scope",
                    "data_logic": {"sql": "SELECT customer_id FROM customers WHERE region = '{{region}}'"},
                },
            }
        ],
    }
    _write_ir(skill_dir, ir)

    db_path = tmp_path / "test.db"
    _create_db(
        db_path,
        [
            "CREATE TABLE customers (customer_id TEXT, region TEXT)",
            "INSERT INTO customers VALUES ('C001', 'east')",
            "INSERT INTO customers VALUES ('C002', 'west')",
        ],
    )

    report = run_agent_skill(str(skill_dir), str(db_path), scope={"region": "east"})
    assert report["scope"] == {"region": "east"}
    assert report["phase_results"][0]["count"] == 1
    assert report["phase_results"][0]["sample"][0]["customer_id"] == "C001"


def test_customer_ids_propagation(tmp_path):
    skill_dir = tmp_path / "skill"
    ir = {
        "ir_version": "2.0",
        "anchors": {"scenario": "测试场景"},
        "entries": [
            {
                "entry_id": "KN-001",
                "sub_scenario": "子场景",
                "step_phase": "客户筛选",
                "fields": {
                    "knowledge_desc": "第一阶段",
                    "data_logic": {"sql": "SELECT customer_id FROM customers WHERE deposit_balance > 100"},
                },
            },
            {
                "entry_id": "KN-002",
                "sub_scenario": "子场景",
                "step_phase": "原因归因",
                "fields": {
                    "knowledge_desc": "第二阶段使用 customer_ids",
                    "data_logic": {"sql": "SELECT customer_id FROM customers WHERE customer_id IN ({{customer_ids}})"},
                },
            },
        ],
    }
    _write_ir(skill_dir, ir)

    db_path = tmp_path / "test.db"
    _create_db(
        db_path,
        [
            "CREATE TABLE customers (customer_id TEXT, deposit_balance REAL)",
            "INSERT INTO customers VALUES ('C001', 200)",
            "INSERT INTO customers VALUES ('C002', 50)",
            "INSERT INTO customers VALUES (\"C'O'003\", 300)",
        ],
    )

    report = run_agent_skill(str(skill_dir), str(db_path))
    assert report["phase_results"][0]["count"] == 2
    assert report["phase_results"][1]["count"] == 2
    assert {r["customer_id"] for r in report["phase_results"][1]["sample"]} == {"C001", "C'O'003"}


def test_phase_ordering(tmp_path):
    skill_dir = tmp_path / "skill"
    ir = {
        "ir_version": "2.0",
        "anchors": {"scenario": "测试场景"},
        "entries": [
            {
                "entry_id": "KN-004",
                "sub_scenario": "子场景",
                "step_phase": "决策建议",
                "fields": {
                    "knowledge_desc": "决策",
                    "data_logic": {"sql": "SELECT customer_id FROM customers LIMIT 1"},
                },
            },
            {
                "entry_id": "KN-001",
                "sub_scenario": "子场景",
                "step_phase": "客户筛选",
                "fields": {
                    "knowledge_desc": "筛选",
                    "data_logic": {"sql": "SELECT customer_id FROM customers LIMIT 1"},
                },
            },
            {
                "entry_id": "KN-002",
                "sub_scenario": "子场景",
                "step_phase": "客户数据匹配",
                "fields": {
                    "knowledge_desc": "匹配",
                    "data_logic": {"sql": "SELECT customer_id FROM customers LIMIT 1"},
                },
            },
        ],
    }
    _write_ir(skill_dir, ir)

    db_path = tmp_path / "test.db"
    _create_db(
        db_path,
        [
            "CREATE TABLE customers (customer_id TEXT)",
            "INSERT INTO customers VALUES ('C001')",
        ],
    )

    report = run_agent_skill(str(skill_dir), str(db_path))
    phases = [p["phase"] for p in report["phase_results"]]
    assert phases == ["客户筛选", "客户数据匹配", "决策建议"]


def test_default_narrative(tmp_path):
    skill_dir = tmp_path / "skill"
    ir = {
        "ir_version": "2.0",
        "anchors": {"scenario": "测试场景"},
        "entries": [
            {
                "entry_id": "KN-001",
                "sub_scenario": "",
                "step_phase": "客户筛选",
                "fields": {
                    "knowledge_desc": "筛选",
                    "data_logic": {"sql": "SELECT customer_id FROM customers"},
                },
            }
        ],
    }
    _write_ir(skill_dir, ir)

    db_path = tmp_path / "test.db"
    _create_db(
        db_path,
        [
            "CREATE TABLE customers (customer_id TEXT)",
            "INSERT INTO customers VALUES ('C001')",
        ],
    )

    report = run_agent_skill(str(skill_dir), str(db_path))
    narrative = report["narrative"]
    assert "# 圈客营销报告：测试场景" in narrative
    assert "## 客户筛选（）" in narrative
    assert "命中客户数：1" in narrative
    assert "规则：筛选" in narrative

import json
import sqlite3
import tempfile
from pathlib import Path
from step5_agent_verify import verify_agent_skill


def test_verify_agent_skill(tmp_path):
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    refs_dir = skill_dir / "references"
    refs_dir.mkdir()
    ir = {
        "ir_version": "2.0",
        "anchors": {"scenario": "测试"},
        "entries": [
            {
                "entry_id": "KN-001",
                "sub_scenario": "子场景",
                "step_phase": "客户筛选",
                "fields": {
                    "knowledge_desc": "高存款",
                    "data_logic": {"sql": "SELECT customer_id, '营销' AS recommended_action FROM customers WHERE deposit_balance > 100"},
                },
            },
            {
                "entry_id": "KN-002",
                "sub_scenario": "子场景",
                "step_phase": "决策建议",
                "fields": {
                    "knowledge_desc": "推荐产品",
                    "data_logic": {"sql": "SELECT customer_id, '营销' AS recommended_action, '信用快贷' AS recommended_product FROM customers WHERE deposit_balance > 100"},
                },
            },
        ],
    }
    (refs_dir / "ir_snapshot.json").write_text(json.dumps(ir), encoding="utf-8")

    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE customers (customer_id TEXT, deposit_balance REAL)")
    conn.execute("INSERT INTO customers VALUES ('C001', 200)")
    conn.execute("INSERT INTO customers VALUES ('C002', 50)")
    conn.commit()

    conn.execute("""
        CREATE TABLE test_customers (
            customer_id TEXT PRIMARY KEY, expected_action TEXT, expected_product TEXT, source TEXT
        )
    """)
    conn.execute("INSERT INTO test_customers VALUES ('C001', '营销', '信用快贷', 'test')")
    conn.execute("INSERT INTO test_customers VALUES ('C002', '拒绝', '', 'test')")
    conn.commit()
    conn.close()

    result = verify_agent_skill(str(skill_dir), str(db_path), source="test")
    assert result["metrics"]["tp"] == 1
    assert result["metrics"]["fn"] == 1
    assert result["metrics"]["precision"] == 1.0
    assert result["metrics"]["recall"] == 0.5

import json
import sqlite3

from step5_agent_verify import verify_agent_skill, build_revision_suggestions


def _setup_skill(skill_dir, decision_sql, extra_entries=None):
    refs_dir = skill_dir / "references"
    refs_dir.mkdir(parents=True)
    entries = (extra_entries or []) + [
        {
            "entry_id": "KN-DEC",
            "sub_scenario": "子场景",
            "step_phase": "决策建议",
            "fields": {
                "knowledge_desc": "推荐产品",
                "data_logic": {"sql": decision_sql},
            },
        },
    ]
    ir = {
        "ir_version": "2.0",
        "anchors": {"scenario": "测试"},
        "entries": entries,
    }
    (refs_dir / "ir_snapshot.json").write_text(json.dumps(ir), encoding="utf-8")
    return ir


def _create_db(db_path, customers, test_customers):
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE customers (customer_id TEXT, deposit_balance REAL)")
    for cid, balance in customers:
        conn.execute("INSERT INTO customers VALUES (?, ?)", (cid, balance))
    conn.execute("""
        CREATE TABLE test_customers (
            customer_id TEXT PRIMARY KEY, expected_action TEXT, expected_product TEXT, source TEXT
        )
    """)
    for row in test_customers:
        conn.execute("INSERT INTO test_customers VALUES (?, ?, ?, ?)", row)
    conn.commit()
    conn.close()


def test_verify_agent_skill(tmp_path):
    skill_dir = tmp_path / "skill"
    _setup_skill(
        skill_dir,
        "SELECT customer_id, '营销' AS recommended_action, '信用快贷' AS recommended_product FROM customers WHERE deposit_balance > 100",
    )
    db_path = tmp_path / "test.db"
    _create_db(
        db_path,
        customers=[("C001", 200), ("C002", 50)],
        test_customers=[("C001", "营销", "信用快贷", "test"), ("C002", "拒绝", "", "test")],
    )

    result = verify_agent_skill(str(skill_dir), str(db_path), source="test")
    assert result["metrics"]["tp"] == 1
    assert result["metrics"]["fn"] == 1
    assert result["metrics"]["precision"] == 1.0
    assert result["metrics"]["recall"] == 0.5


def test_build_revision_suggestions(tmp_path):
    skill_dir = tmp_path / "skill"
    ir = _setup_skill(
        skill_dir,
        "SELECT customer_id, '营销' AS recommended_action, '信用快贷' AS recommended_product FROM customers WHERE deposit_balance > 100",
    )
    mismatches = [
        {
            "customer_id": "C001",
            "expected": {"action": "营销", "product": "抵押快贷"},
            "predicted": {"action": "营销", "product": "信用快贷"},
        }
    ]
    suggestions = build_revision_suggestions(mismatches, ir)
    assert len(suggestions) == 1
    assert suggestions[0]["entry_id"] == "KN-DEC"
    assert "营销/抵押快贷" in suggestions[0]["new_value"]
    assert "营销/信用快贷" in suggestions[0]["new_value"]


def test_empty_test_customers(tmp_path):
    skill_dir = tmp_path / "skill"
    _setup_skill(
        skill_dir,
        "SELECT customer_id, '营销' AS recommended_action, '信用快贷' AS recommended_product FROM customers",
    )
    db_path = tmp_path / "test.db"
    _create_db(db_path, customers=[("C001", 200)], test_customers=[])

    result = verify_agent_skill(str(skill_dir), str(db_path))
    assert result["metrics"]["tp"] == 0
    assert result["metrics"]["fp"] == 1
    assert result["metrics"]["fn"] == 0
    assert result["metrics"]["precision"] == 0.0
    assert result["metrics"]["recall"] == 0.0
    assert result["metrics"]["f1"] == 0.0


def test_source_filtering(tmp_path):
    skill_dir = tmp_path / "skill"
    _setup_skill(
        skill_dir,
        "SELECT customer_id, '营销' AS recommended_action, '信用快贷' AS recommended_product FROM customers",
    )
    db_path = tmp_path / "test.db"
    _create_db(
        db_path,
        customers=[("C001", 200), ("C002", 200)],
        test_customers=[
            ("C001", "营销", "信用快贷", "test"),
            ("C002", "营销", "信用快贷", "other"),
        ],
    )

    result = verify_agent_skill(str(skill_dir), str(db_path), source="test")
    assert result["metrics"]["tp"] == 1
    assert result["metrics"]["fn"] == 0
    assert result["metrics"]["fp"] == 1


def test_all_correct(tmp_path):
    skill_dir = tmp_path / "skill"
    _setup_skill(
        skill_dir,
        "SELECT customer_id, '营销' AS recommended_action, '信用快贷' AS recommended_product FROM customers",
    )
    db_path = tmp_path / "test.db"
    _create_db(
        db_path,
        customers=[("C001", 200), ("C002", 200)],
        test_customers=[
            ("C001", "营销", "信用快贷", "test"),
            ("C002", "营销", "信用快贷", "test"),
        ],
    )

    result = verify_agent_skill(str(skill_dir), str(db_path), source="test")
    assert result["metrics"]["tp"] == 2
    assert result["metrics"]["fp"] == 0
    assert result["metrics"]["fn"] == 0
    assert result["metrics"]["precision"] == 1.0
    assert result["metrics"]["recall"] == 1.0
    assert result["metrics"]["f1"] == 1.0


def test_all_wrong(tmp_path):
    skill_dir = tmp_path / "skill"
    _setup_skill(
        skill_dir,
        "SELECT customer_id, '营销' AS recommended_action, '信用快贷' AS recommended_product FROM customers",
    )
    db_path = tmp_path / "test.db"
    _create_db(
        db_path,
        customers=[("C001", 200)],
        test_customers=[("C001", "拒绝", "", "test")],
    )

    result = verify_agent_skill(str(skill_dir), str(db_path), source="test")
    assert result["metrics"]["tp"] == 0
    assert result["metrics"]["fp"] == 0
    assert result["metrics"]["fn"] == 1
    assert result["metrics"]["precision"] == 0.0
    assert result["metrics"]["recall"] == 0.0
    assert result["metrics"]["f1"] == 0.0


def test_missing_decision_phase(tmp_path):
    skill_dir = tmp_path / "skill"
    refs_dir = skill_dir / "references"
    refs_dir.mkdir(parents=True)
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
                    "data_logic": {"sql": "SELECT customer_id FROM customers WHERE deposit_balance > 100"},
                },
            },
        ],
    }
    (refs_dir / "ir_snapshot.json").write_text(json.dumps(ir), encoding="utf-8")

    db_path = tmp_path / "test.db"
    _create_db(
        db_path,
        customers=[("C001", 200)],
        test_customers=[("C001", "营销", "信用快贷", "test")],
    )

    result = verify_agent_skill(str(skill_dir), str(db_path), source="test")
    assert result["metrics"]["tp"] == 0
    assert result["metrics"]["fn"] == 1
    assert result["metrics"]["fp"] == 0


def test_product_mismatch(tmp_path):
    skill_dir = tmp_path / "skill"
    _setup_skill(
        skill_dir,
        "SELECT customer_id, '营销' AS recommended_action, '信用快贷' AS recommended_product FROM customers",
    )
    db_path = tmp_path / "test.db"
    _create_db(
        db_path,
        customers=[("C001", 200)],
        test_customers=[("C001", "营销", "抵押快贷", "test")],
    )

    result = verify_agent_skill(str(skill_dir), str(db_path), source="test")
    assert result["metrics"]["tp"] == 0
    assert result["metrics"]["fn"] == 1
    assert len(result["mismatches"]) == 1
    assert result["mismatches"][0]["predicted"]["product"] == "信用快贷"

import json
from pathlib import Path

from golden_db import load_golden_cases


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GOLDEN_EN_PATH = REPO_ROOT / "data" / "golden" / "en" / "english-credit-golden.json"


def test_english_golden_file_exists():
    assert GOLDEN_EN_PATH.exists()


def test_load_english_golden_cases():
    cases = load_golden_cases(GOLDEN_EN_PATH)
    assert len(cases) >= 4
    assert all("expected_action" in c for c in cases)


def test_load_english_golden_cases_normalizes_keys():
    cases = load_golden_cases(GOLDEN_EN_PATH)
    first = cases[0]
    assert "case_id" in first
    assert "customer_id" in first
    assert "step_phase" in first
    assert "customer_features" in first
    assert "knowledge_desc" in first
    assert "logic" in first
    assert "confidence" in first
    assert "expected_action" in first


def test_load_golden_cases_accepts_chinese_aliases(tmp_path):
    chinese_cases = {
        "cases": [
            {
                "案例编号": "ZH-001",
                "客户编号": "C999",
                "步骤阶段": "customer_filter",
                "客户特征": {"register_years": 5},
                "结论": "approve",
                "知识描述": "Registered at least 2 years.",
                "判断逻辑": "register_years >= 2 => approve",
                "置信度": "high",
            }
        ]
    }
    path = tmp_path / "chinese-cases.json"
    path.write_text(json.dumps(chinese_cases), encoding="utf-8")
    cases = load_golden_cases(path)
    assert len(cases) == 1
    case = cases[0]
    assert case["case_id"] == "ZH-001"
    assert case["customer_id"] == "C999"
    assert case["step_phase"] == "customer_filter"
    assert case["expected_action"] == "approve"
    assert case["knowledge_desc"] == "Registered at least 2 years."
    assert case["logic"] == "register_years >= 2 => approve"
    assert case["confidence"] == "high"

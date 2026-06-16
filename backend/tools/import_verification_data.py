#!/usr/bin/env python3
"""导入已有验证数据到 KB 验证知识库。"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_DIR / "backend"))
os.chdir(str(PROJECT_DIR))

import knowledge_base as kb

TEST_DATA_DIR = PROJECT_DIR / "data" / "test-cases"
GOLDEN_DB = PROJECT_DIR / "data" / "golden" / "golden_test.db"


def _load_json_file(path: Path) -> dict:
    with open(str(path), "r", encoding="utf-8") as f:
        return json.load(f)


def _case_expected_output(case_file: str) -> dict:
    """根据验证测试指南中的描述，给每个 case 一个期望输出。"""
    mapping = {
        "case-01": {"prediction": "通过", "next_action": "转向结算/理财服务，定期回访"},
        "case-02": {"prediction": "条件通过", "next_action": "降额 + 追加担保，核查流水真实性"},
        "case-03": {"prediction": "条件通过", "next_action": "黄色/红色预警，启动贷后现场检查"},
        "case-04": {"prediction": "拒绝", "next_action": "不良成因归类 + 流程改进建议"},
    }
    prefix = case_file.split("_")[0]
    return mapping.get(prefix, {"prediction": "通过"})


def import_test_cases(skill_id: str = "") -> dict:
    """从 data/test-cases/ 导入测试用例。"""
    created = 0
    skipped = 0
    if not TEST_DATA_DIR.exists():
        return {"created": 0, "skipped": 0, "error": "目录不存在"}

    kb.init_db()
    for path in sorted(TEST_DATA_DIR.glob("*.json")):
        data = _load_json_file(path)
        name = path.stem
        # 避免重复导入
        existing = kb.list_verification_cases(source="result", limit=1000)
        if any(str(name) in (e.get("name") or "") for e in existing):
            skipped += 1
            continue
        kb.add_verification_case(
            name=name,
            input_data=data,
            description=data.get("title", ""),
            expected_output=_case_expected_output(name),
            tags="result,auto",
            source="result",
            skill_id=skill_id,
        )
        created += 1
    return {"created": created, "skipped": skipped}


def import_golden_rules(skill_id: str = "") -> dict:
    """从 golden_test.db 导入验证规则（按知识类型和环节聚合）。"""
    if not GOLDEN_DB.exists():
        return {"created": 0, "skipped": 0, "error": "数据库不存在"}

    kb.init_db()
    conn = sqlite3.connect(str(GOLDEN_DB))
    conn.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT 环节, 知识类型, 知识编号, 适用条件, 判断逻辑, 反模式踩坑提示 FROM golden_items"
        ).fetchall()]
    finally:
        conn.close()

    existing = kb.list_verification_rules(limit=1000)
    existing_names = {e.get("name") for e in existing}

    created = 0
    skipped = 0
    for r in rows:
        name = f"{r.get('知识编号')} {r.get('环节')}"
        if name in existing_names:
            skipped += 1
            continue
        rule = {
            "环节": r.get("环节", ""),
            "知识类型": r.get("知识类型", ""),
            "适用条件": r.get("适用条件", ""),
            "判断逻辑": r.get("判断逻辑", ""),
            "反模式踩坑提示": r.get("反模式踩坑提示", ""),
            "skill_id": skill_id,
        }
        kb.add_verification_rule(
            name=name,
            rule=rule,
            rule_type="structure" if r.get("知识类型") == "操作流程" else "quality",
            description=f"来自 golden_test.db 的规则：{r.get('知识编号')}",
            enabled=True,
        )
        created += 1
    return {"created": created, "skipped": skipped}


def import_result_data(skill_id: str = "") -> dict:
    """一次性导入 result 测试用例和 golden 规则。"""
    cases = import_test_cases(skill_id=skill_id)
    rules = import_golden_rules(skill_id=skill_id)
    return {"cases": cases, "rules": rules}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="导入验证数据到 KB")
    parser.add_argument("--skill-id", default="", help="关联的 skill id")
    args = parser.parse_args()
    stats = import_result_data(skill_id=args.skill_id)
    print(json.dumps(stats, ensure_ascii=False, indent=2))

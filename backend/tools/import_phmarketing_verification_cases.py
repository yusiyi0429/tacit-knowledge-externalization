#!/usr/bin/env python3
"""把对公普惠客户潜力营销验证用例 JSON 导入 knowledge_base.db。

用法:
    cd backend
    python tools/import_phmarketing_verification_cases.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import knowledge_base as kb

CASE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "test-cases"
FILES = [
    "case-phmarketing-01_无融资需求.json",
    "case-phmarketing-02_不满足准入.json",
    "case-phmarketing-03_产品不匹配.json",
]
TAGS = "对公普惠客户潜力营销,营销,验证"
SOURCE = "plan_import"


def import_cases() -> None:
    kb.init_db()
    for filename in FILES:
        path = CASE_DIR / filename
        if not path.is_file():
            print(f"[WARN] 跳过不存在的文件: {path}")
            continue
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        case_uid = kb.add_verification_case(
            name=data["name"],
            input_data=data["input"],
            description=data.get("description", ""),
            expected_output=data.get("expected_output", {}),
            tags=TAGS,
            source=SOURCE,
            skill_id="",
        )
        print(f"[OK] 导入 {filename} -> {case_uid}")


if __name__ == "__main__":
    import_cases()

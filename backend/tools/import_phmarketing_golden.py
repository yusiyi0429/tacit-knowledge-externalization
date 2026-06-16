#!/usr/bin/env python3
"""把对公普惠客户潜力营销 golden JSON 导入 data/golden/golden_test.db。

用法:
    cd backend
    python tools/import_phmarketing_golden.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "golden" / "golden_test.db"
JSON_PATH = PROJECT_ROOT / "data" / "golden" / "对公普惠客户潜力营销_golden_items.json"
DOC_PATH = PROJECT_ROOT / "data" / "samples" / "step2-文档萃取" / "对公普惠客户潜力营销_访谈提纲模板.md"


def get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """仅创建表结构（幂等），不写入种子数据。"""
    schema = """
    CREATE TABLE IF NOT EXISTS golden_scenarios (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        name          TEXT    NOT NULL UNIQUE,
        description   TEXT,
        domain        TEXT    DEFAULT '通用',
        created_at    TEXT    DEFAULT (datetime('now','localtime'))
    );
    CREATE TABLE IF NOT EXISTS golden_documents (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        scenario_id   INTEGER NOT NULL REFERENCES golden_scenarios(id) ON DELETE CASCADE,
        filename      TEXT    NOT NULL,
        content       TEXT    NOT NULL,
        source_type   TEXT    CHECK(source_type IN ('制度','纪要','案例','访谈','培训','其他')),
        created_at    TEXT    DEFAULT (datetime('now','localtime'))
    );
    CREATE TABLE IF NOT EXISTS golden_items (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        scenario_id   INTEGER NOT NULL REFERENCES golden_scenarios(id) ON DELETE CASCADE,
        document_id   INTEGER REFERENCES golden_documents(id) ON DELETE SET NULL,
        知识编号       TEXT,
        环节           TEXT,
        具体方法       TEXT    NOT NULL,
        知识类型       TEXT    CHECK(知识类型 IN ('判断规则','操作流程','反模式')),
        适用条件       TEXT,
        判断逻辑       TEXT,
        反模式踩坑提示  TEXT,
        经验判断       TEXT,
        适用边界       TEXT,
        例外情形       TEXT,
        来源文档       TEXT,
        来源位置       TEXT,
        置信度         TEXT    CHECK(置信度 IN ('高','中','低')),
        贡献专家       TEXT,
        证据数         INTEGER DEFAULT 0,
        突破数         INTEGER DEFAULT 0,
        created_at    TEXT    DEFAULT (datetime('now','localtime'))
    );
    CREATE INDEX IF NOT EXISTS idx_items_scenario ON golden_items(scenario_id);
    CREATE INDEX IF NOT EXISTS idx_items_document ON golden_items(document_id);
    CREATE INDEX IF NOT EXISTS idx_documents_scenario ON golden_documents(scenario_id);
    """
    conn.executescript(schema)


def import_golden() -> None:
    if not JSON_PATH.is_file():
        print(f"[ERROR] 找不到 golden JSON: {JSON_PATH}")
        sys.exit(1)

    with JSON_PATH.open(encoding="utf-8") as f:
        payload = json.load(f)

    scenario = payload["scenario"]
    doc_meta = payload.get("document", {})
    items = payload["items"]

    conn = get_db()
    init_schema(conn)
    cur = conn.cursor()

    # 插入或复用场景
    row = cur.execute(
        "SELECT id FROM golden_scenarios WHERE name = ?", (scenario["name"],)
    ).fetchone()
    if row:
        scenario_id = row["id"]
        print(f"[SKIP] 场景已存在: {scenario['name']} (id={scenario_id})")
    else:
        cur.execute(
            "INSERT INTO golden_scenarios (name, description, domain) VALUES (?,?,?)",
            (scenario["name"], scenario.get("description", ""), scenario.get("domain", "银行信贷")),
        )
        scenario_id = cur.lastrowid
        print(f"[OK] 新建场景: {scenario['name']} (id={scenario_id})")

    # 插入源文档
    doc_content = DOC_PATH.read_text(encoding="utf-8") if DOC_PATH.is_file() else ""
    doc_row = cur.execute(
        "SELECT id FROM golden_documents WHERE scenario_id = ? AND filename = ?",
        (scenario_id, doc_meta.get("filename", "")),
    ).fetchone()
    if doc_row:
        document_id = doc_row["id"]
        print(f"[SKIP] 文档已存在: {doc_meta.get('filename', '')}")
    else:
        cur.execute(
            "INSERT INTO golden_documents (scenario_id, filename, content, source_type) VALUES (?,?,?,?)",
            (scenario_id, doc_meta.get("filename", ""), doc_content,
             doc_meta.get("source_type", "访谈")),
        )
        document_id = cur.lastrowid
        print(f"[OK] 新建文档: {doc_meta.get('filename', '')} (id={document_id})")

    inserted = 0
    skipped = 0
    for item in items:
        编号 = item.get("知识编号")
        existing = cur.execute(
            "SELECT id FROM golden_items WHERE scenario_id = ? AND 知识编号 = ?",
            (scenario_id, 编号),
        ).fetchone()
        if existing:
            skipped += 1
            continue
        cur.execute(
            """INSERT INTO golden_items (
                scenario_id, document_id, 知识编号, 环节, 具体方法, 知识类型,
                适用条件, 判断逻辑, 反模式踩坑提示, 经验判断, 适用边界, 例外情形,
                来源文档, 来源位置, 置信度, 贡献专家, 证据数, 突破数
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                scenario_id, document_id,
                编号, item.get("环节"), item["具体方法"], item.get("知识类型"),
                item.get("适用条件"), item.get("判断逻辑"), item.get("反模式踩坑提示"),
                item.get("经验判断"), item.get("适用边界"), item.get("例外情形"),
                item.get("来源文档"), item.get("来源位置"), item.get("置信度"),
                item.get("贡献专家"), item.get("证据数", 0), item.get("突破数", 0),
            ),
        )
        inserted += 1

    conn.commit()
    conn.close()
    print(f"[OK] 导入完成: 新增 {inserted} 条, 跳过 {skipped} 条, 共 {len(items)} 条")


if __name__ == "__main__":
    import_golden()

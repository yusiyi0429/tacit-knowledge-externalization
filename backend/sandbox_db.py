"""SQLite data sandbox — per-pipeline database for mock tables and data."""

import json
import sqlite3
import threading
from pathlib import Path


class SandboxDB:
    def __init__(self, workspace: Path, pipeline_id: str):
        self._db_path = workspace / f"sandbox_{pipeline_id}.db"
        self._lock = threading.Lock()

    @property
    def db_path(self) -> str:
        return str(self._db_path)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def list_tables(self) -> list[dict]:
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
            tables = []
            for r in rows:
                cols = conn.execute(f"PRAGMA table_info([{r['name']}])").fetchall()
                tables.append({
                    "name": r["name"],
                    "columns": [
                        {"name": c["name"], "type": c["type"], "nullable": not c["notnull"], "pk": bool(c["pk"])}
                        for c in cols
                    ],
                    "row_count": conn.execute(f"SELECT COUNT(*) as n FROM [{r['name']}]").fetchone()["n"],
                })
            return tables

    def get_table(self, name: str) -> dict | None:
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
            ).fetchone()
            if not row:
                return None
            cols = conn.execute(f"PRAGMA table_info([{name}])").fetchall()
            return {
                "name": name,
                "columns": [
                    {"name": c["name"], "type": c["type"], "nullable": not c["notnull"], "pk": bool(c["pk"])}
                    for c in cols
                ],
            }

    def create_table(self, name: str, columns: list[dict]) -> None:
        if not name or not columns:
            raise ValueError("表名和列定义不能为空")
        col_defs = []
        for c in columns:
            col_name = c["name"]
            col_type = c.get("type", "TEXT").upper()
            if col_type not in ("TEXT", "INTEGER", "REAL", "BLOB"):
                col_type = "TEXT"
            null_clause = "NOT NULL" if c.get("nullable") is False else ""
            col_defs.append(f"[{col_name}] {col_type} {null_clause}".strip())
        sql = f"CREATE TABLE IF NOT EXISTS [{name}] ({', '.join(col_defs)})"
        with self._lock, self._conn() as conn:
            conn.execute(sql)

    def drop_table(self, name: str) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(f"DROP TABLE IF EXISTS [{name}]")

    def insert_rows(self, table: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        with self._lock, self._conn() as conn:
            cols = conn.execute(f"PRAGMA table_info([{table}])").fetchall()
            col_names = [c["name"] for c in cols]
            placeholders = ", ".join(["?" for _ in col_names])
            sql = f"INSERT INTO [{table}] ({', '.join(f'[{c}]' for c in col_names)}) VALUES ({placeholders})"
            count = 0
            for row in rows:
                values = tuple(row.get(c) for c in col_names)
                conn.execute(sql, values)
                count += 1
            return count

    def get_data(self, table: str, limit: int = 100, offset: int = 0) -> dict:
        with self._lock, self._conn() as conn:
            cols = conn.execute(f"PRAGMA table_info([{table}])").fetchall()
            col_names = [c["name"] for c in cols]
            total = conn.execute(f"SELECT COUNT(*) as n FROM [{table}]").fetchone()["n"]
            rows = conn.execute(
                f"SELECT * FROM [{table}] LIMIT ? OFFSET ?", (limit, offset)
            ).fetchall()
            return {
                "columns": col_names,
                "rows": [[r[c] for c in col_names] for r in rows],
                "total": total,
                "limit": limit,
                "offset": offset,
            }

    def execute(self, sql: str, params: list | None = None) -> dict:
        sql_upper = sql.strip().upper()
        if not sql_upper.startswith("SELECT") and not sql_upper.startswith("PRAGMA"):
            raise ValueError("仅允许 SELECT / PRAGMA 查询")
        with self._lock, self._conn() as conn:
            cur = conn.execute(sql, params or [])
            if sql_upper.startswith("PRAGMA") or not cur.description:
                return {"columns": [], "rows": [], "total": 0}
            col_names = [d[0] for d in cur.description]
            rows = cur.fetchall()
            return {
                "columns": col_names,
                "rows": [[r[c] for c in col_names] for r in rows],
                "total": len(rows),
            }

    def exists(self) -> bool:
        return self._db_path.exists()


def table_name_from_knowledge_columns(columns: list[str], index: int = 0) -> str:
    """Generate a safe SQLite table name from knowledge column names."""
    if not columns:
        return f"knowledge_table_{index}"
    keywords = ["规则", "判断", "条件", "模式", "经验", "场景", "决策", "评估", "风险"]
    for kw in keywords:
        for col in columns:
            if kw in col:
                safe = col.replace(" ", "_").replace("/", "_")[:20]
                return f"t_{safe}"
    return f"t_knowledge_{index}"


def generate_schema_prompt(knowledge_columns: list[str], scenario_name: str, scenario_content: str) -> str:
    """Build LLM prompt for generating sandbox table schemas."""
    return f"""你是一位银行数据架构师。请根据以下场景，设计 2~4 张 SQLite 数据表来支撑知识判断。

## 场景
名称：{scenario_name}
说明：{scenario_content or '无补充说明'}

## 知识字段（来自场景锚定）
{json.dumps(knowledge_columns, ensure_ascii=False)}

## 要求
1. 表名用中文（如「客户信息」「贷款记录」「风控规则」）
2. 每张表 4~8 列，包含必要的主键和外键关系提示（用列名暗示，如 customer_id）
3. 列类型：TEXT（字符串/日期）、INTEGER（整数）、REAL（小数）
4. 为每张表生成 3~6 条模拟数据（中国银行业场景，数据要真实可信）
5. 模拟数据中尽量包含能让知识字段「触发」的记录——即存在边界案例、反模式、异常值

## 输出格式（严格 JSON）
```json
{{
  "tables": [
    {{
      "name": "客户信息",
      "columns": [
        {{"name": "customer_id", "type": "TEXT", "nullable": false}},
        {{"name": "industry", "type": "TEXT"}}
      ],
      "mock_data": [
        {{"customer_id": "C001", "industry": "制造业"}}
      ]
    }}
  ]
}}
```"""

#!/usr/bin/env python3
"""Agent-Skill 执行器：按 IR 顺序执行 SQL 并生成圈客报告。"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path


STEP_PHASE_ORDER = ["客户筛选", "客户数据匹配", "原因归因", "决策建议"]


def load_ir_from_skill_dir(skill_dir: str) -> dict:
    """从 skill 目录读取 ir_snapshot.json。"""
    snapshot = Path(skill_dir) / "references" / "ir_snapshot.json"
    if snapshot.exists():
        return json.loads(snapshot.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"未找到 IR 快照: {snapshot}")


def execute_sql(db_path: str, sql: str, params: dict | None = None) -> list[dict]:
    """在 SQLite 上执行只读 SQL。"""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        cur = conn.execute(sql, params or {})
        cols = [d[0] for d in cur.description] if cur.description else []
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def run_agent_skill(
    skill_dir: str,
    db_path: str,
    *,
    scope: dict | None = None,
    llm_callback=None,
) -> dict:
    """执行 agent-skill，返回结构化报告。"""
    ir = load_ir_from_skill_dir(skill_dir)
    entries = sorted(
        ir.get("entries", []),
        key=lambda e: (e.get("sub_scenario", ""), STEP_PHASE_ORDER.index(e.get("step_phase", "")) if e.get("step_phase") in STEP_PHASE_ORDER else 99),
    )

    context = {"scope": scope or {}, **(scope or {})}
    phase_results = []

    for entry in entries:
        phase = entry.get("step_phase")
        fields = entry.get("fields", {})
        data_logic = fields.get("data_logic") or {}
        sql = data_logic.get("sql") or ""

        if not sql.strip():
            phase_results.append({
                "entry_id": entry.get("entry_id"),
                "phase": phase,
                "sql": "",
                "count": 0,
                "error": "缺少 SQL",
            })
            context["customer_ids"] = []
            continue

        # 注入上下文变量
        rendered_sql = _render_sql(sql, context)
        try:
            rows = execute_sql(db_path, rendered_sql)
        except Exception as e:
            phase_results.append({
                "entry_id": entry.get("entry_id"),
                "phase": phase,
                "sql": rendered_sql,
                "count": 0,
                "error": str(e),
            })
            context["customer_ids"] = []
            continue

        # 更新当前客户集合上下文
        if rows and "customer_id" in rows[0]:
            current_customers = {r["customer_id"] for r in rows}
        else:
            current_customers = set()
        context["customer_ids"] = list(current_customers)

        phase_results.append({
            "entry_id": entry.get("entry_id"),
            "phase": phase,
            "sub_scenario": entry.get("sub_scenario"),
            "knowledge_desc": fields.get("knowledge_desc"),
            "sql": rendered_sql,
            "count": len(rows),
            "sample": rows[:5],
        })

    report = {
        "ir_version": ir.get("ir_version"),
        "scenario": ir.get("anchors", {}).get("scenario"),
        "executed_at": _now(),
        "scope": scope or {},
        "phase_results": phase_results,
    }

    # LLM 后处理生成营销话术
    if llm_callback:
        report["narrative"] = llm_callback(report)
    else:
        report["narrative"] = _default_narrative(report)

    return report


def _render_sql(sql: str, context: dict) -> str:
    """简单变量替换，如 {{customer_ids}}。"""
    for key, val in context.items():
        placeholder = "{{" + key + "}}"
        if placeholder in sql:
            if isinstance(val, list):
                sql = sql.replace(placeholder, ", ".join("'" + str(v).replace("'", "''") + "'" for v in val))
            else:
                sql = sql.replace(placeholder, str(val))
    return sql


def _default_narrative(report: dict) -> str:
    lines = [f"# 圈客营销报告：{report.get('scenario', '')}", ""]
    for phase in report.get("phase_results", []):
        sub = phase.get("sub_scenario") or ""
        lines.append(f"## {phase.get('phase')}（{sub}）")
        lines.append(f"- 命中客户数：{phase.get('count')}")
        if phase.get("error"):
            lines.append(f"- 错误：{phase['error']}")
        else:
            lines.append(f"- 规则：{phase.get('knowledge_desc', '')}")
    return "\n".join(lines)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="执行 agent-skill 圈客报告")
    parser.add_argument("--db", required=True, help="SQLite 数据库路径")
    parser.add_argument("--output", default="report.json", help="输出报告 JSON 路径")
    parser.add_argument("--scope", default="{}", help="scope JSON 字符串")
    args = parser.parse_args()

    scope = {}
    if args.scope:
        try:
            scope = json.loads(args.scope)
        except json.JSONDecodeError:
            pass

    skill_dir = Path(__file__).resolve().parent.parent
    report = run_agent_skill(str(skill_dir), args.db, scope=scope)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report written to {args.output}")

#!/usr/bin/env python3
"""Step5: 在 test_customers 上验证 agent-skill，计算 P/R/F1。"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from skill_executor import run_agent_skill


def _normalize_action(action: str) -> str:
    s = (action or "").strip().lower()
    if "拒绝" in action or "reject" in s:
        return "拒绝"
    if "条件" in action or "conditional" in s:
        return "条件通过"
    if "培育" in action:
        return "培育"
    return "营销"


def verify_agent_skill(
    skill_dir: str,
    db_path: str,
    *,
    source: str | None = None,
) -> dict:
    """执行 agent-skill 并与 test_customers 期望结果对比。"""
    conn = sqlite3.connect(db_path)
    try:
        sql = "SELECT customer_id, expected_action, expected_product FROM test_customers"
        params = []
        if source:
            sql += " WHERE source = ?"
            params.append(source)
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    expected = {r[0]: {"action": _normalize_action(r[1]), "product": r[2] or ""} for r in rows}

    report = run_agent_skill(skill_dir, db_path)

    # 解析 agent-skill 最终推荐：取最后一个 phase（决策建议）的结果
    decision_phase = None
    for phase in reversed(report.get("phase_results", [])):
        if phase.get("phase") == "决策建议":
            decision_phase = phase
            break

    predicted = {}
    if decision_phase and decision_phase.get("sample"):
        for row in decision_phase["sample"]:
            cid = row.get("customer_id")
            if cid:
                predicted[cid] = {
                    "action": _normalize_action(row.get("recommended_action", "营销")),
                    "product": row.get("recommended_product", ""),
                }

    # 计算 action P/R/F1
    tp = fp = fn = 0
    mismatches = []
    for cid, exp in expected.items():
        pred = predicted.get(cid)
        if pred:
            if pred["action"] == exp["action"]:
                tp += 1
            else:
                fn += 1
                mismatches.append({"customer_id": cid, "expected": exp, "predicted": pred})
        else:
            fn += 1
            mismatches.append({"customer_id": cid, "expected": exp, "predicted": None})
    for cid, pred in predicted.items():
        if cid not in expected:
            fp += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "report": report,
        "metrics": {
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
            "tp": tp,
            "fp": fp,
            "fn": fn,
        },
        "mismatches": mismatches,
    }


def build_revision_suggestions(mismatches: list[dict], ir: dict) -> list[dict]:
    """把验证分歧转换为 Step3 建议池条目。"""
    suggestions = []
    for m in mismatches:
        suggestions.append({
            "entry_id": "",
            "field": "rule_ref",
            "action": "supplement",
            "old_value": "",
            "new_value": f"客户 {m['customer_id']} 期望动作 {m['expected']['action']}，但 agent-skill 输出 {m['predicted']['action'] if m['predicted'] else '未命中'}",
            "note": "来自 Step5 验证分歧",
            "by": "step5_verify",
            "case": m,
        })
    return suggestions

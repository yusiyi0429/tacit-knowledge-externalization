"""
显性化校验闭环（Step5 验证环节）
上传历史案例（含已知专家结论），用生成的 SKILL.md 终版让 LLM（判官模型）判断，
与专家结论比对，输出命中率/分歧清单；分歧自动生成 entry 级修订建议回流 Step3。
"""

from __future__ import annotations

import json
import re
from datetime import datetime


def extract_assistant_content(result: dict) -> str:
    """从 LLM 响应 dict 中提取 assistant content。"""
    choices = result.get("choices") if isinstance(result, dict) else None
    if isinstance(choices, list) and choices:
        msg = choices[0].get("message") or {}
        return str(msg.get("content") or "")
    return ""
def build_validation_prompt(knowledge_text: str, cases: list[dict]) -> tuple[str, str]:
    """构建校验 system prompt 和 user prompt。"""
    system_prompt = (
        "你是一位银行信贷审批专家。请基于下面提供的知识库内容，对每个案例给出你的判断。\n\n"
        "规则：\n"
        "1. 仔细阅读知识库内容，理解其中每条规则的适用条件和判断逻辑\n"
        "2. 对每个案例，先列出你参考了知识库中的哪些规则，再给出结论\n"
        "3. 输出为 JSON 数组，每个案例一条\n\n"
        '格式：[{"case_id": "案例ID", '
        '"prediction": "通过|拒绝|条件通过", '
        '"reasoning": "你的推理过程（引用知识库规则）", '
        '"referenced_rules": ["KN-xxx", ...], '
        '"confidence": "高|中|低"}]\n\n'
        "不要输出任何前后说明文字，只输出 JSON 数组。"
    )

    cases_text = ""
    for c in cases:
        cases_text += f"\n---\n案例ID：{c.get('case_id', '?')}\n"
        cases_text += f"场景描述：{c.get('description', c.get('场景', ''))}\n"
        for k, v in c.items():
            if k not in ("case_id", "description", "场景", "conclusion", "结论", "expert_conclusion"):
                cases_text += f"{k}：{v}\n"

    user_prompt = f"知识库内容：\n{knowledge_text[:8000]}\n\n待判断案例：{cases_text}"

    return system_prompt, user_prompt


def compare_predictions(predictions: list[dict], cases: list[dict]) -> dict:
    """对比 LLM 预测与专家结论。"""
    total = max(len(predictions), 1)
    hits = 0
    mismatches = []
    for pred in predictions:
        case_id = pred.get("case_id", "")
        pred_label = (pred.get("prediction", "") or "").strip()
        # 找对应案例的专家结论
        expert_label = ""
        for c in cases:
            if c.get("case_id") == case_id:
                expert_label = (c.get("结论", c.get("conclusion", c.get("expert_conclusion", ""))) or "").strip()
                break
        pred_norm = _normalize_label(pred_label)
        expert_norm = _normalize_label(expert_label)
        if pred_norm and expert_norm and pred_norm == expert_norm:
            hits += 1
        else:
            mismatches.append({
                "case_id": case_id,
                "prediction": pred_label,
                "expert_conclusion": expert_label,
                "match": pred_norm == expert_norm,
                "reasoning": pred.get("reasoning", ""),
                "referenced_rules": pred.get("referenced_rules", []),
            })
    hit_rate = round(hits / total, 3)
    return {
        "total_cases": total,
        "hits": hits,
        "hit_rate": hit_rate,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
    }


_ACTION_ALIASES = {
    "approve": ["approve", "通过", "同意", "yes"],
    "reject": ["reject", "拒绝", "驳回", "否决", "no"],
    "conditional": ["conditional", "条件通过", "条件", "附条件", "有条件"],
}


def _normalize_label(label: str | None) -> str:
    """Normalize a decision label to English canonical form."""
    s = (label or "").strip().lower()
    if not s:
        return ""
    for canonical, aliases in _ACTION_ALIASES.items():
        if any(alias.lower() in s for alias in aliases):
            return canonical
    return s


def _entry_ids_from_rules(rules: list, valid_ids: set[str]) -> list[str]:
    """从 referenced_rules 中提取合法的 entry_id（KN-xxx）。"""
    ids = []
    for r in rules or []:
        for m in re.findall(r"KN-\d{3,}", str(r)):
            if m in valid_ids and m not in ids:
                ids.append(m)
    return ids


def build_feedback_prompt(mismatches: list[dict], ir: dict) -> tuple[str, str]:
    """构建「分歧 → entry 级修订建议」的 LLM prompt。"""
    entries_brief = []
    for e in (ir or {}).get("entries", []):
        fields = e.get("fields") or {}
        entries_brief.append({
            "entry_id": e.get("entry_id"),
            "知识描述": str(fields.get("知识描述", ""))[:120],
            "适用条件": str(fields.get("适用条件", ""))[:80],
            "例外情形": str(fields.get("例外情形", ""))[:80],
        })

    system_prompt = (
        "你是一位知识工程专家。决策回放发现知识库判断与专家结论存在分歧。\n"
        "请针对每条分歧，判断哪条知识条目（entry_id）需要修订，并生成结构化修订建议。\n\n"
        "规则：\n"
        "1. 只能引用提供的 entry_id；不确定关联哪条时可以建议新增（action=add）\n"
        "2. action 取值：modify（改写字段）| supplement（补充字段，常用于 例外情形/适用边界/经验判断）| add（新增条目）\n"
        "3. 优先用 supplement 补充「例外情形」或「适用边界」——分歧往往说明规则有未覆盖的边界\n"
        "4. 输出 JSON 数组，禁止任何前后说明文字：\n"
        '[{"entry_id": "KN-001", "field": "例外情形", "action": "supplement", '
        '"new_value": "补充内容", "note": "来自案例X的分歧分析"}]\n'
        "5. 每条分歧最多生成 2 条建议，建议总数不超过 10 条"
    )

    mismatch_text = ""
    for m in mismatches[:10]:
        mismatch_text += (
            f"\n---\n案例 {m.get('case_id', '?')}：\n"
            f"知识库判断：{m.get('prediction', '')}\n"
            f"专家结论：{m.get('expert_conclusion', '')}\n"
            f"推理过程：{str(m.get('reasoning', ''))[:300]}\n"
            f"引用规则：{', '.join(str(r) for r in m.get('referenced_rules', []))}\n"
        )

    user_prompt = (
        f"知识条目清单：\n{json.dumps(entries_brief, ensure_ascii=False)}\n\n"
        f"分歧清单：{mismatch_text}"
    )
    return system_prompt, user_prompt


def validation_to_revision_suggestions(
    mismatches: list[dict],
    ir: dict,
    llm_call_fn=None,
    *,
    model_name: str = "",
) -> list[dict]:
    """分歧 → entry 级修订建议（与 Step3 建议池同协议，by=validation）。

    优先 LLM 生成；LLM 不可用/解析失败时降级为程序化建议
    （对分歧引用的条目生成「例外情形」supplement 占位建议，由专家补全）。
    """
    if not mismatches:
        return []
    valid_ids = {str(e.get("entry_id")) for e in (ir or {}).get("entries", [])}

    suggestions: list[dict] = []
    if llm_call_fn:
        try:
            system_prompt, user_prompt = build_feedback_prompt(mismatches, ir)
            raw = llm_call_fn(system_prompt, user_prompt, model_name)
            m = re.search(r"\[[\s\S]*\]", raw or "")
            parsed = json.loads(m.group(0)) if m else []
            for s in parsed if isinstance(parsed, list) else []:
                if not isinstance(s, dict):
                    continue
                action = str(s.get("action", "")).strip().lower()
                entry_id = str(s.get("entry_id", "")).strip()
                if action in ("modify", "supplement") and entry_id not in valid_ids:
                    continue
                if action not in ("modify", "supplement", "add"):
                    continue
                suggestions.append({
                    "entry_id": entry_id if action != "add" else "",
                    "field": str(s.get("field", "")).strip(),
                    "action": action,
                    "new_value": str(s.get("new_value", "")).strip(),
                    "fields": s.get("fields") if isinstance(s.get("fields"), dict) else None,
                    "note": str(s.get("note", "")).strip() or "验证回放分歧建议",
                    "by": "validation",
                })
        except Exception:
            suggestions = []

    if not suggestions:
        # 程序化降级：对每条分歧引用的条目补「例外情形」占位
        seen = set()
        for m_item in mismatches[:10]:
            for eid in _entry_ids_from_rules(m_item.get("referenced_rules"), valid_ids):
                key = (eid, m_item.get("case_id"))
                if key in seen:
                    continue
                seen.add(key)
                suggestions.append({
                    "entry_id": eid,
                    "field": "例外情形",
                    "action": "supplement",
                    "new_value": (
                        f"[待专家确认] 案例 {m_item.get('case_id', '?')} 中专家结论为"
                        f"「{m_item.get('expert_conclusion', '')}」，与本规则推导结果"
                        f"「{m_item.get('prediction', '')}」不一致，可能存在未覆盖的例外情形"
                    ),
                    "note": "验证回放分歧（程序化生成，需专家补全）",
                    "by": "validation",
                })
    return suggestions[:10]


def generate_replay_report(result: dict, cases: list[dict], predictions: list[dict]) -> str:
    lines = [
        "# 显性化校验报告 · 决策回放",
        "",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- 案例数：{result['total_cases']}",
        f"- **命中率：{result['hit_rate'] * 100:.1f}%**（{result['hits']}/{result['total_cases']}）",
        f"- 分歧数：{result['mismatch_count']}",
        "",
        "## 不一致案例分析",
        "",
    ]
    if not result["mismatches"]:
        lines.append("> 所有案例判断与专家结论一致。")
        lines.append("")
    else:
        for i, m in enumerate(result["mismatches"]):
            lines.append(f"### 案例 {m['case_id']}")
            lines.append(f"- **LLM 预测**：{m['prediction']}")
            lines.append(f"- **专家结论**：{m['expert_conclusion']}")
            lines.append(f"- 推理过程：{m.get('reasoning', '')[:200]}")
            rules = m.get("referenced_rules", [])
            if rules:
                lines.append(f"- 引用的规则：{', '.join(rules)}")
            lines.append("")
            lines.append("> 建议：请检查上述规则是否需要更新或补充例外情形。")
            lines.append("")
    return "\n".join(lines)


# ─── Agent-Skill 验证知识库（新增）────────────────────────────────────

def _normalize_verification_output(raw: str) -> dict:
    """从 LLM 原始输出中尽量提取结构化结论。"""
    if not raw:
        return {"raw": "", "prediction": "", "reasoning": ""}
    text = raw.strip()
    # 优先提取 JSON 块
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        text = m.group(1).strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return {
                "raw": raw,
                "prediction": str(parsed.get("prediction") or parsed.get("结论") or parsed.get("result", "")).strip(),
                "reasoning": str(parsed.get("reasoning") or parsed.get("推理") or "").strip(),
            }
    except (json.JSONDecodeError, TypeError):
        pass
    # 退化：从文本中找「通过/拒绝/条件通过」。顺序很重要：
    # 先匹配更具体的「拒绝」「条件通过」，避免「条件通过」被「通过」前缀误吞。
    for keyword, label in [("拒绝", "拒绝"), ("条件通过", "条件通过"), ("通过", "通过")]:
        if keyword in text:
            return {"raw": raw, "prediction": label, "reasoning": text[:500]}
    return {"raw": raw, "prediction": "", "reasoning": text[:500]}


def build_agent_skill_verification_prompt(skill_text: str, case_input: dict) -> tuple[str, str]:
    """构建让 SKILL.md 作为判官的 system/user prompt。"""
    system_prompt = (
        "你是一份已发布的 Agent Skill（银行信贷领域）。请根据你的知识，对输入案例给出判断结论。\n"
        "输出要求：\n"
        "1. 先说明推理过程（引用知识中的规则）\n"
        "2. 最后给出明确结论：通过 / 拒绝 / 条件通过\n"
        "3. 尽量输出 JSON：{\"reasoning\": \"...\", \"prediction\": \"通过|拒绝|条件通过\"}"
    )
    user_prompt = (
        f"## 你的知识（SKILL）\n{skill_text[:8000]}\n\n"
        f"## 待判断案例\n{json.dumps(case_input, ensure_ascii=False, indent=2)}"
    )
    return system_prompt, user_prompt


def compare_verification_output(actual: dict, expected: dict) -> dict:
    """对比实际输出与期望输出，返回 diff 和 score。"""
    actual_pred = _normalize_label(actual.get("prediction", ""))
    expected_pred = _normalize_label(expected.get("prediction", expected.get("结论", "")))
    match = bool(actual_pred and expected_pred and actual_pred == expected_pred)
    score = 1.0 if match else 0.0
    diff = {
        "prediction_match": match,
        "actual_prediction": actual.get("prediction") or "",
        "expected_prediction": expected.get("prediction") or expected.get("结论") or "",
        "actual_reasoning": (actual.get("reasoning") or "")[:500],
        "expected_reasoning": (expected.get("reasoning") or "")[:500],
    }
    status = "pass" if match else "fail"
    return {"status": status, "score": score, "diff": diff}


def run_verification_case(
    case_record: dict,
    skill_text: str,
    model_cfg: dict,
    llm_call_fn=None,
) -> dict:
    """运行单个验证用例，返回结果字典（含 actual_output/diff/status/score）。"""
    case_input = case_record.get("input") or case_record.get("input_json") or {}
    expected_output = case_record.get("expected_output") or case_record.get("expected_output_json") or {}
    case_id = case_record.get("id") or case_record.get("case_uid", "")

    system_prompt, user_prompt = build_agent_skill_verification_prompt(skill_text, case_input)

    if llm_call_fn is None:
        from llm_client import call_llm_with_retry
        llm_call_fn = call_llm_with_retry

    try:
        result = llm_call_fn(
            model_cfg,
            [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            stream=False,
            temperature=0.1,
            max_tokens=4096,
        )
        raw = extract_assistant_content(result) if isinstance(result, dict) else str(result)
    except Exception as e:
        return {
            "case_id": case_id,
            "status": "error",
            "score": 0.0,
            "actual_output": {"error": str(e)},
            "diff": {"error": str(e)},
        }

    actual_output = _normalize_verification_output(raw or "")
    comparison = compare_verification_output(actual_output, expected_output)
    return {
        "case_id": case_id,
        "status": comparison["status"],
        "score": comparison["score"],
        "actual_output": actual_output,
        "diff": comparison["diff"],
    }


def run_verification_suite(
    cases: list[dict],
    skill_text: str,
    model_cfg: dict,
    llm_call_fn=None,
) -> list[dict]:
    """批量运行验证用例。"""
    results = []
    for case in cases:
        try:
            result = run_verification_case(case, skill_text, model_cfg, llm_call_fn=llm_call_fn)
        except Exception as e:
            result = {
                "case_id": case.get("id") or case.get("case_uid", ""),
                "status": "error",
                "score": 0.0,
                "actual_output": {"error": str(e)},
                "diff": {"error": str(e)},
            }
        results.append(result)
    return results


def generate_verification_report(run_records: list[dict]) -> dict:
    """生成验证报告（结构化的命中率和偏差项）。"""
    total = len(run_records)
    if not total:
        return {"total": 0, "pass": 0, "fail": 0, "partial": 0, "pass_rate": 0.0, "mismatches": []}
    pass_count = sum(1 for r in run_records if r.get("status") == "pass")
    fail_count = sum(1 for r in run_records if r.get("status") == "fail")
    partial_count = sum(1 for r in run_records if r.get("status") == "partial")
    pass_rate = round(pass_count / total, 3)
    mismatches = [r for r in run_records if r.get("status") != "pass"]

    suggestions = []
    for r in mismatches:
        diff = r.get("diff") or {}
        suggestions.append({
            "case_id": r.get("case_id", ""),
            "entry_id": "",
            "field": "例外情形",
            "action": "supplement",
            "new_value": (
                f"[待专家确认] 用例 {r.get('case_id', '?')} 期望结论为"
                f"「{diff.get('expected_prediction', '')}」，实际结论为"
                f"「{diff.get('actual_prediction', '')}」，可能存在未覆盖的边界。"
            ),
            "note": "本地知识库验证（程序化生成，需专家补全）",
            "by": "verification",
        })

    return {
        "total": total,
        "pass": pass_count,
        "fail": fail_count,
        "partial": partial_count,
        "pass_rate": pass_rate,
        "mismatches": mismatches,
        "suggestions": suggestions[:10],
    }


def verification_report_to_markdown(report: dict) -> str:
    """将验证报告渲染为 Markdown。"""
    lines = [
        "# Agent-Skill 本地知识库验证报告",
        "",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- 用例总数：{report['total']}",
        f"- **通过率：{report['pass_rate'] * 100:.1f}%**（{report['pass']}/{report['total']}）",
        f"- 失败：{report['fail']}，部分通过：{report['partial']}",
        "",
        "## 不一致用例",
        "",
    ]
    if not report["mismatches"]:
        lines.append("> 所有用例均通过。")
        lines.append("")
    else:
        for m in report["mismatches"]:
            diff = m.get("diff") or {}
            lines.append(f"### 用例 {m.get('case_id', '?')}")
            lines.append(f"- **实际结论**：{diff.get('actual_prediction', '')}")
            lines.append(f"- **期望结论**：{diff.get('expected_prediction', '')}")
            lines.append(f"- 推理：{diff.get('actual_reasoning', '')[:200]}")
            lines.append("")
    return "\n".join(lines)

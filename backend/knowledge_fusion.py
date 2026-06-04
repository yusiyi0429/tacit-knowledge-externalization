"""
多源知识融合模块（Step1.5）
将多份文档/访谈记录的结构化提取结果合并、去重、冲突检测、交叉验证。

用法(后端):
  from knowledge_fusion import fuse_extraction_results
  merged = fuse_extraction_results([result_a, result_b, ...])
"""

from __future__ import annotations

import json
import logging
import re

_logger = logging.getLogger("tacit_knowledge")

# ── 相似度阈值 ──
DUPLICATE_SIMILARITY_THRESHOLD = 0.65  # 高于此值视为重复
CONFLICT_KEYWORDS = ("不可以", "不能", "禁止", "必须", "绝不", "只能", "不得超过")


def _normalize_text(text: str) -> str:
    """归一化文本用于相似度比较。"""
    if not text:
        return ""
    t = text.strip().lower()
    t = re.sub(r"[，。、；：！？“”（）【】\s]+", " ", t)
    return t


def _word_overlap(a: str, b: str) -> float:
    """基于词重叠率的相似度。"""
    if not a or not b:
        return 0.0
    set_a = set(_normalize_text(a).split())
    set_b = set(_normalize_text(b).split())
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    # Jaccard-like but penalize large size mismatches
    overlap = len(intersection) / min(len(set_a), len(set_b))
    return overlap


def _get_knowledge_text(record: dict) -> str:
    """从记录中提取主要知识描述文本。"""
    for key in ("知识描述", "具体方法", "可执行知识", "content", "description", "text"):
        val = record.get(key, "")
        if val and isinstance(val, str):
            return val
    return ""


def detect_duplicates(records: list[dict]) -> list[dict]:
    """检测重复知识条目，返回重复组列表。

    返回: [{ "indices": [0, 3], "texts": ["...", "..."], "similarity": 0.85 }]
    """
    dup_groups = []
    seen = set()
    for i in range(len(records)):
        if i in seen:
            continue
        text_i = _get_knowledge_text(records[i])
        if not text_i:
            continue
        group_indices = [i]
        for j in range(i + 1, len(records)):
            if j in seen:
                continue
            text_j = _get_knowledge_text(records[j])
            sim = _word_overlap(text_i, text_j)
            if sim >= DUPLICATE_SIMILARITY_THRESHOLD:
                group_indices.append(j)
                seen.add(j)
        if len(group_indices) > 1:
            dup_groups.append({
                "indices": group_indices,
                "texts": [records[idx].get("知识描述", records[idx].get("具体方法", "")) for idx in group_indices],
                "similarity": round(_word_overlap(
                    _get_knowledge_text(records[group_indices[0]]),
                    _get_knowledge_text(records[group_indices[1]]),
                ), 2),
                "sources": list(set(
                    records[idx].get("来源", records[idx].get("source_label", "未知"))
                    for idx in group_indices
                )),
            })
            seen.add(i)
    return dup_groups


def detect_conflicts(records: list[dict]) -> list[dict]:
    """检测冲突知识条目（对同一事物有相反判断）。

    返回: [{ "indices": [2, 5], "text_a": "...", "text_b": "...", "reason": "对立判断" }]
    """
    conflicts = []
    # 按分类分组后两两比较
    from collections import defaultdict
    by_category = defaultdict(list)
    for i, rec in enumerate(records):
        cat = rec.get("知识分类", rec.get("category", "未分类"))
        by_category[cat].append(i)

    for cat, indices in by_category.items():
        for a_i in range(len(indices)):
            for b_i in range(a_i + 1, len(indices)):
                idx_a, idx_b = indices[a_i], indices[b_i]
                text_a = _get_knowledge_text(records[idx_a])
                text_b = _get_knowledge_text(records[idx_b])
                if not text_a or not text_b:
                    continue
                # 检查是否一个说"必须X"一个说"不能X"
                judge_a = records[idx_a].get("判断逻辑", "")
                judge_b = records[idx_b].get("判断逻辑", "")
                if judge_a and judge_b:
                    has_neg_a = any(kw in judge_a for kw in CONFLICT_KEYWORDS)
                    has_neg_b = any(kw in judge_b for kw in CONFLICT_KEYWORDS)
                    # 如果一条有否定词一条没有，且文本相似，可能冲突
                    if has_neg_a != has_neg_b and _word_overlap(text_a, text_b) > 0.4:
                        conflicts.append({
                            "indices": [idx_a, idx_b],
                            "text_a": text_a,
                            "text_b": text_b,
                            "judge_a": judge_a,
                            "judge_b": judge_b,
                            "reason": f"「{cat}」分类中存在对立判断",
                            "source_a": records[idx_a].get("来源", records[idx_a].get("source_label", "未知")),
                            "source_b": records[idx_b].get("来源", records[idx_b].get("source_label", "未知")),
                        })
    return conflicts


def detect_ambiguous_boundaries(records: list[dict]) -> list[dict]:
    """检测适用条件为空或模糊的条目，返回边界模糊信号列表。

    返回: [{ "index": int, "record": dict, "reason": str }]
    """
    VAGUE_PATTERNS = ("无", "不详", "未知", "暂无", "不明确", "视情况", "看情况", "不一定", "")
    results = []
    for i, rec in enumerate(records):
        cond = str(rec.get("适用条件", "")).strip()
        if not cond or cond in VAGUE_PATTERNS:
            results.append({
                "index": i,
                "record": rec,
                "reason": "适用条件为空或模糊" if not cond else f"适用条件模糊：{cond}",
            })
    return results


def detect_isolated_items(records: list[dict]) -> list[dict]:
    """检测与其他条目无显著相似度的孤岛知识。

    使用 _word_overlap 计算，最大相似度低于 0.3 视为孤岛。
    返回: [{ "index": int, "record": dict, "max_similarity": float }]
    """
    if len(records) <= 1:
        return []
    results = []
    for i, rec in enumerate(records):
        text_i = _get_knowledge_text(rec)
        if not text_i:
            continue
        max_sim = 0.0
        for j, other in enumerate(records):
            if i == j:
                continue
            text_j = _get_knowledge_text(other)
            sim = _word_overlap(text_i, text_j)
            if sim > max_sim:
                max_sim = sim
        if max_sim < 0.3:
            results.append({
                "index": i,
                "record": rec,
                "max_similarity": round(max_sim, 2),
            })
    return results


def detect_source_consensus(records: list[dict]) -> list[dict]:
    """按 source_label 分组统计每条知识出现在几个来源中。

    源共识度 = 出现次数 / 总来源数。
    返回: [{ "index": int, "record": dict, "source_count": int, "consensus_score": float }]
    """
    source_labels = list(set(r.get("source_label", "未知") for r in records))
    total_sources = len(source_labels)
    if total_sources == 0:
        return []

    results = []
    for i, rec in enumerate(records):
        text_i = _get_knowledge_text(rec)
        if not text_i:
            results.append({
                "index": i, "record": rec,
                "source_count": 1, "consensus_score": round(1.0 / total_sources, 2),
            })
            continue
        own_label = rec.get("source_label", "未知")
        similar_sources = {own_label}
        for j, other in enumerate(records):
            if i == j:
                continue
            other_label = other.get("source_label", "未知")
            if other_label in similar_sources:
                continue
            text_j = _get_knowledge_text(other)
            if _word_overlap(text_i, text_j) >= 0.4:
                similar_sources.add(other_label)
        source_count = len(similar_sources)
        consensus_score = round(source_count / total_sources, 2)
        results.append({
            "index": i,
            "record": rec,
            "source_count": source_count,
            "consensus_score": consensus_score,
        })
    return results


def aggregate_signals(
    records: list[dict],
    duplicates: list[dict],
    conflicts: list[dict],
) -> dict:
    """汇总所有信号（重复、冲突、边界模糊、孤岛、源共识），生成结构化信号报告。

    返回: {
        "signals": [{type, severity, title, detail, record_index, suggested_action}],
        "summary": {total_signals, by_type: {...}},
    }
    """
    boundary_blurs = detect_ambiguous_boundaries(records)
    islands = detect_isolated_items(records)
    consensus_results = detect_source_consensus(records)

    total_sources = len(set(r.get("source_label", "未知") for r in records))

    signals = []

    # 重复信号（高严重度）
    for dg in duplicates:
        primary = dg["indices"][0]
        for idx in dg["indices"]:
            signals.append({
                "type": "duplicate",
                "severity": "high",
                "title": f"与条目 #{primary + 1} 高度相似",
                "detail": f"相似度 {dg.get('similarity', 0):.0%}，来源：{', '.join(dg.get('sources', []))}",
                "record_index": idx,
                "suggested_action": "保留一条代表性条目或合并描述",
            })

    # 冲突信号（高严重度）
    for cf in conflicts:
        for idx in cf["indices"]:
            other_idx = cf["indices"][0] if cf["indices"][0] != idx else cf["indices"][1]
            signals.append({
                "type": "conflict",
                "severity": "high",
                "title": f"与条目 #{other_idx + 1} 存在冲突",
                "detail": cf.get("reason", "存在对立判断"),
                "record_index": idx,
                "suggested_action": "需人工裁决或标注适用范围差异",
            })

    # 边界模糊信号（中严重度）
    for bb in boundary_blurs:
        signals.append({
            "type": "boundary_blur",
            "severity": "medium",
            "title": "适用条件不明确",
            "detail": bb["reason"],
            "record_index": bb["index"],
            "suggested_action": "补充适用条件或标注适用边界",
        })

    # 孤岛信号（低严重度）
    for isl in islands:
        signals.append({
            "type": "island",
            "severity": "low",
            "title": f"孤岛知识（最高相似度 {isl['max_similarity']:.0%}）",
            "detail": "与其他知识条目无显著语义关联",
            "record_index": isl["index"],
            "suggested_action": "确认该知识是否有效，或与其他条目建立关联",
        })

    # 源共识信号（共识度低则中严重度，中等则低严重度）
    for cr in consensus_results:
        if cr["consensus_score"] < 0.5:
            severity = "medium" if cr["consensus_score"] < 0.3 else "low"
            signals.append({
                "type": "consensus",
                "severity": severity,
                "title": f"源共识度低（{cr['consensus_score']:.0%}，{cr['source_count']}/{total_sources} 来源）",
                "detail": "多源未交叉验证，可信度待确认" if cr["source_count"] <= 1 else "仅部分来源覆盖",
                "record_index": cr["index"],
                "suggested_action": "寻求额外来源验证或标注为专家个人经验",
            })

    # 按类型汇总
    by_type = {}
    for s in signals:
        by_type[s["type"]] = by_type.get(s["type"], 0) + 1

    return {
        "signals": signals,
        "summary": {
            "total_signals": len(signals),
            "by_type": by_type,
        },
    }


def merge_extraction_results(results: list[dict]) -> dict:
    """合并多个提取结果（每个 result 是 {records: [...], source_label: "..."}）。

    返回: {
        "records": [...],           # 所有不重复的记录
        "duplicates": [...],        # 重复组
        "conflicts": [...],         # 冲突组
        "source_stats": {...},      # 每个来源的条目数
        "total_raw": N,
        "total_deduped": N,
        "confidence_distribution": {...},
        "signal_report": {...},     # 信号报告（含 duplicate/conflict/boundary_blur/island/consensus）
    }
    """
    all_records = []
    source_stats = {}
    for res in results:
        records = res.get("records", res.get("items", []))
        label = res.get("source_label", res.get("label", "未知"))
        if not records:
            continue
        for rec in records:
            rec_copy = dict(rec)
            rec_copy["source_label"] = label
            all_records.append(rec_copy)
        source_stats[label] = len(records)

    total_raw = len(all_records)

    # 去重标记（不直接删除，交给人工确认）
    dup_groups = detect_duplicates(all_records)
    dup_indices = set()
    for group in dup_groups:
        # 保留第一条，其余标记为重复
        for idx in group["indices"][1:]:
            dup_indices.add(idx)
            all_records[idx]["_duplicate"] = True
            all_records[idx]["_duplicate_of"] = group["indices"][0]

    # 冲突检测
    conflict_groups = detect_conflicts(all_records)
    for conflict in conflict_groups:
        for idx in conflict["indices"]:
            all_records[idx]["_conflict"] = True
            all_records[idx]["_conflict_with"] = [
                i for i in conflict["indices"] if i != idx
            ]

    # 过滤掉标记为重复的（仅保留非重复 + 重复组的第一条）
    deduped = [r for i, r in enumerate(all_records) if i not in dup_indices]

    # 置信度分布
    conf_dist = {"高": 0, "中": 0, "低": 0}
    for rec in deduped:
        conf = rec.get("置信度", rec.get("confidence", ""))
        if conf in conf_dist:
            conf_dist[conf] += 1

    # 生成信号报告（基于全量 all_records，保留重复/冲突等信号供人工审核）
    signal_report = aggregate_signals(all_records, dup_groups, conflict_groups)

    return {
        "records": deduped,
        "all_raw": all_records,
        "duplicates": dup_groups,
        "conflicts": conflict_groups,
        "source_stats": source_stats,
        "stats": {
            "total_raw": total_raw,
            "total_deduped": len(deduped),
            "duplicate_count": len(dup_indices),
            "conflict_count": len(conflict_groups),
        },
        "confidence_distribution": conf_dist,
        "signal_report": signal_report,
    }


def fuse_sources(
    records_list: list[list[dict]],
    source_labels: list[str] | None = None,
) -> dict:
    """便捷函数：直接传入多个 records 列表，自动标注来源后合并。"""
    if source_labels is None:
        source_labels = [f"来源{i+1}" for i in range(len(records_list))]
    results = [
        {"records": recs, "source_label": label}
        for recs, label in zip(records_list, source_labels)
    ]
    return merge_extraction_results(results)


def interview_answers_to_records(
    answers: list[dict],
    source_label: str = "访谈记录",
) -> list[dict]:
    """将访谈问答对转换为标准知识条目格式。

    输入: [{ "question": "...", "answer": "...", "category": "经验判断|适用边界|例外情形" }]
    输出: [{ "知识描述": "...", "适用条件": "...", "知识分类": "经验判断", ... }]
    """
    records = []
    for i, qa in enumerate(answers):
        question = qa.get("question", "").strip()
        answer = qa.get("answer", "").strip()
        category = qa.get("category", "经验判断").strip()
        if not answer:
            continue
        record = {
            "知识描述": answer,
            "适用条件": _extract_condition_from_qa(question, answer),
            "知识分类": _map_interview_category(category),
            "知识类型": "经验判断",
            "来源": source_label,
            "置信度": "中",
            "贡献专家": qa.get("expert", ""),
            "来源文档": f"访谈追问：{question[:50]}",
            "_interview_source": True,
        }
        records.append(record)
    return records


def _extract_condition_from_qa(question: str, answer: str) -> str:
    """从问答中尝试提取适用条件。"""
    # 尝试从问题中提取条件关键词
    patterns = [
        r"(当[^？，,。]*适用)",
        r"(如果[^？，,。]*)",
        r"([^？，,。]*情况下)",
    ]
    for pat in patterns:
        m = re.search(pat, question)
        if m:
            return m.group(1).strip()
    return ""


def _map_interview_category(category: str) -> str:
    """将访谈分类映射到知识分类。"""
    mapping = {
        "经验判断": "经验判断",
        "适用边界": "适用边界",
        "例外情形": "例外情形",
        "反模式": "反模式",
    }
    return mapping.get(category, "经验判断")

#!/usr/bin/env python3
"""
Skill IR（中间表示）— Skill 中心化流水线的单一事实源（SSOT）

流水线产物链：
  Step2 萃取 → skill_draft v1 (status=draft)
  Step3 对齐 → skill_draft vN (status=aligned)
  Step4 转化 → SKILL.md 终版 (status=published)
  Step5 验证 → 分歧生成 entry 级修订建议，回流 Step3

设计约束：
- LLM 永远不直接产 IR 整体；IR 由程序从 records 组装（六层降级解析之后）。
- SKILL.md 永远是渲染产物，由 render_skill_md() 确定性生成。
- 修订寻址协议：{entry_id, field, action, old_value, new_value, note, by}
"""

from __future__ import annotations

import copy
import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path

from pipeline_artifacts import workspace_path_for

IR_VERSION = "1.0"
IR_VERSION_V2 = "2.0"

VALID_STEP_PHASES = ("客户筛选", "客户数据匹配", "原因归因", "决策建议")

_VALID_CONFIDENCE = ("high", "medium", "low")

# IR 状态生命周期
STATUS_DRAFT = "draft"
STATUS_ALIGNED = "aligned"
STATUS_PUBLISHED = "published"
VALID_STATUSES = (STATUS_DRAFT, STATUS_ALIGNED, STATUS_PUBLISHED)

# 修订动作（与 revision_processor 语义平移）
REVISION_ACTIONS = ("modify", "supplement", "delete", "delete_entry", "add")

# record 中的结构性键（进入 entry 顶层而非 fields）
_STRUCTURAL_KEYS = ("场景", "场景说明", "子场景", "子场景说明", "知识编号", "知识分类")

# record 中的内部键（不入 fields）
_INTERNAL_KEY_PREFIX = "_"

ENTRY_ID_PATTERN = re.compile(r"^KN-\d{3,}$")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _norm(val) -> str:
    if val is None:
        return ""
    return str(val).strip()


# ─── 构建 ────────────────────────────────────────────────────────

def _record_to_entry(record: dict, entry_id: str, origin: str, source_label: str = "") -> dict:
    """单条 record → IR entry。结构键提升到顶层，其余进 fields。"""
    fields = {}
    flags = {"duplicate_of": None, "conflict_with": [], "needs_interview": False}
    label = source_label
    for key, val in (record or {}).items():
        k = _norm(key)
        if not k or k.startswith(_INTERNAL_KEY_PREFIX):
            continue
        if k in _STRUCTURAL_KEYS:
            continue
        if k == "source_label":
            label = _norm(val) or label
            continue
        fields[k] = _norm(val)
    # 融合标记升级为正式 flags
    if record.get("_duplicate"):
        flags["duplicate_of"] = _norm(record.get("_duplicate_of")) or "unknown"
    if record.get("_conflict"):
        cw = record.get("_conflict_with")
        flags["conflict_with"] = cw if isinstance(cw, list) else ([_norm(cw)] if cw else ["unknown"])
    return {
        "entry_id": entry_id,
        "sub_scenario": _norm(record.get("子场景")),
        "category": _norm(record.get("知识分类")),
        "fields": fields,
        "lifecycle": {
            "origin": origin,
            "source_label": label or _norm(record.get("来源标注")) or _norm(record.get("来源")),
            "kb_entry_id": _norm(record.get("kb_entry_id")) or None,
            "revisions": [],
        },
        "flags": flags,
    }


def _next_entry_id(entries: list[dict]) -> str:
    max_n = 0
    for e in entries or []:
        m = re.match(r"^KN-(\d+)$", _norm(e.get("entry_id")))
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"KN-{max_n + 1:03d}"


def new_draft(
    scenario_meta: dict,
    records: list[dict],
    *,
    signals: dict | None = None,
    origin: str = "doc_extract",
    pipeline_id: str = "",
) -> dict:
    """从萃取 records 组装 Skill IR v1（status=draft）。"""
    meta = scenario_meta or {}
    sub_list = []
    for sub in meta.get("sub_scenarios") or []:
        if not isinstance(sub, dict):
            continue
        name = _norm(sub.get("name"))
        desc = _norm(sub.get("content") or sub.get("desc"))
        if name or desc:
            sub_list.append({"name": name, "desc": desc})

    entries = []
    for i, rec in enumerate(records or []):
        if not isinstance(rec, dict):
            continue
        explicit = _norm(rec.get("知识编号"))
        entry_id = explicit if ENTRY_ID_PATTERN.match(explicit) else f"KN-{i + 1:03d}"
        rec_origin = _norm(rec.get("_origin")) or origin
        entries.append(_record_to_entry(rec, entry_id, rec_origin, _norm(rec.get("source_label"))))

    # entry_id 去重（显式编号可能冲突）
    seen = set()
    for e in entries:
        if e["entry_id"] in seen:
            e["entry_id"] = _next_entry_id(entries)
        seen.add(e["entry_id"])

    now = _now()
    return {
        "ir_version": IR_VERSION,
        "skill_meta": {
            "scenario_name": _norm(meta.get("scenario_name")),
            "display_name": _norm(meta.get("display_name")) or _norm(meta.get("scenario_name")),
            "domain": _norm(meta.get("domain")) or "通用",
            "slug": _norm(meta.get("slug")),
            "pipeline_id": pipeline_id,
            "draft_version": 1,
            "status": STATUS_DRAFT,
            "parent_version": 0,
            "created_at": now,
            "updated_at": now,
        },
        "anchors": {
            "scenario": _norm(meta.get("scenario_name")),
            "scenario_desc": _norm(meta.get("scenario_content") or meta.get("scenario_desc")),
            "sub_scenarios": sub_list,
        },
        "entries": entries,
        "signals": signals or {},
        "revision_log": [],
    }


def new_draft_v2(
    scenario_meta: dict,
    entries: list[dict],
    *,
    origin: str = "doc_extract",
    pipeline_id: str = "",
) -> dict:
    """从 Step2a/2b 萃取 entries 组装 Skill IR v2。"""
    meta = scenario_meta or {}
    sub_list = []
    for sub in meta.get("sub_scenarios") or []:
        if not isinstance(sub, dict):
            continue
        name = _norm(sub.get("name"))
        desc = _norm(sub.get("content") or sub.get("desc"))
        if name or desc:
            sub_list.append({"name": name, "desc": desc})

    normalized_entries = []
    for i, entry in enumerate(entries or []):
        if not isinstance(entry, dict):
            continue
        explicit = _norm(entry.get("entry_id"))
        entry_id = explicit if ENTRY_ID_PATTERN.match(explicit) else f"KN-{i + 1:03d}"
        fields = entry.get("fields")
        if not isinstance(fields, dict):
            fields = {}
        data_logic = fields.get("data_logic")
        if isinstance(data_logic, dict):
            confidence = data_logic.get("confidence")
            data_logic = {
                "sql": _norm(data_logic.get("sql")),
                "tables": [str(v) for v in (data_logic.get("tables") or []) if v is not None],
                "fields": [str(v) for v in (data_logic.get("fields") or []) if v is not None],
            }
            if confidence:
                data_logic["confidence"] = confidence
        else:
            data_logic = {"sql": ""}
        normalized_entries.append({
            "entry_id": entry_id,
            "sub_scenario": _norm(entry.get("sub_scenario")),
            "step_phase": _norm(entry.get("step_phase")),
            "fields": {
                "knowledge_desc": _norm(fields.get("knowledge_desc")),
                "knowledge_ref": _norm(fields.get("knowledge_ref")),
                "rule_ref": _norm(fields.get("rule_ref")),
                "exception": _norm(fields.get("exception")),
                "output": _norm(fields.get("output")),
                "data_logic": data_logic,
            },
            "lifecycle": {
                "origin": _norm(entry.get("origin")) or origin,
                "source_label": _norm(entry.get("source_label")),
                "revisions": [],
            },
            "flags": {
                "sql_manually_edited": False,
                "sql_history": [],
            },
        })

    # entry_id 去重（显式编号可能冲突）
    seen = set()
    for e in normalized_entries:
        if e["entry_id"] in seen:
            e["entry_id"] = _next_entry_id(normalized_entries)
        seen.add(e["entry_id"])

    now = _now()
    return {
        "ir_version": IR_VERSION_V2,
        "skill_meta": {
            "scenario_name": _norm(meta.get("scenario_name")),
            "display_name": _norm(meta.get("display_name")) or _norm(meta.get("scenario_name")),
            "domain": _norm(meta.get("domain")) or "通用",
            "slug": _norm(meta.get("slug")),
            "pipeline_id": pipeline_id,
            "draft_version": 1,
            "status": STATUS_DRAFT,
            "parent_version": 0,
            "created_at": now,
            "updated_at": now,
        },
        "anchors": {
            "scenario": _norm(meta.get("scenario_name")),
            "scenario_desc": _norm(meta.get("scenario_content") or meta.get("scenario_desc")),
            "sub_scenarios": sub_list,
        },
        "entries": normalized_entries,
        "signals": {},
        "revision_log": [],
    }


def new_draft_from_workbook(
    excel_path: str,
    pipeline_ctx: dict | None = None,
    *,
    origin: str = "doc_extract",
    pipeline_id: str = "",
) -> dict:
    """从知识工作簿（preextract/final Excel）重建 IR（过渡期 Excel ⇄ IR 投影）。"""
    from excel_to_skill import read_excel_knowledge

    records, version_info = read_excel_knowledge(excel_path, pipeline_ctx)
    anchor = version_info.get("scenario_anchor") or {}
    meta = {
        "scenario_name": anchor.get("场景名称") or anchor.get("scenario_name") or "",
        "scenario_content": anchor.get("场景说明") or anchor.get("scenario_content") or "",
        "sub_scenarios": anchor.get("sub_scenarios") or [],
        "domain": (pipeline_ctx or {}).get("domain", ""),
    }
    return new_draft(meta, records, origin=origin, pipeline_id=pipeline_id)


# ─── 转换 ────────────────────────────────────────────────────────

def ir_to_records(ir: dict) -> list[dict]:
    """IR entries → records（喂给 generate_skill_md / delivery / quality 的统一格式）。"""
    anchors = (ir or {}).get("anchors") or {}
    sub_desc_map = {
        _norm(s.get("name")): _norm(s.get("desc"))
        for s in anchors.get("sub_scenarios") or []
        if _norm(s.get("name"))
    }
    records = []
    for entry in (ir or {}).get("entries") or []:
        sub = _norm(entry.get("sub_scenario"))
        rec = {
            "知识编号": _norm(entry.get("entry_id")),
            "知识分类": _norm(entry.get("category")),
            "子场景": sub,
            "场景": _norm(anchors.get("scenario")),
            "场景说明": _norm(anchors.get("scenario_desc")),
            "子场景说明": sub_desc_map.get(sub, ""),
        }
        for k, v in (entry.get("fields") or {}).items():
            rec[k] = v
        records.append(rec)
    return records


def ir_version_info(ir: dict) -> dict:
    """构造 generate_skill_md / delivery 需要的 version_info。"""
    meta = (ir or {}).get("skill_meta") or {}
    anchors = (ir or {}).get("anchors") or {}
    sub_scenarios = [
        {"name": _norm(s.get("name")), "content": _norm(s.get("desc"))}
        for s in anchors.get("sub_scenarios") or []
    ]
    return {
        "scenario_anchor": {
            "scenario_name": _norm(anchors.get("scenario")) or _norm(meta.get("scenario_name")),
            "场景名称": _norm(anchors.get("scenario")) or _norm(meta.get("scenario_name")),
            "scenario_content": _norm(anchors.get("scenario_desc")),
            "场景说明": _norm(anchors.get("scenario_desc")),
            "sub_scenarios": sub_scenarios,
            "slug": _norm(meta.get("slug")),
        },
        "场景名称": _norm(meta.get("scenario_name")),
        "模板版本": f"v{meta.get('draft_version', 1)}",
        "业务领域": _norm(meta.get("domain")) or "通用",
    }


def render_skill_md(ir: dict, config: dict | None = None) -> str:
    """确定性渲染 SKILL.md（IR → md，禁止反向手改 md）。"""
    from excel_to_skill import generate_skill_md, group_by_category

    records = ir_to_records(ir)
    groups = group_by_category(records)
    meta = (ir or {}).get("skill_meta") or {}
    scenario_name = _norm(meta.get("scenario_name")) or "未命名场景"
    return generate_skill_md(records, groups, config or {}, scenario_name, ir_version_info(ir))


# ─── 修订 ────────────────────────────────────────────────────────

def normalize_suggestion(raw: dict, by: str = "expert") -> dict | None:
    """归一化一条 entry 级修订建议；非法返回 None。"""
    if not isinstance(raw, dict):
        return None
    action = _norm(raw.get("action")).lower()
    alias = {
        "修改": "modify", "补充": "supplement", "删除": "delete",
        "删除条目": "delete_entry", "新增": "add", "delete_row": "delete_entry",
    }
    action = alias.get(action, action)
    if action not in REVISION_ACTIONS:
        return None
    entry_id = _norm(raw.get("entry_id"))
    if action != "add" and not entry_id:
        return None
    return {
        "entry_id": entry_id,
        "field": _norm(raw.get("field")),
        "action": action,
        "old_value": _norm(raw.get("old_value")),
        "new_value": _norm(raw.get("new_value")),
        "note": _norm(raw.get("note")),
        "by": _norm(raw.get("by")) or by,
    }


def apply_revisions(
    ir: dict,
    revisions: list[dict],
    *,
    by: str = "expert",
    new_status: str = STATUS_ALIGNED,
) -> tuple[dict, int]:
    """应用 entry 级修订，产出 version+1 的新 IR。

    返回 (new_ir, applied_count)。非法修订条目被跳过（不抛异常）。
    """
    new_ir = copy.deepcopy(ir or {})
    meta = new_ir.setdefault("skill_meta", {})
    entries = new_ir.setdefault("entries", [])
    old_version = int(meta.get("draft_version", 1) or 1)
    new_version = old_version + 1
    now = _now()
    applied = 0

    index = {_norm(e.get("entry_id")): e for e in entries}
    # 已用编号（含本轮删除的）：删除的 entry_id 不得被 add 复用，保证可追溯
    used_ids = set(index.keys())

    def _next_unused_id() -> str:
        max_n = 0
        for eid in used_ids:
            m = re.match(r"^KN-(\d+)$", eid)
            if m:
                max_n = max(max_n, int(m.group(1)))
        return f"KN-{max_n + 1:03d}"

    def _log_entry_revision(entry: dict, rev: dict, old: str):
        entry.setdefault("lifecycle", {}).setdefault("revisions", []).append({
            "version": new_version,
            "action": rev["action"],
            "field": rev["field"],
            "old": old,
            "new": rev["new_value"],
            "by": rev["by"],
            "note": rev["note"],
            "at": now,
        })

    for raw in revisions or []:
        rev = normalize_suggestion(raw, by=by)
        if not rev:
            continue
        action = rev["action"]

        if action == "add":
            new_record = raw.get("fields") if isinstance(raw.get("fields"), dict) else {}
            if not new_record and rev["new_value"]:
                new_record = {"知识描述": rev["new_value"]}
            if not new_record:
                continue
            entry_id = rev["entry_id"] if ENTRY_ID_PATTERN.match(rev["entry_id"]) else _next_unused_id()
            if entry_id in used_ids:
                entry_id = _next_unused_id()
            used_ids.add(entry_id)
            entry = _record_to_entry(new_record, entry_id, origin=f"revision_{rev['by']}")
            if _norm(raw.get("sub_scenario")):
                entry["sub_scenario"] = _norm(raw.get("sub_scenario"))
            if _norm(raw.get("category")):
                entry["category"] = _norm(raw.get("category"))
            _log_entry_revision(entry, rev, "")
            entries.append(entry)
            index[entry_id] = entry
            applied += 1
            continue

        entry = index.get(rev["entry_id"])
        if entry is None:
            continue

        if action == "delete_entry":
            _log_entry_revision(entry, rev, json.dumps(entry.get("fields", {}), ensure_ascii=False)[:200])
            entries.remove(entry)
            index.pop(rev["entry_id"], None)
            applied += 1
            continue

        field = rev["field"]
        if not field:
            continue
        fields = entry.setdefault("fields", {})
        if field == "知识分类":
            old = _norm(entry.get("category"))
        elif field == "子场景":
            old = _norm(entry.get("sub_scenario"))
        else:
            old = _norm(fields.get(field))

        if action == "modify":
            new_val = rev["new_value"]
        elif action == "supplement":
            new_val = f"{old}\n{rev['new_value']}".strip() if old else rev["new_value"]
        elif action == "delete":
            new_val = ""
        else:
            continue

        if field == "知识分类":
            entry["category"] = new_val
        elif field == "子场景":
            entry["sub_scenario"] = new_val
        else:
            fields[field] = new_val
        _log_entry_revision(entry, rev, old)
        applied += 1

    meta["draft_version"] = new_version
    meta["parent_version"] = old_version
    meta["status"] = new_status if new_status in VALID_STATUSES else STATUS_ALIGNED
    meta["updated_at"] = now
    new_ir.setdefault("revision_log", []).append({
        "version": new_version,
        "by": by,
        "applied": applied,
        "submitted": len(revisions or []),
        "at": now,
    })
    return new_ir, applied


def mark_status(ir: dict, status: str) -> dict:
    """仅切换状态（不 bump 版本），用于直通确认 / 发布标记。"""
    new_ir = copy.deepcopy(ir or {})
    meta = new_ir.setdefault("skill_meta", {})
    if status in VALID_STATUSES:
        meta["status"] = status
        meta["updated_at"] = _now()
    return new_ir


# ─── 校验 / 对比 ──────────────────────────────────────────────────

def validate_ir(ir: dict) -> list[str]:
    """结构校验；返回错误列表（空列表 = 合法）。"""
    errors = []
    if not isinstance(ir, dict):
        return ["IR 必须是 JSON 对象"]
    meta = ir.get("skill_meta")
    if not isinstance(meta, dict):
        errors.append("缺少 skill_meta")
        meta = {}
    version = meta.get("draft_version")
    if not isinstance(version, int) or version < 1:
        errors.append(f"draft_version 非法: {version!r}")
    parent = meta.get("parent_version", 0)
    if isinstance(version, int) and isinstance(parent, int) and parent >= version:
        errors.append(f"parent_version({parent}) 必须小于 draft_version({version})")
    status = meta.get("status")
    if status not in VALID_STATUSES:
        errors.append(f"status 非法: {status!r}")
    entries = ir.get("entries")
    if not isinstance(entries, list):
        errors.append("entries 必须是数组")
        entries = []
    seen = set()
    for i, e in enumerate(entries):
        if not isinstance(e, dict):
            errors.append(f"entries[{i}] 必须是对象")
            continue
        eid = _norm(e.get("entry_id"))
        if not eid:
            errors.append(f"entries[{i}] 缺少 entry_id")
        elif eid in seen:
            errors.append(f"entry_id 重复: {eid}")
        seen.add(eid)
        if not isinstance(e.get("fields"), dict):
            errors.append(f"{eid or i}: fields 必须是对象")
    return errors


def validate_ir_v2(ir: dict) -> list[str]:
    """校验 IR v2 基本结构；返回错误列表（空列表 = 合法）。"""
    errors = []
    if not isinstance(ir, dict):
        return ["IR 必须是 JSON 对象"]
    if ir.get("ir_version") != IR_VERSION_V2:
        errors.append(f"ir_version must be {IR_VERSION_V2}")
        return errors
    if not isinstance(ir.get("skill_meta"), dict):
        errors.append("skill_meta must be object")
    if not isinstance(ir.get("anchors"), dict):
        errors.append("anchors must be object")
    entries = ir.get("entries")
    if not isinstance(entries, list):
        errors.append("entries must be array")
        return errors
    seen_ids = set()
    required_fields = ("knowledge_desc", "knowledge_ref", "rule_ref", "output", "data_logic")
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"entries[{i}] 必须是对象")
            continue
        eid = _norm(entry.get("entry_id"))
        prefix = eid or f"entries[{i}]"
        if not eid:
            errors.append(f"entries[{i}] 缺少 entry_id")
        elif not ENTRY_ID_PATTERN.match(eid):
            errors.append(f"{prefix}: entry_id 格式非法: {eid!r}")
        elif eid in seen_ids:
            errors.append(f"entry_id 重复: {eid}")
        else:
            seen_ids.add(eid)
        phase = _norm(entry.get("step_phase"))
        if phase not in VALID_STEP_PHASES:
            errors.append(f"{prefix}: invalid step_phase {phase!r}")
        fields = entry.get("fields") or {}
        if not isinstance(fields, dict):
            errors.append(f"{prefix}: fields 必须是对象")
            continue
        for req in required_fields:
            if req not in fields:
                errors.append(f"{prefix}: missing required field {req}")
        data_logic = fields.get("data_logic")
        if not isinstance(data_logic, dict):
            errors.append(f"{prefix}: data_logic must be object")
        elif "sql" not in data_logic:
            errors.append(f"{prefix}: data_logic.sql is required")
        else:
            if not isinstance(data_logic.get("sql"), str):
                errors.append(f"{prefix}: data_logic.sql must be string")
            for key in ("tables", "fields"):
                val = data_logic.get(key)
                if val is not None and not isinstance(val, list):
                    errors.append(f"{prefix}: data_logic.{key} must be array")
                elif isinstance(val, list):
                    if any(not isinstance(v, str) for v in val):
                        errors.append(f"{prefix}: data_logic.{key} must be string array")
            confidence = data_logic.get("confidence")
            if confidence is not None and confidence not in _VALID_CONFIDENCE:
                errors.append(f"{prefix}: data_logic.confidence must be high|medium|low")
    return errors


def push_sql_history(entry: dict, sql: str, generated_by: str = "llm") -> None:
    """保存 SQL 生成历史。"""
    flags = entry.get("flags")
    if not isinstance(flags, dict):
        flags = {}
        entry["flags"] = flags
    history = flags.setdefault("sql_history", [])
    if not isinstance(history, list):
        history = []
        flags["sql_history"] = history
    history.append({
        "sql": sql,
        "generated_at": _now(),
        "generated_by": generated_by,
    })


def diff_ir(ir_a: dict, ir_b: dict) -> list[dict]:
    """对比两个版本：返回 entry 级变更清单（added / removed / changed）。"""
    a_entries = {_norm(e.get("entry_id")): e for e in (ir_a or {}).get("entries") or []}
    b_entries = {_norm(e.get("entry_id")): e for e in (ir_b or {}).get("entries") or []}
    changes = []
    for eid, entry in b_entries.items():
        if eid not in a_entries:
            changes.append({"entry_id": eid, "change": "added"})
            continue
        old = a_entries[eid]
        changed_fields = []
        all_fields = set((old.get("fields") or {}).keys()) | set((entry.get("fields") or {}).keys())
        for f in sorted(all_fields):
            if _norm((old.get("fields") or {}).get(f)) != _norm((entry.get("fields") or {}).get(f)):
                changed_fields.append(f)
        for top_field, key in (("知识分类", "category"), ("子场景", "sub_scenario")):
            if _norm(old.get(key)) != _norm(entry.get(key)):
                changed_fields.append(top_field)
        if changed_fields:
            changes.append({"entry_id": eid, "change": "changed", "fields": changed_fields})
    for eid in a_entries:
        if eid not in b_entries:
            changes.append({"entry_id": eid, "change": "removed"})
    return changes


# ─── 持久化 ──────────────────────────────────────────────────────

def draft_filename(pipeline_id: str, version: int) -> str:
    pid = (pipeline_id or "nopipe")[:8]
    return f"skill_draft_{pid}_v{int(version)}_{uuid.uuid4().hex[:6]}.json"


def is_skill_draft_filename(name: str) -> bool:
    base = os.path.basename(_norm(name)).lower()
    return base.endswith(".json") and base.startswith("skill_draft_")


def save_ir(workspace, ir: dict, pipeline_id: str = "") -> str:
    """保存 IR 到工作空间，返回文件名（basename）。"""
    if ir.get("ir_version") == IR_VERSION_V2:
        errors = validate_ir_v2(ir)
        if errors:
            raise ValueError("IR v2 校验失败: " + "; ".join(errors[:5]))
    else:
        errors = validate_ir(ir)
        if errors:
            raise ValueError("IR 校验失败: " + "; ".join(errors[:5]))
    meta = ir.get("skill_meta") or {}
    pid = pipeline_id or _norm(meta.get("pipeline_id"))
    version = int(meta.get("draft_version", 1) or 1)
    step = "step2" if version == 1 else "step3"
    name = draft_filename(pid, version)
    path = workspace_path_for(Path(workspace), pid, step, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ir, ensure_ascii=False, indent=2), encoding="utf-8")
    return name


def load_ir(path) -> dict:
    p = Path(path)
    ir = json.loads(p.read_text(encoding="utf-8"))
    if ir.get("ir_version") == IR_VERSION_V2:
        errors = validate_ir_v2(ir)
        if errors:
            raise ValueError(f"IR v2 文件非法 {p.name}: " + "; ".join(errors[:5]))
    else:
        errors = validate_ir(ir)
        if errors:
            raise ValueError(f"IR 文件非法 {p.name}: " + "; ".join(errors[:5]))
    return ir

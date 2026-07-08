"""Step3 知识对齐业务服务."""

from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import uuid
from pathlib import Path

from pipeline_artifacts import (
    basename_only,
    is_step2_preextract_filename,
    is_step3_final_filename,
    is_step3_revision_filename,
    locate_workspace_file,
    resolve_knowledge_ir_path,
    resolve_knowledge_workbook_path,
    safe_workspace_path,
    workspace_path_for,
)
from shared import (
    _debug_log,
    _pipelines_lock,
    _safe_workbook,
    EXTRACT_STYLE_RULES,
    REVISION_STYLE_RULES,
    extract_text_from_file,
    extract_text_from_path,
    get_model_by_name,
    load_llm_config,
    load_pipelines,
    save_pipelines,
    SCHEMA_PATH,
    _extract_json_from_text,
    _pipeline_prefers_markdown,
    call_llm_with_retry,
    extract_assistant_content,
)


_ALIGN_CHAT_ROUND_RE = re.compile(r"^第\d+轮专家意见[：:]\s*", re.MULTILINE)
_ALIGN_REVISION_CUE_RE = re.compile(
    r"(第\s*\d+\s*行|第\s*\d+\s*列|改为|修改|删除|新增|补充(?!意见)|调整|更正|修订|替换|"
    r"单元格|sheet|列[abcde]|行\s*\d+)",
    re.IGNORECASE,
)
_EXPLICIT_NO_OPINION_PHRASES = (
    "没有意见", "无意见", "无异议", "无需修订", "无需修改", "无修改", "没有修改",
    "无修订", "没有修订", "无变更", "保持不变", "专家无意见", "暂无意见",
    "无专家意见", "确认通过", "确认无误", "可以发布", "同意通过", "不需修改",
    "不需要修改", "没有异议", "无会议纪要修订", "无修订意见", "无修改意见",
    "无补充意见", "无补充",
)


def _normalize_expert_text_for_align(expert_text: str) -> str:
    t = (expert_text or "").strip()
    if not t:
        return ""
    t = _ALIGN_CHAT_ROUND_RE.sub("", t)
    t = re.sub(r"[（(]无补充意见[）)]", "", t)
    return t.strip()


def _text_is_explicit_no_opinion(expert_text: str) -> bool:
    t = _normalize_expert_text_for_align(expert_text)
    if not t:
        return True
    if _ALIGN_REVISION_CUE_RE.search(t):
        return False
    compact = re.sub(r"[\s,.，。、；;：:!！?？\-—_（）()]+", "", t.lower())
    if any(p in compact for p in _EXPLICIT_NO_OPINION_PHRASES):
        return True
    if compact in ("无", "没有", "同意", "通过", "ok", "none", "na", "n/a", "暂无"):
        return True
    return False


def _uploaded_expert_material_is_substantive(uploaded_text: str) -> bool:
    t = (uploaded_text or "").strip()
    if len(t) < 30:
        return False
    return not _text_is_explicit_no_opinion(t)


def _should_pass_through_preextract(expert_text: str, uploaded_material_text: str = "") -> bool:
    if _uploaded_expert_material_is_substantive(uploaded_material_text):
        return False
    return _text_is_explicit_no_opinion(expert_text)


def _alignment_llm_guard_rules() -> str:
    return """
## 重要约束
1. 仅根据「专家意见」中**明确写出**的修订要求生成条目；禁止仅依据知识稿内容自行推断、优化或补充修订。
2. 若专家表示无意见、无需修改、确认通过等，必须输出空数组 []。
3. 不得将知识稿中的待完善项自动转为修订建议，除非专家意见中点名要求修改。
"""


def _resolve_align_source_for_pipeline(workspace: Path, pipeline_id: str) -> tuple[str | None, str]:
    with _pipelines_lock:
        pipelines = load_pipelines()
        for p in pipelines:
            if p["id"] == pipeline_id:
                sd = p.get("step_data", {})
                resolved, _src = resolve_knowledge_workbook_path(workspace, sd, purpose="align")
                if resolved:
                    return str(resolved), resolved.name
                break
    return None, ""


def _resolve_step2_excel_path(workspace: Path, pipeline_id: str):
    if not pipeline_id:
        return None, ""
    with _pipelines_lock:
        pipelines = load_pipelines()
        for p in pipelines:
            if p["id"] != pipeline_id:
                continue
            sd = p.get("step_data", {})
            step2_file = sd.get("step2_output_file", "")
            if not is_step2_preextract_filename(step2_file):
                return None, ""
            path = safe_workspace_path(workspace, step2_file, must_exist=True)
            if path:
                return str(path), sd.get("skill_extract_result", "")[:3000]
            break
    return None, ""


def _normalize_revision_style(style: str) -> str:
    style = (style or "").strip()
    return style if style in REVISION_STYLE_RULES else "标准修订"


def _normalize_revision_action(action: str) -> str:
    a = (action or "").strip().lower()
    alias = {
        "修改": "modify",
        "delete": "delete",
        "删除": "delete",
        "新增": "add",
        "add": "add",
        "补充": "supplement",
        "supplement": "supplement",
    }
    return alias.get(a, a)


def _to_int(val, default=0) -> int:
    if isinstance(val, int):
        return val
    if val is None:
        return default
    s = str(val).strip()
    if not s:
        return default
    if s.isalpha():
        n = 0
        for ch in s.upper():
            if "A" <= ch <= "Z":
                n = n * 26 + (ord(ch) - ord("A") + 1)
            else:
                return default
        return n or default
    digits = []
    sign = 1
    found = False
    for i, ch in enumerate(s):
        if ch == "-" and not found:
            sign = -1
            continue
        if ch.isdigit():
            digits.append(ch)
            found = True
        elif found:
            break
    if digits:
        try:
            return sign * int("".join(digits))
        except Exception:
            return default
    return default


def _apply_revision_style_rules(expert_notes: list, style: str) -> tuple[list, dict]:
    style = _normalize_revision_style(style)
    rule = REVISION_STYLE_RULES[style]
    allowed_actions = rule["allowed_actions"]

    dedup = {}
    raw_count = 0
    for raw in expert_notes or []:
        if not isinstance(raw, dict):
            continue
        raw_count += 1

        action = _normalize_revision_action(raw.get("action", ""))
        if action not in allowed_actions:
            continue

        sheet = str(raw.get("sheet") or "").strip() or "Sheet1"
        row = _to_int(raw.get("row"), 0)
        col = _to_int(raw.get("col"), 0)
        old_value = str(raw.get("old_value") or "").strip()
        new_value = str(raw.get("new_value") or "").strip()
        note = str(raw.get("note") or "").strip()

        if action in {"modify", "supplement", "add"} and not new_value:
            continue
        if action == "modify" and not old_value:
            continue
        if action != "add" and row <= 0:
            continue
        if action == "add" and (row <= 0 or col <= 0):
            continue
        if style == "严格修订" and (action in {"add", "delete"}):
            continue

        normalized = {
            "sheet": sheet,
            "row": row,
            "col": col if col > 0 else 1,
            "action": action,
            "old_value": old_value,
            "new_value": new_value,
            "note": note,
        }

        if action == "add":
            dedup_key = (sheet, action, normalized["new_value"][:120])
        else:
            dedup_key = (sheet, row, normalized["col"], action)

        current = dedup.get(dedup_key)
        if current is None or len(normalized["note"]) >= len(current.get("note", "")):
            dedup[dedup_key] = normalized

    filtered = list(dedup.values())

    if style == "严格修订":
        priority = {"modify": 3, "supplement": 2, "add": 0, "delete": 0}
    elif style == "宽松修订":
        priority = {"add": 4, "supplement": 3, "modify": 2, "delete": 1}
    else:
        priority = {"modify": 4, "supplement": 3, "add": 2, "delete": 1}

    filtered.sort(
        key=lambda n: (
            priority.get(n.get("action", ""), 0),
            len((n.get("note") or "")),
            len((n.get("new_value") or "")),
        ),
        reverse=True,
    )
    filtered = filtered[: rule["max_actions"]]

    stats = {
        "raw_count": raw_count,
        "processed_count": len(filtered),
        "max_actions": rule["max_actions"],
    }
    return filtered, stats


def _load_align_expert_upload_text(*, uploaded_file=None, cached_file_name: str = "") -> str:
    text_parts = []
    if uploaded_file and getattr(uploaded_file, "filename", None):
        try:
            text_parts.append(extract_text_from_file(uploaded_file).strip())
        except Exception:
            pass
    if cached_file_name:
        try:
            cached_path = locate_workspace_file(Path(str(__import__("app_server").WORKSPACE)), cached_file_name)
            if cached_path and cached_path.exists():
                text_parts.append(extract_text_from_path(str(cached_path)).strip())
        except Exception:
            pass
    return "\n\n".join(p for p in text_parts if p).strip()


def _publish_final_from_source(
    workspace: Path,
    pipeline_id: str,
    source_file_path: str,
    expert_text: str = "",
    style: str = "标准修订",
):
    output_name = f"final_{pipeline_id[:8]}_{datetime.datetime.now().strftime('%H%M%S')}.xlsx"
    output_path = workspace_path_for(workspace, pipeline_id, "step3", output_name)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_file_path, str(output_path))

    md_name, md_url = "", ""
    if _pipeline_prefers_markdown(pipeline_id):
        from shared import _excel_to_markdown_file
        md_name = f"final_{pipeline_id[:8]}_{datetime.datetime.now().strftime('%H%M%S')}.md"
        md_path = workspace_path_for(workspace, pipeline_id, "step3", md_name)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            _excel_to_markdown_file(output_path, md_path, title=f"Step3 知识对齐 · {pipeline_id[:8]}")
            md_url = "/downloads/" + md_name
        except Exception:
            md_name, md_url = "", ""
    if not md_name:
        from shared import _excel_to_markdown_file
        md_name = f"final_{pipeline_id[:8]}_{datetime.datetime.now().strftime('%H%M%S')}.md"
        md_path = workspace_path_for(workspace, pipeline_id, "step3", md_name)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            _excel_to_markdown_file(output_path, md_path, title=f"Step3 知识对齐 · {pipeline_id[:8]}")
            md_url = "/downloads/" + md_name
        except Exception:
            md_name, md_url = "", ""

    with _pipelines_lock:
        pipelines = load_pipelines()
        for p in pipelines:
            if p["id"] == pipeline_id:
                sd = p.setdefault("step_data", {})
                sd["step3_final_file"] = output_name
                sd["step3_final_download_url"] = "/downloads/" + output_name
                if md_name:
                    sd["step3_final_md_file"] = md_name
                    sd["step3_final_md_download_url"] = md_url
                else:
                    sd.pop("step3_final_md_file", None)
                    sd.pop("step3_final_md_download_url", None)
                sd["step3_final_notes"] = (expert_text or "")[:500]
                sd["step3_final_style"] = style
                sd["step3_final_count"] = 0
                sd.pop("_align_preview_notes", None)
                sd.pop("_align_preview_style", None)
                sd.pop("_align_source_file", None)
                sd.pop("_align_chat_history", None)
                p.setdefault("step_status", {})
                p["step_status"]["3"] = "done"
                if p["step_status"].get("4", "pending") == "pending":
                    p["step_status"]["4"] = "active"
                p["current_step"] = max(p.get("current_step", 1), 4)
                p["updated_at"] = datetime.datetime.now().isoformat()
                save_pipelines(pipelines)
                break

    _persist_step3_aligned_ir(workspace, pipeline_id, output_name, notes=[], style=style)
    return output_name, md_name, md_url


def _align_no_opinion_success_payload(
    workspace: Path,
    pipeline_id: str,
    source_file_path: str,
    expert_text: str,
    style: str,
    style_rule: dict,
    *,
    auto_publish: bool = True,
) -> dict:
    payload = {
        "status": "ok",
        "notes": [],
        "total": 0,
        "no_opinion": True,
        "auto_finalized": False,
        "align_mode": "pass_through",
        "message": "专家意见为无需修订，已自动将当前稿确认为对齐稿。",
        "style": style,
        "style_rule": {
            "mode": style,
            "max_actions": style_rule.get("max_actions", 0),
            "raw_count": 0,
            "processed_count": 0,
        },
    }
    if auto_publish and source_file_path:
        output_name, md_name, md_url = _publish_final_from_source(
            workspace, pipeline_id, source_file_path, expert_text=expert_text, style=style
        )
        payload["auto_finalized"] = True
        payload["revision_count"] = 0
        payload["accepted_count"] = 0
        payload["output_file"] = output_name
        payload["download_name"] = output_name
        payload["download_url"] = "/downloads/" + output_name
        payload["markdown_file"] = md_name
        payload["markdown_download_url"] = md_url or ""
        payload["message"] = "已自动将当前萃取稿确认为对齐稿（无修订），可直接下载。"
    else:
        payload["message"] = "专家意见为无需修订。可直接确认当前稿为对齐稿。"
    return payload


def _persist_step3_aligned_ir(
    workspace: Path,
    pipeline_id: str,
    final_output_name: str,
    *,
    notes: list | None = None,
    style: str = "",
) -> dict:
    if not pipeline_id or not final_output_name:
        return {}
    try:
        from skill_ir import STATUS_ALIGNED, new_draft_from_workbook, render_skill_md, save_ir

        final_path = locate_workspace_file(workspace, final_output_name, pipeline_id=pipeline_id)
        if not final_path or not final_path.exists():
            return {}

        prev_version = 1
        with _pipelines_lock:
            pipelines = load_pipelines()
            for p in pipelines:
                if p["id"] == pipeline_id:
                    sd = p.get("step_data", {}) or {}
                    prev_version = int(
                        sd.get("step3_aligned_version")
                        or sd.get("step2_draft_version")
                        or 1
                    )
                    break

        from services.step2_service import _pipeline_scenario_meta
        meta_ctx = _pipeline_scenario_meta(pipeline_id)
        ir = new_draft_from_workbook(
            str(final_path), meta_ctx,
            origin="alignment", pipeline_id=pipeline_id,
        )
        ir["skill_meta"]["draft_version"] = prev_version + 1
        ir["skill_meta"]["parent_version"] = prev_version
        ir["skill_meta"]["status"] = STATUS_ALIGNED
        ir.setdefault("revision_log", []).append({
            "version": prev_version + 1,
            "by": "expert",
            "applied": len(notes or []),
            "source": "excel_alignment",
            "style": style,
            "at": datetime.datetime.now().isoformat(timespec="seconds"),
        })
        draft_name = save_ir(workspace, ir, pipeline_id=pipeline_id)

        md_name, md_url = "", ""
        try:
            config = {}
            if SCHEMA_PATH.exists():
                from excel_to_skill import load_scenario_config
                config = load_scenario_config(str(SCHEMA_PATH))
            md_content = render_skill_md(ir, config)
            md_name = f"SKILL_aligned_{uuid.uuid4().hex[:8]}.md"
            md_path = workspace_path_for(workspace, pipeline_id, "step3", md_name)
            md_path.parent.mkdir(parents=True, exist_ok=True)
            md_path.write_text(md_content, encoding="utf-8")
            md_url = f"/downloads/{md_name}"
        except Exception as e:
            _debug_log("E", "_persist_step3_aligned_ir", "render_error", str(e)[-200:])
            md_name, md_url = "", ""

        info = {
            "aligned_file": draft_name,
            "aligned_url": f"/downloads/{draft_name}",
            "aligned_md_file": md_name,
            "aligned_md_url": md_url,
            "aligned_version": prev_version + 1,
        }
        with _pipelines_lock:
            pipelines = load_pipelines()
            for p in pipelines:
                if p["id"] == pipeline_id:
                    sd = p.setdefault("step_data", {})
                    sd["step3_aligned_file"] = draft_name
                    sd["step3_aligned_url"] = info["aligned_url"]
                    sd["step3_aligned_version"] = info["aligned_version"]
                    if md_name:
                        sd["step3_aligned_md_file"] = md_name
                        sd["step3_aligned_md_url"] = md_url
                    else:
                        sd.pop("step3_aligned_md_file", None)
                        sd.pop("step3_aligned_md_url", None)
                    save_pipelines(pipelines)
                    break
        return info
    except Exception as e:
        _debug_log("E", "_persist_step3_aligned_ir", "aligned_error", str(e)[-200:])
        return {}


def _push_step3_suggestions(pipeline_id: str, suggestions: list, source: str) -> int:
    if not pipeline_id or not suggestions:
        return 0
    cleaned = []
    for s in suggestions:
        if not isinstance(s, dict):
            continue
        item = dict(s)
        item["id"] = uuid.uuid4().hex[:10]
        item["source"] = source
        item["created_at"] = datetime.datetime.now().isoformat(timespec="seconds")
        cleaned.append(item)
    if not cleaned:
        return 0
    with _pipelines_lock:
        pipelines = load_pipelines()
        for p in pipelines:
            if p["id"] == pipeline_id:
                sd = p.setdefault("step_data", {})
                pool = sd.get("step3_pending_suggestions")
                if not isinstance(pool, list):
                    pool = []
                pool.extend(cleaned)
                sd["step3_pending_suggestions"] = pool[-60:]
                save_pipelines(pipelines)
                break
    return len(cleaned)


def suggestions(workspace: Path, pipeline_id: str) -> dict:
    if not pipeline_id:
        return {"status": "error", "error": "缺少 pipeline_id"}

    pool = []
    sd = {}
    with _pipelines_lock:
        pipelines = load_pipelines()
        for p in pipelines:
            if p["id"] == pipeline_id:
                sd = p.get("step_data", {}) or {}
                raw = sd.get("step3_pending_suggestions")
                if isinstance(raw, list):
                    pool = raw
                break

    flags_summary = {"conflicts": 0, "duplicates": 0}
    ir_path, ir_key = resolve_knowledge_ir_path(workspace, sd)
    aligned_version = sd.get("step3_aligned_version") or 0
    if ir_path:
        try:
            from skill_ir import load_ir
            ir = load_ir(ir_path)
            for e in ir.get("entries", []):
                fl = e.get("flags") or {}
                if fl.get("conflict_with"):
                    flags_summary["conflicts"] += 1
                if fl.get("duplicate_of"):
                    flags_summary["duplicates"] += 1
        except Exception:
            pass

    by_source = {}
    for s in pool:
        src = s.get("source", "unknown")
        by_source[src] = by_source.get(src, 0) + 1

    return {
        "status": "ok",
        "suggestions": pool,
        "total": len(pool),
        "by_source": by_source,
        "flags_summary": flags_summary,
        "has_ir": bool(ir_path),
        "ir_source": ir_key,
        "aligned_version": aligned_version,
        "aligned_md_url": sd.get("step3_aligned_md_url", ""),
    }


def apply_suggestions(workspace: Path, data: dict) -> dict:
    pipeline_id = data.get("pipeline_id", "")
    accepted_ids = set(str(i) for i in data.get("accepted_ids", []))
    rejected_ids = set(str(i) for i in data.get("rejected_ids", []))
    raw_edited = data.get("edited_suggestions", [])
    edited = {str(e.get("id")): e for e in raw_edited if isinstance(e, dict) and e.get("id")}

    if not pipeline_id:
        return {"status": "error", "error": "缺少 pipeline_id"}
    if not accepted_ids and not rejected_ids:
        return {"status": "error", "error": "请至少采纳或驳回一条建议"}

    sd = {}
    with _pipelines_lock:
        pipelines = load_pipelines()
        for p in pipelines:
            if p["id"] == pipeline_id:
                sd = p.get("step_data", {}) or {}
                break
    pool = sd.get("step3_pending_suggestions")
    if not isinstance(pool, list) or not pool:
        return {"status": "error", "error": "建议池为空"}

    accepted = []
    for s in pool:
        sid = str(s.get("id"))
        if sid in accepted_ids:
            accepted.append({**s, **edited.get(sid, {})})

    new_info = {}
    applied = 0
    if accepted:
        ir_path, _key = resolve_knowledge_ir_path(workspace, sd)
        if not ir_path:
            return {"status": "error", "error": "未找到 Skill 草稿（IR），请先完成知识萃取"}
        if str(ir_path).endswith(".md"):
            return {"status": "error", "error": "当前为 Markdown 流程，请使用知识对齐节点的编辑器手动修订，或使用 AI 辅助修订功能"}
        try:
            from skill_ir import STATUS_ALIGNED, apply_revisions, load_ir, render_skill_md, save_ir

            ir = load_ir(ir_path)
            new_ir, applied = apply_revisions(ir, accepted, by="expert", new_status=STATUS_ALIGNED)
            draft_name = save_ir(workspace, new_ir, pipeline_id=pipeline_id)
            md_name, md_url = "", ""
            try:
                config = {}
                if SCHEMA_PATH.exists():
                    from excel_to_skill import load_scenario_config
                    config = load_scenario_config(str(SCHEMA_PATH))
                md_content = render_skill_md(new_ir, config)
                md_name = f"SKILL_aligned_{uuid.uuid4().hex[:8]}.md"
                md_path = workspace_path_for(workspace, pipeline_id, "step3", md_name)
                md_path.parent.mkdir(parents=True, exist_ok=True)
                md_path.write_text(md_content, encoding="utf-8")
                md_url = f"/downloads/{md_name}"
            except Exception:
                md_name, md_url = "", ""
            new_info = {
                "aligned_file": draft_name,
                "aligned_url": f"/downloads/{draft_name}",
                "aligned_md_file": md_name,
                "aligned_md_url": md_url,
                "aligned_version": new_ir["skill_meta"]["draft_version"],
            }
        except Exception as e:
            return {"status": "error", "error": f"应用建议失败: {str(e)}"}

    handled = accepted_ids | rejected_ids
    with _pipelines_lock:
        pipelines = load_pipelines()
        for p in pipelines:
            if p["id"] == pipeline_id:
                sd = p.setdefault("step_data", {})
                old_pool = sd.get("step3_pending_suggestions")
                if isinstance(old_pool, list):
                    sd["step3_pending_suggestions"] = [
                        s for s in old_pool if str(s.get("id")) not in handled
                    ]
                if new_info:
                    sd["step3_aligned_file"] = new_info["aligned_file"]
                    sd["step3_aligned_url"] = new_info["aligned_url"]
                    sd["step3_aligned_version"] = new_info["aligned_version"]
                    if new_info.get("aligned_md_file"):
                        sd["step3_aligned_md_file"] = new_info["aligned_md_file"]
                        sd["step3_aligned_md_url"] = new_info["aligned_md_url"]
                    p.setdefault("step_status", {})
                    p["step_status"]["3"] = "done"
                    if p["step_status"].get("4", "pending") == "pending":
                        p["step_status"]["4"] = "active"
                p["updated_at"] = datetime.datetime.now().isoformat()
                save_pipelines(pipelines)
                break

    return {
        "status": "ok",
        "applied_count": applied,
        "accepted_count": len(accepted),
        "rejected_count": len(rejected_ids),
        "remaining": max(0, len(pool) - len(handled)),
        **new_info,
    }


def revision_context(pipeline_id: str) -> dict:
    if not pipeline_id:
        return {"status": "error", "error": "缺少 pipeline_id"}

    with _pipelines_lock:
        pipelines = load_pipelines()
        sd = {}
        for p in pipelines:
            if p["id"] == pipeline_id:
                sd = p.get("step_data", {}) or {}
                break

    ctx = {"status": "ok", "insights": [], "warnings": []}
    ta = sd.get("step3_tacit_annotations") or []
    if ta:
        ctx["insights"].append({
            "source": "隐性注释",
            "icon": "💡",
            "text": f"已有 {len(ta)} 条专家隐性注释可用于修订参考",
        })
    return ctx


def prev_output(workspace: Path, pipeline_id: str) -> dict:
    if not pipeline_id:
        return {"status": "error", "error": "缺少 pipeline_id"}

    with _pipelines_lock:
        pipelines = load_pipelines()
        for p in pipelines:
            if p["id"] == pipeline_id:
                sd = p.get("step_data", {})

                md_file = sd.get("step2_skill_md_file")
                if md_file:
                    return {
                        "status": "ok",
                        "has_output": True,
                        "markdown_file": md_file,
                        "markdown_download_url": "/downloads/" + md_file,
                        "scenario": p.get("scenario", ""),
                    }

                step2_file = sd.get("step2_output_file", "")
                step2_download = sd.get("step2_download_url", "")
                step2_md_file = sd.get("step2_md_file", "")
                step2_md_download = sd.get("step2_md_download_url", "")
                if not is_step2_preextract_filename(step2_file):
                    return {
                        "status": "ok",
                        "has_output": False,
                        "hint": "未找到有效萃取 Excel（preextract_*.xlsx），请先完成知识萃取（Step2）",
                    }

                fields_info = []
                file_path = safe_workspace_path(workspace, step2_file, must_exist=True)
                if file_path:
                    try:
                        with _safe_workbook(str(file_path)) as wb:
                            for ws_name in wb.sheetnames:
                                ws = wb[ws_name]
                                headers = []
                                if ws.max_row >= 1 and ws.max_column >= 1:
                                    for cell in next(ws.iter_rows(min_row=1, max_row=1)):
                                        headers.append(str(cell.value) if cell.value else "")
                                row_count = ws.max_row - 1 if ws.max_row > 1 else 0
                                fields_info.append({"sheet": ws_name, "headers": headers, "rows": row_count})
                    except Exception:
                        pass

                fusion_meta = None
                fusion_file = sd.get("step2_fusion_file", "")
                if fusion_file:
                    fp = safe_workspace_path(workspace, fusion_file, must_exist=True)
                    if fp:
                        try:
                            fusion_data = json.loads(fp.read_text(encoding="utf-8"))
                            fusion_meta = {
                                "duplicates": fusion_data.get("duplicates", []),
                                "conflicts": fusion_data.get("conflicts", []),
                                "source_stats": fusion_data.get("source_stats", {}),
                                "confidence_distribution": fusion_data.get("confidence_distribution", {}),
                            }
                        except Exception:
                            pass

                return {
                    "status": "ok", "has_output": True,
                    "file_name": step2_file,
                    "download_url": step2_download or ("/downloads/" + step2_file),
                    "markdown_file": step2_md_file,
                    "markdown_download_url": step2_md_download or (f"/downloads/{step2_md_file}" if step2_md_file else ""),
                    "fields_info": fields_info,
                    "scenario": sd.get("skill_extract_scenario", ""),
                    "style": sd.get("skill_extract_style", ""),
                    "extracted_count": sd.get("step2_extracted_count", 0),
                    "step1_file": sd.get("step1_output_file", ""),
                    "fusion_meta": fusion_meta,
                }
    return {"status": "ok", "has_output": False}


def align_output(workspace: Path, pipeline_id: str) -> dict:
    if not pipeline_id:
        return {"status": "error", "error": "缺少 pipeline_id"}

    with _pipelines_lock:
        pipelines = load_pipelines()
        for p in pipelines:
            if p["id"] == pipeline_id:
                sd = p.get("step_data", {})

                md_file = sd.get("step3_skill_md_file") or sd.get("step2_skill_md_file")
                if md_file:
                    return {
                        "status": "ok",
                        "has_output": True,
                        "markdown_file": md_file,
                        "markdown_download_url": "/downloads/" + md_file,
                        "scenario": p.get("scenario", ""),
                    }

                file_path_obj, source_key = resolve_knowledge_workbook_path(workspace, sd, purpose="compile")
                if not file_path_obj:
                    return {"status": "ok", "has_output": False}
                file_path = str(file_path_obj)
                out_name = file_path_obj.name

                try:
                    fields_info = []
                    with _safe_workbook(file_path) as wb:
                        for ws_name in wb.sheetnames:
                            ws = wb[ws_name]
                            headers = []
                            if ws.max_row >= 1 and ws.max_column >= 1:
                                for cell in next(ws.iter_rows(min_row=1, max_row=1)):
                                    headers.append(str(cell.value) if cell.value else "")
                            row_count = ws.max_row - 1 if ws.max_row > 1 else 0
                            fields_info.append({"sheet": ws_name, "headers": headers, "rows": row_count})
                    if source_key == "step3_final_file":
                        dl_url = sd.get("step3_final_download_url") or ("/downloads/" + out_name)
                        md_name = sd.get("step3_final_md_file", "")
                        md_url = sd.get("step3_final_md_download_url") or (f"/downloads/{md_name}" if md_name else "")
                        align_style = sd.get("step3_final_style", "")
                        align_count = sd.get("step3_final_count", 0)
                    elif source_key == "step3_revision_file":
                        dl_url = sd.get("step3_download_url") or ("/downloads/" + out_name)
                        md_name = sd.get("step3_md_file", "")
                        md_url = sd.get("step3_md_download_url") or (f"/downloads/{md_name}" if md_name else "")
                        align_style = sd.get("step3_revision_style", "")
                        align_count = sd.get("step3_revision_count", 0)
                    else:
                        dl_url = sd.get("step2_download_url") or ("/downloads/" + out_name)
                        md_name = sd.get("step2_md_file", "")
                        md_url = sd.get("step2_md_download_url") or (f"/downloads/{md_name}" if md_name else "")
                        align_style = sd.get("skill_extract_style", "")
                        align_count = sd.get("step2_extracted_count", 0)
                    return {
                        "status": "ok", "has_output": True,
                        "file_name": out_name,
                        "download_url": dl_url,
                        "markdown_file": md_name,
                        "markdown_download_url": md_url,
                        "fields_info": fields_info,
                        "revision_style": align_style,
                        "revision_count": align_count,
                        "source": source_key,
                    }
                except Exception:
                    return {"status": "ok", "has_output": False}
    return {"status": "ok", "has_output": False}


def align_ir(workspace: Path, data: dict) -> dict:
    pipeline_id = data.get("pipeline_id", "")
    entry_id = data.get("entry_id", "")
    field = data.get("field", "")
    new_value = data.get("new_value")
    regenerate_sql = data.get("regenerate_sql", False)
    model_name = data.get("model", "")

    if not pipeline_id or not entry_id or not field:
        return {"status": "error", "error": "缺少必要参数"}

    from skill_ir import load_ir, save_ir, apply_field_revision, set_sql_manually_edited
    from knowledge_base import get_db_schema_text
    from services.pipeline_service import get_pipeline

    pipeline = get_pipeline(pipeline_id)
    if not pipeline:
        return {"status": "error", "error": "流水线不存在"}

    sd = pipeline.get("step_data") or {}

    try:
        ir_name = sd.get("step3_aligned_file") or sd.get("step2_draft_file", "")
        ir_path = locate_workspace_file(workspace, ir_name, pipeline_id=pipeline_id)
        if not ir_path:
            return {"status": "error", "error": "未找到 Step2 IR"}

        ir = load_ir(ir_path)
        entry = None
        for e in ir.get("entries", []):
            if e.get("entry_id") == entry_id:
                entry = e
                break
        if not entry:
            return {"status": "error", "error": "entry_id 不存在"}

        if field == "data_logic.sql":
            entry.setdefault("fields", {}).setdefault("data_logic", {})["sql"] = new_value
            set_sql_manually_edited(entry, True)
        else:
            apply_field_revision(entry, field, new_value, by="expert")

        if regenerate_sql and field != "data_logic.sql":
            if not model_name:
                return {"status": "error", "error": "重新生成 SQL 需要提供 model"}
            model_cfg = get_model_by_name(model_name)
            if not model_cfg:
                return {"status": "error", "error": f"模型不存在: {model_name}"}
            from skill_ir import regenerate_sql_for_entry
            table_schema = get_db_schema_text()
            data_logic = regenerate_sql_for_entry(entry, table_schema, model_name)
            entry["fields"]["data_logic"] = data_logic

        ir["skill_meta"]["updated_at"] = datetime.datetime.now().isoformat(timespec="seconds")
        new_ir_path = save_ir(workspace, ir, pipeline_id=pipeline_id)
        new_name = Path(new_ir_path).name

        with _pipelines_lock:
            pipelines = load_pipelines()
            for p in pipelines:
                if p["id"] == pipeline_id:
                    psd = p.setdefault("step_data", {})
                    psd["step3_aligned_file"] = new_name
                    psd["step3_aligned_url"] = "/downloads/" + new_name
                    psd["step2_draft_file"] = new_name
                    psd["step2_draft_url"] = "/downloads/" + new_name
                    psd["step3_aligned_version"] = ir["skill_meta"]["draft_version"]
                    break
            save_pipelines(pipelines)
    except Exception as e:
        return {"status": "error", "error": f"保存 IR 修订失败: {e}"}

    return {"status": "ok", "ir_path": new_name, "entry": entry}


def confirm_as_is(workspace: Path, data: dict) -> dict:
    pipeline_id = data.get("pipeline_id", "")
    if not pipeline_id:
        return {"status": "error", "error": "缺少 pipeline_id"}

    from services.pipeline_service import get_pipeline
    pipeline = get_pipeline(pipeline_id)
    if not pipeline:
        return {"status": "error", "error": "流水线不存在"}

    sd = pipeline.get("step_data") or {}

    md_file = sd.get("step2_skill_md_file")
    if md_file:
        md_path = locate_workspace_file(workspace, md_file, pipeline_id=pipeline_id)
        if md_path:
            try:
                content = md_path.read_text(encoding="utf-8")
                aligned_name = f"skill_aligned_{pipeline_id[:8]}_{uuid.uuid4().hex[:6]}.md"
                aligned_path = workspace_path_for(workspace, pipeline_id, "step3", aligned_name)
                aligned_path.parent.mkdir(parents=True, exist_ok=True)
                aligned_path.write_text(content, encoding="utf-8")

                with _pipelines_lock:
                    pipelines = load_pipelines()
                    for p in pipelines:
                        if p["id"] == pipeline_id:
                            psd = p.setdefault("step_data", {})
                            psd["step3_skill_md_file"] = aligned_name
                            psd["step3_skill_md_url"] = f"/downloads/{aligned_name}"
                            psd["step3_aligned_file"] = aligned_name
                            psd["step3_aligned_url"] = f"/downloads/{aligned_name}"
                            p.setdefault("step_status", {})
                            p["step_status"]["3"] = "done"
                            if p["step_status"].get("4", "pending") == "pending":
                                p["step_status"]["4"] = "active"
                            p["current_step"] = max(p.get("current_step", 1), 4)
                            p["updated_at"] = datetime.datetime.now().isoformat()
                            break
                    save_pipelines(pipelines)
                return {
                    "status": "ok",
                    "aligned_file": aligned_name,
                    "aligned_url": f"/downloads/{aligned_name}",
                    "message": "已确认对齐（无修订）",
                }
            except Exception as e:
                return {"status": "error", "error": f"确认对齐失败: {str(e)}"}

    ir_name = sd.get("step3_aligned_file") or sd.get("step2_draft_file", "")
    if ir_name:
        from skill_ir import STATUS_ALIGNED, load_ir, save_ir, IR_VERSION_V2
        ir_path = locate_workspace_file(workspace, ir_name, pipeline_id=pipeline_id)
        if ir_path:
            try:
                ir = load_ir(ir_path)
                if ir.get("ir_version") == IR_VERSION_V2:
                    old_version = ir["skill_meta"].get("draft_version", 1)
                    ir["skill_meta"]["draft_version"] = old_version + 1
                    ir["skill_meta"]["parent_version"] = old_version
                    ir["skill_meta"]["status"] = STATUS_ALIGNED
                    ir["skill_meta"]["updated_at"] = datetime.datetime.now().isoformat(timespec="seconds")
                    aligned_path = save_ir(workspace, ir, pipeline_id=pipeline_id)
                    aligned_name = Path(aligned_path).name
                    with _pipelines_lock:
                        pipelines = load_pipelines()
                        for p in pipelines:
                            if p["id"] == pipeline_id:
                                psd = p.setdefault("step_data", {})
                                psd["step3_aligned_file"] = aligned_name
                                psd["step3_aligned_url"] = f"/downloads/{aligned_name}"
                                psd["step3_final_file"] = aligned_name
                                psd["step3_final_download_url"] = f"/downloads/{aligned_name}"
                                psd["step3_aligned_version"] = old_version + 1
                                break
                        save_pipelines(pipelines)
                    return {
                        "status": "ok",
                        "aligned_file": aligned_name,
                        "final_file": aligned_name,
                        "aligned_url": f"/downloads/{aligned_name}",
                        "final_url": f"/downloads/{aligned_name}",
                        "message": "已确认 IR v2 为对齐稿（无修订）",
                    }
            except Exception as e:
                return {"status": "error", "error": f"确认 IR 对齐稿失败: {str(e)}"}

    source_file_path, _ = _resolve_align_source_for_pipeline(workspace, pipeline_id)
    if not source_file_path:
        return {"status": "error", "error": "未找到可对齐的知识稿"}

    try:
        style = "标准修订"
        with _pipelines_lock:
            pipelines = load_pipelines()
            for p in pipelines:
                if p["id"] == pipeline_id:
                    style = p.get("step_data", {}).get("_align_preview_style") or style
                    break
        output_name, md_name, md_url = _publish_final_from_source(workspace, pipeline_id, source_file_path, style=style)
        return {
            "status": "ok",
            "revision_count": 0,
            "accepted_count": 0,
            "total_suggested": 0,
            "output_file": output_name,
            "download_name": output_name,
            "download_url": "/downloads/" + output_name,
            "markdown_file": md_name,
            "markdown_download_url": md_url,
            "message": "已确认当前稿为对齐稿（无修订）",
        }
    except Exception as e:
        return {"status": "error", "error": f"确认对齐稿失败: {str(e)}"}

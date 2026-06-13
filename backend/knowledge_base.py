#!/usr/bin/env python3
"""
外部知识库（KB）— 跨流水线知识资产层 / 案例库 / 发布登记 / 验证记录

定位（与 golden_db 互补）：
- golden_db = 人工精标的「基准考卷」，衡量萃取像不像基准
- knowledge_base = 生产「知识资产」，沉淀已发布 Skill 的条目，支持继承/演化/检索

四个角色：
1. 知识资产层 kb_entries：条目级知识 + 版本与生命周期（active/superseded/deprecated）
2. 案例库 kb_cases：历史案例 + 专家结论（Step5 验证弹药 / Step2 案例复盘素材）
3. 发布登记 kb_skill_releases：每个 published SKILL 的版本、IR 快照、质量分
4. 验证记录 kb_validation_runs：Step5 决策回放运行史

检索第一期为关键词过滤 + 词重叠率重排（search_entries 接口已抽象，可平滑替换为向量检索）。
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

_DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "kb" / "knowledge_base.db"
DB_PATH = Path(os.environ.get("KB_DB_PATH", str(_DEFAULT_DB)))

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS kb_entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entry_uid TEXT UNIQUE NOT NULL,
  domain TEXT NOT NULL DEFAULT '',
  scenario TEXT DEFAULT '',
  sub_scenario TEXT DEFAULT '',
  category TEXT DEFAULT '',
  fields_json TEXT NOT NULL,
  status TEXT DEFAULT 'active',
  version INTEGER DEFAULT 1,
  superseded_by TEXT DEFAULT '',
  confidence TEXT DEFAULT '',
  evidence_count INTEGER DEFAULT 0,
  contributed_by TEXT DEFAULT '',
  source_pipeline_id TEXT DEFAULT '',
  source_skill_slug TEXT DEFAULT '',
  created_at TEXT, updated_at TEXT, deprecated_at TEXT
);

CREATE TABLE IF NOT EXISTS kb_entry_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entry_uid TEXT NOT NULL,
  version INTEGER NOT NULL,
  change_type TEXT,
  fields_json TEXT,
  changed_by TEXT,
  change_note TEXT,
  changed_at TEXT
);

CREATE TABLE IF NOT EXISTS kb_cases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  case_uid TEXT UNIQUE NOT NULL,
  domain TEXT DEFAULT '',
  scenario TEXT DEFAULT '',
  description TEXT NOT NULL,
  facts_json TEXT DEFAULT '{}',
  expert_conclusion TEXT NOT NULL,
  expert_reasoning TEXT DEFAULT '',
  difficulty TEXT DEFAULT '',
  tags TEXT DEFAULT '',
  source TEXT DEFAULT '',
  created_at TEXT
);

CREATE TABLE IF NOT EXISTS kb_skill_releases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  skill_slug TEXT NOT NULL,
  version INTEGER NOT NULL,
  pipeline_id TEXT DEFAULT '',
  ir_snapshot_json TEXT NOT NULL,
  skill_md TEXT NOT NULL,
  quality_score REAL,
  replay_hit_rate REAL,
  entry_uids TEXT DEFAULT '',
  released_at TEXT,
  released_by TEXT DEFAULT '',
  UNIQUE(skill_slug, version)
);

CREATE TABLE IF NOT EXISTS kb_validation_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pipeline_id TEXT DEFAULT '',
  skill_slug TEXT DEFAULT '',
  skill_version INTEGER DEFAULT 0,
  case_uids TEXT DEFAULT '',
  total_cases INTEGER DEFAULT 0,
  hits INTEGER DEFAULT 0,
  hit_rate REAL DEFAULT 0,
  mismatches_json TEXT DEFAULT '[]',
  judge_model TEXT DEFAULT '',
  ran_at TEXT
);

CREATE TABLE IF NOT EXISTS kb_verification_cases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  case_uid TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  description TEXT DEFAULT '',
  input_json TEXT NOT NULL,
  expected_output_json TEXT DEFAULT '{}',
  tags TEXT DEFAULT '',
  source TEXT DEFAULT 'manual',
  skill_id TEXT DEFAULT '',
  created_at TEXT,
  updated_at TEXT
);

CREATE TABLE IF NOT EXISTS kb_verification_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_uid TEXT UNIQUE NOT NULL,
  case_id INTEGER DEFAULT 0,
  skill_id TEXT DEFAULT '',
  skill_version TEXT DEFAULT '',
  result_status TEXT DEFAULT '',
  actual_output_json TEXT DEFAULT '{}',
  diff_json TEXT DEFAULT '{}',
  score REAL DEFAULT 0,
  judge_model TEXT DEFAULT '',
  created_at TEXT
);

CREATE TABLE IF NOT EXISTS kb_verification_rules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  rule_type TEXT DEFAULT 'structure',
  rule_json TEXT NOT NULL,
  description TEXT DEFAULT '',
  enabled INTEGER DEFAULT 1
);
"""

_STOPWORDS = {"的", "了", "在", "是", "和", "与", "或", "及", "对", "等", "需", "应", "时"}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_db()
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


# ─── 相似度（第一期：字符 bigram 重叠；接口稳定，可替换语义实现） ──

def _tokenize(text: str) -> set[str]:
    text = re.sub(r"[\s\W]+", "", str(text or ""))
    if not text:
        return set()
    grams = {text[i:i + 2] for i in range(len(text) - 1)}
    return {g for g in grams if g not in _STOPWORDS}


def _similarity(a: str, b: str) -> float:
    ta, tb = _tokenize(a), _tokenize(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    return inter / max(min(len(ta), len(tb)), 1)


def _entry_text(fields: dict) -> str:
    return " ".join(
        str(fields.get(k, "")) for k in ("知识描述", "具体方法", "适用条件", "判断逻辑")
    )


# ─── 知识资产层 ──────────────────────────────────────────────────

def _new_entry_uid(domain: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "", str(domain or "gen").lower())[:8] or "gen"
    return f"KB-{slug}-{uuid.uuid4().hex[:8]}"


def publish_entries(
    ir: dict,
    *,
    pipeline_id: str = "",
    by: str = "",
    skill_md: str = "",
    quality_score: float | None = None,
    replay_hit_rate: float | None = None,
    supersede_threshold: float = 0.7,
) -> dict:
    """Step4 发布：IR 条目逐条入库（新建 / supersede 既有版本），并登记 Skill 发布。

    返回 {created, superseded, unchanged, entry_uids, skill_slug, release_version}。
    """
    init_db()
    meta = (ir or {}).get("skill_meta") or {}
    anchors = (ir or {}).get("anchors") or {}
    domain = str(meta.get("domain") or "").strip()
    scenario = str(anchors.get("scenario") or meta.get("scenario_name") or "").strip()
    skill_slug = str(meta.get("slug") or "").strip() or re.sub(
        r"[^a-z0-9-]+", "-", str(meta.get("scenario_name") or "skill").lower()
    ).strip("-")[:48] or "skill"

    conn = get_db()
    created = superseded = unchanged = 0
    entry_uids: list[str] = []
    now = _now()
    try:
        existing = [dict(r) for r in conn.execute(
            "SELECT * FROM kb_entries WHERE status = 'active' AND domain = ? AND scenario = ?",
            (domain, scenario),
        ).fetchall()]

        for entry in (ir or {}).get("entries") or []:
            fields = dict(entry.get("fields") or {})
            text = _entry_text(fields)
            if not text.strip():
                continue
            confidence = str(fields.get("置信度", ""))
            contributed = str(fields.get("贡献专家", "")) or by
            try:
                evidence = int(str(fields.get("证据数", "0")).strip() or 0)
            except ValueError:
                evidence = 0

            # supersede 预检：同域同场景下语义最相近的 active 条目
            best, best_score = None, 0.0
            for ex in existing:
                try:
                    ex_fields = json.loads(ex.get("fields_json") or "{}")
                except json.JSONDecodeError:
                    ex_fields = {}
                s = _similarity(text, _entry_text(ex_fields))
                if s > best_score:
                    best, best_score = ex, s

            if best is not None and best_score >= supersede_threshold:
                try:
                    same = json.loads(best.get("fields_json") or "{}") == fields
                except json.JSONDecodeError:
                    same = False
                if same:
                    unchanged += 1
                    entry_uids.append(best["entry_uid"])
                    continue
                new_uid = _new_entry_uid(domain)
                new_version = int(best.get("version") or 1) + 1
                conn.execute(
                    "UPDATE kb_entries SET status='superseded', superseded_by=?, updated_at=? WHERE entry_uid=?",
                    (new_uid, now, best["entry_uid"]),
                )
                conn.execute(
                    "INSERT INTO kb_entries (entry_uid, domain, scenario, sub_scenario, category, fields_json,"
                    " status, version, confidence, evidence_count, contributed_by, source_pipeline_id,"
                    " source_skill_slug, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (new_uid, domain, scenario, str(entry.get("sub_scenario") or ""),
                     str(entry.get("category") or ""), json.dumps(fields, ensure_ascii=False),
                     "active", new_version, confidence, evidence, contributed,
                     pipeline_id, skill_slug, now, now),
                )
                conn.execute(
                    "INSERT INTO kb_entry_history (entry_uid, version, change_type, fields_json, changed_by,"
                    " change_note, changed_at) VALUES (?,?,?,?,?,?,?)",
                    (new_uid, new_version, "supersede", json.dumps(fields, ensure_ascii=False),
                     by, f"取代 {best['entry_uid']}（相似度 {best_score:.2f}）", now),
                )
                superseded += 1
                entry_uids.append(new_uid)
                existing = [e for e in existing if e["entry_uid"] != best["entry_uid"]]
            else:
                new_uid = _new_entry_uid(domain)
                conn.execute(
                    "INSERT INTO kb_entries (entry_uid, domain, scenario, sub_scenario, category, fields_json,"
                    " status, version, confidence, evidence_count, contributed_by, source_pipeline_id,"
                    " source_skill_slug, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (new_uid, domain, scenario, str(entry.get("sub_scenario") or ""),
                     str(entry.get("category") or ""), json.dumps(fields, ensure_ascii=False),
                     "active", 1, confidence, evidence, contributed,
                     pipeline_id, skill_slug, now, now),
                )
                conn.execute(
                    "INSERT INTO kb_entry_history (entry_uid, version, change_type, fields_json, changed_by,"
                    " change_note, changed_at) VALUES (?,?,?,?,?,?,?)",
                    (new_uid, 1, "create", json.dumps(fields, ensure_ascii=False), by, "发布入库", now),
                )
                created += 1
                entry_uids.append(new_uid)

        # 登记 Skill 发布版本
        row = conn.execute(
            "SELECT MAX(version) AS v FROM kb_skill_releases WHERE skill_slug = ?", (skill_slug,)
        ).fetchone()
        release_version = int(row["v"] or 0) + 1
        conn.execute(
            "INSERT INTO kb_skill_releases (skill_slug, version, pipeline_id, ir_snapshot_json, skill_md,"
            " quality_score, replay_hit_rate, entry_uids, released_at, released_by)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (skill_slug, release_version, pipeline_id,
             json.dumps(ir, ensure_ascii=False), skill_md or "",
             quality_score, replay_hit_rate,
             json.dumps(entry_uids, ensure_ascii=False), now, by),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "created": created,
        "superseded": superseded,
        "unchanged": unchanged,
        "entry_uids": entry_uids,
        "skill_slug": skill_slug,
        "release_version": release_version,
    }


def search_entries(
    domain: str = "",
    scenario: str = "",
    query: str = "",
    *,
    top_k: int = 20,
    status: str = "active",
) -> list[dict]:
    """检索知识条目：domain/scenario 过滤 + query 词重叠重排。"""
    init_db()
    conn = get_db()
    try:
        sql = "SELECT * FROM kb_entries WHERE 1=1"
        params: list = []
        if status:
            sql += " AND status = ?"
            params.append(status)
        if domain:
            sql += " AND domain = ?"
            params.append(domain)
        if scenario:
            sql += " AND scenario = ?"
            params.append(scenario)
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()

    # 域/场景无精确命中时放宽到全库（跨场景复用）
    if not rows and (domain or scenario):
        return search_entries("", "", query or scenario or domain, top_k=top_k, status=status)

    results = []
    for r in rows:
        try:
            fields = json.loads(r.get("fields_json") or "{}")
        except json.JSONDecodeError:
            fields = {}
        r["fields"] = fields
        r.pop("fields_json", None)
        r["_score"] = _similarity(query, _entry_text(fields)) if query else 0.0
        results.append(r)
    if query:
        results.sort(key=lambda x: x["_score"], reverse=True)
    else:
        results.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
    return results[:top_k]


def import_entries_as_records(entry_uids: list[str]) -> list[dict]:
    """KB 条目 → 标准 records（注入 Step2 作为继承源参与融合）。"""
    if not entry_uids:
        return []
    init_db()
    conn = get_db()
    try:
        placeholders = ",".join("?" for _ in entry_uids)
        rows = [dict(r) for r in conn.execute(
            f"SELECT * FROM kb_entries WHERE entry_uid IN ({placeholders})", list(entry_uids)
        ).fetchall()]
    finally:
        conn.close()
    records = []
    for r in rows:
        try:
            fields = json.loads(r.get("fields_json") or "{}")
        except json.JSONDecodeError:
            fields = {}
        rec = dict(fields)
        rec["知识分类"] = r.get("category") or rec.get("知识分类", "")
        rec["子场景"] = r.get("sub_scenario") or rec.get("子场景", "")
        rec["kb_entry_id"] = r.get("entry_uid")
        rec["_origin"] = "kb_import"
        rec["source_label"] = f"知识库继承（{r.get('entry_uid')}）"
        records.append(rec)
    return records


def deprecate_entry(entry_uid: str, *, note: str = "", by: str = "") -> bool:
    init_db()
    conn = get_db()
    now = _now()
    try:
        row = conn.execute(
            "SELECT version FROM kb_entries WHERE entry_uid = ? AND status != 'deprecated'", (entry_uid,)
        ).fetchone()
        if not row:
            return False
        conn.execute(
            "UPDATE kb_entries SET status='deprecated', deprecated_at=?, updated_at=? WHERE entry_uid=?",
            (now, now, entry_uid),
        )
        conn.execute(
            "INSERT INTO kb_entry_history (entry_uid, version, change_type, fields_json, changed_by,"
            " change_note, changed_at) VALUES (?,?,?,?,?,?,?)",
            (entry_uid, int(row["version"] or 1), "deprecate", "", by, note or "标记失效", now),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def get_entry_timeline(entry_uid: str) -> list[dict]:
    init_db()
    conn = get_db()
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM kb_entry_history WHERE entry_uid = ? ORDER BY id ASC", (entry_uid,)
        ).fetchall()]
    finally:
        conn.close()
    return rows


# ─── 案例库 ──────────────────────────────────────────────────────

def add_case(
    description: str,
    expert_conclusion: str,
    *,
    domain: str = "",
    scenario: str = "",
    facts: dict | None = None,
    expert_reasoning: str = "",
    difficulty: str = "",
    tags: str = "",
    source: str = "",
) -> str:
    """录入历史案例，返回 case_uid。"""
    if not str(description or "").strip() or not str(expert_conclusion or "").strip():
        raise ValueError("案例描述与专家结论均不能为空")
    init_db()
    case_uid = f"CASE-{uuid.uuid4().hex[:8]}"
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO kb_cases (case_uid, domain, scenario, description, facts_json, expert_conclusion,"
            " expert_reasoning, difficulty, tags, source, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (case_uid, domain, scenario, description,
             json.dumps(facts or {}, ensure_ascii=False), expert_conclusion,
             expert_reasoning, difficulty, tags, source, _now()),
        )
        conn.commit()
    finally:
        conn.close()
    return case_uid


def list_cases(
    *,
    domain: str = "",
    scenario: str = "",
    difficulty: str = "",
    limit: int = 20,
) -> list[dict]:
    init_db()
    conn = get_db()
    try:
        sql = "SELECT * FROM kb_cases WHERE 1=1"
        params: list = []
        if domain:
            sql += " AND domain = ?"
            params.append(domain)
        if scenario:
            sql += " AND scenario = ?"
            params.append(scenario)
        if difficulty:
            sql += " AND difficulty = ?"
            params.append(difficulty)
        # 优先 hard/edge 案例（验证弹药价值更高），再按时间倒序
        sql += " ORDER BY CASE difficulty WHEN 'edge' THEN 0 WHEN 'hard' THEN 1 ELSE 2 END, id DESC LIMIT ?"
        params.append(int(limit))
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()
    # 域/场景过滤无结果时放宽（小库阶段避免空集）
    if not rows and (domain or scenario):
        return list_cases(difficulty=difficulty, limit=limit)
    for r in rows:
        try:
            r["facts"] = json.loads(r.pop("facts_json", "{}") or "{}")
        except json.JSONDecodeError:
            r["facts"] = {}
    return rows


# ─── 验证运行记录 / 发布列表 ─────────────────────────────────────

def record_validation_run(
    *,
    pipeline_id: str = "",
    skill_slug: str = "",
    skill_version: int = 0,
    case_uids: list | None = None,
    total_cases: int = 0,
    hits: int = 0,
    hit_rate: float = 0.0,
    mismatches: list | None = None,
    judge_model: str = "",
) -> None:
    init_db()
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO kb_validation_runs (pipeline_id, skill_slug, skill_version, case_uids, total_cases,"
            " hits, hit_rate, mismatches_json, judge_model, ran_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (pipeline_id, skill_slug, int(skill_version), json.dumps(case_uids or [], ensure_ascii=False),
             int(total_cases), int(hits), float(hit_rate),
             json.dumps(mismatches or [], ensure_ascii=False)[:20000], judge_model, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def list_releases(skill_slug: str = "", limit: int = 20) -> list[dict]:
    init_db()
    conn = get_db()
    try:
        if skill_slug:
            rows = conn.execute(
                "SELECT id, skill_slug, version, pipeline_id, quality_score, replay_hit_rate, released_at,"
                " released_by FROM kb_skill_releases WHERE skill_slug = ? ORDER BY id DESC LIMIT ?",
                (skill_slug, int(limit)),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, skill_slug, version, pipeline_id, quality_score, replay_hit_rate, released_at,"
                " released_by FROM kb_skill_releases ORDER BY id DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ─── 验证知识库（用于验证 agent-skill）────────────────────────────────

def _new_verification_case_uid() -> str:
    return f"VC-{uuid.uuid4().hex[:8]}"


def _new_verification_run_uid() -> str:
    return f"VR-{uuid.uuid4().hex[:8]}"


def add_verification_case(
    name: str,
    input_data: dict,  # 写入 input_json；list/get 返回字段为 input，供前端消费
    *,
    description: str = "",
    expected_output: dict | None = None,
    tags: str = "",
    source: str = "manual",
    skill_id: str = "",
) -> str:
    if not str(name or "").strip():
        raise ValueError("测试用例名称不能为空")
    if not isinstance(input_data, dict):
        raise ValueError("input 必须是 dict")
    init_db()
    case_uid = _new_verification_case_uid()
    now = _now()
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO kb_verification_cases (case_uid, name, description, input_json, expected_output_json,"
            " tags, source, skill_id, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (case_uid, name, description,
             json.dumps(input_data, ensure_ascii=False),
             json.dumps(expected_output or {}, ensure_ascii=False),
             tags, source, skill_id, now, now),
        )
        conn.commit()
    finally:
        conn.close()
    return case_uid


def update_verification_case(case_uid: str, **fields) -> bool:
    allowed = {"name", "description", "input_json", "expected_output_json", "tags", "source", "skill_id"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return False
    if "input_json" in updates and not isinstance(updates["input_json"], (dict, list, str)):
        updates["input_json"] = dict(updates["input_json"])
    if "expected_output_json" in updates and not isinstance(updates["expected_output_json"], (dict, list, str)):
        updates["expected_output_json"] = dict(updates["expected_output_json"])
    for k in ("input_json", "expected_output_json"):
        if k in updates and isinstance(updates[k], (dict, list)):
            updates[k] = json.dumps(updates[k], ensure_ascii=False)
    init_db()
    conn = get_db()
    try:
        set_clause = ", ".join(f"{k}=?" for k in updates)
        params = list(updates.values()) + [_now(), case_uid]
        cur = conn.execute(f"UPDATE kb_verification_cases SET {set_clause}, updated_at=? WHERE case_uid=?", params)
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def delete_verification_case(case_uid: str) -> bool:
    init_db()
    conn = get_db()
    try:
        # 级联删除关联运行记录
        case = conn.execute("SELECT id FROM kb_verification_cases WHERE case_uid=?", (case_uid,)).fetchone()
        if case:
            conn.execute("DELETE FROM kb_verification_runs WHERE case_id=?", (case["id"],))
        cur = conn.execute("DELETE FROM kb_verification_cases WHERE case_uid=?", (case_uid,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def list_verification_cases(
    *,
    skill_id: str = "",
    source: str = "",
    tags: str = "",
    limit: int = 100,
) -> list[dict]:
    init_db()
    conn = get_db()
    try:
        sql = "SELECT * FROM kb_verification_cases WHERE 1=1"
        params: list = []
        if skill_id:
            sql += " AND skill_id = ?"
            params.append(skill_id)
        if source:
            sql += " AND source = ?"
            params.append(source)
        if tags:
            sql += " AND tags LIKE ?"
            params.append(f"%{tags}%")
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(int(limit))
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()
    for r in rows:
        for k in ("input_json", "expected_output_json"):
            try:
                r[k.replace("_json", "")] = json.loads(r.pop(k, "{}") or "{}")
            except (json.JSONDecodeError, TypeError):
                r[k.replace("_json", "")] = {}
    return rows


def get_verification_case(case_uid: str) -> dict | None:
    init_db()
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM kb_verification_cases WHERE case_uid=?", (case_uid,)).fetchone()
        if not row:
            return None
        r = dict(row)
    finally:
        conn.close()
    for k in ("input_json", "expected_output_json"):
        try:
            r[k.replace("_json", "")] = json.loads(r.pop(k, "{}") or "{}")
        except (json.JSONDecodeError, TypeError):
            r[k.replace("_json", "")] = {}
    return r


def add_verification_run(
    case_id: int,
    *,
    skill_id: str = "",
    skill_version: str = "",
    result_status: str = "",
    actual_output: dict | None = None,
    diff: dict | None = None,
    score: float = 0.0,
    judge_model: str = "",
) -> str:
    init_db()
    run_uid = _new_verification_run_uid()
    now = _now()
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO kb_verification_runs (run_uid, case_id, skill_id, skill_version, result_status,"
            " actual_output_json, diff_json, score, judge_model, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (run_uid, int(case_id), skill_id, skill_version, result_status,
             json.dumps(actual_output or {}, ensure_ascii=False),
             json.dumps(diff or {}, ensure_ascii=False),
             float(score), judge_model, now),
        )
        conn.commit()
    finally:
        conn.close()
    return run_uid


def list_verification_runs(
    *,
    case_id: int = 0,
    skill_id: str = "",
    limit: int = 100,
) -> list[dict]:
    init_db()
    conn = get_db()
    try:
        sql = "SELECT * FROM kb_verification_runs WHERE 1=1"
        params: list = []
        if case_id:
            sql += " AND case_id = ?"
            params.append(case_id)
        if skill_id:
            sql += " AND skill_id = ?"
            params.append(skill_id)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(int(limit))
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()
    for r in rows:
        for k in ("actual_output_json", "diff_json"):
            try:
                r[k.replace("_json", "")] = json.loads(r.pop(k, "{}") or "{}")
            except (json.JSONDecodeError, TypeError):
                r[k.replace("_json", "")] = {}
        r["status"] = r.get("result_status", "")
    return rows


def get_verification_run(run_uid: str) -> dict | None:
    init_db()
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM kb_verification_runs WHERE run_uid=?", (run_uid,)).fetchone()
        if not row:
            return None
        r = dict(row)
    finally:
        conn.close()
    for k in ("actual_output_json", "diff_json"):
        try:
            r[k.replace("_json", "")] = json.loads(r.pop(k, "{}") or "{}")
        except (json.JSONDecodeError, TypeError):
            r[k.replace("_json", "")] = {}
    r["status"] = r.get("result_status", "")
    return r


def add_verification_rule(
    name: str,
    rule: dict,
    *,
    rule_type: str = "structure",
    description: str = "",
    enabled: bool = True,
) -> int:
    if not str(name or "").strip():
        raise ValueError("规则名称不能为空")
    if not isinstance(rule, dict):
        raise ValueError("rule 必须是 dict")
    init_db()
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO kb_verification_rules (name, rule_type, rule_json, description, enabled)"
            " VALUES (?,?,?,?,?)",
            (name, rule_type, json.dumps(rule, ensure_ascii=False), description, 1 if enabled else 0),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_verification_rules(
    *,
    rule_type: str = "",
    enabled_only: bool = False,
    limit: int = 100,
) -> list[dict]:
    init_db()
    conn = get_db()
    try:
        sql = "SELECT * FROM kb_verification_rules WHERE 1=1"
        params: list = []
        if rule_type:
            sql += " AND rule_type = ?"
            params.append(rule_type)
        if enabled_only:
            sql += " AND enabled = 1"
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(int(limit))
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()
    for r in rows:
        r["enabled"] = bool(r.get("enabled"))
        try:
            r["rule"] = json.loads(r.pop("rule_json", "{}") or "{}")
        except (json.JSONDecodeError, TypeError):
            r["rule"] = {}
    return rows


# ─── CLI ─────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="外部知识库管理")
    parser.add_argument("--init", action="store_true", help="初始化数据库")
    parser.add_argument("--stats", action="store_true", help="统计概览")
    args = parser.parse_args()

    if args.init:
        init_db()
        print(f"KB initialized at {DB_PATH}")
    if args.stats:
        init_db()
        conn = get_db()
        try:
            for table in ("kb_entries", "kb_cases", "kb_skill_releases", "kb_validation_runs"):
                n = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
                print(f"{table}: {n}")
        finally:
            conn.close()


if __name__ == "__main__":
    main()

"""Knowledge base business services."""

from __future__ import annotations


def search_entries(domain: str, scenario: str, query: str, top_k: int, status: str) -> dict:
    import knowledge_base as kb
    entries = kb.search_entries(
        domain=domain,
        scenario=scenario,
        query=query,
        top_k=top_k,
        status=status,
    )
    return {"status": "ok", "entries": entries, "total": len(entries)}


def import_entries(entry_uids: list) -> dict:
    import knowledge_base as kb
    records = kb.import_entries_as_records([str(u) for u in entry_uids])
    return {"status": "ok", "records": records, "count": len(records)}


def publish(pipeline_id: str, by: str, workspace, resolve_knowledge_ir_path, safe_workspace_path) -> dict:
    import knowledge_base as kb
    from skill_ir import STATUS_PUBLISHED, load_ir, mark_status, save_ir

    sd = {}
    from shared import _pipelines_lock, load_pipelines, save_pipelines
    with _pipelines_lock:
        pipelines = load_pipelines()
        for p in pipelines:
            if p["id"] == pipeline_id:
                sd = p.get("step_data", {}) or {}
                break

    ir_path, _key = resolve_knowledge_ir_path(workspace, sd)
    if not ir_path:
        return {"status": "error", "error": "未找到 Skill 草稿（IR），无法发布"}

    skill_md = ""
    skill_file = sd.get("step4_skill_file", "")
    if skill_file:
        sp = safe_workspace_path(workspace, skill_file, must_exist=True)
        if sp:
            try:
                skill_md = sp.read_text(encoding="utf-8")
            except Exception:
                skill_md = ""

    ir = load_ir(ir_path)
    result = kb.publish_entries(
        ir,
        pipeline_id=pipeline_id,
        by=by,
        skill_md=skill_md,
        quality_score=None,
        replay_hit_rate=sd.get("step5_hit_rate"),
    )
    published_ir = mark_status(ir, STATUS_PUBLISHED)
    try:
        pub_name = save_ir(workspace, published_ir, pipeline_id=pipeline_id)
        with _pipelines_lock:
            pipelines = load_pipelines()
            for p in pipelines:
                if p["id"] == pipeline_id:
                    sd2 = p.setdefault("step_data", {})
                    sd2["step3_aligned_file"] = pub_name
                    sd2["step3_aligned_url"] = f"/downloads/{pub_name}"
                    save_pipelines(pipelines)
                    break
    except Exception:
        pass
    result["status"] = "ok"
    return result


def deprecate(entry_uid: str, note: str, by: str) -> dict:
    import knowledge_base as kb
    ok = kb.deprecate_entry(entry_uid, note=note, by=by)
    if not ok:
        return {"status": "error", "error": "条目不存在或已失效"}
    return {"status": "ok"}


def timeline(entry_uid: str) -> dict:
    import knowledge_base as kb
    return {"status": "ok", "timeline": kb.get_entry_timeline(entry_uid)}


def list_cases(domain: str, scenario: str, difficulty: str, limit: int) -> dict:
    import knowledge_base as kb
    cases = kb.list_cases(domain=domain, scenario=scenario, difficulty=difficulty, limit=limit)
    return {"status": "ok", "cases": cases, "total": len(cases)}


def add_cases(raw_cases: list) -> dict:
    import knowledge_base as kb
    uids = []
    errors = []
    for c in raw_cases:
        if not isinstance(c, dict):
            continue
        try:
            uid = kb.add_case(
                description=c.get("description", "") or c.get("场景", ""),
                expert_conclusion=c.get("expert_conclusion", "") or c.get("结论", "") or c.get("conclusion", ""),
                domain=c.get("domain", ""),
                scenario=c.get("scenario", ""),
                facts=c.get("facts") if isinstance(c.get("facts"), dict) else None,
                expert_reasoning=c.get("expert_reasoning", ""),
                difficulty=c.get("difficulty", ""),
                tags=c.get("tags", ""),
                source=c.get("source", ""),
            )
            uids.append(uid)
        except ValueError as ve:
            errors.append(str(ve))
    return {"status": "ok", "case_uids": uids, "created": len(uids), "errors": errors}


def list_releases(skill_slug: str, limit: int) -> dict:
    import knowledge_base as kb
    releases = kb.list_releases(skill_slug=skill_slug, limit=limit)
    return {"status": "ok", "releases": releases, "total": len(releases)}


def list_test_customers(source: str | None, limit: int) -> dict:
    import knowledge_base as kb
    customers = kb.list_test_customers(source=source, limit=limit)
    return {"status": "ok", "customers": customers, "total": len(customers)}


def insert_test_customers(customers: list) -> dict:
    import knowledge_base as kb
    count = kb.insert_test_customers(customers)
    return {"status": "ok", "created": count}


def delete_test_customers(source: str) -> dict:
    import knowledge_base as kb
    count = kb.delete_test_customers(source=source)
    return {"status": "ok", "deleted": count}

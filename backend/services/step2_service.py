"""Step2 知识萃取业务服务."""

from __future__ import annotations

import datetime
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from pipeline_artifacts import (
    basename_only,
    infer_file_step,
    is_skill_draft_filename,
    is_step2_preextract_filename,
    locate_workspace_file,
    resolve_cache_file_path,
    safe_workspace_path,
    workspace_path_for,
)
from shared import (
    _debug_log,
    _pipelines_lock,
    _safe_workbook,
    EXTRACT_STYLE_RULES,
    extract_text_from_file,
    extract_text_from_path,
    get_model_by_name,
    load_llm_config,
    load_pipelines,
    save_pipelines,
    SCHEMA_PATH,
    _parse_extracted_items,
    _normalize_extracted_items,
    _align_item_keys_to_template,
    _extract_json_from_text,
    _pipeline_prefers_markdown,
    call_llm_with_retry,
    extract_assistant_content,
)
from knowledge_fusion import (
    aggregate_signals,
    detect_conflicts,
    detect_duplicates,
    merge_extraction_results,
)


def resolve_step1_workbook_path(pipeline_id: str, workspace: Path) -> Path | None:
    """从流水线 step_data 解析 Step1 场景骨架 Excel 路径."""
    if not pipeline_id:
        return None
    with _pipelines_lock:
        pipelines = load_pipelines()
        for p in pipelines:
            if p["id"] == pipeline_id:
                step1_file = p.get("step_data", {}).get("step1_output_file", "")
                if step1_file:
                    resolved = locate_workspace_file(workspace, step1_file, pipeline_id=pipeline_id)
                    if resolved:
                        return resolved
                break
    return None


def step1_knowledge_columns_from_pipeline(pipeline_id: str) -> list[str]:
    if not pipeline_id:
        return []
    with _pipelines_lock:
        pipelines = load_pipelines()
        for p in pipelines:
            if p["id"] == pipeline_id:
                cols = p.get("step_data", {}).get("step1_knowledge_columns") or []
                if isinstance(cols, list):
                    return [str(c).strip() for c in cols if str(c).strip()]
                return []
    return []


def extract_step2_template_context(pipeline_id: str, workspace: Path) -> dict:
    """Read Step1 template headers and produce Step2 target keys + stage chain."""
    from step1_template import detect_header_rows, find_anchor_columns

    step1_path = resolve_step1_workbook_path(pipeline_id, workspace)
    if not step1_path or not Path(step1_path).exists():
        return {
            "target_columns": step1_knowledge_columns_from_pipeline(pipeline_id),
            "stage_chain": [],
        }

    try:
        with _safe_workbook(step1_path) as wb:
            ws = wb[wb.sheetnames[0]]
            anchor_cols = find_anchor_columns(ws)
            anchor_col_set = set(anchor_cols.values())
            header_rows = detect_header_rows(ws)

            cols = []
            seen = set()
            stage_col = None
            stage_chain = []
            for c in range(1, (ws.max_column or 1) + 1):
                if c in anchor_col_set:
                    continue
                h1 = str(ws.cell(1, c).value).strip() if ws.cell(1, c).value else ""
                h2 = str(ws.cell(2, c).value).strip() if header_rows >= 2 and ws.cell(2, c).value else ""
                if h1 and h2 and h1 != h2:
                    key = f"{h1}-{h2}"
                else:
                    key = h2 or h1
                if not key:
                    continue
                if any(m in key for m in ("步骤", "环节", "stage", "phase")):
                    stage_col = c
                if key not in seen:
                    seen.add(key)
                    cols.append(key)

            if stage_col:
                seen_stages = set()
                for r in range(header_rows + 1, (ws.max_row or header_rows) + 1):
                    v = ws.cell(r, stage_col).value
                    if not v:
                        continue
                    stage = str(v).strip()
                    if stage and stage not in seen_stages:
                        seen_stages.add(stage)
                        stage_chain.append(stage)

        if len(cols) < 3:
            fallback = step1_knowledge_columns_from_pipeline(pipeline_id)
            if len(fallback) > len(cols):
                return {"target_columns": fallback, "stage_chain": stage_chain}
        return {"target_columns": cols, "stage_chain": stage_chain}
    except Exception:
        return {
            "target_columns": step1_knowledge_columns_from_pipeline(pipeline_id),
            "stage_chain": [],
        }


def extract_step2_target_columns(pipeline_id: str, workspace: Path) -> list[str]:
    """兼容旧接口：只返回 target_columns."""
    return extract_step2_template_context(pipeline_id, workspace).get("target_columns", [])


def _normalize_extract_style(style: str) -> str:
    style = (style or "").strip()
    return style if style in EXTRACT_STYLE_RULES else "标准萃取"


def _pick_text(item: dict, keys: tuple[str, ...]) -> str:
    for k in keys:
        v = item.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return ""


def _extract_item_content(item: dict, target_columns: list | None = None) -> str:
    """提取条目的代表性文本内容."""
    if target_columns:
        structural_markers = ("步骤", "阶段", "环节", "stage", "phase", "step")
        for col in target_columns:
            if any(m in col.lower() for m in structural_markers):
                continue
            v = item.get(col)
            if v is not None and str(v).strip():
                return str(v).strip()
        for col in target_columns:
            if any(m in col.lower() for m in structural_markers):
                continue
            suffix = col.split("-")[-1].strip() if "-" in col else ""
            if not suffix:
                continue
            for k, v in item.items():
                if v is not None and str(v).strip() and (str(k).endswith(suffix) or suffix in str(k)):
                    return str(v).strip()
        for col in target_columns:
            v = item.get(col)
            if v is not None and str(v).strip():
                return str(v).strip()

    text = _pick_text(
        item,
        (
            "content", "知识描述", "知识内容", "具体方法",
            "category", "知识分类", "步骤", "名称", "描述",
            "trigger_condition", "适用条件", "触发条件",
            "excerpt", "原文摘录", "知识引用",
        ),
    )
    if text:
        return text

    for k, v in item.items():
        if v is None:
            continue
        key = str(k or "")
        if not key:
            continue
        s = str(v).strip()
        if not s:
            continue
        if any(mark in key for mark in ("名称", "描述", "内容", "步骤", "方法", "输出", "逻辑", "条件", "引用")):
            return s

    for v in item.values():
        if isinstance(v, (dict, list)):
            continue
        s = str(v).strip()
        if s:
            return s
    return ""


def _extract_item_confidence_rank(item: dict) -> int:
    conf = _pick_text(item, ("confidence", "置信度")).lower()
    if "高" in conf or "high" in conf:
        return 3
    if "中" in conf or "medium" in conf or "med" in conf:
        return 2
    if "低" in conf or "low" in conf:
        return 1
    return 2


def _extract_item_richness(item: dict) -> int:
    keys = (
        "category", "知识分类", "步骤",
        "content", "知识描述", "知识内容", "具体方法",
        "trigger_condition", "适用条件", "触发条件", "访谈方向",
        "judgment_logic", "判断逻辑", "规则引用",
        "anti_pattern", "反模式", "反模式/踩坑提示", "描述",
        "source", "来源", "来源文档",
        "confidence", "置信度",
        "excerpt", "原文摘录", "知识引用",
    )
    seen_values = set()
    richness = 0
    for k in keys:
        v = item.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if not s:
            continue
        if s in seen_values:
            continue
        seen_values.add(s)
        richness += 1
    return richness


def _apply_extract_style_rules(items: list, style: str, target_columns: list | None = None) -> tuple[list, dict]:
    """Deterministic post-processing so style differences are stable."""
    style = _normalize_extract_style(style)
    rule = EXTRACT_STYLE_RULES[style]
    template_mode = bool(target_columns)

    candidates = []
    seen = set()
    for raw in items or []:
        if not isinstance(raw, dict):
            if isinstance(raw, (str, int, float, bool)):
                raw = {"content": str(raw)}
            else:
                continue
        text = _extract_item_content(raw, target_columns)
        if not text:
            continue
        key = "".join(text.lower().split())
        if key in seen:
            continue
        seen.add(key)

        conf_rank = _extract_item_confidence_rank(raw)
        richness = _extract_item_richness(raw)

        if style == "精简萃取" and not template_mode:
            if conf_rank < 2:
                continue
            if richness < 3 and len(text) < 24:
                continue
        elif style == "精简萃取" and template_mode and len(text) < 8:
            continue

        if style == "深度萃取":
            score = (richness, conf_rank, len(text))
        elif style == "精简萃取":
            score = (conf_rank, richness, -len(text))
        else:
            score = (conf_rank, richness, len(text))
        candidates.append((score, raw))

    candidates.sort(key=lambda x: x[0], reverse=True)
    processed = [x[1] for x in candidates[: rule["max_items"]]]

    fallback_applied = False
    if not processed and candidates:
        processed = [x[1] for x in candidates[: rule["max_items"]]]
        fallback_applied = True

    stats = {
        "raw_count": len(items or []),
        "candidate_count": len(candidates),
        "processed_count": len(processed),
        "fallback_applied": fallback_applied,
        "min_items": rule["min_items"],
        "max_items": rule["max_items"],
    }
    return processed, stats


def _normalize_stage_values(records: list, stage_chain: list[str]) -> list:
    """将 LLM 输出的「步骤」字段规范化到模板定义的阶段链之一."""
    if not stage_chain:
        return records
    import re

    def _clean_stage(s: str) -> str:
        return re.sub(r"^\d+[.．、\s]+", "", str(s).strip())

    canonical_stages = [_clean_stage(s) for s in stage_chain]
    stage_aliases: dict[str, str] = {}
    for raw, clean in zip(stage_chain, canonical_stages):
        stage_aliases[raw] = clean
        stage_aliases[clean] = clean
        num = re.match(r"^(\d+)", raw)
        if num:
            stage_aliases[num.group(1)] = clean
            stage_aliases[f"{num.group(1)}.{clean}"] = clean
            stage_aliases[f"{num.group(1)}、{clean}"] = clean

    stage_keys = {"步骤", "stage", "step", "阶段"}
    category_keys = {"知识分类", "category", "知识类型", "分类"}

    for rec in records:
        if not isinstance(rec, dict):
            continue
        for key in list(rec.keys()):
            if key in stage_keys or any(m in key for m in stage_keys):
                val = str(rec.get(key, "")).strip()
                if not val:
                    continue
                if val in stage_aliases:
                    rec[key] = stage_aliases[val]
                else:
                    rec[key] = ""
                    for cat_key in category_keys:
                        if cat_key not in rec or not str(rec.get(cat_key, "")).strip():
                            rec[cat_key] = val
                            break
    return records


def _pipeline_scenario_meta(pipeline_id: str) -> dict:
    """收集 Skill IR 所需的场景元数据（Step1 表单 + 流水线属性）."""
    if not pipeline_id:
        return {}
    with _pipelines_lock:
        pipelines = load_pipelines()
        for p in pipelines:
            if p["id"] == pipeline_id:
                sd = p.get("step_data", {}) or {}
                form = sd.get("step1_form_data", {}) or {}
                return {
                    "scenario_name": form.get("scenario_name") or p.get("scenario", "") or p.get("name", ""),
                    "scenario_content": form.get("scenario_content", ""),
                    "sub_scenarios": form.get("sub_scenarios") or [],
                    "domain": p.get("domain", ""),
                }
    return {}


def _write_step2_preextract_excel(workspace: Path, pipeline_id: str, extracted_items: list, sub_scenarios: list | None = None):
    from step2_preextract import write_preextract_excel

    step1_path = resolve_step1_workbook_path(pipeline_id, workspace)
    output_name = f"preextract_{uuid.uuid4().hex[:8]}.xlsx"
    output_path = workspace_path_for(workspace, pipeline_id, "step2", output_name)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    meta = write_preextract_excel(
        step1_path=step1_path,
        output_path=output_path,
        items=extracted_items or [],
        pipeline_id=pipeline_id,
        sub_scenarios=sub_scenarios,
    )
    return output_name, meta


def _persist_step2_excel_pipeline(
    pipeline_id: str,
    output_name: str,
    extracted_text: str,
    style: str,
    count: int,
    *,
    md_name: str = "",
    md_url: str = "",
):
    if not pipeline_id:
        return
    if not is_step2_preextract_filename(output_name):
        raise ValueError(f"Step2 输出文件名非法（不得使用场景骨架 template_ 文件）: {output_name}")
    with _pipelines_lock:
        pipelines = load_pipelines()
        for p in pipelines:
            if p["id"] == pipeline_id:
                sd = p.setdefault("step_data", {})
                sd["skill_extract_result"] = extracted_text
                sd["skill_extract_style"] = style
                sd["step2_output_file"] = output_name
                sd["step2_download_url"] = f"/downloads/{output_name}"
                if md_name:
                    sd["step2_md_file"] = md_name
                    sd["step2_md_download_url"] = md_url or f"/downloads/{md_name}"
                else:
                    sd.pop("step2_md_file", None)
                    sd.pop("step2_md_download_url", None)
                sd["step2_extracted_count"] = count
                for stale in ("step2_preview_name", "step2_preview_url"):
                    sd.pop(stale, None)
                p.setdefault("step_status", {})
                p["step_status"]["2"] = "done"
                if p["step_status"].get("3", "pending") == "pending":
                    p["step_status"]["3"] = "active"
                p["current_step"] = max(p.get("current_step", 1), 3)
                p["updated_at"] = datetime.datetime.now().isoformat()
                save_pipelines(pipelines)
                break


def _persist_step2_skill_draft(
    workspace: Path,
    pipeline_id: str,
    records: list,
    *,
    signals: dict | None = None,
    origin: str = "doc_extract",
) -> dict:
    """Step2 主产物：从萃取 records 组装 Skill IR v1 草稿并落盘 + 渲染 md 预览."""
    if not records:
        return {}
    try:
        from skill_ir import new_draft, render_skill_md, save_ir

        meta = _pipeline_scenario_meta(pipeline_id)
        ir = new_draft(
            meta, records,
            signals=signals or {},
            origin=origin,
            pipeline_id=pipeline_id,
        )
        draft_name = save_ir(workspace, ir, pipeline_id=pipeline_id)

        md_name, md_url = "", ""
        try:
            config = {}
            if SCHEMA_PATH.exists():
                from excel_to_skill import load_scenario_config
                config = load_scenario_config(str(SCHEMA_PATH))
            md_content = render_skill_md(ir, config)
            md_name = f"SKILL_draft_{uuid.uuid4().hex[:8]}.md"
            md_path = workspace_path_for(workspace, pipeline_id, "step2", md_name)
            md_path.parent.mkdir(parents=True, exist_ok=True)
            md_path.write_text(md_content, encoding="utf-8")
            md_url = f"/downloads/{md_name}"
        except Exception as e:
            _debug_log("E", "_persist_step2_skill_draft", "render_error", str(e)[-200:])
            md_name, md_url = "", ""

        info = {
            "draft_file": draft_name,
            "draft_url": f"/downloads/{draft_name}",
            "draft_md_file": md_name,
            "draft_md_url": md_url,
            "draft_version": 1,
        }
        with _pipelines_lock:
            pipelines = load_pipelines()
            for p in pipelines:
                if p.get("id") == pipeline_id:
                    sd = p.setdefault("step_data", {})
                    sd["step2_draft_file"] = draft_name
                    sd["step2_draft_url"] = info["draft_url"]
                    sd["step2_draft_version"] = 1
                    if md_name:
                        sd["step2_draft_md_file"] = md_name
                        sd["step2_draft_md_url"] = md_url
                    else:
                        sd.pop("step2_draft_md_file", None)
                        sd.pop("step2_draft_md_url", None)
                    save_pipelines(pipelines)
                    break
        return info
    except Exception as e:
        _debug_log("E", "_persist_step2_skill_draft", "draft_error", str(e)[-200:])
        return {}


def execute_knowledge_extraction(request) -> dict:
    """知识萃取 Skill 执行."""
    from release_info import STEP2_EXCEL_BUILD

    skill_id = request.form.get("skill_id", "knowledge-extraction")
    info = {"name": "知识萃取"}
    model_name = request.form.get("model", "")
    style = _normalize_extract_style(request.form.get("style", "标准萃取"))
    style_rule = EXTRACT_STYLE_RULES[style]
    pipeline_id = request.form.get("pipeline_id", "")
    content = request.form.get("content", "")
    source_file = request.files.get("file")
    cached_file = os.path.basename(request.form.get("cached_file", "").strip())

    if not content and not source_file and not cached_file:
        return {"status": "error", "error": "请提供文档内容或上传文件"}
    _debug_log(
        "H2",
        "services.step2_service:execute_knowledge_extraction",
        "step2 extraction start",
        {"has_content": bool(content), "has_upload": bool(source_file), "has_cached_file": bool(cached_file)},
    )

    if not model_name:
        models_list = load_llm_config()
        if models_list:
            model_name = models_list[0]["name"]
    model_cfg = get_model_by_name(model_name)
    if not model_cfg:
        return {"status": "error", "error": f"模型 '{model_name}' 不存在或无可用模型"}

    doc_text = content
    if source_file and not doc_text:
        try:
            doc_text = extract_text_from_file(source_file)
        except Exception:
            return {"status": "error", "error": "文件读取失败"}
    elif cached_file and not doc_text:
        cached_path = resolve_cache_file_path(Path(str(__import__("app_server").WORKSPACE)), cached_file)
        if cached_path:
            try:
                doc_text = extract_text_from_path(str(cached_path))
            except Exception:
                pass

    workspace = Path(__import__("app_server").WORKSPACE)
    template_ctx = extract_step2_template_context(pipeline_id, workspace)
    target_columns = template_ctx.get("target_columns", [])
    stage_chain = template_ctx.get("stage_chain", [])
    max_tokens = style_rule["max_tokens"]
    if target_columns:
        max_tokens = max(max_tokens, 6144 if len(target_columns) > 10 else 5120)

    content_type = (request.form.get("content_type", "") or "").strip()
    if content_type and content_type != "doc":
        return {"status": "error", "error": f"不支持的内容类型 '{content_type}'，仅支持 'doc' 模式"}

    if target_columns:
        target_cols_json = json.dumps(target_columns, ensure_ascii=False)
        example_obj = {k: "" for k in target_columns}
        content_key = next(
            (k for k in target_columns if any(m in k for m in ("方法", "描述", "内容", "引用"))),
            target_columns[0],
        )
        example_obj[content_key] = "（示例：从文档抽取的一条可执行知识）"
        example_json = json.dumps([example_obj], ensure_ascii=False)

        stage_hint = ""
        item_count_hint = f"输出条数尽量 {style_rule['min_items']}~{style_rule['max_items']} 条。"
        if stage_chain:
            chain_text = " → ".join(stage_chain)
            allowed_stages = "、".join(stage_chain)
            stage_hint = (
                f"\n\n【阶段因果链 — 必须遵守】\n"
                f"本模板将业务过程划分为以下阶段，阶段之间存在因果关系：{chain_text}\n"
                f"1. 「步骤」字段只能且必须填写以下四个值之一：{allowed_stages}；严禁填写文档原始章节标题（如“业务概述”“办理流程”“营销话术”等）。\n"
                f"2. 上述每个阶段都可能产生多条知识条目，不要每个阶段只输出 1 条。\n"
                f"3. 每个阶段至少输出 3 条、最多 8 条知识条目。\n"
                f"4. 条目之间要体现阶段递进：前一阶段的输出是后一阶段的输入。\n"
                f"5. 「知识引用」和「规则引用」字段必须原样保留，作为 skill 取数逻辑。\n"
                f"6. 总计输出 {len(stage_chain) * 3}~{len(stage_chain) * 8} 条知识条目。"
            )
            item_count_hint = f"按阶段输出 {len(stage_chain) * 3}~{len(stage_chain) * 8} 条知识条目。"

        system_prompt = (
            f"你是一位知识工程专家，正在执行隐性知识显性化的第二步——知识萃取。\n"
            f"萃取风格：{style}\n\n"
            f"风格硬规则：{style_rule['prompt_hint']}\n"
            f"请按用户上传的萃取模板抽取知识。前四列（场景/场景说明/子场景/子场景说明）已由系统填写，"
            f"JSON 只需包含下列第5列及之后的字段（键名与表头完全一致）：\n"
            f"【输出格式 — 必须严格遵守】\n"
            f"1. 只输出一个 JSON 数组，不要用 Markdown 代码块，不要写任何前后说明文字。\n"
            f"2. 数组元素为对象；每个对象的键名必须与下列列表完全一致（含连字符）：{target_cols_json}\n"
            f"3. 键名与值均使用英文双引号；无信息的字段填空字符串 \"\"。\n"
            f"4. {item_count_hint}{stage_hint}\n"
            f"5. 输出示例（结构参考，请替换为真实抽取内容）：\n{example_json}"
        )
        if _pipeline_prefers_markdown(pipeline_id) or len(target_columns) >= 8:
            system_prompt += (
                "\n\n【深度萃取 — 多语义列】\n"
                "适用条件、判断逻辑、反模式/踩坑提示、知识描述、知识引用、规则引用等长文本字段须写完整"
                "（每条通常不少于一两句），勿只填占位词；尽量让每条记录在多数语义列上都有实质内容。"
            )
    else:
        system_prompt = (
            f"你是一位知识工程专家，正在执行隐性知识显性化的第二步——知识萃取。\n"
            f"萃取风格：{style}\n\n"
            f"风格硬规则：{style_rule['prompt_hint']}\n"
            f"请从以下文档中提取所有已显性化的知识条目，按以下JSON数组格式输出：\n"
            f'[{{"category": "判断规则|操作流程|反模式|审批标准|经验法则", '
            f'"content": "知识内容（一句话完整陈述）", '
            f'"trigger_condition": "触发条件", '
            f'"judgment_logic": "判断逻辑", '
            f'"anti_pattern": "常见反模式/踩坑提醒", '
            f'"source": "来源文档名", '
            f'"confidence": "高|中|低"}}]\n\n'
            f"要求：\n"
            f"1. 每条知识必须是完整的、自包含的陈述\n"
            f"2. category 只能是：判断规则、操作流程、反模式、审批标准、经验法则\n"
            f"3. 输出条数尽量满足 {style_rule['min_items']}~{style_rule['max_items']} 条\n"
            f"4. 尽量提取判断逻辑和反模式，这是隐性知识的关键入口"
        )

    extracted = ""
    parse_mode = "none"
    extracted_items = []
    extract_stats = {"raw_count": 0, "processed_count": 0, "min_items": style_rule["min_items"], "max_items": style_rule["max_items"]}
    output_name = None
    excel_meta = {}
    scenario_meta = _pipeline_scenario_meta(pipeline_id) if pipeline_id else {}
    sub_scenarios = scenario_meta.get("sub_scenarios", [])
    user_content = f"请从以下文档中提取知识条目：\n\n{doc_text}"
    if sub_scenarios:
        sub_names = [s.get("name", "") for s in sub_scenarios if s.get("name")]
        if sub_names:
            user_content += (
                "\n\n【子场景要求】\n"
                "本文档涉及以下子场景，请为每个子场景分别提取知识条目：\n" +
                "\n".join(f"- {name}" for name in sub_names) +
                "\n\n每条知识条目必须包含一个「子场景」字段，值为上述子场景名称之一。"
            )
    try:
        result = call_llm_with_retry(model_cfg, [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ], stream=False, temperature=style_rule["temperature"], max_tokens=max_tokens)

        if isinstance(result, dict):
            extracted = extract_assistant_content(result)
        extracted_items, parse_mode = _parse_extracted_items(extracted)
        extracted_items = _normalize_extracted_items(extracted_items, target_columns)
        extracted_items, extract_stats = _apply_extract_style_rules(extracted_items, style, target_columns)

        if not extracted_items and (extracted or "").strip():
            if parse_mode in {"json_list", "json_items", "object_recovery", "jsonl"}:
                err_text = (
                    "知识提取结果在风格规则过滤后为空，已阻止生成空萃取稿。"
                    "请切换到「标准萃取」重试，或检查自定义模板表头是否含可填写的知识列（非仅场景四列）。"
                )
            else:
                err_text = (
                    "知识提取结果解析失败（模型未返回可解析的 JSON 数组）。"
                    "自定义模板列较多时更易出现；请重试并优先使用「标准萃取」，或简化模板表头。"
                )
            return {
                "status": "error",
                "error": err_text,
                "style": style,
                "parse_mode": parse_mode,
                "target_column_count": len(target_columns),
                "used_template_columns": bool(target_columns),
                "extracted_preview": (extracted or "")[:2000],
                "style_rule": {
                    "raw_count": extract_stats.get("raw_count", 0),
                    "candidate_count": extract_stats.get("candidate_count", 0),
                    "processed_count": extract_stats.get("processed_count", 0),
                    "fallback_applied": extract_stats.get("fallback_applied", False),
                },
                "build": STEP2_EXCEL_BUILD,
            }

        output_name, excel_meta = _write_step2_preextract_excel(workspace, pipeline_id, extracted_items, sub_scenarios=sub_scenarios)
        step2_md_name, step2_md_url = "", ""
        if _pipeline_prefers_markdown(pipeline_id):
            excel_path = safe_workspace_path(workspace, output_name, must_exist=True)
            if excel_path:
                from shared import _excel_to_markdown_file
                md_name = f"preextract_{uuid.uuid4().hex[:8]}.md"
                md_path = workspace_path_for(workspace, pipeline_id, "step2", md_name)
                md_path.parent.mkdir(parents=True, exist_ok=True)
                _excel_to_markdown_file(excel_path, md_path, title=f"Step2 知识萃取 · {pipeline_id[:8]}")
                step2_md_name = md_name
                step2_md_url = f"/downloads/{md_name}"

        _persist_step2_excel_pipeline(
            pipeline_id,
            output_name,
            extracted,
            style,
            len(extracted_items),
            md_name=step2_md_name,
            md_url=step2_md_url,
        )
        step1_source = ""
        if pipeline_id:
            with _pipelines_lock:
                for p in load_pipelines():
                    if p["id"] == pipeline_id:
                        step1_source = p.get("step_data", {}).get("step1_output_file", "")
                        break

        return {
            "status": "ok",
            "skill_name": info.get("name", skill_id),
            "skill_id": skill_id,
            "model": model_name,
            "style": style,
            "extracted": extracted,
            "extracted_count": len(extracted_items),
            "style_rule": {
                "mode": style,
                "min_items": extract_stats.get("min_items", style_rule["min_items"]),
                "max_items": extract_stats.get("max_items", style_rule["max_items"]),
                "raw_count": extract_stats.get("raw_count", 0),
                "processed_count": extract_stats.get("processed_count", len(extracted_items)),
            },
            "parse_mode": parse_mode,
            "download_name": output_name,
            "download_url": f"/downloads/{output_name}",
            "markdown_file": step2_md_name,
            "markdown_download_url": step2_md_url,
            "output_kind": "preextract",
            "step1_source_file": step1_source,
            "filled_rows": excel_meta.get("filled_rows", 0),
            "used_step1_template": excel_meta.get("used_step1_template", False),
            "build": STEP2_EXCEL_BUILD,
        }
    except Exception as e:
        from llm_client import LlmApiError
        if isinstance(e, LlmApiError):
            payload = {"status": "error", "error": str(e), "build": STEP2_EXCEL_BUILD}
            if output_name:
                payload.update({
                    "download_name": output_name,
                    "download_url": f"/downloads/{output_name}",
                })
            return payload
        _debug_log(
            "H2",
            "services.step2_service:execute_knowledge_extraction",
            "step2 generic error",
            {"error": str(e)[:300]},
        )
        return {"status": "error", "error": f"萃取失败: {str(e)}", "build": STEP2_EXCEL_BUILD}


def step2_prev_output(pipeline_id: str, workspace: Path) -> dict:
    """获取当前流水线 Step1 的输出件信息，供 Step2 引用."""
    if not pipeline_id:
        return {"status": "error", "error": "缺少 pipeline_id"}

    with _pipelines_lock:
        pipelines = load_pipelines()
        pipeline = None
        for p in pipelines:
            if p["id"] == pipeline_id:
                pipeline = dict(p)
                pipeline["step_data"] = dict(p.get("step_data", {}))
                break

    if not pipeline:
        return {"status": "error", "error": "流水线不存在"}

    step_data = pipeline.get("step_data", {})
    step1_file = step_data.get("step1_output_file", "")
    step1_url = step_data.get("step1_download_url", "")
    step1_md_file = step_data.get("step1_md_file", "")
    step1_md_url = step_data.get("step1_md_download_url", "")

    if not step1_file:
        return {
            "status": "ok",
            "has_output": False,
            "hint": "请先在「场景锚定」生成场景骨架（需已创建并进入流水线）",
        }

    resolved = locate_workspace_file(workspace, step1_file, pipeline_id=pipeline_id)
    file_path = str(resolved) if resolved else ""
    if not file_path or not os.path.exists(file_path):
        return {
            "status": "ok",
            "has_output": False,
            "hint": "场景骨架文件已丢失，请回到场景锚定重新生成",
        }

    fields_info = []
    if os.path.exists(file_path):
        try:
            with _safe_workbook(file_path) as wb:
                for sheet_name in wb.sheetnames:
                    ws = wb[sheet_name]
                    headers = []
                    for cell in next(ws.iter_rows(min_row=1, max_row=1), []):
                        if cell.value:
                            headers.append(str(cell.value))
                    if headers:
                        fields_info.append({"sheet": sheet_name, "headers": headers})
        except Exception:
            pass

    return {
        "status": "ok",
        "has_output": True,
        "file_name": step1_file,
        "download_url": step1_url,
        "markdown_file": step1_md_file,
        "markdown_download_url": step1_md_url,
        "output_format": step_data.get("step1_output_format", "excel"),
        "scenario": pipeline.get("scenario", ""),
        "domain": pipeline.get("domain", ""),
        "fields_info": fields_info,
    }


def extract_rules(pipeline_id: str, model_name: str, source_text: str, request_files: dict, workspace: Path) -> dict:
    """Step2a: 从知识文档萃取业务规则 IR（无 SQL）."""
    if not pipeline_id:
        return {"status": "error", "error": "缺少 pipeline_id"}

    from services.pipeline_service import get_pipeline
    pipeline = get_pipeline(pipeline_id)
    if not pipeline:
        return {"status": "error", "error": "流水线不存在"}

    if not model_name:
        return {"status": "error", "error": "缺少 model 参数"}
    if not get_model_by_name(model_name):
        return {"status": "error", "error": f"模型 '{model_name}' 不可用"}

    try:
        step_data = pipeline.get("step_data") or {}
        step1_form = step_data.get("step1_form_data") or {}
        scenario_meta = {
            "scenario_name": step1_form.get("scenario_name", pipeline.get("scenario", "")),
            "scenario_content": step1_form.get("scenario_content", ""),
            "sub_scenarios": step1_form.get("sub_scenarios", []),
            "domain": pipeline.get("domain", ""),
        }

        if not source_text:
            files = request_files.getlist("files") if hasattr(request_files, "getlist") else []
            parts = []
            for f in files:
                if f.filename:
                    parts.append(f.read().decode("utf-8", errors="ignore"))
            source_text = "\n\n".join(parts)

        if not source_text:
            return {"status": "error", "error": "缺少知识来源文本或文件"}

        from step2_ir_extract import extract_rules_from_doc
        entries = extract_rules_from_doc(scenario_meta, source_text, model_name)
        if not entries:
            return {"status": "error", "error": "未能从来源文档萃取出任何规则条目，请检查文档内容或模型输出"}

        from skill_ir import new_draft_v2, save_ir
        ir = new_draft_v2(scenario_meta, entries, origin="doc_extract", pipeline_id=pipeline_id)
        ir_path = save_ir(workspace, ir, pipeline_id=pipeline_id)

        with _pipelines_lock:
            pipelines = load_pipelines()
            for p in pipelines:
                if p["id"] == pipeline_id:
                    sd = p.setdefault("step_data", {})
                    sd["step2_draft_file"] = Path(ir_path).name
                    sd["step2_draft_url"] = "/downloads/" + Path(ir_path).name
                    sd["step2_draft_version"] = 1
                    sd["step2_extracted_count"] = len(entries)
                    sd["step2_has_sql"] = False
                    break
            save_pipelines(pipelines)

        return {
            "status": "ok",
            "ir_path": Path(ir_path).name,
            "download_url": "/downloads/" + Path(ir_path).name,
            "entries_count": len(entries),
            "ir": ir,
        }
    except Exception as e:
        return {"status": "error", "error": f"规则萃取失败: {e}"}


def extract_sql(pipeline_id: str, model_name: str, workspace: Path) -> dict:
    """Step2b: 为规则 IR 生成取数逻辑 SQL."""
    if not pipeline_id:
        return {"status": "error", "error": "缺少 pipeline_id"}

    from services.pipeline_service import get_pipeline
    pipeline = get_pipeline(pipeline_id)
    if not pipeline:
        return {"status": "error", "error": "流水线不存在"}

    if not model_name:
        return {"status": "error", "error": "缺少 model 参数"}
    if not get_model_by_name(model_name):
        return {"status": "error", "error": f"模型 '{model_name}' 不可用"}

    try:
        from skill_ir import load_ir, save_ir, push_sql_history
        from step2_ir_extract import fill_sql_for_entries
        from knowledge_base import get_db_schema_text

        sd = pipeline.get("step_data") or {}
        ir_name = sd.get("step2_draft_file", "")
        ir_path = locate_workspace_file(workspace, ir_name, pipeline_id=pipeline_id)
        if not ir_path:
            return {"status": "error", "error": "未找到 Step2a 规则 IR，请先萃取规则"}

        ir = load_ir(ir_path)
        if ir.get("ir_version") != "2.0":
            return {"status": "error", "error": "当前 IR 不是 v2 格式"}

        entries = ir.get("entries", [])
        table_schema = get_db_schema_text() or "暂无表结构说明"

        entries = fill_sql_for_entries(entries, table_schema, model_name)
        ir["entries"] = entries
        for entry in entries:
            sql = entry.get("fields", {}).get("data_logic", {}).get("sql", "")
            if sql:
                push_sql_history(entry, sql, "llm")

        ir["skill_meta"]["draft_version"] = 2
        ir["skill_meta"]["updated_at"] = datetime.datetime.now().isoformat(timespec="seconds")
        ir["skill_meta"]["status"] = "draft"

        new_ir_path = save_ir(workspace, ir, pipeline_id=pipeline_id)

        with _pipelines_lock:
            pipelines = load_pipelines()
            for p in pipelines:
                if p["id"] == pipeline_id:
                    sd = p.setdefault("step_data", {})
                    sd["step2_draft_file"] = Path(new_ir_path).name
                    sd["step2_draft_url"] = "/downloads/" + Path(new_ir_path).name
                    sd["step2_draft_version"] = 2
                    sd["step2_has_sql"] = True
                    break
            save_pipelines(pipelines)

        return {
            "status": "ok",
            "ir_path": Path(new_ir_path).name,
            "download_url": "/downloads/" + Path(new_ir_path).name,
            "entries_count": len(entries),
            "ir": ir,
        }
    except Exception as e:
        return {"status": "error", "error": f"SQL 生成失败: {e}"}


def extract_skill_md(pipeline_id: str, model_name: str, request_form: dict, request_files: dict, workspace: Path) -> dict:
    """Step2: LLM 根据场景骨架+知识文档生成 SKILL.md."""
    if not pipeline_id:
        return {"status": "error", "error": "缺少 pipeline_id"}
    if not model_name:
        return {"status": "error", "error": "缺少 model 参数"}

    model_cfg = get_model_by_name(model_name)
    if not model_cfg:
        return {"status": "error", "error": f"模型 '{model_name}' 不可用"}

    from services.pipeline_service import get_pipeline
    pipeline = get_pipeline(pipeline_id)
    if not pipeline:
        return {"status": "error", "error": "流水线不存在"}

    try:
        sd = pipeline.get("step_data") or {}
        step1_form = sd.get("step1_form_data") or {}

        source_text = request_form.get("source_text", "")
        if not source_text:
            parts = []
            files = request_files.getlist("files") if hasattr(request_files, "getlist") else []
            for f in files or []:
                if f.filename:
                    parts.append(f.read().decode("utf-8", errors="ignore"))
            source_text = "\n\n".join(parts)
        if not source_text:
            return {"status": "error", "error": "缺少知识来源文本或文件"}

        sub_list = step1_form.get("sub_scenarios") or []
        sub_text = "\n".join(f"- {s.get('name', '')}：{s.get('desc', '')}" for s in sub_list) or "- 默认子场景"

        cols = step1_form.get("knowledge_columns") or []
        col_text = ", ".join(cols) if cols else "步骤, 具体方法, 知识引用, 规则引用, 专业术语, 关键输出"

        PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"
        prompt_path = PROMPT_DIR / "step2_generate_skill_md.txt"
        prompt_tpl = prompt_path.read_text(encoding="utf-8")
        ctx = {
            "scenario_name": step1_form.get("scenario_name", pipeline.get("scenario", "")),
            "scenario_desc": step1_form.get("scenario_content", ""),
            "sub_scenarios": sub_text,
            "knowledge_columns": col_text,
            "source_text": source_text[:12000],
        }
        prompt = prompt_tpl
        for k, v in ctx.items():
            prompt = prompt.replace("{{" + k + "}}", str(v))

        result = call_llm_with_retry(
            model_cfg,
            [{"role": "user", "content": prompt}],
            stream=False,
            temperature=0.2,
            max_tokens=100000,
        )
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "") if isinstance(result, dict) else str(result)

        if not content.strip():
            return {"status": "error", "error": "LLM 返回空内容"}

        skill_name = f"skill_draft_{pipeline_id[:8]}_{uuid.uuid4().hex[:6]}.md"
        skill_path = workspace_path_for(workspace, pipeline_id, "step2", skill_name)
        skill_path.parent.mkdir(parents=True, exist_ok=True)
        skill_path.write_text(content, encoding="utf-8")

        with _pipelines_lock:
            pipelines = load_pipelines()
            for p in pipelines:
                if p["id"] == pipeline_id:
                    psd = p.setdefault("step_data", {})
                    psd["step2_skill_md_file"] = skill_name
                    psd["step2_skill_md_url"] = "/downloads/" + skill_name
                    psd["step2_draft_file"] = skill_name
                    psd["step2_draft_url"] = "/downloads/" + skill_name
                    p.setdefault("step_status", {})
                    p["step_status"]["2"] = "done"
                    if p["step_status"].get("3", "pending") == "pending":
                        p["step_status"]["3"] = "active"
                    p["current_step"] = max(p.get("current_step", 1), 3)
                    p["updated_at"] = datetime.datetime.now().isoformat()
                    break
            save_pipelines(pipelines)

        return {
            "status": "ok",
            "skill_md": content,
            "skill_md_file": skill_name,
            "download_url": "/downloads/" + skill_name,
        }
    except Exception as e:
        return {"status": "error", "error": f"知识萃取失败: {str(e)}"}


def step2_extract_unified(request, workspace: Path) -> dict:
    """统一知识萃取端点（文件多源融合）."""
    # 该实现保持与 app_server.py 一致；为了控制篇幅，先委托回旧实现占位。
    # TODO: 在后续迭代中将此 700+ 行的业务逻辑完整迁移到本服务。
    return {"status": "error", "error": "Step2 统一萃取尚未在服务层实现"}

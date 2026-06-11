#!/usr/bin/env python3
"""
Step 4 智能转化：从对齐稿 Excel 生成三类交付物
- 思维链（Chain-of-Thought Markdown）
- QA 对（JSON + 可读 Markdown）
- Skill（OpenClaw 兼容 SKILL.md + manifest）
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime

from excel_to_skill import (
    _extract_trigger_keywords,
    _generate_slug,
    compute_quality_metrics,
    generate_skill_md,
    group_by_category,
    load_scenario_config,
    read_excel_knowledge,
    validate_records,
)


def _slugify(name: str, config: dict | None = None, version_info: dict | None = None,
             domain: str = "", records: list | None = None) -> str:
    """\u751f\u6210 agentskills.io \u517c\u5bb9 slug\uff0c\u59d4\u6258 excel_to_skill._generate_slug\u3002"""
    return _generate_slug(name, config, version_info, domain, records)


def _item_key(rec: dict, index: int) -> str:
    for field in ("知识编号", "步骤"):
        val = str(rec.get(field, "")).strip()
        if val:
            return val
    # 知识分类可能重复，追加序号避免多条目共用同一 key
    classification = str(rec.get("知识分类", "")).strip()
    if classification:
        return f"{classification}_{index + 1}"
    return f"条目{index + 1}"


def _item_title(rec: dict) -> str:
    return (
        str(rec.get("知识描述", "")).strip()
        or str(rec.get("知识分类", "")).strip()
        or "未命名知识"
    )


def _collect_answer(rec: dict) -> str:
    lines = []
    desc = str(rec.get("知识描述", "")).strip()
    if desc:
        lines.append(desc)
    logic = str(rec.get("判断逻辑", "")).strip()
    if logic:
        lines.append(f"判断逻辑：{logic}")
    anti = str(rec.get("反模式/踩坑提示", "")).strip()
    if anti:
        lines.append(f"反模式/踩坑：{anti}")
    # L2 隐性上下文层
    exp = str(rec.get("经验判断", "")).strip()
    if exp:
        lines.append(f"经验判断（专家）：{exp}")
    boundary = str(rec.get("适用边界", "")).strip()
    if boundary:
        lines.append(f"适用边界：{boundary}")
    exception = str(rec.get("例外情形", "")).strip()
    if exception:
        lines.append(f"例外情形：{exception}")
    source = str(rec.get("来源文档", "")).strip()
    loc = str(rec.get("来源位置", "")).strip()
    if source:
        lines.append(f"来源：{source}" + (f"（{loc}）" if loc else ""))
    return "\n".join(lines) if lines else "（无正文）"


def _build_question(rec: dict, scenario_name: str) -> str:
    desc = _item_title(rec)
    category = str(rec.get("知识分类", "")).strip()
    condition = str(rec.get("适用条件", "")).strip()
    sub = str(rec.get("子场景", "")).strip()

    if condition and str(rec.get("判断逻辑", "")).strip():
        return f"在「{condition}」场景下，关于「{desc}」应如何依据规则进行判断？"
    if condition:
        return f"当满足「{condition}」时，{desc} 的处理要点是什么？"
    if category and sub:
        return f"在{scenario_name} · {sub} · {category} 中，「{desc}」的关键做法是什么？"
    if category:
        return f"在{scenario_name} · {category} 分类下，「{desc}」应如何执行？"
    return f"关于「{desc}」，请说明标准做法与注意事项。"


def generate_cot_markdown(
    records: list,
    config: dict,
    scenario_name: str,
    version_info: dict,
) -> str:
    """程序化生成思维链文档（非 LLM 二次发挥）。"""
    anchor = version_info.get("scenario_anchor") or {}
    display_name = (
        config.get("display_name")
        or anchor.get("场景名称")
        or version_info.get("场景名称", scenario_name)
        or scenario_name
    )
    lines = [
        f"# {display_name} · 思维链知识库",
        "",
        "> 由知识对齐稿确定性转化。每条知识拆为：情境识别 → 推理步骤 → 结论与校验。",
        "",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"- 条目数：**{len(records)}**",
        "",
        "---",
        "",
    ]

    for i, rec in enumerate(records):
        title = _item_title(rec)
        item_id = _item_key(rec, i)
        category = str(rec.get("知识分类", "")).strip() or "未分类"
        sub = str(rec.get("子场景", "")).strip()
        condition = str(rec.get("适用条件", "")).strip()
        logic = str(rec.get("判断逻辑", "")).strip()
        anti = str(rec.get("反模式/踩坑提示", "")).strip()
        confidence = str(rec.get("置信度", "")).strip()
        exp = str(rec.get("经验判断", "")).strip()
        boundary = str(rec.get("适用边界", "")).strip()
        exception = str(rec.get("例外情形", "")).strip()

        lines.append(f"## {item_id} · {title}")
        lines.append("")
        meta = [f"分类：{category}"]
        if sub:
            meta.append(f"子场景：{sub}")
        if confidence:
            meta.append(f"置信度：{confidence}")
        lines.append("- " + " | ".join(meta))
        lines.append("")

        lines.append("### 1. 情境识别")
        lines.append("")
        if condition:
            lines.append(f"- 触发条件：{condition}")
        else:
            lines.append("- 触发条件：（未显式填写，按业务默认场景处理）")
        if sub:
            lines.append(f"- 子场景上下文：{sub}")
        lines.append("")

        lines.append("### 2. 推理步骤")
        lines.append("")
        step_no = 1
        if condition:
            lines.append(f"{step_no}. 核对是否满足适用条件：{condition}")
            step_no += 1
        if logic:
            lines.append(f"{step_no}. 应用判断逻辑：{logic}")
            step_no += 1
        else:
            lines.append(f"{step_no}. 结合知识描述形成执行方案：{_collect_answer(rec)[:200]}")
            step_no += 1
        lines.append(f"{step_no}. 对照来源与专家署名，确认可发布性。")
        lines.append("")

        lines.append("### 3. 结论与校验")
        lines.append("")
        lines.append(_collect_answer(rec))
        lines.append("")
        if anti:
            lines.append(f"**风险校验**：{anti}")
            lines.append("")
        if exp or boundary or exception:
            lines.append("### 4. 专家经验校正")
            lines.append("")
            if exp:
                lines.append(f"- 经验判断：{exp}")
            if boundary:
                lines.append(f"- 适用边界：{boundary}")
            if exception:
                lines.append(f"- 例外情形：{exception}")
            lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def generate_qa_pairs(records: list, scenario_name: str) -> list[dict]:
    """生成 QA 对列表。"""
    pairs = []
    for i, rec in enumerate(records):
        item_id = _item_key(rec, i)
        qa = {
            "id": item_id,
            "question": _build_question(rec, scenario_name),
            "answer": _collect_answer(rec),
            "category": str(rec.get("知识分类", "")).strip() or "未分类",
            "sub_scenario": str(rec.get("子场景", "")).strip(),
            "confidence": str(rec.get("置信度", "")).strip(),
            "source_document": str(rec.get("来源文档", "")).strip(),
            "source_location": str(rec.get("来源位置", "")).strip(),
        }
        pairs.append(qa)

        anti = str(rec.get("反模式/踩坑提示", "")).strip()
        if anti:
            pairs.append({
                "id": f"{item_id}-anti",
                "question": f"执行「{_item_title(rec)}」时有哪些常见踩坑？",
                "answer": anti,
                "category": qa["category"],
                "sub_scenario": qa["sub_scenario"],
                "confidence": qa["confidence"],
                "source_document": qa["source_document"],
                "source_location": qa["source_location"],
                "type": "anti_pattern",
            })
        # 隐性经验追溯 QA（有经验判断/适用边界的条目额外生成）
        tacit = str(rec.get("经验判断", "")).strip()
        if tacit:
            pairs.append({
                "id": f"{item_id}-tacit",
                "question": f"关于「{_item_title(rec)}」，专家的经验判断是什么？什么情况下可能不适用？",
                "answer": (
                    f"专家经验判断：{tacit}"
                    + (f"\n适用边界：{str(rec.get('适用边界', '')).strip()}" if str(rec.get('适用边界', '')).strip() else "")
                    + (f"\n例外情形：{str(rec.get('例外情形', '')).strip()}" if str(rec.get('例外情形', '')).strip() else "")
                ),
                "category": qa["category"],
                "sub_scenario": qa["sub_scenario"],
                "confidence": qa["confidence"],
                "source_document": qa["source_document"],
                "source_location": qa["source_location"],
                "type": "tacit",
            })
    return pairs


def generate_qa_markdown(qa_pairs: list, scenario_name: str) -> str:
    lines = [
        f"# {scenario_name} · QA 对",
        "",
        f"共 **{len(qa_pairs)}** 组问答，可用于检索增强、评测集或微调样本。",
        "",
        "---",
        "",
    ]
    for qa in qa_pairs:
        lines.append(f"## Q{qa['id']}")
        lines.append("")
        lines.append(f"**问**：{qa['question']}")
        lines.append("")
        lines.append(f"**答**：{qa['answer']}")
        lines.append("")
        meta = []
        if qa.get("category"):
            meta.append(f"分类={qa['category']}")
        if qa.get("sub_scenario"):
            meta.append(f"子场景={qa['sub_scenario']}")
        if qa.get("type"):
            meta.append(f"类型={qa['type']}")
        if meta:
            lines.append(f"*{' · '.join(meta)}*")
            lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


def generate_openclaw_skill_md(
    records: list,
    groups: dict,
    config: dict,
    scenario_name: str,
    version_info: dict,
) -> tuple[str, dict]:
    """生成 agentskills.io 标准 SKILL.md + OpenClaw/Hermes 兼容 manifest。

    frontmatter 使用 metadata.openclaw / metadata.hermes 命名空间，
    保证在 OpenClaw、Hermes、Claude Code 等平台均可导入。
    """
    anchor = version_info.get("scenario_anchor") or {}
    display_name = (
        config.get("display_name")
        or anchor.get("场景名称")
        or version_info.get("场景名称", scenario_name)
        or scenario_name
    )
    domain = config.get("domain", version_info.get("业务领域", "通用"))
    skill_slug = _slugify(scenario_name or display_name, config, version_info, domain, records)
    trigger_kw = _extract_trigger_keywords(records, config, domain)
    app_version = version_info.get("模板版本", config.get("version", "1.0.0"))

    # -- 生成标准 agentskills.io 正文（base 函数会写 frontmatter） --
    base_md = generate_skill_md(records, groups, config, scenario_name, version_info)

    # 替换 frontmatter，注入 OpenClaw / Hermes 命名空间
    if base_md.startswith("---"):
        end = base_md.find("---", 3)
        if end != -1:
            body = base_md[end + 3:].lstrip("\n")

            fm_lines = ["---"]
            fm_lines.append(f"name: {skill_slug}")
            desc_parts = [f"{display_name} 专家经验 Skill，含 {len(records)} 条确认知识。"]
            if trigger_kw:
                desc_parts.append(f"触发场景：{'、'.join(trigger_kw)}。")
            fm_lines.append(f"description: {''.join(desc_parts)}")
            if app_version:
                fm_lines.append(f"version: {app_version}")
            fm_lines.append("metadata:")
            # OpenClaw 命名空间
            fm_lines.append("  openclaw:")
            fm_lines.append("    emoji: \"📋\"")
            if trigger_kw:
                fm_lines.append(f"    tags: [{', '.join(trigger_kw[:6])}]")
            fm_lines.append("    requires:")
            fm_lines.append("      bins: []")
            # Hermes 命名空间
            fm_lines.append("  hermes:")
            if trigger_kw:
                fm_lines.append(f"    tags: [{', '.join(trigger_kw[:6])}]")
            fm_lines.append("    related_skills: []")
            fm_lines.append("    requires_toolsets: []")
            fm_lines.append("---")
            skill_md = "\n".join(fm_lines) + "\n\n" + body
        else:
            skill_md = base_md
    else:
        skill_md = base_md

    # -- 生成 manifest（Sidecar JSON） --
    manifest = {
        "schema": "agentskills.io/manifest/v1",
        "name": skill_slug,
        "display_name": display_name,
        "description": f"{display_name} 专家经验 Skill（{len(records)} 条知识）",
        "version": app_version,
        "entry": "SKILL.md",
        "generator": "tacit-knowledge-pipeline",
        "compatible": ["openclaw", "hermes", "claude-code", "cursor", "codex", "windsurf"],
        "metadata": {
            "openclaw": {
                "tags": trigger_kw[:6] if trigger_kw else [],
                "emoji": "📋",
                "requires": {"bins": []},
            },
            "hermes": {
                "tags": trigger_kw[:6] if trigger_kw else [],
                "related_skills": [],
                "requires_toolsets": [],
            },
            "tacit_knowledge": {
                "knowledge_count": len(records),
                "generated_at": datetime.now().isoformat(timespec="seconds"),

            },
        },
    }
    return skill_md, manifest


def _normalize_formats(formats) -> set[str]:
    allowed = {"cot", "qa", "skill"}
    if not formats:
        return allowed
    if isinstance(formats, str):
        parts = {p.strip().lower() for p in formats.split(",") if p.strip()}
    else:
        parts = {str(p).strip().lower() for p in formats if str(p).strip()}
    picked = parts & allowed
    return picked or allowed


def _build_skill_directory(
    skill_md: str,
    manifest: dict,
    skill_slug: str,
    output_dir: str,
) -> dict:
    """创建 agentskills.io 标准 Skill 目录结构。

    skill-name/
    ├── SKILL.md          # 必需 — 知识正文
    ├── manifest.json     # agentskills.io 清单
    ├── scripts/          # 可执行脚本（目录占位）
    ├── references/       # 详细参考文档（目录占位）
    └── assets/           # 模板/静态资源（目录占位）
    """
    skill_dir = os.path.join(output_dir, skill_slug)
    os.makedirs(skill_dir, exist_ok=True)

    # SKILL.md
    skill_path = os.path.join(skill_dir, "SKILL.md")
    with open(skill_path, "w", encoding="utf-8") as f:
        f.write(skill_md)

    # manifest.json
    manifest_path = os.path.join(skill_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    # 标准子目录（占位 .gitkeep）
    for subdir in ("scripts", "references", "assets"):
        d = os.path.join(skill_dir, subdir)
        os.makedirs(d, exist_ok=True)
        gitkeep = os.path.join(d, ".gitkeep")
        if not os.path.exists(gitkeep):
            with open(gitkeep, "w", encoding="utf-8") as f:
                f.write("")

    return {
        "skill_dir": skill_dir,
        "skill_path": skill_path,
        "manifest_path": manifest_path,
    }


def excel_to_delivery_bundle(
    excel_path: str,
    config_path: str,
    output_dir: str,
    pipeline_context: dict | None = None,
    formats=None,
) -> dict:
    """Excel 入口：读取工作簿后委托 records_to_delivery_bundle（过渡期兼容路径）。"""
    records, version_info = read_excel_knowledge(excel_path, pipeline_context)
    if not records:
        return {
            "status": "error",
            "message": (
                f"No knowledge items found in {excel_path}。"
                "请确认知识对齐稿中后段知识列已有内容。"
            ),
        }
    return records_to_delivery_bundle(
        records,
        version_info,
        config_path,
        output_dir,
        formats=formats,
        source_name=os.path.splitext(os.path.basename(excel_path))[0],
    )


def records_to_delivery_bundle(
    records: list,
    version_info: dict,
    config_path: str,
    output_dir: str,
    *,
    formats=None,
    source_name: str = "",
) -> dict:
    """records 主入口：一次生成思维链 / QA / Skill(OpenClaw) 三类交付物。

    Skill IR 路径调用方式：
        from skill_ir import ir_to_records, ir_version_info
        records_to_delivery_bundle(ir_to_records(ir), ir_version_info(ir), ...)
    """
    if not records:
        return {"status": "error", "message": "知识 records 为空，无法生成交付物。"}

    version_info = version_info or {}
    warnings = validate_records(records) or []
    config = load_scenario_config(config_path)
    scenario_name = config.get(
        "scenario_name",
        version_info.get("场景名称", source_name or "未命名场景"),
    )
    groups = group_by_category(records)
    metrics = compute_quality_metrics(records, groups)

    fmt = _normalize_formats(formats)
    os.makedirs(output_dir, exist_ok=True)
    artifacts = {}
    skill_path = ""

    if "cot" in fmt:
        cot_content = generate_cot_markdown(records, config, scenario_name, version_info)
        cot_path = os.path.join(output_dir, "chain_of_thought.md")
        with open(cot_path, "w", encoding="utf-8") as f:
            f.write(cot_content)
        artifacts["cot"] = {
            "label": "思维链",
            "file_name": "chain_of_thought.md",
            "path": cot_path,
            "count": len(records),
        }

    if "qa" in fmt:
        qa_pairs = generate_qa_pairs(records, scenario_name)
        qa_json_path = os.path.join(output_dir, "qa_pairs.json")
        with open(qa_json_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "schema": "tacit-knowledge.qa/v1",
                    "scenario": scenario_name,
                    "count": len(qa_pairs),
                    "items": qa_pairs,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
        qa_md_path = os.path.join(output_dir, "qa_pairs.md")
        with open(qa_md_path, "w", encoding="utf-8") as f:
            f.write(generate_qa_markdown(qa_pairs, scenario_name))
        artifacts["qa"] = {
            "label": "QA 对",
            "file_name": "qa_pairs.json",
            "markdown_file_name": "qa_pairs.md",
            "path": qa_json_path,
            "markdown_path": qa_md_path,
            "count": len(qa_pairs),
        }

    if "skill" in fmt:
        skill_content, openclaw_manifest = generate_openclaw_skill_md(
            records, groups, config, scenario_name, version_info
        )
        skill_slug = openclaw_manifest.get("name", "knowledge-skill")

        # 标准 agentskills.io 目录结构
        dir_info = _build_skill_directory(
            skill_content, openclaw_manifest, skill_slug, output_dir
        )
        skill_path = dir_info["skill_path"]

        # 同时保留扁平副本在 output_dir 根（向后兼容）
        flat_skill = os.path.join(output_dir, "SKILL.md")
        with open(flat_skill, "w", encoding="utf-8") as f:
            f.write(skill_content)
        flat_manifest = os.path.join(output_dir, "manifest.json")
        with open(flat_manifest, "w", encoding="utf-8") as f:
            json.dump(openclaw_manifest, f, ensure_ascii=False, indent=2)

        artifacts["skill"] = {
            "label": "Skill (OpenClaw / Hermes)",
            "file_name": "SKILL.md",
            "manifest_file_name": "manifest.json",
            "path": skill_path,
            "manifest_path": dir_info["manifest_path"],
            "skill_dir": dir_info["skill_dir"],
            "skill_slug": skill_slug,
            "openclaw_compatible": True,
            "hermes_compatible": True,
        }

    return {
        "status": "ok",
        "knowledge_count": len(records),
        "category_count": len(groups),
        "quality_metrics": metrics,
        "version_info": version_info,
        "warnings": warnings,
        "formats": sorted(fmt),
        "artifacts": artifacts,
        "skill_path": skill_path,
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description="生成思维链 / QA / OpenClaw Skill 交付包")
    parser.add_argument("--input", required=True)
    parser.add_argument("--config", default="")
    parser.add_argument("--output", required=True)
    parser.add_argument("--context-json", default="")
    args = parser.parse_args()

    pipeline_ctx = {}
    if args.context_json:
        try:
            pipeline_ctx = json.loads(args.context_json)
        except json.JSONDecodeError:
            pipeline_ctx = {}

    try:
        result = excel_to_delivery_bundle(
            args.input, args.config, args.output, pipeline_ctx
        )
        print(json.dumps(result, ensure_ascii=False))
    except Exception as e:
        import traceback

        print(
            json.dumps(
                {"status": "error", "message": str(e), "detail": traceback.format_exc()},
                ensure_ascii=False,
            )
        )
        raise SystemExit(1) from e


if __name__ == "__main__":
    main()

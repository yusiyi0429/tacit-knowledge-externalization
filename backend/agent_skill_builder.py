#!/usr/bin/env python3
"""从对齐 IR 构建可执行 agent-skill zip。"""
from __future__ import annotations

import json
import re
import shutil
import zipfile
from pathlib import Path

from knowledge_delivery import generate_cot_markdown, generate_qa_pairs, generate_qa_markdown


def build_agent_skill_bundle(
    ir: dict,
    output_dir: str,
) -> dict:
    """构建 agent-skill 交付包：SKILL.md + execute.py + manifest + IR 快照。"""
    scenario_name = ir.get("anchors", {}).get("scenario", "未命名场景")
    skill_slug = _slugify(scenario_name) or "agent-skill"
    skill_dir = Path(output_dir) / skill_slug
    skill_dir.mkdir(parents=True, exist_ok=True)

    # SKILL.md
    skill_md = _render_agent_skill_md(ir)
    (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")

    # manifest.json
    manifest = {
        "name": skill_slug,
        "version": "1.0.0",
        "description": f"{scenario_name} 圈客 agent-skill",
        "entry": "scripts/execute.py",
        "ir_version": ir.get("ir_version"),
    }
    (skill_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # scripts/execute.py
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir(exist_ok=True)
    executor_src = Path(__file__).resolve().parent / "skill_executor.py"
    shutil.copy2(executor_src, scripts_dir / "execute.py")
    (scripts_dir / "__init__.py").write_text("", encoding="utf-8")

    # references/ir_snapshot.json
    refs_dir = skill_dir / "references"
    refs_dir.mkdir(exist_ok=True)
    (refs_dir / "ir_snapshot.json").write_text(json.dumps(ir, ensure_ascii=False, indent=2), encoding="utf-8")

    # zip
    zip_path = Path(output_dir) / f"{skill_slug}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in skill_dir.rglob("*"):
            if file_path.is_file():
                zf.write(file_path, file_path.relative_to(skill_dir))

    # CoT & QA
    records = _ir_to_records(ir)
    cot_md = generate_cot_markdown(records, {}, scenario_name, {})
    cot_path = Path(output_dir) / "chain_of_thought.md"
    cot_path.write_text(cot_md, encoding="utf-8")

    qa_pairs = generate_qa_pairs(records, scenario_name)
    qa_json_path = Path(output_dir) / "qa_pairs.json"
    qa_json_path.write_text(json.dumps({
        "schema": "tacit-knowledge.qa/v1",
        "scenario": scenario_name,
        "count": len(qa_pairs),
        "items": qa_pairs,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    qa_md_path = Path(output_dir) / "qa_pairs.md"
    qa_md_path.write_text(generate_qa_markdown(qa_pairs, scenario_name), encoding="utf-8")

    return {
        "skill_dir": str(skill_dir),
        "skill_path": str(skill_dir / "SKILL.md"),
        "manifest_path": str(skill_dir / "manifest.json"),
        "zip_path": str(zip_path),
        "cot_path": str(cot_path),
        "qa_json_path": str(qa_json_path),
        "qa_md_path": str(qa_md_path),
    }


def _render_agent_skill_md(ir: dict) -> str:
    lines = [
        f"# {ir.get('anchors', {}).get('scenario', 'Agent Skill')}",
        "",
        "## 执行说明",
        "",
        "```bash",
        "python scripts/execute.py --db path/to/knowledge_base.db --output report.json",
        "```",
        "",
        "## 知识规则",
        "",
    ]
    for entry in ir.get("entries", []):
        fields = entry.get("fields", {})
        data_logic = fields.get("data_logic") or {}
        lines.append(f"### {entry.get('entry_id')} | {entry.get('sub_scenario')} | {entry.get('step_phase')}")
        lines.append(f"- 业务描述：{fields.get('knowledge_desc', '')}")
        lines.append(f"- 数据来源：{fields.get('knowledge_ref', '')}")
        lines.append(f"- 规则：{fields.get('rule_ref', '')}")
        lines.append(f"- SQL：`{data_logic.get('sql', '')}`")
        lines.append(f"- 输出：{fields.get('output', '')}")
        lines.append("")
    return "\n".join(lines)


def _ir_to_records(ir: dict) -> list[dict]:
    from skill_ir import ir_to_records
    return ir_to_records(ir)


def _slugify(text: str) -> str:
    return re.sub(r"[^\w\-]", "-", text or "").strip("-")[:50]

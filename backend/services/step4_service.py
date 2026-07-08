"""Step4 智能转化业务服务."""

from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import zipfile
from pathlib import Path

from excel_to_skill import compute_quality_metrics, group_by_category
from knowledge_delivery import records_to_delivery_bundle
from pipeline_artifacts import basename_only, resolve_knowledge_ir_path, workspace_path_for
from shared import SCHEMA_PATH, _pipelines_lock, load_pipelines, save_pipelines
from skill_ir import ir_to_records, ir_version_info, load_ir


def _update_pipeline_step4(
    pipeline: dict,
    artifacts: dict,
    version: int | str,
) -> dict:
    """把 Step4 产物信息写回 pipeline step_data，返回下载 URL 映射."""
    sd = pipeline.setdefault("step_data", {})
    downloads: dict[str, str] = {}

    skill = artifacts.get("skill", {})
    if skill:
        skill_name = skill.get("file_name", "")
        if skill_name:
            sd["step4_skill_file"] = skill_name
            sd["step4_download_url"] = f"/downloads/{skill_name}"
            downloads["skill"] = sd["step4_download_url"]

        manifest_name = skill.get("manifest_file_name", "")
        if manifest_name:
            sd["step4_manifest_file"] = manifest_name
            sd["step4_manifest_url"] = f"/downloads/{manifest_name}"

        zip_path = skill.get("zip_path", "")
        if zip_path:
            zip_name = os.path.basename(zip_path)
            sd["step4_skill_dir_zip_file"] = zip_name
            sd["step4_skill_dir_zip_url"] = f"/downloads/{zip_name}"
            downloads["skill_zip"] = sd["step4_skill_dir_zip_url"]

    cot = artifacts.get("cot", {})
    if cot:
        cot_name = cot.get("file_name", "")
        if cot_name:
            sd["step4_cot_file"] = cot_name
            sd["step4_cot_download_url"] = f"/downloads/{cot_name}"
            downloads["cot"] = sd["step4_cot_download_url"]

    qa = artifacts.get("qa", {})
    if qa:
        qa_name = qa.get("file_name", "")
        qa_md_name = qa.get("markdown_file_name", "")
        if qa_name:
            sd["step4_qa_file"] = qa_name
            sd["step4_qa_download_url"] = f"/downloads/{qa_name}"
            downloads["qa"] = sd["step4_qa_download_url"]
        if qa_md_name:
            sd["step4_qa_md_file"] = qa_md_name
            sd["step4_qa_md_download_url"] = f"/downloads/{qa_md_name}"

    sd["step4_published_version"] = f"v{version}" if not str(version).startswith("v") else str(version)
    return downloads


def _slugify(name: str) -> str:
    """生成 agentskills.io 兼容 slug."""
    return re.sub(r"[^\w\-]", "-", name or "knowledge-skill").strip("-").lower()[:50] or "knowledge-skill"


def _artifact_publish_name(
    pipeline_id: str,
    prefix: str,
    original_name: str,
    slug: str = "",
) -> str:
    """给产物文件名加上 pipeline id 前缀，使其可通过 /downloads 白名单校验."""
    base = basename_only(original_name)
    suffix = "" if base.lower().endswith(".zip") else Path(base).suffix
    stem = Path(base).stem
    safe_slug = re.sub(r"[^\w\-]", "-", slug or stem).strip("-").lower()[:30]
    if suffix:
        return f"{prefix}{pipeline_id[:8]}_{safe_slug}{suffix}"
    return f"{prefix}{pipeline_id[:8]}_{safe_slug}.zip"


def _publish_artifact(
    step4_dir: Path,
    src_name: str,
    dst_name: str,
) -> Path:
    """把 step4_dir 内的 src 文件复制为带前缀的 dst，返回 dst 路径."""
    src = step4_dir / basename_only(src_name)
    dst = step4_dir / basename_only(dst_name)
    if src.is_file():
        shutil.copy2(str(src), str(dst))
    return dst


def _build_skill_dir_from_markdown(
    md_content: str,
    scenario_name: str,
    output_dir: Path,
    pipeline_context: dict,
) -> dict:
    """Markdown 流兜底：把 SKILL.md 包装成 agentskills.io 目录结构并打包 zip."""
    skill_slug = _slugify(scenario_name)
    skill_dir = output_dir / skill_slug
    skill_dir.mkdir(parents=True, exist_ok=True)

    # SKILL.md
    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text(md_content, encoding="utf-8")

    # manifest.json
    manifest = {
        "schema": "agentskills.io/manifest/v1",
        "name": skill_slug,
        "display_name": scenario_name,
        "description": f"{scenario_name} 专家经验 Skill",
        "version": "1.0.0",
        "entry": "SKILL.md",
        "generator": "tacit-knowledge-pipeline",
        "compatible": ["openclaw", "hermes", "claude-code", "cursor", "codex", "windsurf"],
        "metadata": {
            "openclaw": {"emoji": "📋", "requires": {"bins": []}},
            "tacit_knowledge": {
                "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            },
        },
    }
    manifest_path = skill_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # references / scripts / assets
    for subdir_name in ("references", "scripts", "assets"):
        subdir = skill_dir / subdir_name
        subdir.mkdir(exist_ok=True)
        (subdir / ".gitkeep").write_text("", encoding="utf-8")

    # 把源 markdown 路径写到 references 做追溯
    source_md = pipeline_context.get("source_md_file", "")
    if source_md:
        (skill_dir / "references" / "source.md").write_text(
            f"来源对齐稿：{source_md}\n", encoding="utf-8"
        )

    # zip
    zip_path = output_dir / f"{skill_slug}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in skill_dir.rglob("*"):
            if file_path.is_file():
                zf.write(file_path, file_path.relative_to(skill_dir))

    # 同时在 output_dir 根保留扁平副本
    flat_skill = output_dir / "SKILL.md"
    flat_skill.write_text(md_content, encoding="utf-8")
    flat_manifest = output_dir / "manifest.json"
    flat_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "skill_dir": str(skill_dir),
        "skill_path": str(skill_path),
        "manifest_path": str(manifest_path),
        "zip_path": str(zip_path),
    }


def _compile_from_ir(
    pipeline: dict,
    ir_path: Path,
    step4_dir: Path,
    formats: str | None,
) -> dict:
    """IR 流：读取 JSON IR，调用 knowledge_delivery 生成三类交付物."""
    ir = load_ir(str(ir_path))
    records = ir_to_records(ir)
    if not records:
        return {"status": "error", "error": "IR 中无知识条目，无法编译"}

    version_info = ir_version_info(ir)
    ir_meta = ir.get("skill_meta", {}) or {}
    ir_version = ir_meta.get("draft_version", 1)

    pipeline_context = {
        "domain": pipeline.get("step_data", {}).get("domain", ""),
        "scenario": pipeline.get("step_data", {}).get("scenario", ""),
        "pipeline_id": pipeline["id"],
        "step1_output_file": pipeline.get("step_data", {}).get("step1_output_file", ""),
        "step2_output_file": pipeline.get("step_data", {}).get("step2_output_file", ""),
        "step3_final_file": pipeline.get("step_data", {}).get("step3_final_file", ""),
    }

    result = records_to_delivery_bundle(
        records=records,
        version_info=version_info,
        config_path=str(SCHEMA_PATH),
        output_dir=str(step4_dir),
        formats=formats,
        pipeline_context=pipeline_context,
        ir_path=str(ir_path),
    )
    if result.get("status") != "ok":
        return {"status": "error", "error": result.get("message", "编译失败")}

    artifacts = result.get("artifacts", {})
    pid_short = pipeline["id"][:8]

    # 重命名为带前缀的文件名，使其可通过 /downloads 白名单
    skill = artifacts.get("skill", {})
    if skill:
        skill_slug = skill.get("skill_slug", "") or _slugify(version_info.get("场景名称", "knowledge-skill"))
        if skill.get("file_name"):
            skill["file_name"] = _artifact_publish_name(pid_short, "SKILL_", skill["file_name"], skill_slug)
            _publish_artifact(step4_dir, "SKILL.md", skill["file_name"])
        if skill.get("manifest_file_name"):
            skill["manifest_file_name"] = _artifact_publish_name(pid_short, "SKILL_DIR_", skill["manifest_file_name"], skill_slug)
            _publish_artifact(step4_dir, "manifest.json", skill["manifest_file_name"])
        if skill.get("zip_path"):
            zip_name = os.path.basename(skill["zip_path"])
            new_zip_name = _artifact_publish_name(pid_short, "SKILL_DIR_", zip_name, skill_slug)
            _publish_artifact(step4_dir, zip_name, new_zip_name)
            skill["zip_path"] = str(step4_dir / new_zip_name)

    cot = artifacts.get("cot", {})
    if cot and cot.get("file_name"):
        cot_slug = _slugify(version_info.get("场景名称", "cot"))
        cot["file_name"] = _artifact_publish_name(pid_short, "COT_", cot["file_name"], cot_slug)
        _publish_artifact(step4_dir, "chain_of_thought.md", cot["file_name"])

    qa = artifacts.get("qa", {})
    if qa:
        qa_slug = _slugify(version_info.get("场景名称", "qa"))
        if qa.get("file_name"):
            qa["file_name"] = _artifact_publish_name(pid_short, "QA_", qa["file_name"], qa_slug)
            _publish_artifact(step4_dir, "qa_pairs.json", qa["file_name"])
        if qa.get("markdown_file_name"):
            qa["markdown_file_name"] = _artifact_publish_name(pid_short, "QA_", qa["markdown_file_name"], qa_slug)
            _publish_artifact(step4_dir, "qa_pairs.md", qa["markdown_file_name"])

    quality_score = 0
    try:
        groups = group_by_category(records)
        metrics = compute_quality_metrics(records, groups)
        quality_score = round(metrics.get("overall", 0) * 100)
    except Exception:
        quality_score = 0

    downloads = _update_pipeline_step4(pipeline, artifacts, ir_version)

    return {
        "status": "ok",
        "input_kind": "ir",
        "ir_version": ir_version,
        "knowledge_count": result.get("knowledge_count", 0),
        "category_count": result.get("category_count", 0),
        "quality_score": quality_score,
        "formats": result.get("formats", []),
        "skill_dir_zip_url": downloads.get("skill_zip", ""),
        "downloads": downloads,
    }


def _normalize_formats(formats: str | None) -> set[str]:
    allowed = {"cot", "qa", "skill"}
    if not formats:
        return allowed
    parts = {p.strip().lower() for p in str(formats).split(",") if p.strip()}
    return parts & allowed or allowed


def _compile_from_markdown(
    pipeline: dict,
    md_path: Path,
    step4_dir: Path,
    formats: str | None,
) -> dict:
    """Markdown 流：把对齐稿 SKILL.md 包装为可执行 Skill 目录，CoT/QA 暂由说明占位."""
    fmt = _normalize_formats(formats)
    md_content = md_path.read_text(encoding="utf-8")
    # 尝试从 frontmatter 或标题提取场景名
    scenario_name = "未命名场景"
    m = re.search(r"^#\s+(.+)$", md_content, re.MULTILINE)
    if m:
        scenario_name = m.group(1).strip()

    pipeline_context = {
        "source_md_file": md_path.name,
        "pipeline_id": pipeline["id"],
    }

    dir_info = _build_skill_dir_from_markdown(
        md_content, scenario_name, step4_dir, pipeline_context
    )

    pid_short = pipeline["id"][:8]
    skill_slug = _slugify(scenario_name)

    artifacts: dict = {}
    # Skill 产物
    skill_file = _artifact_publish_name(pid_short, "SKILL_", "SKILL.md", skill_slug)
    manifest_file = _artifact_publish_name(pid_short, "SKILL_DIR_", "manifest.json", skill_slug)
    zip_file = _artifact_publish_name(pid_short, "SKILL_DIR_", f"{skill_slug}.zip", skill_slug)
    _publish_artifact(step4_dir, "SKILL.md", skill_file)
    _publish_artifact(step4_dir, "manifest.json", manifest_file)
    _publish_artifact(step4_dir, os.path.basename(dir_info["zip_path"]), zip_file)
    artifacts["skill"] = {
        "file_name": skill_file,
        "manifest_file_name": manifest_file,
        "zip_path": str(step4_dir / zip_file),
    }

    # CoT：Markdown 流无法结构化生成，写说明占位
    if "cot" in fmt:
        cot_name = _artifact_publish_name(pid_short, "COT_", "chain_of_thought.md", skill_slug)
        cot_path = step4_dir / "chain_of_thought.md"
        cot_path.write_text(
            f"# {scenario_name} · 思维链\n\n"
            "当前为 Markdown 流，思维链需要从 IR 流或 Excel 对齐稿结构化生成。\n",
            encoding="utf-8",
        )
        _publish_artifact(step4_dir, "chain_of_thought.md", cot_name)
        artifacts["cot"] = {"file_name": cot_name}

    # QA：Markdown 流无法结构化生成，写说明占位
    if "qa" in fmt:
        qa_name = _artifact_publish_name(pid_short, "QA_", "qa_pairs.json", skill_slug)
        qa_md_name = _artifact_publish_name(pid_short, "QA_", "qa_pairs.md", skill_slug)
        qa_path = step4_dir / "qa_pairs.json"
        qa_md_path = step4_dir / "qa_pairs.md"
        qa_data = {
            "schema": "tacit-knowledge.qa/v1",
            "scenario": scenario_name,
            "count": 0,
            "items": [],
            "note": "当前为 Markdown 流，QA 对需要从 IR 流或 Excel 对齐稿结构化生成。",
        }
        qa_path.write_text(json.dumps(qa_data, ensure_ascii=False, indent=2), encoding="utf-8")
        qa_md_path.write_text(
            f"# {scenario_name} · QA 对\n\n{qa_data['note']}\n",
            encoding="utf-8",
        )
        _publish_artifact(step4_dir, "qa_pairs.json", qa_name)
        _publish_artifact(step4_dir, "qa_pairs.md", qa_md_name)
        artifacts["qa"] = {"file_name": qa_name, "markdown_file_name": qa_md_name}

    downloads = _update_pipeline_step4(pipeline, artifacts, "1.0.0")

    return {
        "status": "ok",
        "input_kind": "markdown",
        "ir_version": None,
        "knowledge_count": 0,
        "category_count": 0,
        "quality_score": 0,
        "formats": sorted(fmt),
        "skill_dir_zip_url": downloads.get("skill_zip", ""),
        "downloads": downloads,
    }


def compile_pipeline(
    pipeline_id: str,
    workspace: Path,
    formats: str | None = None,
) -> dict:
    """Step4: 从知识对齐稿生成思维链 / QA / Skill 交付包.

    支持 IR 流（step3_aligned_file / step2_draft_file）与 Markdown 流。
    """
    if not pipeline_id:
        return {"status": "error", "error": "缺少 pipeline_id"}

    workspace = Path(workspace)
    step4_dir = workspace_path_for(workspace, pipeline_id, "step4", "")
    step4_dir.mkdir(parents=True, exist_ok=True)

    with _pipelines_lock:
        pipelines = load_pipelines()
        pipeline = next((p for p in pipelines if p["id"] == pipeline_id), None)
        if not pipeline:
            return {"status": "error", "error": "流水线不存在"}

        sd = pipeline.setdefault("step_data", {})
        source_path, _source_key = resolve_knowledge_ir_path(workspace, sd)
        if not source_path:
            return {"status": "error", "error": "未找到 Step3 对齐稿或 Step2 萃取稿，无法编译"}

        try:
            if str(source_path).lower().endswith(".md"):
                result = _compile_from_markdown(pipeline, source_path, step4_dir, formats)
            else:
                result = _compile_from_ir(pipeline, source_path, step4_dir, formats)
        except Exception as e:
            return {"status": "error", "error": f"编译失败: {e}"}

        if result.get("status") != "ok":
            return result

        # 推进流水线状态
        step_status = pipeline.setdefault("step_status", {})
        step_status["4"] = "done"
        pipeline["current_step"] = max(pipeline.get("current_step", 1), 5)
        step_status["5"] = step_status.get("5", "active")
        pipeline["updated_at"] = datetime.datetime.now().isoformat()

        save_pipelines(pipelines)

        return result

"""Pipeline workspace artifact naming and path safety invariants."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

PROTECTED_WORKSPACE_FILES = frozenset({
    "pipelines.json",
    "custom_models.json",
    "preset_overrides.json",
})

DOWNLOAD_ALLOWED_PREFIXES = (
    "template_",
    "preextract_",
    "revision_",
    "final_",
    "edited_step",
    "upload_",
    "edit_read_",
    "upload_tpl_",
    "signal_report_",
    "SKILL_",
    "COT_",
    "QA_",
    "openclaw_",
    "quality_report_",
    "report_",
    "cache_",
    # 新 Skill 产出报告
    "pattern_mining_",
    "gap_analysis_",
    "freshness_audit_",
    # 多源融合
    "fusion_",
    "interview_",
    # 信号报告
    "signal_report_",
    # Skill IR 草稿（Skill 中心化流水线）
    "skill_draft_",
    # Step5 验证环节
    "validation_",
    "revision_suggestions_",
    # 知识库导出
    "kb_",
)

STEP_OUTPUT_KEYS_BY_STEP = {
    1: (
        "step1_output_file", "step1_download_url",
        "step1_md_file", "step1_md_download_url",
        "step1_knowledge_columns", "step1_output_format",
        "step1_template_source", "step1_template_name",
    ),
    2: (
        "step2_output_file", "step2_download_url",
        "step2_md_file", "step2_md_download_url",
        "step2_extracted_count", "skill_extract_result", "skill_extract_style",
        # 多源融合
        "step2_fusion_file", "step2_fusion_download_url",
        "step2_fusion_count", "step2_fusion_conflicts",
        "step2_fusion_sources",
        # 访谈
        "step2_interview_file", "step2_interview_count",
        # 信号报告（新版统一端点产出）
        "step2_signal_report_file", "step2_signal_report_url",
        "step2_source_count", "step2_dedup_count",
        # Skill IR 草稿 v1（Skill 中心化流水线主产物）
        "step2_draft_file", "step2_draft_url",
        "step2_draft_md_file", "step2_draft_md_url",
        "step2_draft_version",
    ),
    # UI 第 3 步「知识对齐」产出 final_*.xlsx + 对齐版 Skill IR（vN, status=aligned）
    3: (
        "step3_final_file", "step3_final_download_url", "step3_final_md_file", "step3_final_md_download_url",
        "step3_final_notes", "step3_final_style", "step3_final_count",
        "step3_revision_file", "step3_download_url", "step3_md_file", "step3_md_download_url",
        "step3_revision_notes", "step3_revision_style", "step3_revision_count", "step3_excel_path",
        "step3_aligned_file", "step3_aligned_url",
        "step3_aligned_md_file", "step3_aligned_md_url",
        "step3_aligned_version", "step3_pending_suggestions",
    ),
    4: (
        "step4_skill_file", "step4_download_url",
        "step4_cot_file", "step4_cot_download_url",
        "step4_qa_file", "step4_qa_download_url", "step4_qa_md_file", "step4_qa_md_download_url",
        "step4_manifest_file", "step4_manifest_url",
        "step4_quality_file", "step4_quality_url",
        "step4_published_version",
    ),
    # 第 5 步「验证」：决策回放 + 分歧回流
    5: (
        "step5_replay_file", "step5_replay_url",
        "step5_result_file", "step5_result_url",
        "step5_suggestions_file", "step5_suggestions_url",
        "step5_hit_rate", "step5_case_source", "step5_run_id",
        "step5_golden_report_file", "step5_golden_report_url",
    ),
}


def basename_only(name: str) -> str:
    return os.path.basename((name or "").strip().replace("\\", "/"))


def is_step1_filename(name: str) -> bool:
    n = basename_only(name).lower()
    return n.endswith(".xlsx") and (n.startswith("template_") or n.startswith("edited_step1_"))


def is_step2_preextract_filename(name: str) -> bool:
    n = basename_only(name).lower()
    return n.endswith(".xlsx") and (n.startswith("preextract_") or n.startswith("edited_step2_"))


def is_step3_revision_filename(name: str) -> bool:
    n = basename_only(name).lower()
    return n.endswith(".xlsx") and (n.startswith("revision_") or n.startswith("edited_step3_"))


def is_step3_final_filename(name: str) -> bool:
    n = basename_only(name).lower()
    return n.endswith(".xlsx") and (n.startswith("final_") or n.startswith("edited_step3_"))


def is_skill_draft_filename(name: str) -> bool:
    """Skill IR 草稿文件（Step2 v1 draft / Step3 aligned vN）。"""
    n = basename_only(name).lower()
    return n.endswith(".json") and n.startswith("skill_draft_")


_STEP_PREFIX_RULES = [
    (re.compile(r"^(?:edited_step1_|template_)"), "step1"),
    (re.compile(r"^(?:edited_step2_|preextract_|fusion_|signal_report_|interview_|skill_draft_.*_v1_)"), "step2"),
    (re.compile(r"^(?:edited_step3_|final_|revision_|skill_draft_.*_v(?!1\b)\d+_)"), "step3"),
    (re.compile(r"^(?:SKILL_|SKILL_DIR_|COT_|QA_|openclaw_|delivery_|pattern_mining_|gap_analysis_|freshness_audit_)"), "step4"),
    (re.compile(r"^(?:validation_|quality_report_)"), "step5"),
    (re.compile(r"^(?:cache_s\d+|upload|edit_read|upload_tpl)_"), "uploads"),
]


def infer_file_step(name: str) -> str | None:
    """根据文件名前缀推断所属 step/目录。"""
    base = basename_only(name)
    for pattern, step in _STEP_PREFIX_RULES:
        if pattern.search(base):
            return step
    return None


def workspace_path_for(workspace: Path, pipeline_id: str, step: str, filename: str) -> Path:
    """返回产物应写入的完整路径。"""
    if not pipeline_id or not step:
        return Path(workspace) / basename_only(filename)
    return Path(workspace) / str(pipeline_id) / str(step) / basename_only(filename)


def locate_workspace_file(
    workspace: Path,
    filename: str,
    *,
    pipeline_id: str | None = None,
) -> Path | None:
    """按 basename 定位文件，优先子目录，fallback 根目录。"""
    base = basename_only(filename)
    workspace = Path(workspace)

    # 1. 如果给了 pipeline_id，优先在对应目录按推断 step 查找
    if pipeline_id:
        step = infer_file_step(base)
        if step:
            candidate = workspace / str(pipeline_id) / step / base
            if candidate.is_file():
                return candidate
        # 兜底：在该 pipeline 所有子目录里找
        pipeline_dir = workspace / str(pipeline_id)
        if pipeline_dir.is_dir():
            for subdir in pipeline_dir.iterdir():
                if subdir.is_dir():
                    candidate = subdir / base
                    if candidate.is_file():
                        return candidate

    # 2. 全局子目录搜索
    for root, _dirs, files in os.walk(workspace):
        if base in files:
            return Path(root) / base

    # 3. fallback 根目录
    root_candidate = workspace / base
    return root_candidate if root_candidate.is_file() else None


def resolve_knowledge_ir_path(
    workspace: Path,
    step_data: dict,
) -> tuple[Path | None, str]:
    """Resolve the best Skill IR draft for compile/validation.

    优先级：step3_aligned_file（对齐版）→ step2_draft_file（萃取稿，smoke only）。
    """
    if not isinstance(step_data, dict):
        return None, ""
    for key in ("step3_aligned_file", "step2_draft_file"):
        raw = step_data.get(key, "")
        if not raw or not is_skill_draft_filename(str(raw)):
            continue
        resolved = safe_workspace_path(workspace, str(raw), must_exist=True)
        if resolved:
            return resolved, key
    return None, ""


def resolve_knowledge_workbook_path(
    workspace: Path,
    step_data: dict,
    *,
    purpose: str = "compile",
) -> tuple[Path | None, str]:
    """Resolve the best on-disk knowledge Excel for align/compile.

    purpose=align: prefer latest alignment draft, then legacy revision, then Step2 preextract.
    purpose=compile: prefer final_*.xlsx, then legacy revision_*.xlsx, then preextract (smoke only).
    """
    if not isinstance(step_data, dict):
        return None, ""

    candidates = (
        ("step3_final_file", is_step3_final_filename),
        ("step3_revision_file", is_step3_revision_filename),
        ("step2_output_file", is_step2_preextract_filename),
    )

    for key, validator in candidates:
        raw = step_data.get(key, "")
        if not raw or not validator(str(raw)):
            continue
        resolved = safe_workspace_path(workspace, str(raw), must_exist=True)
        if resolved:
            return resolved, key
    return None, ""


def is_download_allowed(name: str) -> bool:
    base = basename_only(name)
    if not base or base in PROTECTED_WORKSPACE_FILES:
        return False
    return any(base.startswith(p) for p in DOWNLOAD_ALLOWED_PREFIXES)


def is_cache_filename(name: str) -> bool:
    """Uploaded source files cached for Step2/3/4 (cache_s2_*, cache_s3_*, etc.)."""
    base = basename_only(name)
    return bool(base) and base.startswith("cache_")


def resolve_cache_file_path(workspace: Path, name: str) -> Path | None:
    """Resolve a cached upload path; rejects non-cache and protected names."""
    if not is_cache_filename(name):
        return None
    return safe_workspace_path(workspace, name, must_exist=True)


def safe_workspace_path(workspace: Path, name: str, *, must_exist: bool = True) -> Path | None:
    base = basename_only(name)
    if not base or base in PROTECTED_WORKSPACE_FILES:
        return None
    try:
        root = workspace.resolve()
        path = (workspace / base).resolve()
        path.relative_to(root)
    except ValueError:
        return None
    if must_exist and not path.is_file():
        return None
    return path


def resolve_client_excel_path(workspace: Path, file_path: str, file_name: str = "") -> Path | None:
    """Resolve excel editor path: prefer basename file_name under workspace."""
    if file_name:
        return safe_workspace_path(workspace, file_name, must_exist=True)
    raw = (file_path or "").strip()
    if not raw:
        return None
    base = basename_only(raw)
    candidate = safe_workspace_path(workspace, base, must_exist=True)
    if candidate:
        return candidate
    try:
        p = Path(raw).resolve()
        p.relative_to(workspace.resolve())
        if p.is_file():
            return p
    except (ValueError, OSError):
        pass
    return None


def validate_step_data_patch(patch: dict) -> str | None:
    """Return error message if step_data output fields violate invariants."""
    if not isinstance(patch, dict):
        return None
    checks = (
        ("step1_output_file", is_step1_filename),
        ("step2_output_file", is_step2_preextract_filename),
        ("step3_revision_file", is_step3_revision_filename),
        ("step3_final_file", is_step3_final_filename),
        ("step2_draft_file", is_skill_draft_filename),
        ("step3_aligned_file", is_skill_draft_filename),
    )
    for key, fn in checks:
        val = patch.get(key)
        if val and not fn(str(val)):
            return f"非法 {key}: {val}"
    for key in ("step1_download_url", "step2_download_url", "step3_download_url", "step3_final_download_url", "step4_download_url",
                "step2_draft_url", "step3_aligned_url", "step5_replay_url", "step5_suggestions_url"):
        url = patch.get(key)
        if not url:
            continue
        part = str(url).split("/")[-1]
        if part and not is_download_allowed(part):
            return f"非法下载路径 {key}: {url}"
    return None


def downstream_output_keys(from_step: int) -> list[str]:
    keys = []
    for step, names in STEP_OUTPUT_KEYS_BY_STEP.items():
        if step > from_step:
            keys.extend(names)
    return keys


MAX_PIPELINE_STEP = 5


def auxiliary_step_data_keys(from_step: int) -> list[str]:
    """Non-output step_data keys to clear on rollback / upstream regenerate."""
    keys = []
    for step in range(from_step, MAX_PIPELINE_STEP + 1):
        keys.extend((
            f"step{step}_cached_file",
            f"step{step}_excel_path",
            f"step{step}_preview_name",
            f"step{step}_preview_url",
        ))
    if from_step <= 4:
        keys.extend(("step4_quality_file", "step4_quality_url"))
    return keys


def keys_to_clear_from_step(from_step: int) -> list[str]:
    return list(dict.fromkeys(downstream_output_keys(from_step) + auxiliary_step_data_keys(from_step)))


def organize_workspace(workspace: Path) -> dict:
    """一次性迁移：把根目录下能识别归属的文件按 pipeline/step 分类，无归属的删除。"""
    workspace = Path(workspace)
    marker = workspace / ".workspace_organized"
    if marker.exists():
        return {"moved": 0, "deleted": 0, "skipped": 0}

    result = {"moved": 0, "deleted": 0, "skipped": 0}

    # 建立每个 pipeline 引用过的 basename 集合
    pipeline_refs: dict[str, set[str]] = {}
    pipelines_file = workspace / "pipelines.json"
    if pipelines_file.is_file():
        try:
            pipelines = json.loads(pipelines_file.read_text(encoding="utf-8"))
            for p in pipelines or []:
                pid = str(p.get("id", ""))
                if not pid:
                    continue
                refs: set[str] = set()
                sd = p.get("step_data", {})
                for val in sd.values():
                    if isinstance(val, str):
                        refs.add(basename_only(val))
                pipeline_refs[pid] = refs
        except Exception:
            pass

    for item in list(workspace.iterdir()):
        if not item.is_file():
            continue
        if item.name in PROTECTED_WORKSPACE_FILES or item.name == ".workspace_organized":
            result["skipped"] += 1
            continue

        step = infer_file_step(item.name)
        if not step:
            try:
                item.unlink()
                result["deleted"] += 1
            except Exception:
                pass
            continue

        target_pid = None
        for pid, refs in pipeline_refs.items():
            if item.name in refs:
                target_pid = pid
                break

        if target_pid:
            dest_dir = workspace / target_pid / step
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / item.name
            try:
                item.rename(dest)
                result["moved"] += 1
            except Exception:
                pass
        else:
            try:
                item.unlink()
                result["deleted"] += 1
            except Exception:
                pass

    marker.write_text("", encoding="utf-8")
    return result

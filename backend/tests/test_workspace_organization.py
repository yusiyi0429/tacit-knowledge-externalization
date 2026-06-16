#!/usr/bin/env python3
"""Tests for pipeline workspace organization utilities."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pipeline_artifacts as pa  # noqa: E402


def test_infer_file_step():
    assert pa.infer_file_step("template_abc.xlsx") == "step1"
    assert pa.infer_file_step("edited_step1_abc.xlsx") == "step1"

    assert pa.infer_file_step("preextract_abc.xlsx") == "step2"
    assert pa.infer_file_step("edited_step2_abc.xlsx") == "step2"
    assert pa.infer_file_step("skill_draft_pid_v1_abc.json") == "step2"
    assert pa.infer_file_step("fusion_abc.json") == "step2"
    assert pa.infer_file_step("signal_report_abc.json") == "step2"
    assert pa.infer_file_step("interview_abc.json") == "step2"

    assert pa.infer_file_step("final_pid_123456.xlsx") == "step3"
    assert pa.infer_file_step("revision_pid_123456.xlsx") == "step3"
    assert pa.infer_file_step("edited_step3_abc.xlsx") == "step3"
    assert pa.infer_file_step("skill_draft_pid_v2_abc.json") == "step3"
    assert pa.infer_file_step("skill_draft_pid_v10_abc.json") == "step3"

    assert pa.infer_file_step("SKILL_abc.md") == "step4"
    assert pa.infer_file_step("SKILL_DIR_abc.zip") == "step4"
    assert pa.infer_file_step("COT_abc.md") == "step4"
    assert pa.infer_file_step("QA_abc.json") == "step4"
    assert pa.infer_file_step("openclaw_abc.json") == "step4"
    assert pa.infer_file_step("delivery_abc") == "step4"
    assert pa.infer_file_step("pattern_mining_abc.json") == "step4"
    assert pa.infer_file_step("gap_analysis_abc.json") == "step4"
    assert pa.infer_file_step("freshness_audit_abc.json") == "step4"

    assert pa.infer_file_step("validation_result_abc.json") == "step5"
    assert pa.infer_file_step("quality_report_abc.md") == "step5"

    assert pa.infer_file_step("cache_s2_abc.txt") == "uploads"
    assert pa.infer_file_step("cache_s3_abc.txt") == "uploads"
    assert pa.infer_file_step("upload_abc.xlsx") == "uploads"
    assert pa.infer_file_step("edit_read_abc.xlsx") == "uploads"
    assert pa.infer_file_step("upload_tpl_abc.xlsx") == "uploads"

    assert pa.infer_file_step("unknown.bin") is None
    assert pa.infer_file_step("pipelines.json") is None


def test_workspace_path_for_and_locate(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()

    path = pa.workspace_path_for(workspace, "pid123", "step2", "preextract_abc.xlsx")
    assert path == workspace / "pid123" / "step2" / "preextract_abc.xlsx"

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x")

    # Direct lookup via inferred step inside pipeline.
    assert pa.locate_workspace_file(workspace, "preextract_abc.xlsx", pipeline_id="pid123") == path
    # Fallback search across all subdirectories.
    assert pa.locate_workspace_file(workspace, "preextract_abc.xlsx") == path
    # Root fallback when no subdirectories match.
    root_file = workspace / "template_root.xlsx"
    root_file.write_text("y")
    assert pa.locate_workspace_file(workspace, "template_root.xlsx") == root_file
    # Missing file returns None.
    assert pa.locate_workspace_file(workspace, "missing.bin") is None


def test_organize_workspace(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()

    # Protected files stay in root.
    (workspace / "pipelines.json").write_text(
        json.dumps([
            {
                "id": "pid123",
                "step_data": {
                    "step2_output_file": "preextract_abc.xlsx",
                    "step2_interview_file": "/downloads/interview_abc.json",
                    "step4_skill_file": "SKILL_abc.md",
                    "step4_skill_dir_zip_file": "SKILL_DIR_abc.zip",
                    "step5_result_file": "validation_result_abc.json",
                    "step1_output_file": "template_abc.xlsx",
                    "step3_final_file": "final_pid123_20260101.xlsx",
                    "note": "This is a string but not a file reference",
                },
            }
        ]),
        encoding="utf-8",
    )
    (workspace / "custom_models.json").write_text("{}", encoding="utf-8")
    (workspace / "preset_overrides.json").write_text("{}", encoding="utf-8")

    # Referenced artifacts at root.
    (workspace / "preextract_abc.xlsx").write_text("x", encoding="utf-8")
    (workspace / "interview_abc.json").write_text("y", encoding="utf-8")
    (workspace / "SKILL_abc.md").write_text("z", encoding="utf-8")
    (workspace / "SKILL_DIR_abc.zip").write_text("zip", encoding="utf-8")
    (workspace / "validation_result_abc.json").write_text("v", encoding="utf-8")
    (workspace / "template_abc.xlsx").write_text("t", encoding="utf-8")
    (workspace / "final_pid123_20260101.xlsx").write_text("f", encoding="utf-8")

    # Unreferenced but recognizable files are deleted.
    (workspace / "preextract_orphan.xlsx").write_text("o", encoding="utf-8")
    (workspace / "random.txt").write_text("r", encoding="utf-8")

    result = pa.organize_workspace(workspace)
    assert result["moved"] == 7
    assert result["deleted"] == 2
    assert result["skipped"] == 3  # protected files

    # Referenced files moved into pipeline/step subdirectories.
    assert (workspace / "pid123" / "step1" / "template_abc.xlsx").is_file()
    assert (workspace / "pid123" / "step2" / "preextract_abc.xlsx").is_file()
    assert (workspace / "pid123" / "step2" / "interview_abc.json").is_file()
    assert (workspace / "pid123" / "step4" / "SKILL_abc.md").is_file()
    assert (workspace / "pid123" / "step4" / "SKILL_DIR_abc.zip").is_file()
    assert (workspace / "pid123" / "step5" / "validation_result_abc.json").is_file()
    assert (workspace / "pid123" / "step3" / "final_pid123_20260101.xlsx").is_file()

    # Deleted/unreferenced files no longer exist at root.
    assert not (workspace / "preextract_abc.xlsx").exists()
    assert not (workspace / "preextract_orphan.xlsx").exists()
    assert not (workspace / "random.txt").exists()

    # Marker created.
    assert (workspace / ".workspace_organized").is_file()

    # Idempotency: second run reports no work.
    result2 = pa.organize_workspace(workspace)
    assert result2 == {"moved": 0, "deleted": 0, "skipped": 0}


def test_organize_workspace_delivery_directories(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()

    delivery_name = "delivery_abc123"
    (workspace / "pipelines.json").write_text(
        json.dumps([
            {
                "id": "pid123",
                "step_data": {
                    "step4_skill_file": "SKILL_abc.md",
                    # Reference the delivery directory by its basename so it is migrated.
                    "step4_delivery_dir": delivery_name,
                },
            }
        ]),
        encoding="utf-8",
    )

    # Referenced delivery directory at root.
    delivery_dir = workspace / delivery_name
    delivery_dir.mkdir()
    (delivery_dir / "SKILL.md").write_text("skill", encoding="utf-8")
    (delivery_dir / "chain_of_thought.md").write_text("cot", encoding="utf-8")

    # Unreferenced delivery directory should be deleted.
    orphan_delivery = workspace / "delivery_orphan"
    orphan_delivery.mkdir()
    (orphan_delivery / "file.txt").write_text("x", encoding="utf-8")

    result = pa.organize_workspace(workspace)
    assert result["moved"] == 1
    assert result["deleted"] == 1
    assert result["skipped"] == 1  # pipelines.json

    # Referenced delivery directory moved into pipeline step4 subdir.
    assert (workspace / "pid123" / "step4" / delivery_name / "SKILL.md").is_file()
    assert (workspace / "pid123" / "step4" / delivery_name / "chain_of_thought.md").is_file()
    assert not delivery_dir.exists()

    # Orphan delivery directory deleted.
    assert not orphan_delivery.exists()
    assert (workspace / ".workspace_organized").is_file()

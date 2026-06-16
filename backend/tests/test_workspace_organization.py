#!/usr/bin/env python3
"""Tests for pipeline workspace organization utilities."""

from __future__ import annotations

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

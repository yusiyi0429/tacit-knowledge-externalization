from pathlib import Path

import openpyxl
from field_aliases import resolve_header
from shared import get_samples_dir


def test_english_samples_dir_exists():
    path = get_samples_dir("en")
    assert path.exists()
    assert path.name == "en"


def test_english_excel_template_exists():
    path = get_samples_dir("en") / "step1-scenario-anchoring" / "english-credit-scenario-template.xlsx"
    assert path.exists()


def test_english_source_doc_exists():
    path = get_samples_dir("en") / "step2-doc-extraction" / "english-loan-marketing-guide.txt"
    assert path.exists()


def test_english_excel_headers_are_recognized():
    path = get_samples_dir("en") / "step1-scenario-anchoring" / "english-credit-scenario-template.xlsx"
    wb = openpyxl.load_workbook(path)
    ws = wb.active
    headers = [str(cell.value).strip() if cell.value else "" for cell in next(ws.iter_rows(min_row=1, max_row=1))]
    wb.close()

    recognized = {h: resolve_header(h) for h in headers if h}
    assert recognized["method"] == "knowledge_desc"
    assert recognized["condition"] == "applicable_condition"
    assert recognized["logic"] == "judgment_logic"
    # Anchor columns and the remaining knowledge columns should also resolve
    assert recognized["scenario"] == "scenario"
    assert recognized["scenario_desc"] == "scenario_desc"
    assert recognized["sub_scenario"] == "sub_scenario"
    assert recognized["sub_scenario_desc"] == "sub_scenario_desc"
    assert recognized["stage"] == "stage"
    assert recognized["interview_direction"] == "interview_direction"
    assert recognized["knowledge_type"] == "knowledge_type"
    assert recognized["reference"] == "reference"
    assert recognized["anti_pattern"] == "anti_pattern"
    assert recognized["experience_judgment"] == "expert_judgment"
    assert recognized["boundary"] == "applicable_boundary"
    assert recognized["exception"] == "exception_case"
    assert recognized["source_doc"] == "source_doc"
    assert recognized["source_location"] == "source_location"
    assert recognized["confidence"] == "confidence"
    assert recognized["contributor"] == "contributor"
    assert recognized["evidence_count"] == "evidence_count"
    assert recognized["breakthrough_count"] == "breakthrough_count"

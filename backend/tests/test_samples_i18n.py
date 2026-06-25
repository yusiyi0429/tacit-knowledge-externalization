from pathlib import Path
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

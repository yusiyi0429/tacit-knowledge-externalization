from pathlib import Path

from skill_registry import get_prompt_template_path


def test_english_prompt_selected():
    path = get_prompt_template_path("step2_generate_skill_md.txt", locale="en")
    assert path.name == "step2_generate_skill_md.en.txt"
    text = path.read_text(encoding="utf-8")
    assert "Customer Filter" in text


def test_chinese_prompt_fallback():
    path = get_prompt_template_path("step2_generate_skill_md.txt", locale="zh-CN")
    assert path.name == "step2_generate_skill_md.txt"


def test_invalid_locale_falls_back_to_chinese():
    path = get_prompt_template_path("step2_generate_skill_md.txt", locale="fr")
    assert path.name == "step2_generate_skill_md.txt"

from skill_registry import get_skill_registry


def test_english_skill_name():
    registry = get_skill_registry("en")
    assert registry["knowledge-extraction"]["name"] == "Knowledge Extraction"
    assert registry["knowledge-revision"]["name"] == "Knowledge Alignment"
    assert registry["skill-generator"]["name"] == "Skill Generator"


def test_chinese_skill_name_unchanged():
    registry = get_skill_registry("zh-CN")
    assert registry["knowledge-extraction"]["name"] == "知识萃取"


def test_invalid_locale_falls_back_to_chinese():
    registry = get_skill_registry("fr")
    assert registry["knowledge-extraction"]["name"] == "知识萃取"

from field_aliases import FIELD_ALIASES, DISPLAY_NAMES, resolve_header


def test_resolve_header_english():
    assert resolve_header("Knowledge Description") == "knowledge_desc"


def test_resolve_header_chinese():
    assert resolve_header("知识描述") == "knowledge_desc"


def test_resolve_header_method_alias():
    assert resolve_header("method") == "knowledge_desc"


def test_resolve_header_knowledge_id():
    assert resolve_header("知识编号") == "knowledge_id"
    assert resolve_header("KN编号") == "knowledge_id"


def test_resolve_header_unknown():
    assert resolve_header("未知列") == "未知列"


def test_all_english_display_names_resolve():
    for canonical, labels in DISPLAY_NAMES.items():
        display = labels.get("en")
        if display and canonical in FIELD_ALIASES:
            assert resolve_header(display) == canonical, f"{display!r} did not resolve to {canonical}"

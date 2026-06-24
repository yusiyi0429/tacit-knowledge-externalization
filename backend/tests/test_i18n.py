from i18n import resolve_locale, t, add_messages


def test_resolve_locale_prefers_query():
    assert resolve_locale(query_lang="en", pipeline_locale="zh-CN") == "en"


def test_resolve_locale_falls_back_to_pipeline():
    assert resolve_locale(pipeline_locale="en", header_lang="zh-CN") == "en"


def test_resolve_locale_accepts_accept_language():
    assert resolve_locale(header_lang="en-US,zh;q=0.9") == "en"


def test_t_english_message():
    assert t("pipeline_name_required", lang="en") == "Pipeline name is required"


def test_t_format_kwargs():
    assert t("skill_generation_failed", lang="en", error="timeout") == "Skill generation failed: timeout"


def test_add_messages():
    add_messages("en", {"custom_key": "Custom value"})
    assert t("custom_key", lang="en") == "Custom value"

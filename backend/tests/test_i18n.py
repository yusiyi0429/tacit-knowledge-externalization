from i18n import DEFAULT_LANG, SUPPORTED_LANGS, add_messages, get_messages, resolve_locale, t


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
    try:
        assert t("custom_key", lang="en") == "Custom value"
    finally:
        _MESSAGES = __import__("i18n", fromlist=["_MESSAGES"])._MESSAGES
        _MESSAGES["en"].pop("custom_key", None)


def test_add_messages_rejects_unsupported_language():
    try:
        add_messages("fr", {"custom_key": "valeur"})
    except ValueError as exc:
        assert "fr" in str(exc)
    else:
        raise AssertionError("Expected ValueError for unsupported language")


def test_resolve_locale_unsupported_falls_back_to_default():
    assert resolve_locale(query_lang="fr") == DEFAULT_LANG


def test_t_missing_key_returns_key():
    assert t("missing_key_12345", lang="en") == "missing_key_12345"


def test_t_unsupported_lang_falls_back_to_default():
    default_message = t("pipeline_name_required", lang=DEFAULT_LANG)
    assert t("pipeline_name_required", lang="fr") == default_message


def test_t_missing_format_placeholder_returns_template():
    assert t("skill_generation_failed", lang="en") == "Skill generation failed: {error}"


def test_resolve_locale_falls_back_when_all_candidates_unsupported():
    assert resolve_locale(query_lang="fr", header_lang="de") == DEFAULT_LANG


def test_resolve_locale_empty_candidates_fallback():
    assert resolve_locale(query_lang="", header_lang=None, pipeline_locale="") == DEFAULT_LANG


def test_get_messages_returns_copy():
    messages = get_messages("en")
    messages["new_key"] = "new value"
    assert "new_key" not in get_messages("en")


def test_resolve_locale_case_insensitive():
    assert resolve_locale(query_lang="EN") == "en"
    assert resolve_locale(query_lang="zh-cn") == "zh-CN"


def test_resolve_locale_zh_variant_header():
    assert resolve_locale(header_lang="zh-TW,en;q=0.9") == "zh-CN"

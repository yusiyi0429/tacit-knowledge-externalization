"""Label helpers for locale-aware artifact rendering."""
from i18n import t


def report_label(key: str, locale: str = "zh-CN") -> str:
    return t(key, locale)

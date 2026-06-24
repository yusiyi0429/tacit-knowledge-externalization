import os
import re
import subprocess
import sys
import time
from html.parser import HTMLParser

import requests


FRONTEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
)

# Chinese fallback text inside elements with matching data-i18n attributes.
TARGETS = {
    "选择模型": "select_model_label",
    "生成待验证 Skill + 思维链 + QA 对": "step4_generate_btn",
    "执行 P/R/F1 验证": "step5_run_validation_btn",
    "反馈分歧到 Step3": "step5_feedback_btn",
    "简体中文": "lang_zh_cn",
}


class _I18nHtmlParser(HTMLParser):
    """Collect the text content of elements that have a data-i18n attribute."""

    def __init__(self):
        super().__init__()
        # Stack of i18n keys for currently open tags (None for tags without data-i18n).
        self._stack = []
        # Accumulated text parts per i18n key.
        self._text_parts = {}
        # Final mapping of data-i18n key -> stripped text content.
        self.i18n_texts = {}

    def _current_key(self):
        for key in reversed(self._stack):
            if key is not None:
                return key
        return None

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        key = attrs_dict.get("data-i18n")
        self._stack.append(key)
        if key is not None:
            # Start fresh text collection for this element occurrence.
            self._text_parts[key] = []

    def handle_endtag(self, tag):
        if not self._stack:
            return
        key = self._stack.pop()
        if key is not None and key in self._text_parts:
            text = "".join(self._text_parts[key]).strip()
            if text:
                self.i18n_texts[key] = text

    def handle_data(self, data):
        key = self._current_key()
        if key is not None:
            self._text_parts[key].append(data)


def _read_assigned_port(stdout):
    # http.server writes its "Serving HTTP on ..." startup line to stdout.
    pattern = re.compile(r"Serving HTTP on .* port (\d+)")
    deadline = time.time() + 10
    while time.time() < deadline:
        line = stdout.readline()
        if not line:
            time.sleep(0.05)
            continue
        match = pattern.search(line)
        if match:
            return int(match.group(1))
    raise RuntimeError("Could not read assigned server port from http.server output")


def test_css_english_diff_labels_present():
    css_path = os.path.join(FRONTEND_DIR, "css", "style.css")
    assert os.path.exists(css_path), f"expected CSS file at {css_path}"
    with open(css_path, "r", encoding="utf-8") as f:
        css = f.read()

    expected_rules = [
        'html[lang="en"] .align-diff-old::before { content: \'Original\'; }',
        'html[lang="en"] .align-diff-new::before { content: \'Modified\'; }',
        'html[lang="en"] .align-diff-add::before { content: \'Added\'; }',
    ]
    for rule in expected_rules:
        assert rule in css, f"expected CSS to contain {rule!r}"


def _extract_i18n_block(content, lang):
    """Extract the top-level object body for a language key."""
    # Match either quoted ('zh-CN') or bare (en) keys.
    prefix = re.escape(lang) if lang in ("'zh-CN'", "en") else re.escape(lang)
    pattern = re.compile(rf"{prefix}\s*:\s*{{", re.S)
    m = pattern.search(content)
    if not m:
        raise ValueError(f"Could not find language block {lang!r}")
    start = m.end() - 1
    balance = 0
    i = start
    in_str = False
    esc = False
    start_quote = None
    while i < len(content):
        ch = content[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif start_quote is not None and ch == content[start_quote]:
                in_str = False
                start_quote = None
        else:
            if ch in ('"', "'", "`"):
                in_str = True
                start_quote = i
            elif ch == "{":
                balance += 1
            elif ch == "}":
                balance -= 1
                if balance == 0:
                    return content[start + 1 : i]
        i += 1
    raise ValueError(f"Unterminated language block {lang!r}")


def _parse_js_string_keys(block):
    """Return {key: raw_string_value} for simple string literals in a JS object body."""
    result = {}
    # Single-quoted values
    for m in re.finditer(r"(\w+):\s*'((?:[^'\\]|\\.)*)'", block):
        result[m.group(1)] = m.group(2)
    # Double-quoted values
    for m in re.finditer(r'(\w+):\s*"((?:[^"\\]|\\.)*)"', block):
        result[m.group(1)] = m.group(2)
    return result


def _collect_runtime_i18n_keys():
    """Collect keys used via App.I18n.t('key', 'fallback') or t('key', 'fallback') in JS."""
    keys = {}
    js_dir = os.path.join(FRONTEND_DIR, "js")
    for filename in os.listdir(js_dir):
        if not filename.endswith(".js") or filename == "i18n.js":
            continue
        path = os.path.join(js_dir, filename)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        for m in re.finditer(
            r"(?:App\.I18n\.)?(?<![A-Za-z0-9_])t\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]*)['\"]\s*\)",
            content,
        ):
            keys[m.group(1)] = {"file": filename, "fallback": m.group(2)}
    return keys


def test_js_i18n_keys_have_translations():
    i18n_path = os.path.join(FRONTEND_DIR, "js", "i18n.js")
    with open(i18n_path, "r", encoding="utf-8") as f:
        content = f.read()
    zh = _parse_js_string_keys(_extract_i18n_block(content, "'zh-CN'"))
    en = _parse_js_string_keys(_extract_i18n_block(content, "en"))
    runtime_keys = _collect_runtime_i18n_keys()
    missing_zh = [k for k in runtime_keys if k not in zh]
    missing_en = [k for k in runtime_keys if k not in en]
    assert not missing_zh, f"Runtime i18n keys missing in zh-CN: {missing_zh}"
    assert not missing_en, f"Runtime i18n keys missing in en: {missing_en}"


def test_english_i18n_values_no_unexpected_cjk():
    i18n_path = os.path.join(FRONTEND_DIR, "js", "i18n.js")
    with open(i18n_path, "r", encoding="utf-8") as f:
        content = f.read()
    en = _parse_js_string_keys(_extract_i18n_block(content, "en"))
    # Bilingual UI labels are intentionally allowed to contain CJK.
    whitelist = {"lang_toggle", "lang_toggle_title"}
    offenders = [
        (k, v) for k, v in en.items() if re.search(r"[\u4e00-\u9fff]", v) and k not in whitelist
    ]
    assert not offenders, f"English i18n values contain unexpected CJK: {offenders[:20]}"


def test_no_unwrapped_chinese_labels():
    proc = subprocess.Popen(
        # -u ensures http.server prints its "Serving HTTP ..." line immediately.
        [sys.executable, "-u", "-m", "http.server", "0"],
        cwd=FRONTEND_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        port = _read_assigned_port(proc.stdout)
        resp = requests.get(f"http://127.0.0.1:{port}/index.html")
        assert resp.status_code == 200

        # http.server does not declare charset; index.html is UTF-8.
        html = resp.content.decode("utf-8")

        parser = _I18nHtmlParser()
        parser.feed(html)

        for expected_text, key in TARGETS.items():
            actual_text = parser.i18n_texts.get(key)
            assert actual_text == expected_text, (
                f"expected data-i18n={key!r} to contain {expected_text!r}, "
                f"got {actual_text!r}"
            )
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

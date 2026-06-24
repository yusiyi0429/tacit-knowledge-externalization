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

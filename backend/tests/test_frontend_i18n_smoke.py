import os
import subprocess
import sys
import time

import requests


FRONTEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
)


def test_no_unwrapped_chinese_labels():
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", "8123"],
        cwd=FRONTEND_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1)
    try:
        resp = requests.get("http://127.0.0.1:8123/index.html")
        assert resp.status_code == 200
        html = resp.text
        assert "选择模型" not in html or 'data-i18n="select_model_label"' in html
        assert (
            "生成待验证 Skill + 思维链 + QA 对" not in html
            or 'data-i18n="step4_generate_btn"' in html
        )
        assert (
            "执行 P/R/F1 验证" not in html
            or 'data-i18n="step5_run_validation_btn"' in html
        )
        assert (
            "反馈分歧到 Step3" not in html
            or 'data-i18n="step5_feedback_btn"' in html
        )
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

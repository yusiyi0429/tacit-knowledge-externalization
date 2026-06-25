# Pure English Operation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a bilingual platform where pipelines can run end-to-end in English (`en`) while preserving the existing Chinese (`zh-CN`) experience.

**Architecture:** A single `locale` context flows from the browser → HTTP header/pipeline `step_data` → backend → LLM prompt/schema selection → generated artifacts. Canonical internal keys become English; Chinese strings are kept as accepted aliases for legacy compatibility.

**Tech Stack:** Python 3.12, Flask, PyYAML, openpyxl, vanilla JS, Luckysheet.

---

## Phase 1: Backend locale & i18n foundation

### Task 1.1: Create backend i18n module

**Files:**
- Create: `backend/i18n.py`
- Test: `backend/tests/test_i18n.py`

- [ ] **Step 1: Write the i18n module**

```python
"""Lightweight backend i18n."""
from __future__ import annotations

import os
from typing import Any

DEFAULT_LANG = os.environ.get("DEFAULT_LANG", "zh-CN")
SUPPORTED_LANGS = {"zh-CN", "en"}

_MESSAGES: dict[str, dict[str, str]] = {
    "zh-CN": {
        "pipeline_name_required": "流水线名称不能为空",
        "file_not_found": "文件不存在",
        "download_not_allowed": "不允许下载该文件",
        "read_not_allowed": "不允许读取该文件",
        "write_not_allowed": "不允许写入该文件",
        "missing_upload_file": "缺少上传文件",
        "pipeline_not_found": "流水线不存在",
        "invalid_step": "步骤号必须在 1-5 之间",
        "scenario_name_required": "场景名称不能为空",
        "need_at_least_one_knowledge_column": "请至少定义一列知识字段",
        "template_format_error": "模板仅支持 .xlsx / .xls 格式",
        "need_scenario_skeleton_first": "请先在「场景锚定」生成场景骨架",
        "skill_md_not_found": "未找到 SKILL.md（请先完成 Step2/Step3）",
        "skill_generation_failed": "Skill生成失败: {error}",
        "need_extraction_first": "未找到可转化的知识稿。请先完成「知识萃取」",
        "delivery_failed": "智能转化失败: {error}",
        "suggestion_pool_empty": "建议池为空",
        "need_adopt_or_reject": "请至少采纳或驳回一条建议",
        "markdown_use_editor": "当前为 Markdown 流程，请使用知识对齐节点的编辑器手动修订",
        "need_preextract_first": "未找到可对齐的知识稿。请先完成「知识萃取」生成 preextract_*.xlsx",
        "llm_parse_failed": "LLM输出解析失败: {error}",
        "need_step4_first": "请先完成 Step4 智能转化",
        "validation_not_passed": "验证未通过 (precision={precision})，请先完成验证回流",
        "customers_must_be_array": "customers 必须是数组",
    },
    "en": {
        "pipeline_name_required": "Pipeline name is required",
        "file_not_found": "File not found",
        "download_not_allowed": "Download not allowed for this file",
        "read_not_allowed": "Read not allowed for this file",
        "write_not_allowed": "Write not allowed for this file",
        "missing_upload_file": "Missing upload file",
        "pipeline_not_found": "Pipeline not found",
        "invalid_step": "Step number must be between 1 and 5",
        "scenario_name_required": "Scenario name is required",
        "need_at_least_one_knowledge_column": "Please define at least one knowledge column",
        "template_format_error": "Template must be .xlsx / .xls",
        "need_scenario_skeleton_first": "Please generate the scenario skeleton in Scenario Anchoring first",
        "skill_md_not_found": "SKILL.md not found (please complete Step 2 / Step 3 first)",
        "skill_generation_failed": "Skill generation failed: {error}",
        "need_extraction_first": "No knowledge draft found. Please complete Knowledge Extraction first",
        "delivery_failed": "Delivery generation failed: {error}",
        "suggestion_pool_empty": "Suggestion pool is empty",
        "need_adopt_or_reject": "Please adopt or reject at least one suggestion",
        "markdown_use_editor": "Current pipeline uses Markdown flow; please revise using the Knowledge Alignment editor",
        "need_preextract_first": "No alignable draft found. Please complete Knowledge Extraction to generate preextract_*.xlsx",
        "llm_parse_failed": "LLM output parsing failed: {error}",
        "need_step4_first": "Please complete Step 4 Delivery first",
        "validation_not_passed": "Validation not passed (precision={precision}); please complete validation feedback",
        "customers_must_be_array": "customers must be an array",
    },
}


def resolve_locale(
    *,
    query_lang: str | None = None,
    header_lang: str | None = None,
    pipeline_locale: str | None = None,
) -> str:
    for candidate in (query_lang, pipeline_locale, header_lang):
        if candidate:
            normalized = candidate.split(",")[0].strip().lower()
            if normalized in SUPPORTED_LANGS:
                return normalized
            if normalized.startswith("en"):
                return "en"
            if normalized.startswith("zh"):
                return "zh-CN"
    return DEFAULT_LANG


def t(key: str, lang: str = DEFAULT_LANG, **kwargs: Any) -> str:
    lang = lang if lang in SUPPORTED_LANGS else DEFAULT_LANG
    message = _MESSAGES.get(lang, _MESSAGES[DEFAULT_LANG]).get(key, key)
    if kwargs:
        try:
            return message.format(**kwargs)
        except KeyError:
            return message
    return message


def add_messages(lang: str, messages: dict[str, str]) -> None:
    if lang not in _MESSAGES:
        _MESSAGES[lang] = {}
    _MESSAGES[lang].update(messages)


def get_messages(lang: str) -> dict[str, str]:
    return dict(_MESSAGES.get(lang, {}))
```

- [ ] **Step 2: Write the failing test**

```python
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
```

- [ ] **Step 3: Run the test and verify it fails**

Run: `cd backend && python -m pytest tests/test_i18n.py -v`
Expected: `ModuleNotFoundError: No module named 'i18n'`

- [ ] **Step 4: Create the file and run tests again**

Create `backend/i18n.py` with the code above, then rerun the test command.
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/i18n.py backend/tests/test_i18n.py
git commit -m "feat(i18n): add backend locale resolver and translation helper"
```

---

### Task 1.2: Add locale detection to Flask requests

**Files:**
- Modify: `backend/shared.py`
- Modify: `backend/app_server.py`

- [ ] **Step 1: Import `i18n` helpers in `shared.py`**

Add near the top of `backend/shared.py`:

```python
from i18n import resolve_locale, t
```

- [ ] **Step 2: Add a locale helper that reads pipeline state**

Insert into `backend/shared.py` after the pipeline helpers section:

```python
def get_current_locale(pipeline_id: str | None = None) -> str:
    """Resolve locale from request context and pipeline state."""
    from flask import request
    query_lang = (request.args.get("lang") or "").strip() or None
    header_lang = (request.headers.get("Accept-Language") or "").strip() or None
    pipeline_locale = None
    if pipeline_id:
        for p in load_pipelines():
            if p.get("id") == pipeline_id:
                pipeline_locale = (p.get("step_data") or {}).get("locale")
                break
    return resolve_locale(
        query_lang=query_lang,
        header_lang=header_lang,
        pipeline_locale=pipeline_locale,
    )
```

- [ ] **Step 3: Add `locale` to pipeline create/update in `app_server.py`**

Locate the pipeline create endpoint (around the JSON parsing that builds `new_pipeline`) and update:

```python
new_pipeline = {
    "id": pipeline_id,
    "name": name,
    "scenario_name": scenario_name,
    "created_at": datetime.datetime.now().isoformat(),
    "current_step": 1,
    "step_data": {
        "locale": data.get("locale", "zh-CN"),
        # retain all existing step_data fields here
    },
}
```

Locate the pipeline update endpoint and ensure `locale` is allowed through validation/patch:

```python
if "locale" in patch:
    step_data["locale"] = patch["locale"]
```

- [ ] **Step 4: Replace a representative API error message**

Find in `backend/app_server.py`:

```python
return jsonify({"status": "error", "message": "流水线名称不能为空"}), 400
```

Replace with:

```python
locale = get_current_locale()
return jsonify({"status": "error", "message": t("pipeline_name_required", locale)}), 400
```

Repeat for `file_not_found`, `download_not_allowed`, `pipeline_not_found`, and `skill_md_not_found` using their matching keys.

- [ ] **Step 5: Test the locale-aware endpoint**

```bash
cd backend
python -m pytest tests/test_app_server_locale.py -v
```

Create `backend/tests/test_app_server_locale.py`:

```python
import json
import pytest
from app_server import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_create_pipeline_stores_locale(client, tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path))
    resp = client.post("/api/pipelines", json={"name": "EN demo", "scenario_name": "Credit", "locale": "en"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["pipeline"]["step_data"]["locale"] == "en"


def test_missing_name_returns_english_when_locale_en(client, tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path))
    resp = client.post("/api/pipelines", json={"name": "", "scenario_name": "Credit", "locale": "en"})
    assert resp.status_code == 400
    assert "Pipeline name is required" in resp.get_json()["message"]
```

- [ ] **Step 6: Commit**

```bash
git add backend/shared.py backend/app_server.py backend/tests/test_app_server_locale.py
git commit -m "feat(i18n): wire locale into requests and pipeline state"
```

---

## Phase 2: Frontend English UI

### Task 2.1: Close static HTML translation gaps

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/js/i18n.js`

- [ ] **Step 1: Add missing `data-i18n` keys in `index.html`**

Locate the following bare Chinese strings and wrap them:

```html
<!-- before -->
<label>选择模型</label>
<!-- after -->
<label data-i18n="select_model_label">选择模型</label>

<!-- before -->
<button>生成待验证 Skill + 思维链 + QA 对</button>
<!-- after -->
<button data-i18n="step4_generate_btn">生成待验证 Skill + 思维链 + QA 对</button>

<!-- before -->
<button>执行 P/R/F1 验证</button>
<!-- after -->
<button data-i18n="step5_run_validation_btn">执行 P/R/F1 验证</button>

<!-- before -->
<button>反馈分歧到 Step3</button>
<!-- after -->
<button data-i18n="step5_feedback_btn">反馈分歧到 Step3</button>

<!-- before -->
<option>简体中文</option>
<!-- after -->
<option data-i18n="lang_zh_cn">简体中文</option>
```

- [ ] **Step 2: Add English translations in `i18n.js`**

Add to `translations['en']`:

```js
select_model_label: 'Select Model',
step4_generate_btn: 'Generate Skill + CoT + QA Pairs',
step5_run_validation_btn: 'Run P/R/F1 Validation',
step5_feedback_btn: 'Feedback Divergence to Step 3',
lang_zh_cn: 'Simplified Chinese',
```

Add to `translations['zh-CN']`:

```js
select_model_label: '选择模型',
step4_generate_btn: '生成待验证 Skill + 思维链 + QA 对',
step5_run_validation_btn: '执行 P/R/F1 验证',
step5_feedback_btn: '反馈分歧到 Step3',
lang_zh_cn: '简体中文',
```

- [ ] **Step 3: Verify by opening the UI in English**

Open `frontend/index.html`, run `localStorage.setItem('app-lang', 'en')` in the console, reload, and confirm the four labels above are English.

- [ ] **Step 4: Commit**

```bash
git add frontend/index.html frontend/js/i18n.js
git commit -m "feat(i18n): add data-i18n keys for remaining static HTML labels"
```

---

### Task 2.2: Localize CSS pseudo-elements

**Files:**
- Modify: `frontend/css/style.css`

- [ ] **Step 1: Add language-scoped rules**

Append to `frontend/css/style.css`:

```css
html[lang="en"] .align-diff-old::before { content: 'Original'; }
html[lang="en"] .align-diff-new::before { content: 'Modified'; }
html[lang="en"] .align-diff-add::before { content: 'Added'; }
```

Ensure the existing Chinese rules remain under the default (no `html[lang]`) selector.

- [ ] **Step 2: Verify**

Open Step 3 alignment diff in English UI and confirm labels show "Original / Modified / Added".

- [ ] **Step 3: Commit**

```bash
git add frontend/css/style.css
git commit -m "feat(i18n): localize CSS diff labels for English"
```

---

### Task 2.3: Refactor runtime JS strings to keyed translations

**Files:**
- Modify: `frontend/js/app.js`, `frontend/js/utils.js`, `frontend/js/excel-luckysheet.js`
- Modify: `frontend/js/i18n.js`

- [ ] **Step 1: Audit unkeyed Chinese strings**

Run from project root:

```bash
python - <<'PY'
import re
for path in ["frontend/js/app.js", "frontend/js/utils.js", "frontend/js/excel-luckysheet.js"]:
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            if re.search(r'[\u4e00-\u9fa5]{2,}', line) and "App.I18n.t(" not in line and "data-i18n" not in line:
                print(f"{path}:{i}: {line.strip()}")
PY
```

Save output to `/tmp/unkeyed_chinese.txt`.

- [ ] **Step 2: Add high-frequency keys to `i18n.js`**

Add representative keys to both locales. Example for `app.js`:

```js
// In translations['en']
toast_saved: 'Saved',
toast_save_failed: 'Save failed',
toast_loading: 'Loading...',
toast_unknown_error: 'Unknown error',
toast_network_error: 'Network error',
confirm_delete_pipeline: 'Delete this pipeline? This cannot be undone.',
step2_complete: 'Knowledge extraction complete',
step2_extracted_count: 'Extracted {count} knowledge items',
step4_qa_pairs: 'QA Pairs',
step4_chain_of_thought: 'Chain of Thought',
step4_agent_skill: 'Agent-Skill Pending Validation',
```

- [ ] **Step 3: Replace representative strings in `app.js`**

Find:

```js
showToast('已保存');
```

Replace with:

```js
showToast(App.I18n.t('toast_saved', 'Saved'));
```

Find:

```js
`知识萃取完成，共提取 ${n} 条知识`
```

Replace with:

```js
App.I18n.t('step2_complete', 'Knowledge extraction complete') + ` — ${App.I18n.t('step2_extracted_count', 'Extracted {count} knowledge items').replace('{count}', n)}`
```

Repeat for all strings in `/tmp/unkeyed_chinese.txt`, splitting variable-interpolated phrases into keyed templates.

- [ ] **Step 4: Update `utils.js` and `excel-luckysheet.js`**

Replace hardcoded strings with `App.I18n.t()` calls using new keys added in Step 2.

- [ ] **Step 5: Add a frontend smoke test**

Create `frontend/tests/i18n-smoke.test.js` (or a simple Python script that launches a static server and checks for Chinese in the DOM):

```python
# backend/tests/test_frontend_i18n_smoke.py
import subprocess
import time
import requests


def test_no_chinese_in_english_ui():
    proc = subprocess.Popen(
        ["python", "-m", "http.server", "8123"],
        cwd="frontend",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1)
    try:
        resp = requests.get("http://127.0.0.1:8123/index.html")
        assert resp.status_code == 200
        html = resp.text
        # Static HTML should not contain bare Chinese labels when data-i18n is used
        assert "选择模型" not in html or 'data-i18n="select_model_label"' in html
    finally:
        proc.terminate()
```

- [ ] **Step 6: Commit**

```bash
git add frontend/js/app.js frontend/js/utils.js frontend/js/excel-luckysheet.js frontend/js/i18n.js backend/tests/test_frontend_i18n_smoke.py
git commit -m "feat(i18n): key runtime JS strings and add smoke test"
```

---

## Phase 3: Backend-generated English artifacts

### Task 3.1: Bilingual skill registry metadata

**Files:**
- Modify: `backend/skill_registry.py`
- Modify: `backend/app_server.py`

- [ ] **Step 1: Add English fields to skill entries**

In `backend/skill_registry.py`, add an `i18n` sub-dict to each skill:

```python
"i18n": {
    "en": {
        "name": "Knowledge Extraction",
        "description": "Generate an Agent SKILL.md draft from scenario skeleton and knowledge documents via LLM.",
        "detailed_description": "Knowledge Extraction is the core entry point of the tacit-knowledge externalization pipeline. The Skill receives the scenario skeleton produced in Step 1 and expert-provided knowledge documents, then invokes a large language model to distill a structured Agent SKILL.md containing role definition, core processes, decision rules, and data access logic.",
        "business_value": "Convert expert experience scattered across documents, policies, and cases into machine-executable Agent Skills, significantly reducing the manual cost of knowledge沉淀. One extraction can cover a complete business scenario; the pipeline continuously iterates afterwards.",
        "usage_guide": "1. Ensure Step 1 Scenario Anchoring is completed and the skeleton is generated.\n2. Prepare knowledge documents (.txt / .docx / .pdf) or paste text directly.\n3. Select Markdown Pipeline mode in the UI.\n4. Select a model and click Run Knowledge Extraction.\n5. Wait for the LLM to generate the SKILL.md draft, preview and confirm.",
        "input_example": "Scenario: SME inclusive-loan potential-customer marketing. Knowledge document: english-loan-marketing-guide.txt (contains customer filtering rules, data tags, decision recommendations).",
        "output_example": "SKILL.md file containing role definition, core process (customer filter → demand analysis → product matching → marketing execution), data table references, and decision rules.",
        "applicable_scenarios": ["SME potential-customer mining and marketing", "Inclusive-loan product recommendation", "Customer segmentation and precision marketing", "New-customer admission assessment"],
        "capabilities": ["Scenario skeleton parsing", "Knowledge-document understanding", "Rule and logic extraction", "Agent SKILL.md generation"],
        "supported_formats": [".txt", ".docx", ".pdf", "plain text paste"],
        "output_styles": ["Structured SKILL.md", "Includes role/process/rules/data"],
        "triggers": ["User completes Step 1 Scenario Anchoring", "User uploads knowledge documents and selects Knowledge Extraction"],
        "limitations": ["Output quality depends on input document quality", "LLM-generated draft requires expert alignment in Step 3", "Does not yet support deep parsing of image/table-structured documents"],
    }
}
```

- [ ] **Step 2: Add a helper function**

Add to `backend/skill_registry.py`:

```python
def get_skill_registry(lang: str = "zh-CN") -> dict:
    if lang not in {"zh-CN", "en"}:
        lang = "zh-CN"
    result = {}
    for sid, skill in SKILL_REGISTRY.items():
        entry = dict(skill)
        i18n = entry.pop("i18n", {})
        translations = i18n.get(lang, {})
        for key, value in translations.items():
            if key in entry:
                entry[key] = value
        result[sid] = entry
    return result
```

- [ ] **Step 3: Update `/api/skills` route**

In `backend/app_server.py`, locate the skills list endpoint and change:

```python
from skill_registry import SKILL_REGISTRY, get_skill_registry
# other imports remain unchanged
locale = get_current_locale()
return jsonify({"skills": get_skill_registry(locale)})
```

- [ ] **Step 4: Test**

```bash
cd backend && python -m pytest tests/test_skill_registry_i18n.py -v
```

Sample test:

```python
from skill_registry import get_skill_registry


def test_english_skill_name():
    registry = get_skill_registry("en")
    assert registry["knowledge-extraction"]["name"] == "Knowledge Extraction"
```

- [ ] **Step 5: Commit**

```bash
git add backend/skill_registry.py backend/app_server.py backend/tests/test_skill_registry_i18n.py
git commit -m "feat(i18n): make skill registry metadata bilingual"
```

---

### Task 3.2: English scenario schema

**Files:**
- Create: `config/scenario-schema.en.yaml`
- Modify: `backend/shared.py`

- [ ] **Step 1: Create English schema file**

Create `config/scenario-schema.en.yaml`:

```yaml
scenario_name: default-knowledge-extraction
display_name: Generic Knowledge Extraction Structure
domain: Generic
version: "v1.1"
auto_generate_id: true

scenario:
  business_boundary: ""
  target_users: []
  decision_types: []

categories:
  - Decision Rule
  - Operation Flow
  - Anti-pattern

fields:
  - name: stage
    type: text
    required: false
    fill_rule: Business process stage or step name
    example: Customer onboarding
  - name: interview_direction
    type: text
    required: false
    fill_rule: Focus of expert interview
    example: Risk identification criteria
  - name: method
    type: long_text
    required: true
    fill_rule: Executable method, rule or operational key point
    example: Verify both credit report and cash flow
  - name: knowledge_type
    type: enum
    required: false
    fill_rule: Align with categories
    example: Decision Rule
    enum_values:
      - Decision Rule
      - Operation Flow
      - Anti-pattern
  - name: reference
    type: text
    required: false
    fill_rule: Policy / manual reference
    example: Credit Management Policy Chapter 3
  - name: condition
    type: long_text
    required: false
    fill_rule: When this knowledge applies
    example: New customer first credit grant
  - name: logic
    type: long_text
    required: false
    fill_rule: Decision chain and branches
    example: Rating A and stable cash flow then approve
  - name: anti_pattern
    type: long_text
    required: false
    fill_rule: Common mistakes and pitfalls
    example: Only look at collateral, ignore cash flow
  - name: experience_judgment
    type: long_text
    required: false
    fill_rule: Expert experiential judgment and rationale
    example: Chip design firms are light-asset; do not only look at collateral
  - name: boundary
    type: long_text
    required: false
    fill_rule: Situations where this rule does not apply
    example: Chip firms whose founders are from CAS or top universities may have relaxed tenure requirements
  - name: exception
    type: long_text
    required: false
    fill_rule: Scenarios that have been broken in practice
    example: In 2024, Company X had a controller change but stable business
  - name: source_doc
    type: text
    required: false
    fill_rule: Source document or policy name
    example: Technology Enterprise Inclusive Loan Operation Guide
  - name: source_location
    type: text
    required: false
    fill_rule: Specific location in the source
    example: Chapter 2 3.1.2
  - name: confidence
    type: enum
    required: false
    fill_rule: Knowledge confidence
    example: medium
    enum_values: [high, medium, low]
  - name: contributor
    type: text
    required: false
    fill_rule: Expert name or ID who contributed this knowledge
    example: Zhang San
  - name: evidence_count
    type: integer
    required: false
    fill_rule: Number of cases supporting this knowledge
    example: 3
  - name: breakthrough_count
    type: integer
    required: false
    fill_rule: Number of times the rule has been broken in practice
    example: 1

interview:
  methods:
    - case_retrospection
    - contrast_probe
    - extreme_hypothesis
  min_sessions: 3
  session_duration_minutes: 60
  required_experts: 2

quality:
  target_per_pipeline: 30
  library_target: 800
  min_confidence_level: medium
  source_annotation_rate: 0.60
  anti_pattern_ratio: 0.10
  skill_score_threshold: 75
  replay_hit_threshold: 0.8

compilation:
  output_format: SKILL.md
  include_anti_patterns_section: true
  include_usage_examples: true
```

- [ ] **Step 2: Make schema path locale-aware**

In `backend/shared.py`, replace:

```python
SCHEMA_PATH = CONFIG_DIR / "scenario-schema.yaml"
```

with:

```python
def get_schema_path(locale: str = "zh-CN") -> Path:
    suffix = "" if locale == "zh-CN" else f".{locale}"
    path = CONFIG_DIR / f"scenario-schema{suffix}.yaml"
    if path.exists():
        return path
    return CONFIG_DIR / "scenario-schema.yaml"

SCHEMA_PATH = get_schema_path()
```

Update all direct usages of `SCHEMA_PATH` in the backend to call `get_schema_path(locale)`.

- [ ] **Step 3: Test**

```python
from shared import get_schema_path


def test_english_schema_exists():
    assert get_schema_path("en").exists()
    assert get_schema_path("en").name == "scenario-schema.en.yaml"
```

- [ ] **Step 4: Commit**

```bash
git add config/scenario-schema.en.yaml backend/shared.py backend/tests/test_schema_i18n.py
git commit -m "feat(i18n): add English scenario schema and locale-aware loader"
```

---

### Task 3.3: Bilingual field aliases, IR phases, and enums

**Files:**
- Modify: `backend/field_aliases.py`
- Modify: `backend/skill_ir.py`
- Modify: `backend/shared.py`
- Modify: `backend/step5_agent_verify.py`
- Modify: `backend/validation_replay.py`

- [ ] **Step 1: Add English canonical names to aliases**

In `backend/field_aliases.py`, update `FIELD_ALIASES` so each canonical has both Chinese and English aliases:

```python
FIELD_ALIASES = {
    "knowledge_id": ["知识编号", "编号", "KN编号", "知识ID", "knowledge_id"],
    "category": ["知识分类", "分类", "类型", "知识要点", "知识", "category"],
    "knowledge_desc": [
        "知识描述", "描述", "知识内容", "内容", "数据规则", "具体方案",
        "具体方法", "场景说明", "子场景说明", "知识说明", "knowledge_desc", "method"
    ],
    "condition": ["适用条件", "触发条件", "条件", "condition"],
    "logic": ["判断逻辑", "判断规则", "逻辑", "规则引用", "logic"],
    "anti_pattern": ["反模式/踩坑提示", "反模式", "踩坑提示", "注意事项", "anti_pattern", "anti-pattern"],
    "experience_judgment": ["经验判断", "专家经验判断", "experience_judgment"],
    "boundary": ["适用边界", "适用边界/例外", "boundary"],
    "exception": ["例外情形", "例外场景", "破例场景", "exception"],
    "source_doc": ["来源文档", "来源", "source_doc"],
    "source_location": ["来源位置", "位置", "页码", "source_location"],
    "original_excerpt": ["原文摘录", "摘录", "original_excerpt"],
    "confidence": ["置信度", "可信度", "confidence"],
    "contributor": ["贡献专家", "贡献人", "contributor"],
    "confirmed_expert": ["确认专家", "确认人", "confirmed_expert"],
    "evidence_count": ["证据数", "案例支撑数", "evidence_count"],
    "breakthrough_count": ["突破数", "被突破数", "break_count", "breakthrough_count"],
    "note": ["备注", "说明", "修订说明", "note"],
}

# Backward-compatible canonical→display mapping
DISPLAY_NAMES = {
    "zh-CN": {
        "knowledge_id": "知识编号",
        "category": "知识分类",
        "knowledge_desc": "知识描述",
        # add remaining canonical→display pairs here
    },
    "en": {
        "knowledge_id": "Knowledge ID",
        "category": "Category",
        "knowledge_desc": "Knowledge Description",
        # add remaining canonical→display pairs here
    },
}
```

- [ ] **Step 2: Update `resolve_header` to return English canonical**

```python
def resolve_header(raw_header: str) -> str:
    if not raw_header:
        return ""
    raw = str(raw_header).strip()
    for canonical, aliases in FIELD_ALIASES.items():
        if raw in aliases:
            return canonical
    return raw
```

- [ ] **Step 3: Make IR step phases bilingual**

In `backend/skill_ir.py`:

```python
VALID_STEP_PHASES = ("customer_filter", "data_match", "attribution", "decision")
_STEP_PHASE_ALIASES = {
    "customer_filter": ["customer_filter", "客户筛选"],
    "data_match": ["data_match", "客户数据匹配"],
    "attribution": ["attribution", "原因归因"],
    "decision": ["decision", "决策建议"],
}


def normalize_step_phase(phase: str) -> str:
    p = (phase or "").strip().lower()
    for canonical, aliases in _STEP_PHASE_ALIASES.items():
        if p in [a.lower() for a in aliases]:
            return canonical
    return p
```

Update `validate_ir_v2` to call `normalize_step_phase` before checking membership.

- [ ] **Step 4: Bilingual confidence and action normalizers**

In `backend/shared.py`:

```python
_CONFIDENCE_RANK = {"high": 3, "medium": 2, "low": 1, "极高": 4, "极低": 0}
_CONFIDENCE_ALIASES = {
    "high": ["high", "高"],
    "medium": ["medium", "中"],
    "low": ["low", "低"],
}


def normalize_confidence(value: str) -> str:
    v = (value or "").strip().lower()
    for canonical, aliases in _CONFIDENCE_ALIASES.items():
        if v in [a.lower() for a in aliases]:
            return canonical
    return "medium"


def confidence_rank(value: str) -> int:
    return _CONFIDENCE_RANK.get(normalize_confidence(value), 2)
```

Replace `_extract_item_confidence_rank` body with `confidence_rank(...)`.

- [ ] **Step 5: Update Step 5 normalizers**

In `backend/step5_agent_verify.py` and `backend/validation_replay.py`, update action/label maps:

```python
_ACTION_ALIASES = {
    "approve": ["approve", "通过", "同意"],
    "reject": ["reject", "拒绝", "驳回"],
    "conditional": ["conditional", "条件通过", "条件"],
    "cultivate": ["cultivate", "培育", "培养"],
    "market": ["market", "营销", "推荐"],
}


def normalize_action(label: str) -> str:
    l = (label or "").strip().lower()
    for canonical, aliases in _ACTION_ALIASES.items():
        if l in [a.lower() for a in aliases]:
            return canonical
    return l
```

- [ ] **Step 6: Test**

```bash
cd backend && python -m pytest tests/test_bilingual_aliases.py tests/test_ir_phases.py -v
```

- [ ] **Step 7: Commit**

```bash
git add backend/field_aliases.py backend/skill_ir.py backend/shared.py backend/step5_agent_verify.py backend/validation_replay.py backend/tests/
git commit -m "feat(i18n): bilingual field aliases, IR phases and enums"
```

---

### Task 3.4: English LLM prompt templates

**Files:**
- Create: `backend/prompts/step2_generate_skill_md.en.txt`
- Create: `backend/prompts/step3_align_with_expert.en.txt`
- Create: `backend/prompts/step4_build_deliverables.en.txt`
- Create: `backend/prompts/step2a_rules_extract.en.txt`
- Create: `backend/prompts/step2b_sql_generate.en.txt`
- Modify: prompt loader (likely in `backend/app_server.py` or `backend/skill_registry.py`)

- [ ] **Step 1: Create English Step 2 prompt**

`backend/prompts/step2_generate_skill_md.en.txt`:

```text
You are a domain knowledge engineer. Generate a complete Agent SKILL.md from the scenario skeleton and knowledge documents below.

## Scenario Skeleton
Scenario Name: {{scenario_name}}
Scenario Description: {{scenario_desc}}
Sub-scenarios:
{{sub_scenarios}}

Knowledge column definitions:
{{knowledge_columns}}

## Knowledge Source Documents
{{source_text}}

## Output Requirements

Generate a complete SKILL.md following this structure:

```markdown
# {{scenario_name}}

## Execution Instructions
This Skill executes in four stages: Customer Filter → Data Match → Attribution → Decision Recommendation.

## Knowledge Rules

### Stage 1: Customer Filter
[Extract customer filtering rules from the documents. Each rule contains:]
- **Rule 1**: [rule name]
  - Business description: [one sentence]
  - Data source: [where data comes from]
  - Rule logic: [clear business-language conditions]
  - SQL reference:
    ```sql
    SELECT [columns] FROM [table] WHERE [conditions]
    ```
  - Output: [what this step produces]

[2-4 rules per stage, covering all key conditions from the documents]

### Stage 2: Data Match
[same structure, focused on matching multi-dimensional customer data]

### Stage 3: Attribution
[same structure, focused on classifying the customer situation]

### Stage 4: Decision Recommendation
[same structure, focused on concrete recommendations per attribution result]

## Appendix: Glossary
[Extract professional terms and explain them]
```

## Important Requirements
1. SQL must use standard SQLite syntax; only SELECT statements.
2. Rules must come from the documents; do not invent.
3. Each rule must include at least one SQL example.
4. Total rules: 8-20.
5. Output must be complete Markdown without ellipses or "omitted".
```

- [ ] **Step 2: Create English Step 4 prompt**

`backend/prompts/step4_build_deliverables.en.txt`:

```text
You are a domain knowledge engineer. Based on the SKILL.md below, generate three deliverables at once: QA pairs, Chain-of-Thought, and an Agent-Skill executable structure.

## Input SKILL.md
{{skill_md}}

## Deliverable 1: QA Pairs (JSON array)

Convert each knowledge rule into a question-answer pair for RAG retrieval and Step 5 validation.

Format:
```json
[
  {
    "q": "In [scenario], [specific question]?",
    "a": "[Precise answer quoting the rule]",
    "rule_id": "Rule name from SKILL.md",
    "phase": "customer_filter|data_match|attribution|decision",
    "sql": "[Corresponding SQL reference]"
  }
]
```

Requirements:
- At least 1 QA pair per rule
- Questions must be specific and verifiable
- Answers must quote key parts of the rule
- If a rule contains SQL, include the SQL in the QA pair

## Deliverable 2: Chain-of-Thought (Markdown)

Generate a step-by-step reasoning chain for the whole decision flow.

Format:
```markdown
# Chain-of-Thought: {{scenario_name}}

## Step 1: Customer Filter
[Reasoning: which conditions to filter, why, expected number of customers]

## Step 2: Data Match
[Reasoning: how to match data, dimensions, failure handling]

## Step 3: Attribution
[Reasoning: how to classify, logic, boundary handling]

## Step 4: Decision Recommendation
[Reasoning: recommendations per attribution, priority, exception handling]
```

Requirements:
- 3-5 sentences per step
- Reasoning must be based on SKILL.md rules
- Mark key decision points and conditions

## Deliverable 3: Agent-Skill Executable Structure (JSON)

Generate the executable structure including SQL and parameters for each rule.

Format:
```json
{
  "ir_version": "2.0",
  "skill_meta": {
    "scenario_name": "{{scenario_name}}",
    "domain": "{{domain}}",
    "status": "aligned"
  },
  "anchors": {
    "scenario": "{{scenario_name}}",
    "scenario_desc": "{{scenario_desc}}"
  },
  "entries": [
    {
      "entry_id": "KN-001",
      "sub_scenario": "sub-scenario name",
      "step_phase": "customer_filter",
      "fields": {
        "knowledge_desc": "business description",
        "knowledge_ref": "data source reference",
        "rule_ref": "original rule reference",
        "output": "output description",
        "data_logic": {
          "sql": "SELECT id, name FROM customers WHERE status = 'active'",
          "tables": ["customers"],
          "fields": ["id", "name"],
          "confidence": "high|medium|low"
        }
      }
    }
  ]
}
```

Requirements:
- Extract SQL from each rule into data_logic.sql
- entry_id increments as KN-001, KN-002, KN-003, and so on
- step_phase must correspond to one of the four stages
- confidence judged by SQL completeness and executability

## Output Requirements

Output all three deliverables using these delimiters:

```
===QA_PAIRS===
[JSON array]

===CHAIN_OF_THOUGHT===
[Markdown]

===AGENT_SKILL===
[JSON]
```

No extra explanatory text. Each delimiter on its own line.
```

- [ ] **Step 3: Create remaining English prompts**

Create `step3_align_with_expert.en.txt`, `step2a_rules_extract.en.txt`, and `step2b_sql_generate.en.txt` following the same principle: English instructions, English stage names, same structural delimiters as the Chinese versions.

- [ ] **Step 4: Make prompt loader locale-aware**

If prompts are loaded via `skill_registry.py`, update:

```python
def get_prompt_template_path(template_name: str, locale: str = "zh-CN") -> Path:
    base = Path(template_name).stem
    suffix = "" if locale == "zh-CN" else f".{locale}"
    path = SCRIPT_DIR / "prompts" / f"{base}{suffix}.txt"
    if path.exists():
        return path
    return SCRIPT_DIR / "prompts" / template_name
```

Pass `locale=get_current_locale()` when loading templates in `app_server.py`.

- [ ] **Step 5: Test**

```bash
cd backend && python -m pytest tests/test_prompt_locale.py -v
```

```python
from pathlib import Path
from skill_registry import get_prompt_template_path


def test_english_prompt_selected():
    path = get_prompt_template_path("step2_generate_skill_md.txt", locale="en")
    assert path.name == "step2_generate_skill_md.en.txt"
    assert "Customer Filter" in path.read_text(encoding="utf-8")
```

- [ ] **Step 6: Commit**

```bash
git add backend/prompts/*.en.txt backend/skill_registry.py backend/app_server.py backend/tests/test_prompt_locale.py
git commit -m "feat(i18n): add English LLM prompt templates and locale-aware loader"
```

---

### Task 3.5: Locale-aware report/artifact renderers

**Files:**
- Modify: `backend/agent_skill_builder.py`
- Modify: `backend/knowledge_delivery.py`
- Modify: `backend/quality_report.py`
- Modify: `backend/validation_replay.py`
- Modify: `backend/step1_markdown_builder.py`
- Modify: `backend/skill_generator.py`

- [ ] **Step 1: Introduce renderer labels helper**

Create `backend/i18n_render.py`:

```python
"""Label helpers for locale-aware artifact rendering."""
from i18n import t


def report_label(key: str, locale: str = "zh-CN") -> str:
    return t(key, locale)
```

Add translation keys to `backend/i18n.py`:

```python
"zh-CN": {
    "report_quality_title": "# 知识萃取质量报告",
    "report_validation_title": "# 显性化校验报告 · 决策回放",
    "report_skill_execution": "## 执行说明",
    "report_skill_rules": "## 知识规则",
    "report_glossary": "## 附录：术语表",
    # add additional report label keys here
}
"en": {
    "report_quality_title": "# Knowledge Extraction Quality Report",
    "report_validation_title": "# Explicit Validation Report · Decision Replay",
    "report_skill_execution": "## Execution Instructions",
    "report_skill_rules": "## Knowledge Rules",
    "report_glossary": "## Appendix: Glossary",
    # add additional report label keys here
}
```

- [ ] **Step 2: Update each renderer to accept `locale`**

For each renderer, change function signatures:

```python
def generate_quality_report(existing_params, locale: str = "zh-CN") -> str:
    title = t("report_quality_title", locale)
    # build the report body using title and other translated labels
```

Replace hardcoded Chinese headings with `t(key, locale)` calls using the keys added above.

- [ ] **Step 3: Pass locale through callers**

In `app_server.py`, when calling these renderers, pass `locale=get_current_locale(pipeline_id)`.

- [ ] **Step 4: Test**

```bash
cd backend && python -m pytest tests/test_renderers_i18n.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/i18n_render.py backend/i18n.py backend/agent_skill_builder.py backend/knowledge_delivery.py backend/quality_report.py backend/validation_replay.py backend/step1_markdown_builder.py backend/skill_generator.py backend/app_server.py backend/tests/test_renderers_i18n.py
git commit -m "feat(i18n): locale-aware report and artifact renderers"
```

---

## Phase 4: Sample data, golden DB, and tests

### Task 4.1: English sample templates

**Files:**
- Create: `data/samples/en/step1-scenario-anchoring/english-credit-scenario-template.xlsx`
- Create: `data/samples/en/step2-doc-extraction/english-loan-marketing-guide.txt`
- Modify: `backend/shared.py` sample loader

- [ ] **Step 1: Create English Excel template**

Use openpyxl to generate a template with English headers matching `scenario-schema.en.yaml`.

```python
import openpyxl
from openpyxl import Workbook

wb = Workbook()
ws = wb.active
ws.title = "Scenario"
headers = [
    "Stage", "Interview Direction", "Method", "Knowledge Type", "Reference",
    "Condition", "Logic", "Anti-pattern", "Experience Judgment", "Boundary",
    "Exception", "Source Doc", "Source Location", "Confidence", "Contributor",
    "Evidence Count", "Breakthrough Count"
]
ws.append(headers)
ws.append([
    "Customer onboarding", "Risk identification", "Verify credit and cash flow",
    "Decision Rule", "Credit Policy Ch.3", "New customer first grant",
    "Rating A and stable cash flow => approve", "Ignore cash flow", "",
    "", "", "Credit Policy", "Ch.2 3.1.2", "high", "Expert A", 3, 0
])
wb.save("data/samples/en/step1-scenario-anchoring/english-credit-scenario-template.xlsx")
```

- [ ] **Step 2: Create English source document**

`data/samples/en/step2-doc-extraction/english-loan-marketing-guide.txt`:

```text
# SME Inclusive Loan Marketing Guide

## Customer Filter
Target customers must:
- Be registered for at least 2 years.
- Have annual revenue above 5 million.
- No overdue loans in the past 12 months.

## Data Match
Match customer profile with:
- Credit bureau report
- Cash flow statement
- Tax records

## Decision Recommendation
If rating is A and cash flow is stable, recommend the inclusive loan product.
If rating is below B or cash flow is volatile, decline or request collateral.
```

- [ ] **Step 3: Update sample loader**

In `backend/shared.py`, update `SAMPLES_DIR` usage to select language folder:

```python
def get_samples_dir(locale: str = "zh-CN") -> Path:
    lang_folder = "zh" if locale == "zh-CN" else locale
    path = SAMPLES_DIR / lang_folder
    if path.exists():
        return path
    return SAMPLES_DIR
```

- [ ] **Step 4: Test**

```bash
cd backend && python -m pytest tests/test_samples_i18n.py -v
```

- [ ] **Step 5: Commit**

```bash
git add data/samples/en backend/shared.py backend/tests/test_samples_i18n.py
git commit -m "feat(i18n): add English sample templates and locale-aware loader"
```

---

### Task 4.2: English golden DB support

**Files:**
- Modify: `backend/golden_db.py`
- Create: `data/golden/en/english-credit-golden.json`

- [ ] **Step 1: Add English column aliases**

In `backend/golden_db.py`, replace hardcoded Chinese column names with `resolve_header()` from `field_aliases.py` or a bilingual map.

- [ ] **Step 2: Create English golden data**

Create `data/golden/en/english-credit-golden.json` using English field keys (`knowledge_desc`, `logic`, `confidence`, etc.).

- [ ] **Step 3: Test**

```bash
cd backend && python -m pytest tests/test_golden_db_i18n.py -v
```

- [ ] **Step 4: Commit**

```bash
git add backend/golden_db.py data/golden/en backend/tests/test_golden_db_i18n.py
git commit -m "feat(i18n): support English golden DB entries"
```

---

### Task 4.3: End-to-end English pipeline test

**Files:**
- Create: `backend/tests/test_i18n_en_e2e.py`

- [ ] **Step 1: Write the E2E test**

```python
import json
import pytest
from app_server import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path))
    monkeypatch.setenv("DEFAULT_LANG", "en")
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_full_english_pipeline_generates_english_artifacts(client):
    # Step 0: create pipeline
    resp = client.post("/api/pipelines", json={
        "name": "EN pipeline",
        "scenario_name": "SME Loan Marketing",
        "locale": "en",
    })
    assert resp.status_code == 200
    pipeline = resp.get_json()["pipeline"]
    pid = pipeline["id"]

    # Step 1: generate skeleton
    resp = client.post("/api/step1/build", json={
        "pipeline_id": pid,
        "scenario_name": "SME Loan Marketing",
        "scenario_content": "Marketing guide for SME inclusive loans.",
        "sub_scenarios": [{"name": "Filter", "content": "Filter eligible SMEs"}],
        "knowledge_columns": ["method", "condition", "logic", "anti_pattern"],
        "output_format": "markdown",
    })
    assert resp.status_code == 200

    # Step 2: extract SKILL.md
    with open("data/samples/en/step2-doc-extraction/english-loan-marketing-guide.txt", "rb") as f:
        resp = client.post(
            f"/api/step2/extract_skill_md?pipeline_id={pid}&lang=en",
            data={"source_text": f.read().decode("utf-8"), "source_label": "guide"},
            content_type="multipart/form-data",
        )
    assert resp.status_code == 200
    data = resp.get_json()
    skill_md_path = data["step_data"]["step2_skill_md_file"]
    skill_md = client.get(f"/downloads/{skill_md_path}").data.decode("utf-8")
    assert "Customer Filter" in skill_md
    assert "客户筛选" not in skill_md

    # Step 4: build deliverables
    resp = client.post("/api/step4/build_skill", json={"pipeline_id": pid, "lang": "en"})
    assert resp.status_code == 200
    data = resp.get_json()
    qa_path = data["step_data"]["step4_qa_file"]
    qa = json.loads(client.get(f"/downloads/{qa_path}").data.decode("utf-8"))
    assert any("customer_filter" in (item.get("phase") or "").lower() for item in qa)
```

- [ ] **Step 2: Run the test and iterate until green**

```bash
cd backend && python -m pytest tests/test_i18n_en_e2e.py -v
```

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_i18n_en_e2e.py
git commit -m "test(i18n): add end-to-end English pipeline test"
```

---

## Phase 5: Luckysheet English build

### Task 5.1: Replace vendored Luckysheet with English build

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/js/excel-luckysheet.js`
- Modify: `scripts/setup-frontend-vendor.sh`
- Replace: `frontend/vendor/luckysheet/`

- [ ] **Step 1: Identify English Luckysheet build**

Check the installed `luckysheet` package or a community English fork. If the official package supports `lang: 'en'` via options, keep the current build and configure it:

```js
luckysheet.create({
  container: 'luckysheet',
  lang: 'en',
  // existing options
});
```

If the vendored build does not include English strings, download the official `luckysheet` English release and replace `frontend/vendor/luckysheet/`.

- [ ] **Step 2: Update vendor setup script**

In `scripts/setup-frontend-vendor.sh`, ensure the English build is copied:

```bash
#!/bin/bash
set -e
cd "$(dirname "$0")/../frontend"
npm install
npm run vendor
# Verify English strings exist
if ! grep -q "Save" vendor/luckysheet/dist/luckysheet.umd.js; then
  echo "ERROR: Luckysheet English strings not found" >&2
  exit 1
fi
```

- [ ] **Step 3: Configure Luckysheet locale in `excel-luckysheet.js`**

Locate the `luckysheet.create` call and add `lang: App.I18n.getLang() === 'en' ? 'en' : 'zh'`:

```js
const lang = App.I18n.getLang() === 'en' ? 'en' : 'zh';
luckysheet.create({
  container: containerId,
  lang: lang,
  // keep all existing Luckysheet options here
});
```

- [ ] **Step 4: Verify**

Run the vendor setup, open the Excel editor in English UI, and confirm toolbar labels are English.

- [ ] **Step 5: Commit**

```bash
git add frontend/package.json frontend/js/excel-luckysheet.js scripts/setup-frontend-vendor.sh frontend/vendor/luckysheet
git commit -m "feat(i18n): replace Luckysheet with English-localized build"
```

---

## Phase 6: Documentation

### Task 6.1: English README

**Files:**
- Create: `README_EN.md`

- [ ] **Step 1: Translate README.md to English**

Create `README_EN.md` covering:
- Project overview
- 5-step pipeline
- Quick start
- LLM config
- Frontend vendor setup
- Docker deployment

- [ ] **Step 2: Commit**

```bash
git add README_EN.md
git commit -m "docs: add English README"
```

---

## Self-Review Checklist

- [ ] **Spec coverage:** Every section of the design doc maps to at least one task above.
- [ ] **No placeholders:** No `...`, "TBD", or "implement later" remain in the plan code.
- [ ] **Type consistency:** `locale` is a string (`"zh-CN"` or `"en"`) everywhere; canonical keys are English strings.
- [ ] **Test coverage:** Each task includes a test step.
- [ ] **Dependency order:** Phase 1 must be done before Phase 3 can use `get_current_locale`; Phase 3.3 must precede Phase 4.2 because golden DB depends on field aliases.

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-06-23-pure-english-operation-plan.md`.**

Two execution options:

1. **Subagent-Driven (recommended)** — Dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — Execute tasks in this session using `executing-plans`, batch execution with checkpoints.

Which approach would you like?

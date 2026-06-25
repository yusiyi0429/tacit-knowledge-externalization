# Pure English Operation Design (全流程英文化方案)

**Date:** 2026-06-23  
**Scope:** Make the tacit-knowledge platform runnable end-to-end in English for foreign customers, while preserving the existing Chinese experience as a second locale.

## 1. Goals

- Foreign customers see an all-English UI, API messages, and generated deliverables.
- The same codebase supports both `zh-CN` and `en` deployments/users.
- Generated artifacts (SKILL.md, QA pairs, CoT, Excel, validation/quality reports) are produced in English when the pipeline locale is `en`.
- No regression for existing Chinese users: Chinese remains the default when no locale is selected, and all existing tests continue to pass.

## 2. Non-Goals

- **Not** a one-off English demo branch: this design keeps Chinese and English co-existent.
- **Not** translating internal code comments, admin logs, or developer docs in the first pass.
- **Not** localizing the LLM model itself; we only change the language of prompts and expected output.
- **Not** renaming SQLite columns or internal IR keys wholesale; instead we introduce bilingual aliases.

## 3. Background

The codebase already has a lightweight frontend i18n layer (`frontend/js/i18n.js`) that can switch the UI to English, but:

- Many runtime JS strings are hardcoded Chinese or only covered by a brittle `DYNAMIC_PHRASES` regex table.
- CSS pseudo-elements (`原文`, `修改后`, `新增内容`) cannot be translated by JS.
- The backend has no locale awareness: error messages, skill metadata, and generated content are always Chinese.
- LLM prompt templates in `backend/prompts/*.txt` explicitly request Chinese output.
- `config/scenario-schema.yaml` uses Chinese field names, categories, confidence levels, and interview methods, which propagate into Excel and IR.
- Business logic normalizers (`通过`/`拒绝`, `高`/`中`/`低`, step phases like `客户筛选`) use Chinese strings as keys.

## 4. Design Overview

We introduce a single **locale context** that flows through the system:

```
Browser / API client
        │
        ▼
Frontend ── locale stored in localStorage + pipeline state
        │
        ▼
HTTP header / query param (Accept-Language or ?lang=)
        │
        ▼
Backend ── locale attached to pipeline step_data
        │
        ├── API error/status messages → backend/i18n.py
        ├── LLM prompt selection      → *_en.txt templates
        ├── Schema/config selection   → scenario-schema.en.yaml
        ├── Field/enum normalization  → bilingual aliases
        └── Report/artifact templates → locale-aware renderers
```

Key principles:

1. **Canonical English keys internally, Chinese aliases for legacy compatibility.**
   - Step phases: `customer_filter`, `data_match`, `attribution`, `decision`.
   - Confidence: `high`, `medium`, `low`.
   - Revision actions: `modify`, `delete`, `add`, `supplement`.
   - Chinese strings are accepted on import and mapped to English canonical values; Chinese is emitted only when locale is `zh-CN`.

2. **Schema-driven artifacts.**
   - Excel headers, IR field names, report headings, and skill metadata are derived from the active schema, so switching the schema switches the artifact language.

3. **Minimal backend translation helper.**
   - `backend/i18n.py` with a flat dict per module, selected by pipeline locale or `Accept-Language`. No heavy `gettext`/Babel dependency.

## 5. Locale Model

### 5.1 Where locale lives

- **Frontend:** `localStorage['app-lang']` (`en` | `zh-CN`).
- **Pipeline:** `step_data['locale']` stored in the backend pipeline JSON.
- **Backend request context:** read from (in order):
  1. `?lang=` query param (useful for direct links/tests),
  2. Pipeline `step_data['locale']` when a `pipeline_id` is provided,
  3. `Accept-Language` header,
  4. Environment variable `DEFAULT_LANG` (default `zh-CN` to protect existing users).

### 5.2 Frontend/backend synchronization

- When a user creates a pipeline, the frontend sends `locale` from `localStorage`.
- When the language switcher is toggled, the frontend calls `PUT /api/pipelines/{id}` to update `step_data['locale']` and re-renders the UI.
- The frontend sends `Accept-Language` on every request; the backend uses it as a fallback.

## 6. Frontend Design

### 6.1 Complete keyed translations

- Replace as many hardcoded Chinese strings in `frontend/js/app.js`, `frontend/js/utils.js`, and `frontend/js/excel-luckysheet.js` as possible with `App.I18n.t('key', fallback)`.
- Add the corresponding keys to `translations['en']` (and `translations['zh-CN']` if missing).
- Keep `DYNAMIC_PHRASES` as a safety net for third-party/unkeyed strings, but do not rely on it for first-party UI.

### 6.2 Static HTML gaps

Add `data-i18n` keys for the remaining bare Chinese in `frontend/index.html`:

- `选择模型` (Step 4 model selector label)
- `生成待验证 Skill + 思维链 + QA 对` (Step 4 primary button)
- `执行 P/R/F1 验证` (Step 5 primary button)
- `反馈分歧到 Step3` (Step 5 feedback button)
- `简体中文` language picker option text

### 6.3 CSS pseudo-elements

Move diff labels out of CSS `content` or add language-scoped rules in `frontend/css/style.css`:

```css
html[lang="en"] .align-diff-old::before { content: 'Original'; }
html[lang="en"] .align-diff-new::before { content: 'Modified'; }
html[lang="en"] .align-diff-add::before { content: 'Added'; }
```

### 6.4 Luckysheet

Replace the current Chinese-localized vendored Luckysheet build with an English-localized build:

- Evaluate the official Luckysheet English bundle or a community `luckysheet-en` package.
- If no ready-made bundle exists, patch the vendored build’s UI strings to English and rebuild `frontend/vendor/`.
- Keep the integration API in `frontend/js/excel-luckysheet.js` unchanged as much as possible; only the vendored assets change.
- Update `frontend/package.json` / `scripts/setup-frontend-vendor.sh` so future deployments pull the English build.

### 6.5 Default language for foreign customers

- Keep the i18n default as `zh-CN` in code, but expose an environment-specific build config or a deployment flag (`FORCED_LANG=en`) that sets the initial language on first visit.
- Use `navigator.language` detection so an English browser gets English by default.

## 7. Backend Design

### 7.1 Translation helper

Create `backend/i18n.py`:

```python
MESSAGES = {
    'zh-CN': {
        'pipeline_name_required': '流水线名称不能为空',
        'file_not_found': '文件不存在',
        # additional messages keyed by usage site
    },
    'en': {
        'pipeline_name_required': 'Pipeline name is required',
        'file_not_found': 'File not found',
        # additional messages keyed by usage site
    }
}

def get_locale(step_data=None, request=None):
    """Resolve locale from request, pipeline, header, or env."""
    ...

def t(key, lang='zh-CN'):
    return MESSAGES.get(lang, MESSAGES['zh-CN']).get(key, key)
```

All API error/status strings in `backend/app_server.py` are replaced with `t('key', locale)`.

### 7.2 Locale injection

- Add a helper `get_locale_from_request()` used at the top of each endpoint.
- Store `locale` in pipeline `step_data` on create/update.
- Pass `locale` explicitly to service functions (`skill_ir`, `knowledge_delivery`, `validation_replay`, etc.) instead of relying on global state.

### 7.3 Skill registry metadata

- Extend `backend/skill_registry.py` entries with English fields:
  - `name_en`, `description_en`, `business_value_en`, `input_example_en`, `output_example_en`.
- `/api/skills` returns the correct language based on locale.

## 8. Prompts, Schema, and Generated Artifacts

### 8.1 English prompt variants

For each prompt template, create an English version:

- `backend/prompts/step2_generate_skill_md.txt` → `step2_generate_skill_md.en.txt`
- `backend/prompts/step3_align_with_expert.txt` → `step3_align_with_expert.en.txt`
- `backend/prompts/step4_build_deliverables.txt` → `step4_build_deliverables.en.txt`
- `backend/prompts/step2a_rules_extract.txt` → `step2a_rules_extract.en.txt`
- `backend/prompts/step2b_sql_generate.txt` → `step2b_sql_generate.en.txt`

The prompt loader chooses the `.en.txt` variant when `locale == 'en'`.

English prompts must:
- Use the English phase names (`Customer Filter`, `Data Match`, `Attribution`, `Decision`).
- Instruct the LLM to output headings, field names, and content in English.
- Preserve the same structural delimiters (`===QA_PAIRS===`, `===CHAIN_OF_THOUGHT===`, `===AGENT_SKILL===`) so downstream parsers work unchanged.

### 8.2 English scenario schema

Create `config/scenario-schema.en.yaml`:

- `display_name: Generic Knowledge Extraction Structure`
- `domain: Generic`
- Categories: `Decision Rule`, `Operation Flow`, `Anti-pattern`
- Field names: `stage`, `interview_direction`, `method`, `knowledge_type`, `reference`, `condition`, `logic`, `anti_pattern`, `experience_judgment`, `boundary`, `exception`, `source_doc`, `source_location`, `confidence`, `contributor`, `evidence_count`, `breakthrough_count`
- Confidence enum: `high`, `medium`, `low`
- Interview methods: `case_retrospection`, `contrast_probe`, `extreme_hypothesis`

The backend loads the correct schema file based on locale.

### 8.3 Bilingual key normalization

Update canonical-key modules to accept Chinese aliases and work internally in English:

- `backend/field_aliases.py`: add English canonical names to `FIELD_ALIASES`.
- `backend/skill_ir.py`: `VALID_STEP_PHASES = ("customer_filter", "data_match", "attribution", "decision")`; accept Chinese aliases on parse.
- `backend/shared.py`: confidence map `{"high": 3, "medium": 2, "low": 1}` plus reverse Chinese map.
- `backend/step5_agent_verify.py` and `backend/validation_replay.py`: normalizers accept both English and Chinese action labels.
- `backend/revision_processor.py`: `STATUS_MAP` uses English keys internally, emits Chinese labels only for Chinese locale.

### 8.4 Generated reports and deliverables

Make these modules locale-aware:

- `backend/agent_skill_builder.py`
- `backend/knowledge_delivery.py`
- `backend/quality_report.py`
- `backend/validation_replay.py`
- `backend/step1_markdown_builder.py`
- `backend/skill_generator.py`

Use translation keys or schema-driven labels; do not hardcode Chinese headings.

### 8.5 Excel generation

Excel headers, sheet titles, and dropdowns come from the active schema, so switching to the English schema automatically produces English workbooks. Provide English sample templates under `data/samples/en/`.

## 9. Data, Samples, and Tests

### 9.1 Sample data layout

```
data/samples/
  zh/   (existing samples, moved from current root)
  en/   (new English sample scenarios and templates)
```

- Update import/seed scripts to load the correct language folder based on pipeline locale.
- Keep Chinese golden data in `data/golden/` as legacy; create `data/golden/en/` for English scenarios.

### 9.2 Golden DB / KB

- `backend/golden_db.py`: support English column aliases and English seed data.
- `backend/knowledge_base.py`: search/analytics labels come from schema, not hardcoded Chinese.

### 9.3 Tests

- Add `tests/test_i18n_en.py` that runs a minimal end-to-end flow with `locale='en'`:
  - Create pipeline with `locale=en`.
  - Step2 generates English SKILL.md.
  - Step4 produces English QA/CoT/zip.
  - Step5 validation accepts English action labels.
- Make existing Chinese tests locale-agnostic by explicitly passing `zh-CN` or relying on the default.

## 10. Implementation Phases

| Phase | Focus | Estimated Effort | Deliverable |
|-------|-------|------------------|-------------|
| 1 | Frontend UI complete English coverage; default-language detection; CSS pseudo-elements | 1–2 days | English UI with no Chinese leakage in first-party code |
| 2 | Backend locale detection, API message translation, skill registry bilingual | 2–3 days | API returns English errors/status; skill metadata English |
| 3 | English prompt templates + English schema + bilingual field/enum normalization | 3–4 days | English SKILL.md / QA / CoT / Excel for `locale=en` |
| 4 | Locale-aware report/artifact renderers + English samples + tests | 2–3 days | English reports, sample data, golden DB, passing tests |
| 5 | Luckysheet English toolbar + docs (README_EN.md) | 1–2 days | Fully polished English demo |

Total: **1.5–2 weeks** for a production-grade, bilingual system.

## 11. Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Chinese strings used as logical keys break when translated | Introduce canonical English keys + Chinese alias mapping, keep Chinese accepted on import |
| LLM output structure changes when prompts are translated | Keep structural delimiters identical; validate with tests |
| Existing Chinese users see regressions | Default remains `zh-CN`; `en` is opt-in per pipeline/deployment |
| `DYNAMIC_PHRASES` regex causes awkward partial translations | Replace first-party strings with keyed translations; keep regex only for third-party content |
| English prompts produce lower quality for Chinese source docs | Document that English mode is optimized for English source docs; do not auto-translate source content |
| Tests break due to schema language changes | Run test matrix for both `zh-CN` and `en` in CI |

## 12. Success Criteria

- With `locale=en`, a user can complete all 5 steps without seeing Chinese in the UI, API messages, generated SKILL.md, QA pairs, CoT, Excel, validation report, or quality report.
- With `locale=zh-CN`, the existing experience is unchanged.
- `pytest tests/test_i18n_en.py` passes.
- All existing backend tests continue to pass.

## 13. Decisions

1. **Deployment default:** Keep `zh-CN` as the default locale. English is opt-in per pipeline or per deployment via `DEFAULT_LANG=en` / `FORCED_LANG=en`.
2. **Source document content:** Do **not** translate uploaded source documents. The English mode localizes structure, labels, and generated artifacts; the extracted knowledge content retains the original source language.
3. **Luckysheet:** Replace the vendored Chinese Luckysheet build with an English-localized build rather than using a custom toolbar overlay.

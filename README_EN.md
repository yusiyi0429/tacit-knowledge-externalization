# Tacit Knowledge Externalization · Skill-Centric 5-Step Pipeline

Transform domain experts' tacit experience (policy documents, case reviews, meeting minutes) into structured, reusable, and auditable knowledge assets — AI Skills.

---

## Core Pipeline

```
Scenario Anchoring → Knowledge Extraction → Knowledge Alignment → Smart Transformation → Validation Replay
      Step1              Step2                Step3                 Step4                Step5
                          │                    ↑                            │
                          │                    └──── Divergence feedback ◄───┘
                          ↓
                    External Knowledge Base (inherit / publish / case library)
```

The pipeline produces **Skill IR (structured JSON draft)** as the single source of truth; `SKILL.md` is rendered deterministically from the IR.
An Excel workbook is retained as a transitional editing surface and compatibility artifact.

| Step | What it does | Input | Output |
|------|--------------|-------|--------|
| **Step1 Scenario Anchoring** | Define the knowledge structure and generate an Excel skeleton | Scenario name, description, sub-scenarios, knowledge column definitions | `template_*.xlsx` |
| **Step2 Knowledge Extraction** | Documents / cases → **Skill draft v1** | Policy docs / case reviews / KB inheritance | `skill_draft_*_v1.json` + `preextract_*.xlsx` |
| **Step3 Knowledge Alignment** | Expert review & revision + suggestion-pool adjudication → aligned vN | Expert feedback / validation-loop suggestions / interview conversions | `skill_draft_*_vN.json` (aligned) + `final_*.xlsx` |
| **Step4 Smart Transformation** | Deterministically compile the aligned IR into deliverables and publish | Aligned Skill IR | Final `SKILL.md` / QA pairs / Chain-of-Thought / manifest |
| **Step5 Validation Replay** | Run the final SKILL against historical cases; divergences feed back to Step3 | Historical cases (uploaded / from KB) | Replay report / hit rate / `revision_suggestions_*.json` |

---

## 5 AI Skills

| Skill | Step | Capability |
|-------|:----:|------------|
| 🔍 **Knowledge Extraction** | Step2 | Documents → structured knowledge; supports 📄 document mode and 📋 case-review mode |
| 🔬 **Cross-Case Pattern Discovery** | Step2 | Cross-case analysis to uncover recurring tacit signals and systemic risk blind spots |
| 🎯 **Knowledge Gap Detection** | Step2 | Compare schema vs. actual fill rate to identify "should-know-but-don't-yet" content |
| 📝 **Knowledge Alignment** | Step3 | Expert revision + tacit-note follow-up cards (auto-capturing the experiential judgement behind edits) |
| 🔄 **Knowledge Freshness Audit** | Step4 | Audit knowledge timeliness, detect rules broken by new cases and confidence decay |

---

## Validation Loop & External Knowledge Base

- **Decision Replay** (`POST /api/step5/replay`): Evaluate historical cases one-by-one with the final SKILL (or IR render), comparing against expert conclusions to compute hit rate. The **judge model can be specified independently** (`judge_model`) to avoid same-model self-evaluation bias.
- **Divergence Feedback** (`POST /api/step5/feedback`): Automatically generate entry-level revision suggestions from divergences → push to the Step3 suggestion pool → expert adjudicates → IR v+1 → recompile & revalidate, forming a **Alignment ↔ Validation micro-loop**.
- **Golden Benchmark Verification** (`POST /api/step5/golden_verify`): Compare pipeline knowledge against human-annotated golden entries (P/R/F1).
- **External Knowledge Base** (`backend/knowledge_base.py`, SQLite):
  - Knowledge asset layer `kb_entries`: entry-level versioning and lifecycle (active / superseded / deprecated)
  - Case library `kb_cases`: historical cases + expert conclusions, ammunition for Step5 validation
  - Release registry `kb_skill_releases` + validation records `kb_validation_runs`
  - Integration points: Step2 "inherit from KB" participates in fusion/deduplication; Step4 one-click publish after quality gate; Step5 samples validation sets from the case library

---

## Quick Start

```bash
# 1. Install dependencies
cd backend
pip install -r ../requirements.txt

# 2. Start the backend
python app_server.py --host 127.0.0.1 --port 5000
```

Open your browser at `http://127.0.0.1:5000`.

```bash
# 3. Configure LLM (copy template and edit your API key)
cp config/llm-config.local.yaml.example config/llm-config.local.yaml
# Edit config/llm-config.local.yaml

# 4. Initialize frontend vendor (first run or after Luckysheet update)
cd ../frontend
npm install
npm run vendor
# Or: cd ../scripts && ./setup-frontend-vendor.sh

# 5. Run tests
cd ../backend
python -m pytest tests/ -v
```

---

## Test Data

`data/samples/` is organized by step and contains full-process sample data for technology-enterprise inclusive lending.

[→ Test Data Guide](data/samples/README.md)

---

## Architecture Overview

The system supports **two parallel pipeline paths**:

| Path | Use Case | Steps |
|------|----------|-------|
| **Markdown Flow** (default) | LLM directly extracts knowledge | Step2 produces `SKILL.md` → Step3 revises → Step4 generates three deliverables (QA / CoT / zip) → Step5 validates + finalizes |
| **Excel / IR Flow** (legacy) | Expert edits Excel directly | Step1 produces Excel → Step2 extracts entries → Step3 revises → Step4 deterministic transformation → Step5 validates |

```
┌─────────────────┐     HTTP/API     ┌─────────────────────────────────┐
│   Frontend      │ ◄─────────────► │   Backend (Flask)               │
│  (Vanilla JS)   │                 │  app_server.py (router bus)     │
│  Luckysheet     │                 │  skill_ir.py (IR engine)        │
│  index.html     │                 │  knowledge_base.py (KB)         │
│  app.js/state.js│                 │  validation_replay.py           │
│                 │                 │  knowledge_delivery.py          │
│                 │                 │  prompts/ (LLM prompt templates)│
│                 │                 │  skill_registry (built-in Skills)
└─────────────────┘                 └──────────────┬──────────────────┘
                                                   │
         ┌─────────────────────────────────────────┼──────────────────────────┐
         ▼                     ▼                   ▼                          ▼
    ┌──────────┐        ┌──────────┐         ┌──────────┐              ┌──────────┐
    │ data/kb  │        │ workspace│         │data/golden│             │ config/  │
    │ SQLite   │        │<pipeline>│         │golden DB  │             │ llm-config.yaml
    └──────────┘        │ step1-5/ │         └──────────┘             └──────────┘
                        └──────────┘
```

---

## Project Structure

```
├── backend/              # Flask API + business modules
│   ├── app_server.py     # Main service (routes + Skill executor)
│   ├── skill_ir.py       # Skill IR (single source of truth: draft/revise/render/version)
│   ├── knowledge_base.py # External KB (knowledge assets / case library / release registry, SQLite)
│   ├── validation_replay.py   # Step5 decision replay + divergence → revision suggestions
│   ├── llm_client.py     # LLM client adapter (OpenAI / CCB gateway + retries)
│   ├── pipeline_artifacts.py  # File naming, safety policy + step data key contracts
│   ├── step1_*.py        # Scenario anchoring modules
│   ├── step2_preextract.py    # Knowledge extraction Excel generation (transitional artifact)
│   ├── revision_processor.py  # Knowledge revision processor (Excel editing surface)
│   ├── knowledge_delivery.py  # Smart transformation (Skill/QA/CoT, records-driven)
│   ├── prompts/          # LLM prompt templates (Markdown flow)
│   └── scripts/          # Test scripts (including e2e_ir_pipeline_test.py)
├── frontend/             # Frontend (Vanilla JS + Luckysheet)
│   ├── js/
│   │   ├── state.js      # Pipeline state manager
│   │   ├── utils.js      # Common utilities
│   │   ├── app.js        # Main logic
│   │   └── excel-luckysheet.js  # Excel online editor
│   ├── vendor/           # Offline static assets (intranet deployment)
│   └── package.json      # Frontend dependencies (Luckysheet, jQuery)
├── config/               # LLM config + scenario schema
├── data/                 # Runtime data
│   ├── workspace/        # Pipeline runtime data (gitignored)
│   ├── kb/               # SQLite knowledge base
│   ├── golden/           # Golden database
│   ├── samples/          # Test data (organized by step)
│   └── deliveries/       # Final published Skill deliverables
├── docker/               # Docker build files
├── deploy/               # Deployment artifacts and compose files
├── scripts/              # Build / start / vendor setup scripts
└── docs/                 # Documentation
```

---

## LLM Configuration

Two `api_type` values are supported:

| api_type | Description |
|----------|-------------|
| `openai` (default) | OpenAI-compatible `/v1/chat/completions`, Bearer auth |
| `ccb_ainlplm` | CCB internal gateway; requires `tx_code` and `sec_node_no` |

Config file: `config/llm-config.yaml`; secrets go in `config/llm-config.local.yaml` (gitignored).

---

## Deployment

### Development

Run the Flask development server directly:

```bash
python app_server.py
```

### Docker (Intranet / ARM64)

```bash
cd deploy
docker load -i tacit-knowledge-externalization-*.tar
mkdir -p workspace data/kb data/golden logs
# Edit config/llm-config.yaml for intranet endpoints
docker compose up -d
```

Health check: `http://127.0.0.1:5000/api/health`

Build image from project root:

```bash
bash deploy/scripts/build-docker-arm64.sh
```

Or on Windows:

```powershell
.\scripts\build-docker-arm64.ps1
```

This produces `tacit-knowledge-externalization-arm64.tar`. See [docker/README.md](docker/README.md) for details.

### Data Volumes

| Path | Purpose | Mount mode |
|------|---------|------------|
| `data/workspace/` | Pipeline runtime data | Read-write volume |
| `data/kb/` | SQLite knowledge base | Read-write volume |
| `data/golden/` | Golden database | Read-write volume |
| `logs/` | Application logs | Read-write volume |
| `config/llm-config.yaml` | LLM configuration | Read-only volume |

---

## Internationalization (i18n)

Chinese (`zh`) is the default locale. English can be enabled in either of the following ways:

- Per pipeline: set `locale: "en"` in the pipeline configuration/scenario.
- Globally via environment variables: `DEFAULT_LANG=en` changes the default, or `FORCED_LANG=en` forces English for all pipelines regardless of per-pipeline settings.

All backend route messages, prompt templates, and deliverable generation respect the selected locale.

---

## License

See project repository for license details.

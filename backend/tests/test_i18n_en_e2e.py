"""End-to-end English pipeline test for the Markdown flow.

Patches the LLM client so no real LLM calls are made, then verifies that
Step2 and Step4 artifacts are persisted in English without Chinese phase names.
"""

import json
from unittest.mock import patch

import pytest


MOCK_STEP2_RESPONSE = """# SME Inclusive Loan Marketing

## Execution Instructions
This Skill executes in four stages: Customer Filter → Data Match → Attribution → Decision Recommendation.

## Knowledge Rules

### Stage 1: Customer Filter
- **Rule 1**: Registration and revenue filter
  - Business description: Target customers must be registered for at least 2 years and have annual revenue above 5 million.
  - Data source: corporate_customer table
  - Rule logic: register_years >= 2 AND annual_revenue >= 5000000
  - SQL reference:
    ```sql
    SELECT customer_id FROM corporate_customer WHERE register_years >= 2 AND annual_revenue >= 5000000
    ```
  - Output: list of eligible customers

### Stage 2: Data Match
- **Rule 1**: Credit and cash flow match
  - Business description: Match customer profile with credit bureau report and cash flow statement.
  - Data source: credit_bureau, cash_flow
  - Rule logic: credit_report exists AND cash_flow exists
  - SQL reference:
    ```sql
    SELECT c.customer_id FROM corporate_customer c JOIN credit_bureau cb ON c.customer_id = cb.customer_id JOIN cash_flow cf ON c.customer_id = cf.customer_id
    ```
  - Output: matched customer records

### Stage 3: Attribution
- **Rule 1**: Stable business classification
  - Business description: Classify customers as stable or volatile based on cash flow and rating.
  - Data source: rating, cash_flow
  - Rule logic: rating = 'A' AND cash_flow_stable = true
  - SQL reference:
    ```sql
    SELECT customer_id FROM rating r JOIN cash_flow cf ON r.customer_id = cf.customer_id WHERE r.rating = 'A' AND cf.stable = 1
    ```
  - Output: stable / volatile attribution

### Stage 4: Decision Recommendation
- **Rule 1**: Approve stable customers
  - Business description: Recommend inclusive loan product for stable customers.
  - Data source: attribution result
  - Rule logic: attribution = 'stable'
  - SQL reference:
    ```sql
    SELECT customer_id FROM attribution WHERE result = 'stable'
    ```
  - Output: approve recommendation
"""


MOCK_STEP4_RESPONSE = """===QA_PAIRS===
[
  {"q": "What are the customer filter conditions?", "a": "Register for at least 2 years and annual revenue above 5 million.", "rule_id": "Customer Filter Rule 1", "phase": "customer_filter"},
  {"q": "What data must be matched?", "a": "Credit bureau report and cash flow statement.", "rule_id": "Data Match Rule 1", "phase": "data_match"},
  {"q": "When is a customer classified as stable?", "a": "Rating A and stable cash flow.", "rule_id": "Attribution Rule 1", "phase": "attribution"},
  {"q": "What is recommended for stable customers?", "a": "Recommend the inclusive loan product.", "rule_id": "Decision Recommendation Rule 1", "phase": "decision"}
]

===CHAIN_OF_THOUGHT===
# Chain-of-Thought: SME Inclusive Loan Marketing

## Step 1: Customer Filter
Filter customers by registration years and annual revenue.

## Step 2: Data Match
Match credit bureau and cash flow data.

## Step 3: Attribution
Classify stable vs volatile customers.

## Step 4: Decision Recommendation
Recommend loan for stable customers.

===AGENT_SKILL===
{
  "ir_version": "2.0",
  "skill_meta": {"scenario_name": "SME Inclusive Loan Marketing", "domain": "Generic", "status": "aligned"},
  "anchors": {"scenario": "SME Inclusive Loan Marketing", "scenario_desc": "Marketing guide for SME inclusive loans"},
  "entries": [
    {"entry_id": "KN-001", "sub_scenario": "First-time customer credit grant", "step_phase": "customer_filter", "fields": {"knowledge_desc": "Registration and revenue filter", "condition": "register_years >= 2 AND annual_revenue >= 5000000", "logic": "Eligible customers", "data_logic": {"sql": "SELECT customer_id FROM corporate_customer WHERE register_years >= 2 AND annual_revenue >= 5000000", "confidence": "high"}}},
    {"entry_id": "KN-002", "sub_scenario": "First-time customer credit grant", "step_phase": "data_match", "fields": {"knowledge_desc": "Credit and cash flow match", "condition": "credit_report exists AND cash_flow exists", "logic": "Matched records", "data_logic": {"sql": "SELECT c.customer_id FROM corporate_customer c JOIN credit_bureau cb ON c.customer_id = cb.customer_id JOIN cash_flow cf ON c.customer_id = cf.customer_id", "confidence": "high"}}},
    {"entry_id": "KN-003", "sub_scenario": "First-time customer credit grant", "step_phase": "attribution", "fields": {"knowledge_desc": "Stable business classification", "condition": "rating = 'A' AND cash_flow_stable = true", "logic": "Stable / volatile", "data_logic": {"sql": "SELECT customer_id FROM rating r JOIN cash_flow cf ON r.customer_id = cf.customer_id WHERE r.rating = 'A' AND cf.stable = 1", "confidence": "high"}}},
    {"entry_id": "KN-004", "sub_scenario": "First-time customer credit grant", "step_phase": "decision", "fields": {"knowledge_desc": "Approve stable customers", "condition": "attribution = 'stable'", "logic": "Approve recommendation", "data_logic": {"sql": "SELECT customer_id FROM attribution WHERE result = 'stable'", "confidence": "high"}}}
  ]
}
"""


# Dummy model config used when patching shared.get_model_by_name.
_DUMMY_MODEL_CFG = {
    "name": "dummy-model",
    "api_type": "openai",
    "url": "http://localhost:9999/v1",
    "model": "dummy-model",
    "api_key": "dummy-key",
}


def _llm_result(content: str):
    """Build an OpenAI-shaped response dict consumed by app_server routes."""
    return {"choices": [{"message": {"content": content}}]}


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Flask test client backed by an isolated workspace."""
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path))
    # Import app_server after setting WORKSPACE_DIR so path resolution is clean.
    import app_server
    import shared

    monkeypatch.setattr(app_server, "WORKSPACE", tmp_path)
    monkeypatch.setattr(app_server, "PIPELINES_PATH", tmp_path / "pipelines.json")
    monkeypatch.setattr(app_server, "CUSTOM_MODELS_PATH", tmp_path / "custom_models.json")
    monkeypatch.setattr(app_server, "PRESET_OVERRIDES_PATH", tmp_path / "preset_overrides.json")
    monkeypatch.setattr(shared, "get_model_by_name", lambda _name: _DUMMY_MODEL_CFG)

    app_server.app.config["TESTING"] = True
    with app_server.app.test_client() as c:
        yield c


def test_full_english_pipeline_generates_english_artifacts(client):
    # Create pipeline with English locale.
    resp = client.post("/api/pipelines", json={
        "name": "EN pipeline",
        "scenario": "SME Loan Marketing",
        "locale": "en",
    })
    assert resp.status_code == 200
    pipeline = resp.get_json()["pipeline"]
    pid = pipeline["id"]
    assert pipeline["step_data"]["locale"] == "en"

    # Step 2: extract SKILL.md with mocked LLM.
    with patch("llm_client.call_llm_with_retry", return_value=_llm_result(MOCK_STEP2_RESPONSE)):
        resp = client.post(
            "/api/step2/extract_skill_md",
            data={
                "pipeline_id": pid,
                "model": "dummy-model",
                "source_text": "SME loan marketing guide.",
                "source_label": "guide",
            },
            query_string={"lang": "en"},
            content_type="multipart/form-data",
        )
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    skill_md_path = data["skill_md_file"]
    skill_md = client.get(f"/downloads/{skill_md_path}?pipeline_id={pid}").data.decode("utf-8")
    assert "Customer Filter" in skill_md
    assert "Data Match" in skill_md
    assert "Attribution" in skill_md
    assert "Decision Recommendation" in skill_md
    assert "客户筛选" not in skill_md
    assert "客户数据匹配" not in skill_md
    assert "原因归因" not in skill_md
    assert "决策建议" not in skill_md

    # Confirm the pipeline step_data records the English artifact.
    pipeline = client.get(f"/api/pipelines/{pid}").get_json()["pipeline"]
    assert pipeline["step_data"]["step2_skill_md_file"] == skill_md_path

    # Step 4: build deliverables with mocked LLM.
    with patch("llm_client.call_llm_with_retry", return_value=_llm_result(MOCK_STEP4_RESPONSE)):
        resp = client.post(
            "/api/step4/build_skill",
            data={"pipeline_id": pid, "model": "dummy-model"},
            query_string={"lang": "en"},
        )
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    qa_path = data["qa_file"]
    qa = json.loads(client.get(f"/downloads/{qa_path}?pipeline_id={pid}").data.decode("utf-8"))
    phases = {item.get("phase", "").lower() for item in qa}
    assert "customer_filter" in phases
    assert "data_match" in phases
    assert "attribution" in phases
    assert "decision" in phases
    assert "客户筛选" not in json.dumps(qa)
    assert "客户数据匹配" not in json.dumps(qa)
    assert "原因归因" not in json.dumps(qa)
    assert "决策建议" not in json.dumps(qa)

    # Confirm the pipeline step_data records the English QA artifact.
    pipeline = client.get(f"/api/pipelines/{pid}").get_json()["pipeline"]
    assert pipeline["step_data"]["step4_qa_file"] == qa_path

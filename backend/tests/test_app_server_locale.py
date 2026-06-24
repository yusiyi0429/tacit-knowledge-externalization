import pytest
from app_server import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path))
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_create_pipeline_stores_locale(client):
    resp = client.post("/api/pipelines", json={
        "name": "EN demo",
        "scenario": "Credit",
        "locale": "en",
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["pipeline"]["step_data"]["locale"] == "en"


def test_missing_name_returns_english_when_locale_en(client):
    resp = client.post("/api/pipelines", json={
        "name": "",
        "scenario": "Credit",
        "locale": "en",
    })
    assert resp.status_code == 400
    assert "Pipeline name is required" in resp.get_json()["message"]


def test_update_locale_changes_pipeline_locale(client):
    resp = client.post("/api/pipelines", json={
        "name": "Demo",
        "scenario": "Credit",
        "locale": "zh-CN",
    })
    pid = resp.get_json()["pipeline"]["id"]
    resp = client.put(f"/api/pipelines/{pid}", json={"locale": "en"})
    assert resp.status_code == 200
    resp = client.get(f"/api/pipelines/{pid}")
    assert resp.get_json()["pipeline"]["step_data"]["locale"] == "en"


def test_query_lang_overrides_body_locale(client):
    resp = client.post("/api/pipelines", json={
        "name": "",
        "scenario": "Credit",
        "locale": "zh-CN",
    }, query_string={"lang": "en"})
    assert resp.status_code == 400
    assert "Pipeline name is required" in resp.get_json()["message"]


def test_header_lang_falls_back_to_english(client):
    resp = client.post("/api/pipelines", json={
        "name": "",
        "scenario": "Credit",
    }, headers={"Accept-Language": "en-US"})
    assert resp.status_code == 400
    assert "Pipeline name is required" in resp.get_json()["message"]

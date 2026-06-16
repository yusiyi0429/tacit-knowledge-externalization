import pytest
from app_server import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_api_test_customers_crud(client, monkeypatch, tmp_path):
    db_path = tmp_path / "kb.db"
    monkeypatch.setenv("KB_DB_PATH", str(db_path))
    from knowledge_base import init_db
    init_db()

    r = client.post(
        "/api/kb/test_customers",
        json={"customers": [{"customer_id": "C001", "expected_action": "营销", "source": "t"}]},
    )
    assert r.status_code == 200
    assert r.get_json()["status"] == "ok"

    r = client.get("/api/kb/test_customers?source=t")
    data = r.get_json()
    assert data["status"] == "ok"
    assert len(data["customers"]) == 1
    assert data["total"] == 1

    r = client.delete("/api/kb/test_customers?source=t")
    assert r.get_json()["status"] == "ok"

    r = client.delete("/api/kb/test_customers")
    assert r.get_json()["status"] == "error"

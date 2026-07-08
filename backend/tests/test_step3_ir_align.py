import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure backend is on path for app_server import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_apply_field_revision():
    from skill_ir import apply_field_revision
    entry = {"fields": {"rule_ref": "old"}, "lifecycle": {"revisions": []}}
    apply_field_revision(entry, "rule_ref", "new", by="expert")
    assert entry["fields"]["rule_ref"] == "new"
    assert len(entry["lifecycle"]["revisions"]) == 1


def test_sql_manual_edit_flag():
    from skill_ir import set_sql_manually_edited
    entry = {"flags": {}}
    set_sql_manually_edited(entry, True)
    assert entry["flags"]["sql_manually_edited"] is True


def test_regenerate_sql_for_entry(tmp_path):
    from skill_ir import regenerate_sql_for_entry
    from unittest.mock import patch
    entry = {
        "sub_scenario": "S",
        "step_phase": "客户筛选",
        "fields": {
            "knowledge_desc": "x",
            "knowledge_ref": "",
            "rule_ref": "",
            "output": "",
            "data_logic": {"sql": ""},
        },
        "flags": {},
    }
    with patch("step2_ir_extract.generate_sql_for_entry") as mock_gen:
        mock_gen.return_value = {"sql": "SELECT 1", "tables": [], "fields": [], "confidence": "high"}
        result = regenerate_sql_for_entry(entry, "schema", "test")
        assert result["sql"] == "SELECT 1"
        assert entry["flags"]["sql_manually_edited"] is False
        assert len(entry["flags"]["sql_history"]) == 1


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    """Provide a Flask test client backed by an isolated workspace."""
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path))
    import app_server
    import skill_ir
    import shared

    monkeypatch.setattr(shared, "WORKSPACE", tmp_path)
    monkeypatch.setattr(shared, "PIPELINES_PATH", tmp_path / "pipelines.json")
    monkeypatch.setattr(shared, "CUSTOM_MODELS_PATH", tmp_path / "custom_models.json")
    monkeypatch.setattr(shared, "PRESET_OVERRIDES_PATH", tmp_path / "preset_overrides.json")
    tmp_path.mkdir(parents=True, exist_ok=True)
    return app_server.app.test_client()


def _make_pipeline_with_ir(app_server_module, workspace, pipeline_id="pipe-1", version=1):
    """Create a pipeline with a valid IR v2 saved in the isolated workspace."""
    from skill_ir import new_draft_v2, save_ir

    ir = new_draft_v2(
        {"scenario_name": "S", "sub_scenarios": []},
        [
            {
                "entry_id": "KN-001",
                "step_phase": "客户筛选",
                "fields": {
                    "knowledge_desc": "desc",
                    "knowledge_ref": "ref",
                    "rule_ref": "old_rule",
                    "output": "out",
                },
            }
        ],
        pipeline_id=pipeline_id,
    )
    ir["skill_meta"]["draft_version"] = version
    ir_name = save_ir(str(workspace), ir, pipeline_id=pipeline_id)

    pipeline = {
        "id": pipeline_id,
        "name": "test",
        "status": "running",
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
        "step_data": {"step2_draft_file": ir_name},
    }
    app_server_module.save_pipelines([pipeline])
    return pipeline_id, ir_name


class TestApiStep3AlignIr:
    def test_align_ir_missing_params(self, app_client):
        resp = app_client.post(
            "/api/step3/align_ir",
            data=json.dumps({"pipeline_id": "p", "entry_id": "e"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "error"

    def test_align_ir_pipeline_not_found(self, app_client):
        resp = app_client.post(
            "/api/step3/align_ir",
            data=json.dumps({"pipeline_id": "missing", "entry_id": "KN-001", "field": "rule_ref", "new_value": "x"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "error"
        assert "流水线不存在" in resp.get_json()["error"]

    def test_align_ir_edits_and_updates_both_pointers(self, app_client, tmp_path, monkeypatch):
        import app_server
        import skill_ir

        pipeline_id, ir_name = _make_pipeline_with_ir(app_server, tmp_path, version=1)
        resp = app_client.post(
            "/api/step3/align_ir",
            data=json.dumps(
                {"pipeline_id": pipeline_id, "entry_id": "KN-001", "field": "rule_ref", "new_value": "new_rule"}
            ),
            content_type="application/json",
        )
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["entry"]["fields"]["rule_ref"] == "new_rule"

        p = app_server._get_pipeline(pipeline_id)
        sd = p["step_data"]
        assert sd["step3_aligned_file"] == data["ir_path"]
        assert sd["step3_aligned_url"] == f"/downloads/{data['ir_path']}"
        assert sd["step2_draft_file"] == data["ir_path"]
        assert sd["step2_draft_url"] == f"/downloads/{data['ir_path']}"

        # Verify saved IR carries the edit.
        new_ir_path = app_server.locate_workspace_file(tmp_path, data["ir_path"], pipeline_id=pipeline_id)
        new_ir = skill_ir.load_ir(new_ir_path)
        assert new_ir["entries"][0]["fields"]["rule_ref"] == "new_rule"

    def test_align_ir_prefers_aligned_file(self, app_client, tmp_path, monkeypatch):
        import app_server
        import skill_ir

        pipeline_id, draft_name = _make_pipeline_with_ir(app_server, tmp_path, version=1)
        # Create a second IR that will be marked as the aligned version.
        draft_path = app_server.locate_workspace_file(tmp_path, draft_name, pipeline_id=pipeline_id)
        aligned_ir = skill_ir.load_ir(draft_path)
        aligned_ir["skill_meta"]["draft_version"] = 2
        aligned_ir["entries"][0]["fields"]["rule_ref"] = "aligned_rule"
        aligned_name = skill_ir.save_ir(str(tmp_path), aligned_ir, pipeline_id=pipeline_id)

        p = app_server._get_pipeline(pipeline_id)
        p["step_data"]["step3_aligned_file"] = aligned_name
        app_server.save_pipelines([p])

        resp = app_client.post(
            "/api/step3/align_ir",
            data=json.dumps(
                {"pipeline_id": pipeline_id, "entry_id": "KN-001", "field": "rule_ref", "new_value": "edited"}
            ),
            content_type="application/json",
        )
        data = resp.get_json()
        assert data["status"] == "ok"
        # Edit should start from aligned_rule, not old_rule.
        new_ir_path = app_server.locate_workspace_file(tmp_path, data["ir_path"], pipeline_id=pipeline_id)
        new_ir = skill_ir.load_ir(new_ir_path)
        revisions = new_ir["entries"][0]["lifecycle"]["revisions"]
        assert any(r["old_value"] == "aligned_rule" for r in revisions)

    def test_align_ir_handles_save_validation_error(self, app_client, tmp_path, monkeypatch):
        import app_server
        import skill_ir

        pipeline_id, ir_name = _make_pipeline_with_ir(app_server, tmp_path, version=1)

        def _broken_validate(ir):
            return ["forced validation error"]

        monkeypatch.setattr(skill_ir, "validate_ir_v2", _broken_validate)

        resp = app_client.post(
            "/api/step3/align_ir",
            data=json.dumps(
                {"pipeline_id": pipeline_id, "entry_id": "KN-001", "field": "rule_ref", "new_value": "x"}
            ),
            content_type="application/json",
        )
        data = resp.get_json()
        assert data["status"] == "error"
        assert "保存 IR 修订失败" in data["error"]

    def test_align_ir_updates_aligned_version(self, app_client, tmp_path, monkeypatch):
        import app_server

        pipeline_id, ir_name = _make_pipeline_with_ir(app_server, tmp_path, version=4)
        resp = app_client.post(
            "/api/step3/align_ir",
            data=json.dumps(
                {"pipeline_id": pipeline_id, "entry_id": "KN-001", "field": "rule_ref", "new_value": "new_rule"}
            ),
            content_type="application/json",
        )
        data = resp.get_json()
        assert data["status"] == "ok"

        p = app_server._get_pipeline(pipeline_id)
        assert p["step_data"]["step3_aligned_version"] == 4


class TestApiStep3ConfirmAsIs:
    def test_confirm_as_is_ir_v2_bumps_version_and_urls(self, app_client, tmp_path):
        import app_server
        import skill_ir

        pipeline_id, ir_name = _make_pipeline_with_ir(app_server, tmp_path, version=2)
        resp = app_client.post(
            "/api/step3/confirm_as_is",
            data=json.dumps({"pipeline_id": pipeline_id}),
            content_type="application/json",
        )
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["aligned_file"] == data["final_file"]
        assert data["aligned_url"] == f"/downloads/{data['aligned_file']}"
        assert data["final_url"] == f"/downloads/{data['final_file']}"
        assert "已确认 IR v2" in data["message"]

        p = app_server._get_pipeline(pipeline_id)
        sd = p["step_data"]
        assert sd["step3_aligned_file"] == data["aligned_file"]
        assert sd["step3_aligned_url"] == data["aligned_url"]
        assert sd["step3_final_file"] == data["final_file"]
        assert sd["step3_final_download_url"] == data["final_url"]
        assert sd["step3_aligned_version"] == 3

        aligned_ir_path = app_server.locate_workspace_file(tmp_path, data["aligned_file"], pipeline_id=pipeline_id)
        aligned_ir = skill_ir.load_ir(aligned_ir_path)
        assert aligned_ir["skill_meta"]["draft_version"] == 3
        assert aligned_ir["skill_meta"]["parent_version"] == 2
        assert aligned_ir["skill_meta"]["status"] == "aligned"

    def test_confirm_as_is_prefers_aligned_file(self, app_client, tmp_path):
        import app_server
        import skill_ir

        pipeline_id, draft_name = _make_pipeline_with_ir(app_server, tmp_path, version=1)
        draft_path = app_server.locate_workspace_file(tmp_path, draft_name, pipeline_id=pipeline_id)
        aligned_ir = skill_ir.load_ir(draft_path)
        aligned_ir["skill_meta"]["draft_version"] = 5
        aligned_ir["entries"][0]["fields"]["rule_ref"] = "aligned_rule"
        aligned_name = skill_ir.save_ir(str(tmp_path), aligned_ir, pipeline_id=pipeline_id)

        p = app_server._get_pipeline(pipeline_id)
        p["step_data"]["step3_aligned_file"] = aligned_name
        p["step_data"]["step2_draft_file"] = draft_name
        app_server.save_pipelines([p])

        resp = app_client.post(
            "/api/step3/confirm_as_is",
            data=json.dumps({"pipeline_id": pipeline_id}),
            content_type="application/json",
        )
        data = resp.get_json()
        assert data["status"] == "ok"

        p = app_server._get_pipeline(pipeline_id)
        sd = p["step_data"]
        assert sd["step3_aligned_version"] == 6
        assert sd["step3_aligned_file"] == data["aligned_file"]

        aligned_ir_path = app_server.locate_workspace_file(
            tmp_path, sd["step3_aligned_file"], pipeline_id=pipeline_id
        )
        aligned_ir = skill_ir.load_ir(aligned_ir_path)
        assert aligned_ir["skill_meta"]["draft_version"] == 6
        assert aligned_ir["skill_meta"]["parent_version"] == 5
        assert aligned_ir["entries"][0]["fields"]["rule_ref"] == "aligned_rule"

import json
import zipfile
from pathlib import Path

from agent_skill_builder import build_agent_skill_bundle


def test_build_agent_skill_bundle(tmp_path):
    ir = {
        "ir_version": "2.0",
        "skill_meta": {"scenario_name": "测试场景", "domain": "测试", "draft_version": 3, "status": "aligned"},
        "anchors": {"scenario": "测试场景", "scenario_desc": "", "sub_scenarios": []},
        "entries": [
            {
                "entry_id": "KN-001",
                "sub_scenario": "子场景",
                "step_phase": "客户筛选",
                "fields": {
                    "knowledge_desc": "筛选",
                    "knowledge_ref": "",
                    "rule_ref": "",
                    "output": "",
                    "data_logic": {"sql": "SELECT 1"},
                },
            }
        ],
    }
    result = build_agent_skill_bundle(ir, str(tmp_path))

    assert Path(result["skill_path"]).exists()
    assert Path(result["manifest_path"]).exists()
    assert Path(result["zip_path"]).exists()
    assert Path(result["cot_path"]).exists()
    assert Path(result["qa_json_path"]).exists()

    skill_dir = Path(result["skill_dir"])
    assert (skill_dir / "SKILL.md").exists()
    assert (skill_dir / "manifest.json").exists()
    assert (skill_dir / "scripts" / "execute.py").exists()
    assert (skill_dir / "references" / "ir_snapshot.json").exists()

    manifest = json.loads((skill_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["entry"] == "scripts/execute.py"

    with zipfile.ZipFile(result["zip_path"], "r") as zf:
        names = zf.namelist()
        assert "SKILL.md" in names
        assert "manifest.json" in names
        assert "scripts/execute.py" in names
        assert "references/ir_snapshot.json" in names

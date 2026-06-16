#!/usr/bin/env python3
"""Skill IR 模块单元测试（无 LLM、无 HTTP）。"""

import json
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from skill_ir import (  # noqa: E402
    STATUS_ALIGNED,
    STATUS_DRAFT,
    apply_revisions,
    diff_ir,
    ir_to_records,
    ir_version_info,
    is_skill_draft_filename,
    load_ir,
    mark_status,
    new_draft,
    normalize_suggestion,
    render_skill_md,
    save_ir,
    validate_ir,
)


def ok(msg):
    print(f"[OK] {msg}")


SCENARIO_META = {
    "scenario_name": "对公信贷尽调",
    "scenario_content": "对公客户授信前的尽职调查场景",
    "domain": "银行信贷",
    "sub_scenarios": [
        {"name": "贷前尽调", "content": "授信申请受理后的现场尽调"},
        {"name": "贷后检查", "content": "放款后的定期检查"},
    ],
}

RECORDS = [
    {
        "知识分类": "判断规则",
        "子场景": "贷前尽调",
        "知识描述": "当客户负债率超过70%时需提高审查等级",
        "适用条件": "对公授信申请",
        "判断逻辑": "负债率=总负债/总资产，超过70%触发",
        "反模式/踩坑提示": "不能只看报表数字，需核对银行流水",
        "来源文档": "授信管理办法",
        "置信度": "高",
        "贡献专家": "张三",
    },
    {
        "知识分类": "反模式",
        "子场景": "贷后检查",
        "知识描述": "贷后检查不能只走形式拍照留痕",
        "适用条件": "所有已放款客户",
        "置信度": "中",
        "_duplicate": True,
        "source_label": "案例复盘A",
    },
]


@pytest.fixture
def ir():
    return new_draft(SCENARIO_META, RECORDS, pipeline_id="pipe1234abcd", origin="doc_extract")


@pytest.fixture
def new_ir(ir):
    revisions = [
        {"entry_id": "KN-001", "field": "适用条件", "action": "modify",
         "new_value": "对公授信申请（含展期）", "note": "专家补充展期场景"},
        {"entry_id": "KN-001", "field": "经验判断", "action": "supplement",
         "new_value": "科技型轻资产企业可放宽到80%", "by": "expert"},
        {"entry_id": "KN-002", "field": "", "action": "delete_entry", "note": "重复条目"},
        {"action": "add", "category": "操作流程", "sub_scenario": "贷前尽调",
         "fields": {"知识描述": "现场尽调必须核对水电费单据", "置信度": "高"}},
        {"entry_id": "KN-999", "field": "x", "action": "modify", "new_value": "应被跳过"},
        {"entry_id": "KN-001", "field": "x", "action": "unknown_action"},
    ]
    new_ir, _ = apply_revisions(ir, revisions, by="expert")
    return new_ir


def test_new_draft_and_validate():
    ir = new_draft(SCENARIO_META, RECORDS, pipeline_id="pipe1234abcd", origin="doc_extract")
    assert validate_ir(ir) == [], validate_ir(ir)
    assert ir["skill_meta"]["draft_version"] == 1
    assert ir["skill_meta"]["status"] == STATUS_DRAFT
    assert len(ir["entries"]) == 2
    assert ir["entries"][0]["entry_id"] == "KN-001"
    assert ir["entries"][1]["entry_id"] == "KN-002"
    assert ir["entries"][1]["flags"]["duplicate_of"]
    assert ir["entries"][1]["lifecycle"]["source_label"] == "案例复盘A"
    assert ir["anchors"]["scenario"] == "对公信贷尽调"
    assert len(ir["anchors"]["sub_scenarios"]) == 2
    ok("new_draft + validate_ir")
    return ir


def test_records_roundtrip(ir):
    records = ir_to_records(ir)
    assert len(records) == 2
    assert records[0]["知识编号"] == "KN-001"
    assert records[0]["知识分类"] == "判断规则"
    assert records[0]["子场景"] == "贷前尽调"
    assert records[0]["子场景说明"] == "授信申请受理后的现场尽调"
    assert records[0]["判断逻辑"].startswith("负债率")
    vinfo = ir_version_info(ir)
    assert vinfo["scenario_anchor"]["场景名称"] == "对公信贷尽调"
    assert vinfo["模板版本"] == "v1"
    ok("ir_to_records / ir_version_info")


def test_render(ir):
    md = render_skill_md(ir)
    assert md.startswith("---")
    assert "对公信贷尽调" in md
    assert "负债率超过70%" in md
    assert "子场景：贷前尽调" in md
    assert "反模式与踩坑总结" in md
    # 渲染幂等
    assert render_skill_md(ir) == md
    ok("render_skill_md（幂等）")


def test_apply_revisions(ir):
    revisions = [
        {"entry_id": "KN-001", "field": "适用条件", "action": "modify",
         "new_value": "对公授信申请（含展期）", "note": "专家补充展期场景"},
        {"entry_id": "KN-001", "field": "经验判断", "action": "supplement",
         "new_value": "科技型轻资产企业可放宽到80%", "by": "expert"},
        {"entry_id": "KN-002", "field": "", "action": "delete_entry", "note": "重复条目"},
        {"action": "add", "category": "操作流程", "sub_scenario": "贷前尽调",
         "fields": {"知识描述": "现场尽调必须核对水电费单据", "置信度": "高"}},
        {"entry_id": "KN-999", "field": "x", "action": "modify", "new_value": "应被跳过"},
        {"entry_id": "KN-001", "field": "x", "action": "unknown_action"},
    ]
    new_ir, applied = apply_revisions(ir, revisions, by="expert")
    assert applied == 4, applied
    assert new_ir["skill_meta"]["draft_version"] == 2
    assert new_ir["skill_meta"]["parent_version"] == 1
    assert new_ir["skill_meta"]["status"] == STATUS_ALIGNED
    assert validate_ir(new_ir) == []
    ids = [e["entry_id"] for e in new_ir["entries"]]
    assert "KN-002" not in ids
    assert "KN-003" in ids
    e1 = next(e for e in new_ir["entries"] if e["entry_id"] == "KN-001")
    assert e1["fields"]["适用条件"] == "对公授信申请（含展期）"
    assert "80%" in e1["fields"]["经验判断"]
    assert len(e1["lifecycle"]["revisions"]) == 2
    # 原 IR 不被修改
    assert ir["skill_meta"]["draft_version"] == 1
    assert len(ir["entries"]) == 2
    ok("apply_revisions（modify/supplement/delete_entry/add + 非法跳过 + 不可变）")
    return new_ir


def test_diff(ir, new_ir):
    changes = diff_ir(ir, new_ir)
    kinds = {c["entry_id"]: c["change"] for c in changes}
    assert kinds.get("KN-002") == "removed"
    assert kinds.get("KN-003") == "added"
    assert kinds.get("KN-001") == "changed"
    changed = next(c for c in changes if c["entry_id"] == "KN-001")
    assert "适用条件" in changed["fields"]
    ok("diff_ir")


def test_persist(new_ir):
    with tempfile.TemporaryDirectory() as td:
        name = save_ir(td, new_ir, pipeline_id="pipe1234abcd")
        assert is_skill_draft_filename(name)
        assert "_v2_" in name
        loaded = load_ir(Path(td) / name)
        assert loaded["skill_meta"]["draft_version"] == 2
        assert len(loaded["entries"]) == 2
        # 非法 IR 拒绝保存
        bad = json.loads(json.dumps(new_ir))
        bad["skill_meta"]["draft_version"] = 0
        try:
            save_ir(td, bad)
            raise AssertionError("应拒绝非法 IR")
        except ValueError:
            pass
    assert not is_skill_draft_filename("final_x.xlsx")
    assert not is_skill_draft_filename("skill_draft_x.xlsx")  # 必须是 .json
    assert is_skill_draft_filename("/tmp/evil/../skill_draft_a.json")  # basename 化后判断
    ok("save_ir / load_ir / 文件名约束")


def test_normalize_and_status(new_ir):
    assert normalize_suggestion({"entry_id": "KN-001", "field": "a", "action": "修改", "new_value": "x"})["action"] == "modify"
    assert normalize_suggestion({"entry_id": "", "field": "a", "action": "modify"}) is None
    assert normalize_suggestion({"action": "add", "new_value": "x"}) is not None
    published = mark_status(new_ir, "published")
    assert published["skill_meta"]["status"] == "published"
    assert published["skill_meta"]["draft_version"] == new_ir["skill_meta"]["draft_version"]
    ok("normalize_suggestion / mark_status")


def test_delivery_and_quality(new_ir):
    """records 化的 delivery 与 quality 入口可直接消费 IR。"""
    from knowledge_delivery import records_to_delivery_bundle
    from quality_report import quality_report_from_records

    records = ir_to_records(new_ir)
    with tempfile.TemporaryDirectory() as td:
        result = records_to_delivery_bundle(
            records, ir_version_info(new_ir), "", td, formats="skill,cot,qa",
        )
        assert result["status"] == "ok", result
        assert result["knowledge_count"] == 2
        assert set(result["formats"]) == {"cot", "qa", "skill"}
        assert Path(result["skill_path"]).is_file()
    q = quality_report_from_records(records, {})
    assert q["status"] == "ok"
    assert 0 < q["total_score"] <= 100
    assert set(q["scores"].keys()) == {"完整性", "准确性", "可操作性", "反模式覆盖", "来源可溯"}
    ok("records_to_delivery_bundle / quality_report_from_records")


def main():
    ir = test_new_draft_and_validate()
    test_records_roundtrip(ir)
    test_render(ir)
    new_ir = test_apply_revisions(ir)
    test_diff(ir, new_ir)
    test_persist(new_ir)
    test_normalize_and_status(new_ir)
    test_delivery_and_quality(new_ir)
    print("All skill_ir tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""外部知识库模块单元测试（独立临时 DB，无 LLM、无 HTTP）。"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_tmpdir = tempfile.mkdtemp()
os.environ["KB_DB_PATH"] = str(Path(_tmpdir) / "kb_test.db")

import knowledge_base as kb  # noqa: E402

kb.DB_PATH = Path(os.environ["KB_DB_PATH"])

from skill_ir import new_draft  # noqa: E402


def ok(msg):
    print(f"[OK] {msg}")


META = {"scenario_name": "对公信贷尽调", "scenario_content": "x", "domain": "银行信贷"}
RECORDS_V1 = [
    {"知识分类": "判断规则", "子场景": "贷前尽调",
     "知识描述": "当客户负债率超过70%时需提高审查等级", "适用条件": "对公授信申请",
     "判断逻辑": "负债率超过70%触发", "置信度": "高", "贡献专家": "张三"},
    {"知识分类": "反模式", "子场景": "贷后检查",
     "知识描述": "贷后检查不能只走形式拍照留痕", "置信度": "中"},
]


def test_publish_and_search():
    ir = new_draft(META, RECORDS_V1, pipeline_id="pipeA")
    result = kb.publish_entries(ir, pipeline_id="pipeA", by="tester")
    assert result["created"] == 2, result
    assert result["superseded"] == 0
    assert result["release_version"] == 1
    assert len(result["entry_uids"]) == 2

    entries = kb.search_entries(domain="银行信贷", scenario="对公信贷尽调")
    assert len(entries) == 2
    entries_q = kb.search_entries(domain="银行信贷", scenario="对公信贷尽调", query="负债率审查")
    assert "负债率" in entries_q[0]["fields"]["知识描述"]
    ok("publish_entries / search_entries")
    return result


def test_supersede(first):
    # 修订后的同义条目应 supersede 旧版本
    records_v2 = [
        {"知识分类": "判断规则", "子场景": "贷前尽调",
         "知识描述": "当客户负债率超过70%时需提高审查等级（科技型轻资产企业放宽至80%）",
         "适用条件": "对公授信申请（含展期）", "判断逻辑": "负债率超过70%触发", "置信度": "高"},
    ]
    ir2 = new_draft(META, records_v2, pipeline_id="pipeA")
    result = kb.publish_entries(ir2, pipeline_id="pipeA", by="tester")
    assert result["superseded"] == 1, result
    assert result["release_version"] == 2

    active = kb.search_entries(domain="银行信贷", scenario="对公信贷尽调")
    descs = [e["fields"]["知识描述"] for e in active]
    assert any("80%" in d for d in descs)
    # 旧版本被标记 superseded
    new_uid = result["entry_uids"][0]
    timeline = kb.get_entry_timeline(new_uid)
    assert timeline and timeline[0]["change_type"] == "supersede"
    ok("supersede 版本演化 + timeline")
    return new_uid


def test_import_records(first):
    records = kb.import_entries_as_records(first["entry_uids"][:1])
    assert len(records) == 1
    assert records[0]["_origin"] == "kb_import"
    assert records[0]["kb_entry_id"] == first["entry_uids"][0]
    assert records[0]["知识描述"]
    ok("import_entries_as_records（继承源格式）")


def test_deprecate(uid):
    assert kb.deprecate_entry(uid, note="政策失效", by="tester")
    assert not kb.deprecate_entry(uid)  # 二次失效返回 False
    active = kb.search_entries(domain="银行信贷", scenario="对公信贷尽调", query="负债率")
    assert all(e["entry_uid"] != uid for e in active)
    ok("deprecate_entry")


def test_cases():
    uid1 = kb.add_case("芯片设计企业成立1年申请授信500万", "通过",
                       domain="银行信贷", scenario="对公信贷尽调", difficulty="hard")
    kb.add_case("贸易企业无抵押物申请授信", "拒绝",
                domain="银行信贷", scenario="对公信贷尽调", difficulty="edge",
                facts={"行业": "贸易"})
    kb.add_case("常规制造企业续贷", "通过", domain="银行信贷", scenario="对公信贷尽调")
    cases = kb.list_cases(domain="银行信贷", scenario="对公信贷尽调", limit=10)
    assert len(cases) == 3
    # edge/hard 优先
    assert cases[0]["difficulty"] == "edge"
    assert cases[1]["difficulty"] == "hard"
    assert cases[1]["case_uid"] == uid1
    hard_only = kb.list_cases(difficulty="hard")
    assert len(hard_only) == 1
    try:
        kb.add_case("", "")
        raise AssertionError("空案例应被拒绝")
    except ValueError:
        pass
    ok("add_case / list_cases（难度优先排序）")


def test_validation_runs_and_releases():
    kb.record_validation_run(
        pipeline_id="pipeA", total_cases=5, hits=4, hit_rate=0.8,
        mismatches=[{"case_id": "C1"}], judge_model="judge-x",
    )
    releases = kb.list_releases()
    assert len(releases) == 2
    assert releases[0]["version"] == 2
    ok("record_validation_run / list_releases")


def main():
    kb.init_db()
    first = test_publish_and_search()
    new_uid = test_supersede(first)
    test_import_records(first)
    test_deprecate(new_uid)
    test_cases()
    test_validation_runs_and_releases()
    print("All knowledge_base tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

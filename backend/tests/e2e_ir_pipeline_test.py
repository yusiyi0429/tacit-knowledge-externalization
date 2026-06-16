#!/usr/bin/env python3
"""Skill 中心化流水线端到端测试（无 LLM）。

覆盖：Step1 锚定 → Step2 草稿（程序注入）→ Step3 直通对齐（aligned IR）
→ Step4 IR 编译 + 质量 → Step5 回流建议 → Step3 建议池采纳（IR v+1）
→ KB 发布/检索/案例库 → 回滚清理。

用法：python3 backend/tests/e2e_ir_pipeline_test.py
（自动拉起临时服务器，独立 WORKSPACE 与 KB DB）
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PORT = int(os.environ.get("E2E_PORT", "5057"))
BASE = f"http://127.0.0.1:{PORT}"

_failures = []


def ok(msg):
    print(f"[OK] {msg}")


def fail(msg):
    print(f"[FAIL] {msg}")
    _failures.append(msg)


def main():
    tmp = tempfile.mkdtemp(prefix="e2e_ir_")
    workspace = Path(tmp) / "workspace"
    workspace.mkdir(parents=True)
    env = dict(os.environ)
    env["WORKSPACE_DIR"] = str(workspace)
    env["KB_DB_PATH"] = str(Path(tmp) / "kb.db")

    server = subprocess.Popen(
        [sys.executable, str(ROOT / "app_server.py"), "--host", "127.0.0.1", "--port", str(PORT)],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(40):
            try:
                if requests.get(f"{BASE}/api/health", timeout=2).status_code == 200:
                    break
            except requests.RequestException:
                time.sleep(0.5)
        else:
            fail("server not up")
            return 1
        ok("server up")
        return run_flow(workspace, env)
    finally:
        server.terminate()
        server.wait(timeout=10)


def run_flow(workspace: Path, env: dict) -> int:
    # 1. 创建流水线
    r = requests.post(f"{BASE}/api/pipelines", json={
        "name": f"E2E-{uuid.uuid4().hex[:6]}", "scenario": "对公信贷尽调", "domain": "银行信贷",
    }, timeout=30).json()
    assert r["status"] == "ok", r
    pid = r["pipeline"]["id"]
    assert r["pipeline"]["step_status"].get("5") == "pending", "新流水线应含第 5 步"
    ok(f"pipeline created {pid}（含 step5 状态）")

    # 2. Step1 生成 + 保存表单
    r = requests.post(f"{BASE}/api/step1/generate", data={
        "pipeline_id": pid,
        "scenario_name": "对公信贷尽调",
        "scenario_content": "对公客户授信前的尽职调查",
        "sub_scenarios": json.dumps([{"name": "贷前尽调", "content": "授信申请受理后的现场尽调"}]),
    }, timeout=60).json()
    assert r["status"] == "ok", r
    requests.put(f"{BASE}/api/pipelines/{pid}", json={"step_data": {"step1_form_data": {
        "scenario_name": "对公信贷尽调",
        "scenario_content": "对公客户授信前的尽职调查",
        "sub_scenarios": [{"name": "贷前尽调", "content": "授信申请受理后的现场尽调"}],
    }}}, timeout=30)
    ok("step1 generated")

    # 3. 程序注入 Step2 产物（preextract Excel + Skill 草稿 v1，模拟 LLM 萃取结果）
    items = [
        {"知识分类": "判断规则", "子场景": "贷前尽调",
         "知识描述": "当客户负债率超过70%时需提高审查等级",
         "适用条件": "对公授信申请", "判断逻辑": "负债率=总负债/总资产，超过70%触发",
         "反模式/踩坑提示": "不能只看报表数字", "置信度": "高", "贡献专家": "张三",
         "来源文档": "授信管理办法"},
        {"知识分类": "反模式", "子场景": "贷前尽调",
         "知识描述": "贷前尽调不能只走形式拍照留痕", "适用条件": "所有尽调",
         "置信度": "中", "来源文档": "案例复盘"},
    ]
    from step2_preextract import write_preextract_excel
    pre_name = f"preextract_{uuid.uuid4().hex[:8]}.xlsx"
    write_preextract_excel(step1_path=None, output_path=workspace / pre_name, items=items, pipeline_id=pid)

    from skill_ir import new_draft, save_ir
    ir = new_draft(
        {"scenario_name": "对公信贷尽调", "scenario_content": "对公客户授信前的尽职调查",
         "sub_scenarios": [{"name": "贷前尽调", "content": "授信申请受理后的现场尽调"}],
         "domain": "银行信贷"},
        items, pipeline_id=pid,
    )
    draft_name = save_ir(workspace, ir, pipeline_id=pid)

    r = requests.put(f"{BASE}/api/pipelines/{pid}", json={"step_data": {
        "step2_output_file": pre_name, "step2_download_url": f"/downloads/{pre_name}",
        "step2_draft_file": draft_name, "step2_draft_url": f"/downloads/{draft_name}",
        "step2_draft_version": 1, "step2_extracted_count": len(items),
    }}, timeout=30).json()
    assert r["status"] == "ok", r
    ok("step2 artifacts injected（preextract + skill_draft v1）")

    # 非法草稿文件名应被拒绝
    r = requests.put(f"{BASE}/api/pipelines/{pid}", json={"step_data": {
        "step2_draft_file": "evil_draft.json"}}, timeout=30).json()
    assert r["status"] == "error", "非法 step2_draft_file 应被拒绝"
    ok("契约校验拒绝非法 skill_draft 文件名")

    # 4. Step3 直通确认 → final + aligned IR v2
    r = requests.post(f"{BASE}/api/step3/confirm_as_is", json={"pipeline_id": pid}, timeout=60).json()
    assert r["status"] == "ok", r
    sd = requests.get(f"{BASE}/api/pipelines/{pid}", timeout=30).json()["pipeline"]["step_data"]
    assert sd.get("step3_final_file", "").startswith("final_"), sd.get("step3_final_file")
    assert sd.get("step3_aligned_file", "").startswith("skill_draft_"), sd.get("step3_aligned_file")
    assert sd.get("step3_aligned_version") == 2, sd.get("step3_aligned_version")
    ok(f"step3 confirm_as_is → aligned IR v2（{sd['step3_aligned_file']}）")

    # 5. Step4 IR 编译（确定性）
    r = requests.post(f"{BASE}/api/step4/compile", data={
        "pipeline_id": pid, "formats": "skill,cot,qa"}, timeout=120).json()
    assert r["status"] == "ok", r
    assert r.get("input_kind") == "ir", f"应走 IR 路径: {r.get('input_kind')}"
    assert r.get("ir_version") == 2
    assert r.get("knowledge_count") == 2
    assert r.get("download_url"), "缺少 SKILL 下载"
    assert "quality_score" in r, "缺少质量分"
    ok(f"step4 compile (IR v2) → SKILL/COT/QA，质量分 {r.get('quality_score')}")

    skill_md = requests.get(f"{BASE}{r['download_url']}", timeout=30).text
    assert "负债率超过70%" in skill_md and "KN-001" not in skill_md[:50]
    ok("SKILL.md 终版内容校验")

    # 6. Step4 质量（IR 进程内评分）
    r = requests.post(f"{BASE}/api/step4/quality", data={"pipeline_id": pid}, timeout=60).json()
    assert r["status"] == "ok" and r.get("input_kind") == "ir", r
    ok(f"step4 quality (IR) → {r.get('total_score')} / {r.get('grade')}")

    # 7. Step5 回流建议（模拟回放分歧产物，不调 LLM）
    suggestions = [{
        "entry_id": "KN-001", "field": "例外情形", "action": "supplement",
        "new_value": "科技型轻资产企业负债率可放宽到80%（案例 CASE-001 验证分歧）",
        "note": "验证回放分歧", "by": "validation",
    }]
    r = requests.post(f"{BASE}/api/step5/feedback", json={
        "pipeline_id": pid, "suggestions": suggestions}, timeout=30).json()
    assert r["status"] == "ok" and r["pushed"] == 1, r
    ok("step5 feedback → 建议入池")

    # 8. Step3 建议池 → 采纳 → IR v3
    r = requests.get(f"{BASE}/api/step3/suggestions", params={"pipeline_id": pid}, timeout=30).json()
    assert r["status"] == "ok" and r["total"] == 1, r
    sug_id = r["suggestions"][0]["id"]
    assert r["suggestions"][0]["source"] == "validation"
    r = requests.post(f"{BASE}/api/step3/apply_suggestions", json={
        "pipeline_id": pid, "accepted_ids": [sug_id]}, timeout=60).json()
    assert r["status"] == "ok" and r["applied_count"] == 1, r
    assert r["aligned_version"] == 3, r
    ok("建议池采纳 → aligned IR v3（验证回流闭环走通）")

    sd = requests.get(f"{BASE}/api/pipelines/{pid}", timeout=30).json()["pipeline"]["step_data"]
    assert sd.get("step3_pending_suggestions") == [], "采纳后建议池应清空"
    ir_v3 = json.loads((Path(workspace) / sd["step3_aligned_file"]).read_text(encoding="utf-8"))
    e1 = next(e for e in ir_v3["entries"] if e["entry_id"] == "KN-001")
    assert "80%" in e1["fields"].get("例外情形", ""), e1["fields"]
    assert e1["lifecycle"]["revisions"], "应有修订审计"
    ok("IR v3 内容与修订审计校验")

    # 9. 重新编译应使用 v3
    r = requests.post(f"{BASE}/api/step4/compile", data={
        "pipeline_id": pid, "formats": "skill"}, timeout=120).json()
    assert r["status"] == "ok" and r.get("ir_version") == 3, r
    skill_md = requests.get(f"{BASE}{r['download_url']}", timeout=30).text
    assert "80%" in skill_md, "回流修订应进入 SKILL 终版"
    ok("对齐↔验证小循环：v3 重编译，回流内容进入终版")

    # 10. KB 发布 / 检索 / 案例库
    r = requests.post(f"{BASE}/api/kb/publish", json={"pipeline_id": pid, "by": "e2e"}, timeout=60).json()
    assert r["status"] == "ok" and r["created"] == 2, r
    ok(f"kb publish → created={r['created']} slug={r['skill_slug']}")

    r = requests.get(f"{BASE}/api/kb/entries", params={
        "domain": "银行信贷", "scenario": "对公信贷尽调"}, timeout=30).json()
    assert r["status"] == "ok" and r["total"] == 2, r
    entry_uid = r["entries"][0]["entry_uid"]
    ok("kb entries 检索")

    r = requests.post(f"{BASE}/api/kb/cases", json={"cases": [
        {"description": "芯片设计企业成立1年申请授信500万", "结论": "通过",
         "domain": "银行信贷", "scenario": "对公信贷尽调", "difficulty": "hard"},
        {"description": "贸易企业无抵押物申请授信", "结论": "拒绝",
         "domain": "银行信贷", "scenario": "对公信贷尽调", "difficulty": "edge"},
    ]}, timeout=30).json()
    assert r["status"] == "ok" and r["created"] == 2, r
    r = requests.get(f"{BASE}/api/kb/cases", params={"domain": "银行信贷"}, timeout=30).json()
    assert r["total"] == 2
    ok("kb cases 录入/查询")

    r = requests.get(f"{BASE}/api/kb/entries/{entry_uid}/timeline", timeout=30).json()
    assert r["status"] == "ok" and r["timeline"], r
    r = requests.get(f"{BASE}/api/kb/skills", timeout=30).json()
    assert r["status"] == "ok" and r["total"] >= 1, r
    ok("kb timeline / releases")

    # 11. 回滚到第 2 步：step3/4/5 下游键应清理（rollback 清 from_step 之后的产物）
    r = requests.post(f"{BASE}/api/pipelines/{pid}/rollback/2", timeout=30).json()
    assert r["status"] == "ok", r
    sd = r["pipeline"]["step_data"]
    for key in ("step3_aligned_file", "step3_final_file", "step3_pending_suggestions",
                "step4_skill_file", "step4_published_version",
                "step5_replay_file", "step5_hit_rate", "step5_suggestions_file"):
        assert not sd.get(key), f"rollback 后 {key} 应被清理: {sd.get(key)}"
    assert r["pipeline"]["step_status"].get("5") == "pending"
    ok("rollback(2) 清理 step3/4/5 全部键（含第 5 步）")

    if _failures:
        print("FAILURES:", _failures)
        return 1
    print("\nAll IR pipeline e2e tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# 陈总监知识导入与流水线试点 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将陈总监的会议纪要文档试点导入知识库，并通过 5 步流水线生成「总监带队访谈/会议纪要方法论」SKILL.md。

**Architecture:** 用一个 Python 导入脚本读取 `.md` 文件，调用 `knowledge_base.py` 的 `publish_entries` 写入 KB entries；然后通过平台现有的 API/模块依次执行 Step1~Step5，产出 SKILL.md 及相关产物。所有产物存入 `data/archive/chen-director-pilot/`。

**Tech Stack:** Python 3.x、Flask 后端、SQLite (`data/kb/knowledge_base.db`)、现有流水线模块。

---

## 背景

- 知识源目录：`/mnt/c/Users/yusiyi/Desktop/我的工作空间/samples/陈总监知识汇集`
- 试点文件：4 个 `.md` 中的 1~2 个。推荐第一个试点为 `总监在新员工培训中的会议纪要.md`（内容最完整）。
- 后端已启动：`http://127.0.0.1:5000`
- 知识库存储：`tacit-knowledge-platform/data/kb/knowledge_base.db`
- 产物目录：`tacit-knowledge-platform/data/archive/chen-director-pilot/`

---

## 文件结构

| 文件 | 作用 |
|------|------|
| `backend/tools/import_chen_kb.py` | 新建：读取 `.md` 文件并写入 `kb_entries` |
| `data/archive/chen-director-pilot/` | 新建目录：存放流水线产物 |
| `data/archive/chen-director-pilot/pipeline.json` | 手动创建/脚本更新的流水线状态 |
| `data/archive/chen-director-pilot/template_*.xlsx` | Step1 场景锚定产物 |
| `data/archive/chen-director-pilot/preextract_*.xlsx` | Step2 知识萃取产物 |
| `data/archive/chen-director-pilot/skill_draft_*.json` | Step2 Skill IR 草稿 |
| `data/archive/chen-director-pilot/final_*.xlsx` / `skill_draft_aligned_*.json` | Step3 知识对齐产物 |
| `data/archive/chen-director-pilot/SKILL_*.md` | Step4 智能转化产物 |
| `data/archive/chen-director-pilot/validation_report_*.md` | Step5 验证回放产物 |

---

## Task 1: 创建导入脚本 `backend/tools/import_chen_kb.py`

**Files:**
- Create: `backend/tools/import_chen_kb.py`
- Modify: 无
- Test: 运行脚本并检查数据库

- [ ] **Step 1: 创建脚本骨架并解析单个 .md 文件**

```python
#!/usr/bin/env python3
"""导入陈总监会议纪要 .md 文档到知识库 (kb_entries)。"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# 把 backend 加入路径
BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from knowledge_base import get_db, init_db, publish_entries

SOURCE_DIR = Path("/mnt/c/Users/yusiyi/Desktop/我的工作空间/samples/陈总监知识汇集")


def read_markdown(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    # 提取第一行 # 标题作为 title
    title = path.stem
    m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if m:
        title = m.group(1).strip()
    return {
        "title": title,
        "content": text,
        "filename": path.name,
    }


def classify_domain(title: str, content: str) -> str:
    text = (title + " " + content).lower()
    if any(k in text for k in ["信贷", "风控", "审批", "授信", "不良"]):
        return "银行信贷风控审批"
    if any(k in text for k in ["客户交流", "会议纪要", "会议总结", "bpi", "shb", "jkb", "moniepoint", "格鲁吉亚", "约旦", "峰会"]):
        return "金融科技出海客户交流"
    if any(k in text for k in ["销售", "解决方案", "培训", "企业级"]):
        return "企业级银行解决方案销售"
    return "金融科技出海客户交流"


def main() -> None:
    init_db()
    md_files = sorted(SOURCE_DIR.glob("*.md"))
    if not md_files:
        print("未找到 .md 文件", file=sys.stderr)
        sys.exit(1)

    # 试点：先处理第一个 .md
    for path in md_files[:1]:
        doc = read_markdown(path)
        domain = classify_domain(doc["title"], doc["content"])
        entry = {
            "title": doc["title"],
            "summary": doc["content"][:500] + "..." if len(doc["content"]) > 500 else doc["content"],
            "content": doc["content"],
            "source_file": doc["filename"],
            "expert": "陈总监",
            "doc_type": "会议纪要",
        }
        entry_uid = publish_entries(
            domain=domain,
            scenario="总监知识汇集",
            category="会议纪要",
            fields_list=[entry],
            contributed_by="import-script",
            source_pipeline_id="chen-director-pilot",
        )[0]
        print(f"导入 [{domain}] {path.name} -> {entry_uid}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 运行脚本验证数据库写入**

Run:
```bash
cd /mnt/d/my-workspace/tacit-knowledge-platform/backend
source .venv/bin/activate
python tools/import_chen_kb.py
```

Expected: 输出形如 `导入 [金融科技出海客户交流] 总监在新员工培训中的会议纪要.md -> kb-...`。

- [ ] **Step 3: 查询数据库确认 entry 已写入**

Run:
```bash
sqlite3 /mnt/d/my-workspace/tacit-knowledge-platform/data/kb/knowledge_base.db \
  "SELECT entry_uid, domain, scenario, category FROM kb_entries WHERE source_pipeline_id='chen-director-pilot';"
```

Expected: 看到 1 条记录。

- [ ] **Step 4: Commit**

```bash
git add backend/tools/import_chen_kb.py
git commit -m "feat: add script to import Chen director meeting notes into KB"
```

---

## Task 2: 设计 Step1 场景锚定

**Files:**
- Create: `data/archive/chen-director-pilot/pipeline.json`
- Modify: 无
- Test: 文件存在且 JSON 合法

- [ ] **Step 1: 创建流水线状态文件**

```json
{
  "pipeline_id": "chen-director-pilot",
  "name": "总监带队访谈/会议纪要方法论",
  "expert": "陈总监",
  "current_step": 1,
  "step_status": "ready",
  "source_kb_entry_uids": ["PLACEHOLDER_AFTER_IMPORT"],
  "step_data": {}
}
```

Run:
```bash
mkdir -p /mnt/d/my-workspace/tacit-knowledge-platform/data/archive/chen-director-pilot
cat > /mnt/d/my-workspace/tacit-knowledge-platform/data/archive/chen-director-pilot/pipeline.json <<'EOF'
{
  "pipeline_id": "chen-director-pilot",
  "name": "总监带队访谈/会议纪要方法论",
  "expert": "陈总监",
  "current_step": 1,
  "step_status": "ready",
  "source_kb_entry_uids": [],
  "step_data": {}
}
EOF
```

- [ ] **Step 2: 更新 pipeline.json 中的 source_kb_entry_uids**

将 Task 1 中得到的 `entry_uid` 填入 `source_kb_entry_uids` 数组。

Run（把 `<ENTRY_UID>` 替换为实际 uid）：
```bash
python - <<'PY'
import json, pathlib
p = pathlib.Path("/mnt/d/my-workspace/tacit-knowledge-platform/data/archive/chen-director-pilot/pipeline.json")
data = json.loads(p.read_text())
data["source_kb_entry_uids"] = ["<ENTRY_UID>"]
p.write_text(json.dumps(data, indent=2, ensure_ascii=False))
PY
```

- [ ] **Step 3: Commit**

```bash
git add data/archive/chen-director-pilot/pipeline.json
git commit -m "chore: create chen-director-pilot pipeline state"
```

---

## Task 3: 执行 Step1（场景锚定）

**Files:**
- Create: `data/archive/chen-director-pilot/template_*.xlsx`
- Create: `data/archive/chen-director-pilot/step1_*.md`
- Modify: `data/archive/chen-director-pilot/pipeline.json`
- Test: 检查产物存在且 pipeline.json current_step 更新

- [ ] **Step 1: 使用 API 创建流水线并执行 Step1**

通过 `curl` 调用后端 API：

```bash
# 创建流水线
curl -s -X POST http://127.0.0.1:5000/api/pipeline \
  -H "Content-Type: application/json" \
  -d '{
    "name": "总监带队访谈/会议纪要方法论",
    "expert": "陈总监",
    "domain": "金融科技出海客户交流",
    "scenario": "总监知识汇集",
    "description": "基于陈总监多篇会议纪要，沉淀总监带队访谈与会议纪要方法论"
  }' | tee /tmp/create_pipeline.json

# 记录 pipeline_id
PIPELINE_ID=$(python -c "import json; print(json.load(open('/tmp/create_pipeline.json'))['pipeline_id'])")

# 执行 Step1
curl -s -X POST "http://127.0.0.1:5000/api/step/1?pipeline_id=${PIPELINE_ID}" \
  -H "Content-Type: application/json" \
  -d '{
    "sub_scenarios": [
      {"name": "会议前准备", "description": "明确访谈/会议目标、参会人、议题清单"},
      {"name": "会议中记录", "description": "结构化记录关键观点、案例、决策与待办"},
      {"name": "会议后提炼", "description": "从纪要中萃取方法论、监管洞察与可复用框架"},
      {"name": "知识转化", "description": "将提炼内容转化为 SKILL.md / QA / COT"}
    ]
  }' | tee /tmp/step1_result.json
```

- [ ] **Step 2: 检查 Step1 产物**

Run:
```bash
python - <<'PY'
import json
r = json.load(open('/tmp/step1_result.json'))
print('current_step:', r.get('current_step'))
print('step_status:', r.get('step_status'))
print('step1 keys:', [k for k in r.get('step_data', {}) if k.startswith('step1_')])
PY
```

Expected: `current_step=1`, `step_status=done` 或 `completed`，`step_data` 中包含 `step1_output_file` 和 `step1_md_file`。

- [ ] **Step 3: 把产物路径保存到 pilot pipeline.json**

手动把 Step1 产物路径复制到 `data/archive/chen-director-pilot/pipeline.json` 的 `step_data` 中，并设置 `current_step=1`, `step_status=done`。

- [ ] **Step 4: Commit**

```bash
git add data/archive/chen-director-pilot/
git commit -m "feat: run Step1 scenario anchoring for chen-director pilot"
```

---

## Task 4: 执行 Step2（知识萃取）

**Files:**
- Create: `data/archive/chen-director-pilot/preextract_*.xlsx`
- Create: `data/archive/chen-director-pilot/skill_draft_*.json`
- Modify: `data/archive/chen-director-pilot/pipeline.json`
- Test: 检查 Excel + IR draft 文件存在

- [ ] **Step 1: 调用 Step2 API**

```bash
PIPELINE_ID=$(python -c "import json; print(json.load(open('/tmp/create_pipeline.json'))['pipeline_id'])")

curl -s -X POST "http://127.0.0.1:5000/api/step/2?pipeline_id=${PIPELINE_ID}" \
  -H "Content-Type: application/json" \
  -d '{
    "source_type": "kb_entries",
    "entry_uids": ["<ENTRY_UID>"]
  }' | tee /tmp/step2_result.json
```

- [ ] **Step 2: 检查 Step2 产物**

Run:
```bash
python - <<'PY'
import json
r = json.load(open('/tmp/step2_result.json'))
print('current_step:', r.get('current_step'))
print('step_status:', r.get('step_status'))
print('step2 keys:', [k for k in r.get('step_data', {}) if k.startswith('step2_')])
PY
```

Expected: `current_step=2`, `step_status=done`，`step_data` 中包含 `step2_output_file` 和 `step2_draft_file`。

- [ ] **Step 3: 同步 pilot pipeline.json**

把 Step2 产物路径写入 `data/archive/chen-director-pilot/pipeline.json`。

- [ ] **Step 4: Commit**

```bash
git add data/archive/chen-director-pilot/
git commit -m "feat: run Step2 knowledge extraction for chen-director pilot"
```

---

## Task 5: 执行 Step3（知识对齐）

**Files:**
- Create: `data/archive/chen-director-pilot/final_*.xlsx`
- Create: `data/archive/chen-director-pilot/skill_draft_aligned_*.json`
- Modify: `data/archive/chen-director-pilot/pipeline.json`
- Test: 检查对齐产物存在

- [ ] **Step 1: 调用 Step3 API 或手动对齐**

Step3 通常需要人工在 Excel 中编辑后上传。如果 API 支持自动对齐：

```bash
PIPELINE_ID=$(python -c "import json; print(json.load(open('/tmp/create_pipeline.json'))['pipeline_id'])")

curl -s -X POST "http://127.0.0.1:5000/api/step/3?pipeline_id=${PIPELINE_ID}" \
  -H "Content-Type: application/json" \
  -d '{}' | tee /tmp/step3_result.json
```

如果 API 返回需要上传编辑后的 Excel，则使用 `/api/step/3/upload` 上传。

- [ ] **Step 2: 检查 Step3 产物**

Expected: `current_step=3`, `step_status=done`，`step_data` 中包含 `step3_final_file` 或 `step3_aligned_file`。

- [ ] **Step 3: 同步 pilot pipeline.json**

- [ ] **Step 4: Commit**

```bash
git add data/archive/chen-director-pilot/
git commit -m "feat: run Step3 knowledge alignment for chen-director pilot"
```

---

## Task 6: 执行 Step4（智能转化）

**Files:**
- Create: `data/archive/chen-director-pilot/SKILL_*.md`
- Create: `data/archive/chen-director-pilot/QA_*.md`
- Create: `data/archive/chen-director-pilot/COT_*.md`
- Modify: `data/archive/chen-director-pilot/pipeline.json`
- Test: SKILL.md 内容包含方法论结构

- [ ] **Step 1: 调用 Step4 API**

```bash
PIPELINE_ID=$(python -c "import json; print(json.load(open('/tmp/create_pipeline.json'))['pipeline_id'])")

curl -s -X POST "http://127.0.0.1:5000/api/step/4?pipeline_id=${PIPELINE_ID}" \
  -H "Content-Type: application/json" \
  -d '{}' | tee /tmp/step4_result.json
```

- [ ] **Step 2: 检查 Step4 产物**

Expected: `current_step=4`, `step_status=done`，`step_data` 中包含 `step4_skill_file`。

- [ ] **Step 3: 预览 SKILL.md 开头**

Run:
```bash
head -50 data/archive/chen-director-pilot/SKILL_*.md
```

- [ ] **Step 4: 同步 pilot pipeline.json**

- [ ] **Step 5: Commit**

```bash
git add data/archive/chen-director-pilot/
git commit -m "feat: run Step4 skill generation for chen-director pilot"
```

---

## Task 7: 执行 Step5（验证回放）

**Files:**
- Create: `data/archive/chen-director-pilot/validation_report_*.md`
- Create: `data/archive/chen-director-pilot/revision_suggestions_*.md`
- Modify: `data/archive/chen-director-pilot/pipeline.json`
- Test: 验证报告生成

- [ ] **Step 1: 调用 Step5 API**

```bash
PIPELINE_ID=$(python -c "import json; print(json.load(open('/tmp/create_pipeline.json'))['pipeline_id'])")

curl -s -X POST "http://127.0.0.1:5000/api/step/5?pipeline_id=${PIPELINE_ID}" \
  -H "Content-Type: application/json" \
  -d '{}' | tee /tmp/step5_result.json
```

- [ ] **Step 2: 检查 Step5 产物**

Expected: `current_step=5`, `step_status=done`，`step_data` 中包含 `step5_replay_file` 或 `step5_result_file`。

- [ ] **Step 3: 同步 pilot pipeline.json**

- [ ] **Step 4: Commit**

```bash
git add data/archive/chen-director-pilot/
git commit -m "feat: run Step5 validation replay for chen-director pilot"
```

---

## Task 8: 扩展导入全部 .md 文件

**Files:**
- Modify: `backend/tools/import_chen_kb.py`
- Test: 数据库中新增 4 条 entries

- [ ] **Step 1: 修改脚本处理所有 .md 文件**

把脚本中的 `md_files[:1]` 改为 `md_files`，并更新 `classify_domain` 逻辑确保每个文件进入正确 domain。

- [ ] **Step 2: 重新运行导入脚本**

Run:
```bash
python tools/import_chen_kb.py
```

Expected: 4 条记录，分别归入对应的 domain。

- [ ] **Step 3: 查询数据库确认**

```bash
sqlite3 /mnt/d/my-workspace/tacit-knowledge-platform/data/kb/knowledge_base.db \
  "SELECT entry_uid, domain, category, fields_json FROM kb_entries WHERE source_pipeline_id='chen-director-pilot';"
```

Expected: 4 条记录。

- [ ] **Step 4: Commit**

```bash
git add backend/tools/import_chen_kb.py
git commit -m "feat: import all 4 Chen director markdown files into KB"
```

---

## Task 9: 扩展流水线覆盖全部 .md entries

**Files:**
- Modify: `data/archive/chen-director-pilot/pipeline.json`
- Test: Step2 调用时使用 4 个 entry_uids

- [ ] **Step 1: 更新 pilot pipeline.json 的 source_kb_entry_uids**

把 4 个 entry_uids 都填入数组。

- [ ] **Step 2: 用 4 个 entries 重新跑 Step2~Step5**

参考 Task 4~7 的 API 调用，把 Step2 的 `entry_uids` 替换为全部 4 个 uid。

- [ ] **Step 3: 检查最终产物并 Commit**

```bash
git add data/archive/chen-director-pilot/
git commit -m "feat: run full pipeline with all Chen director entries"
```

---

## Task 10: 添加导入脚本测试

**Files:**
- Create: `backend/tests/test_import_chen_kb.py`
- Modify: 无
- Test: `pytest backend/tests/test_import_chen_kb.py -v`

- [ ] **Step 1: 编写测试**

```python
import sqlite3
from pathlib import Path

import pytest

from knowledge_base import get_db
from scripts.import_chen_kb import classify_domain, read_markdown

SOURCE_DIR = Path("/mnt/c/Users/yusiyi/Desktop/我的工作空间/samples/陈总监知识汇集")


def test_read_markdown():
    path = SOURCE_DIR / "总监在新员工培训中的会议纪要.md"
    doc = read_markdown(path)
    assert doc["title"].startswith("总监")
    assert "中国数字金融" in doc["content"]
    assert doc["filename"].endswith(".md")


def test_classify_domain_meeting_notes():
    domain = classify_domain("金融峰会期间总监与 BPI 交流的会议纪要", "")
    assert domain == "金融科技出海客户交流"


def test_kb_has_entries_after_import():
    conn = get_db()
    rows = conn.execute(
        "SELECT COUNT(*) FROM kb_entries WHERE source_pipeline_id='chen-director-pilot'"
    ).fetchone()[0]
    assert rows >= 1
```

- [ ] **Step 2: 运行测试**

```bash
pytest backend/tests/test_import_chen_kb.py -v
```

Expected: 3 passed。

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_import_chen_kb.py
git commit -m "test: add tests for Chen director KB importer"
```

---

## Self-Review

**Spec coverage:** 计划覆盖了从导入 KB entries → Step1 → Step5 → 扩展全部 .md → 测试的完整流程。

**Placeholder scan：** 唯一占位符是 `<ENTRY_UID>`，它将在 Task 1 运行后由实际值替换，符合流程需要。

**类型一致性：** 所有 API 调用使用 JSON body，字段名与 `pipeline_artifacts.py` 中的 `STEP_OUTPUT_KEYS_BY_STEP` 保持一致。

---

## 执行方式

**Plan complete and saved to `docs/superpowers/plans/2026-06-13-import-chen-director-knowledge-plan.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**

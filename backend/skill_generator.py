"""Meta-skill: generate executable SKILL.md from pipeline knowledge + golden database.

This module takes step3 alignment output (structured knowledge items) and the
golden database schema, then uses LLM to produce a SKILL.md that an Agent
(Hermes / OpenClaw) can load and execute — including SQL queries, decision
rules, and assessment report templates.
"""

import json
from pathlib import Path

GOLDEN_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "golden" / "golden_test.db"


def build_golden_schema_prompt() -> str:
    """Read golden DB schema and sample data, return a prompt-ready description."""
    import sqlite3

    if not GOLDEN_DB_PATH.exists():
        return "（golden 知识库不可用）"

    db = sqlite3.connect(str(GOLDEN_DB_PATH))
    db.row_factory = sqlite3.Row

    parts = []
    tables = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name != 'verification_runs' ORDER BY name"
    ).fetchall()

    for t in tables:
        name = t["name"]
        cols = db.execute(f"PRAGMA table_info([{name}])").fetchall()
        col_desc = ", ".join(f"{c['name']}({c['type']})" for c in cols)
        count = db.execute(f"SELECT COUNT(*) as n FROM [{name}]").fetchone()["n"]
        parts.append(f"### {name} ({count} rows)\nColumns: {col_desc}")

        if name == "golden_items":
            samples = db.execute("SELECT * FROM golden_items LIMIT 2").fetchall()
            for s in samples:
                d = dict(s)
                parts.append(
                    "  " + json.dumps({k: v for k, v in d.items() if v and k != "created_at"}, ensure_ascii=False)[:300]
                )

    db.close()
    return "\n\n".join(parts)


def build_skill_generation_prompt(
    scenario_name: str,
    scenario_description: str,
    knowledge_items: list[dict],
    golden_schema: str,
    existing_skill_template: str = "",
) -> str:
    """Build the LLM prompt for generating an executable Agent SKILL.md."""

    items_json = json.dumps(knowledge_items[:15], ensure_ascii=False, indent=2)

    return f"""你是一位 Agent 技能设计师。请根据以下输入，生成一份可部署到 Hermes / OpenClaw Agent 平台的 SKILL.md 文件。

## 场景信息
- 名称：{scenario_name}
- 说明：{scenario_description}

## 知识条目（来自五步法流水线萃取+对齐）
{items_json}

## Golden 知识库 Schema（可查询的真实 SQLite 数据库）
{golden_schema}

## 生成的 SKILL.md 必须包含以下章节

### 1. 元数据 (frontmatter)
```yaml
name: {{slug}}
description: {{一句话描述触发条件与能力}}
metadata:
  version: "1.0"
  triggers:
    - {{触发关键词1}}
    - {{触发关键词2}}
  database: data/golden/golden_test.db
```

### 2. 触发规则 (TRIGGER)
明确什么类型的输入文档/事件会激活此 Skill：
- 文档类型（如：贷款申请、案例复盘、贷后检查报告）
- 关键信号词（如场景和知识列中出现的术语）
- 排除条件

### 3. 知识匹配引擎 (MATCHING)
对每条 golden_items 中的知识，定义匹配方式：
```sql
-- 示例：按环节和关键词匹配
SELECT * FROM golden_items
WHERE 环节 = '贷前尽调'
  AND (具体方法 LIKE '%流水%' OR 判断逻辑 LIKE '%流水%');
```
至少给出 3~5 条可直接执行的 SQL 查询，引用 golden_items 和 golden_documents 的真实列名。

### 4. 决策链 (DECISION_FLOW)
按环节组织决策步骤，每步包含：
- 输入条件
- 匹配的知识条目引用
- 输出判断/建议
- 下一跳步骤

### 5. 评估输出模板 (OUTPUT)
定义 Agent 评估报告的标准格式（JSON 或 Markdown），包含：
- 匹配到的知识条目列表（知识编号、置信度、匹配依据）
- 风险信号汇总（来自反模式/例外情形）
- 建议动作（审批/拒绝/补充尽调/降额/追加担保）
- 缺失信息提示（哪些字段在输入中未提供但判断所需）

### 6. 使用示例 (EXAMPLE)
给出一个简短的输入→处理→输出示例，让 Agent 理解执行流程。

## 要求
1. 所有 SQL 查询必须引用 golden DB 的真实表名和列名
2. 决策链须覆盖知识条目中出现的所有「环节」值
3. 输出格式须包含「匹配知识」「置信度」「建议动作」三个核心字段
4. 全文使用中文撰写，SQL 保留英文
5. 生成的 SKILL.md 可直接保存为文件并加载到 Agent 平台

仅输出完整的 SKILL.md 文件内容，不要任何前后说明。"""


def parse_skill_output(llm_text: str) -> dict:
    """Parse LLM output into structured fields for frontend display."""
    # Extract frontmatter
    frontmatter = ""
    if llm_text.startswith("---"):
        end = llm_text.find("---", 3)
        if end > 0:
            frontmatter = llm_text[3:end].strip()

    # Extract section headers
    sections = {}
    current_section = "preamble"
    current_content = []
    for line in llm_text.split("\n"):
        if line.startswith("## "):
            if current_content:
                sections[current_section] = "\n".join(current_content).strip()
            current_section = line[3:].strip()
            current_content = []
        else:
            current_content.append(line)
    if current_content:
        sections[current_section] = "\n".join(current_content).strip()

    return {
        "frontmatter": frontmatter,
        "sections": sections,
        "full_markdown": llm_text,
        "section_count": len(sections),
        "has_sql": "SELECT" in llm_text.upper() and "FROM" in llm_text.upper(),
    }


def get_golden_stats() -> dict:
    """Return summary stats about the golden DB for the frontend."""
    import sqlite3

    if not GOLDEN_DB_PATH.exists():
        return {"available": False}

    db = sqlite3.connect(str(GOLDEN_DB_PATH))
    stats = {
        "available": True,
        "path": str(GOLDEN_DB_PATH),
        "tables": {},
    }
    tables = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    for t in tables:
        name = t[0]
        count = db.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]
        cols = db.execute(f"PRAGMA table_info([{name}])").fetchall()
        stats["tables"][name] = {"rows": count, "columns": len(cols)}
    db.close()
    return stats

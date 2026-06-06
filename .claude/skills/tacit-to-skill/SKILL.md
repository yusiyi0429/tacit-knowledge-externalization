---
name: tacit-to-skill
description: 引导领域专家通过 4 步流水线（场景锚定→知识萃取→知识对齐→智能转化），将隐性经验转化为可被 Agent 执行的标准 SKILL.md
metadata:
  version: "1.0"
  triggers:
    - 知识萃取
    - 经验沉淀
    - 专家访谈
    - 把经验变成 Skill
    - 隐性知识显性化
    - 专家知识转化
    - 写 Skill
---

# 隐性知识显性化 — Agent 端 Skill

将银行信贷专家的隐性经验 → 结构化、可交付的 AI Skill。你（Agent）就是 LLM，不需要调外部 API，直接用你的推理能力走完 4 步。

## 核心脚本（方式二：直接调 Python 模块，无需 Flask）

| 步骤 | 脚本 | 用途 |
|------|------|------|
| Step 1 | Agent 直接写 Excel | 创建场景骨架模板 |
| Step 2 | `python -c "from step2_preextract import ..."` | 将萃取条目写入 Excel |
| Step 3 | `python backend/revision_processor.py` | 按修订意见生成修订稿 |
| Step 4 | `python backend/knowledge_delivery.py` | 生成 SKILL.md / QA / 思维链 |

所有脚本从 `backend/` 目录执行。

---

## 第一步：场景锚定

**目标**：与专家对话，明确场景边界和知识维度。

### 对话引导

向专家依次确认：

1. **场景名称**：这个知识 Skill 叫什么？（如「信贷审批反欺诈」「零售贷后预警」）
2. **业务边界**：覆盖哪些环节？不覆盖哪些？
3. **目标用户**：谁会使用这个 Skill？
4. **知识维度**：需要从专家经验中捕捉哪些维度的知识？

参考 `config/scenario-schema.yaml` 的标准知识列：
- 环节、访谈方向、具体方法、知识类型、知识引用、适用条件、判断逻辑、反模式/踩坑提示

对话中你可以根据专家描述增加领域特有的知识列。

### 产出：场景骨架 Excel

对话结束后，创建模板 Excel：

```python
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from pathlib import Path

output_dir = Path("workspace")
output_dir.mkdir(exist_ok=True)
output_path = output_dir / "template_scenario.xlsx"

wb = openpyxl.Workbook()
ws = wb.active
ws.title = "场景骨架"

# 锚定列（固定）
anchor_cols = ["场景", "场景说明", "子场景", "子场景说明"]
# 知识列（与专家确认的）
knowledge_cols = ["环节", "访谈方向", "具体方法", "知识类型", "知识引用",
                  "适用条件", "判断逻辑", "反模式/踩坑提示"]

headers = anchor_cols + knowledge_cols
header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
header_font = Font(bold=True, color="FFFFFF")

for col, h in enumerate(headers, 1):
    cell = ws.cell(1, col, value=h)
    cell.font = header_font
    cell.fill = header_fill
    cell.alignment = Alignment(horizontal="center", vertical="center")

# 写入场景信息行
ws.cell(2, 1, value="场景名称")
ws.cell(2, 2, value="专家确认的场景描述")
# ... 填充子场景

wb.save(output_path)
print(f"模板已创建: {output_path}")
```

将脚本保存为 `backend/_gen_template.py` 并执行：
```bash
cd backend && python _gen_template.py && cd ..
```

记录产出文件路径 `workspace/template_scenario.xlsx`，后续步骤需要用到。

---

## 第二步：知识萃取

**目标**：从专家提供的文档/口述中提取结构化知识条目。

### 对话引导

1. 请专家提供知识来源：制度文件、操作手册、案例复盘、培训材料等
2. 请专家口述关键经验（你可以主动追问）：
   - 「这个判断你是怎么做的？依据是什么？」
   - 「有没有踩过坑？后来怎么避免的？」
   - 「如果你的徒弟来做，你会叮嘱他什么？」
3. 将专家口述整理成结构化的知识条目

### 萃取格式

每条知识必须至少包含 `category`、`content`、`trigger_condition` 三个字段。完整条目结构：

```json
[
  {
    "category": "判断规则",
    "content": "新客户首次授信时，需同时核验企业征信与近6个月银行流水",
    "trigger_condition": "新客户首次授信申请",
    "judgment_logic": "若征信有逾期记录且流水不稳定，则进入人工复核",
    "anti_pattern": "不要仅凭征信评分直接通过，必须交叉验证流水",
    "source": "《信贷管理办法》第3章",
    "confidence": "高"
  }
]
```

### 产出：萃取 Excel

将萃取条目写入 Excel：

```python
import sys, json
sys.path.insert(0, 'backend')
from step2_preextract import write_preextract_excel
from pathlib import Path

items = json.loads(sys.argv[1])  # 萃取条目 JSON
step1_path = Path(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2] else None
output_path = Path("workspace/preextract.xlsx")

meta = write_preextract_excel(
    step1_path=step1_path,
    output_path=output_path,
    items=items,
    pipeline_id="tacit-skill"
)
print(f"萃取完成: {meta['count']} 条, 写入 {meta['filled_rows']} 行")
```

执行：
```bash
cd backend && python -c "
import sys, json
sys.path.insert(0, '.')
from step2_preextract import write_preextract_excel
from pathlib import Path

items = json.loads(open('_extracted_items.json', encoding='utf-8').read())
step1_path = Path('../workspace/template_scenario.xlsx')
output_path = Path('../workspace/preextract.xlsx')

meta = write_preextract_excel(
    step1_path=step1_path if step1_path.exists() else None,
    output_path=output_path,
    items=items,
    pipeline_id='tacit-skill'
)
print(json.dumps(meta, ensure_ascii=False))
" && cd ..
```

萃取条目较多时（>10 条），先将条目 JSON 写入临时文件 `backend/_extracted_items.json`，再执行上述脚本。

---

## 第三步：知识对齐

**目标**：专家逐条审核萃取成果，Agent 根据修订意见生成最终定稿。

### 对话引导

1. 将萃取 Excel 展示给专家（告知路径，专家可在 Luckysheet 中打开）
2. 逐条或逐类确认：
   - 「这部分内容描述准确吗？」
   - 「有没有遗漏的关键判断？」
   - 「有没有需要修正的细节？」
3. 收集专家的修订意见，整理为结构化修订条目

### 修订条目格式

```json
[
  {
    "sheet": "知识萃取",
    "row": 5,
    "col": 3,
    "action": "modify",
    "old_value": "原内容",
    "new_value": "修订后内容",
    "note": "专家指出需要补充流水验证步骤"
  }
]
```

`action` 取值：`modify`（修改）、`add`（新增）、`delete`（删除）、`supplement`（补充）。

### 产出：修订稿 Excel

将修订条目写入 JSON 文件后执行 revision_processor：

```bash
cd backend && python revision_processor.py \
  --input ../workspace/preextract.xlsx \
  --expert-notes-file _revision_notes.json \
  --output ../workspace/final.xlsx && cd ..
```

---

## 第四步：智能转化

**目标**：将对齐稿转化为 Agent 可装载的标准 Skill。

### 产出：SKILL.md + manifest.json

```bash
cd backend && python knowledge_delivery.py \
  --input ../workspace/final.xlsx \
  --config ../config/scenario-schema.yaml \
  --output ../workspace/delivery \
  --context-json '{"场景名称":"<专家确认的场景名>","领域":"<领域>"}' && cd ..
```

产出目录结构：
```
workspace/delivery/
├── SKILL.md              # agentskills.io 标准 Skill（含 frontmatter）
├── manifest.json         # OpenClaw/Hermes/Claude Code 兼容清单
├── chain_of_thought.md   # 思维链（可选）
└── qa_pairs.json         # QA 对（可选）
```

### 生成后确认

1. 将 SKILL.md 内容展示给专家，确认无误
2. 告知专家：此文件可直接放入任意 Agent 项目的 `.claude/skills/<name>/SKILL.md`
3. 记录 Skill 的关键元数据：场景名、知识条目数、版本日期

---

## 完整执行示例

```
专家: 我想把信贷审批中的反欺诈经验沉淀成 Skill

Agent（你）:
  → Step 1: 确认场景边界（覆盖贷前审批，不含贷后），确认知识维度（8列）
  → 生成 workspace/template_scenario.xlsx

  → Step 2: 专家提供《反欺诈操作手册》+ 口述 3 个典型案例
  → Agent 提取 15 条知识条目 → 写入 workspace/preextract.xlsx

  → Step 3: 专家审核 → 5 处修改 + 2 条补充
  → Agent 整理修订 JSON → 执行 revision_processor.py → workspace/final.xlsx

  → Step 4: 执行 knowledge_delivery.py → workspace/delivery/SKILL.md
  → Agent 展示 SKILL.md 给专家确认 ✓
```

## 注意事项

- **Agent 即 LLM**：萃取和修订分析直接用你的推理能力，不需要调外部 API
- **所有脚本从 `backend/` 目录执行**：Python 模块间有相对引用
- **workspace/ 目录存放中间产物**：template → preextract → final → delivery
- **专家确认是必须的**：每个步骤产出后都要让专家过目确认再继续
- **SKILL.md 是最终交付物**：可以直接装载到 Claude Code、OpenClaw、Hermes 等平台

# 重构实施方案：Skill 中心化流水线 + 外部知识库 + 验证回流

> 状态：**已实施**（Phase 0–6 全部落地，本文档保留为架构设计依据）
> 配套阅读：`CLAUDE.md`（step data key 同步契约 + Skill IR 不变量）、`docs/业务说明文档.md`

## 实施偏差说明（落地时的取舍）

与方案的主要差异，均为降低风险的过渡期设计：

1. **Step3 对齐采用「Excel 编辑面 + IR 收口」双轨**：专家意见解析/采纳/直通仍走成熟的 Excel 单元格寻址机制（`revision_processor` 色标审计保留），每次产出 `final_*.xlsx` 后由 `_persist_step3_aligned_ir()` 重建对齐版 IR（vN, status=aligned）。entry 级寻址的 IR 直接修订路径已实现（`/api/step3/apply_suggestions`），服务于验证回流与访谈转化两类建议；专家意见路径的 IR 直改可在后续迭代切换。
2. **建议池来源**：当前聚合 验证回流（validation）+ 访谈转化（interview）两路 entry 级建议；融合冲突/重复以 flags_summary 形式展示，不生成可应用建议。
3. **Step1 继承预检落在 Step2**：`kb_inherit` 勾选项在知识萃取界面（继承条目作为融合源参与去重），Step1 不单独做勾选 UI。
4. **旧 `/api/validate/replay` 原样保留**（验证 Excel 知识文本），新 `/api/step5/replay` 验证 SKILL 终版/IR 渲染。
5. **测试**：新增 `backend/tests/test_skill_ir.py`、`test_knowledge_base.py`（单元）与 `e2e_ir_pipeline_test.py`（无 LLM 全链路端到端，覆盖 草稿→对齐→编译→回流→采纳→v+1 重编译→KB 发布→回滚清理）。

---

## 0. 重构目标（一句话）

把流水线的核心产物从 **「Excel 知识工作簿」** 切换为 **「Agent-Skill 草稿（结构化 JSON + 渲染 SKILL.md）」**，专家对齐直接发生在 Skill 草稿上；新增 **第 5 步验证环节**，验证分歧自动回流第 3 步形成闭环；并以 **外部知识库** 作为跨流水线的知识资产层、案例库与检索底座。

### 新旧流水线对比

```
旧：场景锚定 → 萃取(Excel preextract) → 对齐(Excel final) → 转化(SKILL/COT/QA) ──[终点]
新：场景锚定 → 萃取(Skill草稿v1) → 对齐(Skill草稿vN·专家介入) → 转化(SKILL终版/COT/QA·按需) → 验证(回放)
                    ↑                       ↑                                                  │
                    │                       └────────── 分歧 → 修订建议（回流）◄────────────────┘
                    │
              外部知识库（已沉淀知识检索 / 案例库 / 发布与版本）
```

---

## 1. 核心设计决策（先定调，再动手）

### 决策 1：中间表示用「Skill IR（结构化 JSON）」，不是裸 Markdown

第 2 步的产物**不是直接生成一篇 SKILL.md 文本**，而是生成一个结构化的 **Skill 草稿 JSON（下称 Skill IR）**，SKILL.md 由 IR **确定性渲染**得到（复用 `excel_to_skill.py` 的渲染逻辑改造）。

理由：

| 若用裸 Markdown | 用 Skill IR |
|---|---|
| 对齐修订无法精确定位到条目/字段 | 每条知识有稳定 `entry_id`，修订可寻址（沿用现有 `{row, col, action}` 修订协议的思想，改为 `{entry_id, field, action}`） |
| 验证分歧无法映射回具体知识条目 | 回放结果中 `referenced_rules`（KN-编号）直接关联 `entry_id`，分歧可自动转成修订建议 |
| 质量评分（`quality_report.py`）无从下手 | 五维规则评分只需把数据源从 Excel 行换成 IR 条目，逻辑全保留 |
| QA/COT 需重新从文本反解析 | `knowledge_delivery.py` 的 `generate_cot_markdown` / `generate_qa_pairs` 本来就吃 records list，近乎零改动 |
| 知识库无法做条目级入库/版本化 | IR 条目即知识库条目，发布即入库 |

**Skill IR = 单一事实源（SSOT），SKILL.md 永远是渲染产物，不允许反向手改 md。**

### 决策 2：Excel 降级为「可选编辑视图」，不再是数据主轴

- Luckysheet 在线编辑、`revision_processor.py` 的颜色标注审计是现有投资，保留为第 3 步的**可选编辑面**：IR ⇄ Excel 双向投影（导出编辑 → 回读 diff 合并进 IR）。
- 但流水线状态、回滚、下游输入全部以 IR 文件为准。第一期可以先不做 Excel 投影（见 Phase 划分），直接用「条目卡片 + md 预览」的前端对齐界面。

### 决策 3：验证回流是「生成修订建议，专家裁决」，不是自动改稿

回放分歧自动生成的修订建议，复用第 3 步现有的「建议列表 → 专家采纳/驳回/编辑」交互（`/api/step3/apply_notes` 的模式），**绝不自动写入草稿**。隐性知识的最终裁决权必须留在专家手里，这也是整个产品的方法论立场。

### 决策 4：知识库先用 SQLite，检索接口先抽象后实现

与 `golden_db.py` 同栈（SQLite + 纯 Python），零新增基础设施即可跑通闭环；语义检索定义统一接口，第一期用「LLM 批量相似度判断」实现，后续可平滑替换为 embedding/向量库。**不要一开始就引向量数据库**，项目是文件工作空间架构，部署环境（含建行 CCB 网关模式）未必允许。

---

## 2. Skill IR 规格（新文件 `backend/skill_ir.py`）

### 2.1 文件命名与持久化

- 工作空间内文件名：`skill_draft_{pipeline_id}_{version}_{timestamp}.json`（草稿）、`SKILL_{slug}_{timestamp}.md`（渲染预览/终版，沿用现有前缀）
- `pipeline_artifacts.py` 的 `DOWNLOAD_ALLOWED_PREFIXES` 新增：`skill_draft_`、`validation_`、`revision_suggestions_`

### 2.2 IR 结构（v1）

```json
{
  "ir_version": "1.0",
  "skill_meta": {
    "scenario_name": "对公信贷尽调",
    "display_name": "...",
    "domain": "bank_credit",
    "slug": "corporate-credit-dd",
    "draft_version": 3,
    "status": "draft | aligned | published",
    "parent_version": 2,
    "created_at": "...", "updated_at": "..."
  },
  "anchors": {
    "scenario": "...", "scenario_desc": "...",
    "sub_scenarios": [{"name": "...", "desc": "..."}]
  },
  "entries": [
    {
      "entry_id": "KN-001",
      "sub_scenario": "贷前尽调",
      "category": "判断规则 | 操作流程 | 反模式",
      "fields": {
        "知识描述": "...", "适用条件": "...", "判断逻辑": "...",
        "反模式/踩坑提示": "...",
        "经验判断": "...", "适用边界": "...", "例外情形": "...",
        "来源文档": "...", "来源位置": "...", "置信度": "高",
        "贡献专家": "...", "证据数": 2, "突破数": 0
      },
      "lifecycle": {
        "origin": "doc_extract | case_review | interview | kb_import | validation_feedback",
        "source_label": "上传文件名/访谈会话ID/kb条目ID",
        "kb_entry_id": null,
        "revisions": [
          {"version": 2, "action": "modify", "field": "适用条件",
           "old": "...", "new": "...", "by": "expert|llm|validation",
           "note": "...", "at": "..."}
        ]
      },
      "flags": {"duplicate_of": null, "conflict_with": [], "needs_interview": false}
    }
  ],
  "signals": { "fusion_report": "signal_report_*.json 内容内嵌或引用" }
}
```

要点：

- `entries[].fields` 的键**继续对齐 `config/scenario-schema.yaml` 的列名**（L1/L2/L3 三层不变），`field_aliases.py` 继续做别名归一。这样 schema、质量评分、QA/COT 生成全部无感迁移。
- `lifecycle.revisions` 取代 Excel 的「修订状态/原始内容/修订内容」审计列，每个版本的 diff 都可追溯（前端可据此渲染等价于颜色标注的修订视图）。
- `flags` 承接 `knowledge_fusion.py` 的 `_duplicate` / `_conflict` 标记，从「内部下划线键」升级为正式字段。

### 2.3 `backend/skill_ir.py` 模块职责

```
load_ir(path) / save_ir(workspace, ir, version)      # 读写 + 文件名约束
new_draft(scenario_meta, entries) -> ir              # 从萃取条目组装 v1
apply_revisions(ir, revisions) -> new_ir             # 产生 version+1，写 lifecycle.revisions
render_skill_md(ir, config) -> str                   # 确定性渲染（改造 excel_to_skill 主体）
ir_to_records(ir) -> list[dict]                      # 转 records 喂给 quality_report / knowledge_delivery
diff_ir(ir_a, ir_b) -> list[change]                  # 版本对比（前端修订视图用）
validate_ir(ir) -> list[error]                       # 结构校验（entry_id 唯一、必填字段、版本单调）
```

---

## 3. 新流水线分步设计

### Step 1 场景锚定 —— 基本保留，小改

| 项 | 内容 |
|---|---|
| 保留 | `/api/step1/generate`、schema 驱动、子场景定义。锚定信息直接进 IR 的 `anchors` 与 `skill_meta` |
| 改动 | 产物从「必须生成 Excel 模板」改为「生成 `scenario_anchor_*.json`（锚定配置）+ 可选 Excel 模板」。锚定 JSON 是 Step2 的直接输入 |
| 新增 | **知识库预检**：场景创建时调用 KB 检索同域已发布知识（见 §5.4 集成点 A），返回「可继承条目清单」，专家勾选后作为 Step2 的种子条目（`origin=kb_import`）注入 IR |
| step_data | 新增 `step1_anchor_file`；保留现有键 |

### Step 2 知识萃取 —— 直接产出 Skill 草稿 v1

| 项 | 内容 |
|---|---|
| 输入 | 锚定 JSON + 多文件/文本/案例复盘（全沿用现有 `/api/step2/extract` 的多源入口与 `content_type=case_review`）+ KB 继承条目 |
| 处理 | 1) 复用现有并行 LLM 抽取（最多 4 worker）与 `_parse_extracted_items` 六层降级 → 得到 records；2) 复用 `knowledge_fusion.merge_extraction_results` 做多源融合（KB 继承条目**作为一个源参与融合**，天然实现「新萃取 vs 已沉淀」去重）；3) **新增**：`skill_ir.new_draft()` 组装 IR v1 + `render_skill_md()` 渲染预览 |
| 萃取 prompt 改造 | 现有 prompt 输出的 JSON 字段已对齐列名，只需小改：要求 LLM 按「子场景 → 分类」归位、补充 `entry_id` 暂占位（程序统一重编号 KN-xxx）。**不要让 LLM 直接写 markdown**，仍然输出条目 JSON |
| 输出 | `skill_draft_*_v1_*.json`（主产物）+ `SKILL_draft_*.md`（预览）+ 沿用 `signal_report_*.json` |
| step_data 变更 | 新增 `step2_draft_file`、`step2_draft_url`、`step2_draft_md_file`、`step2_draft_md_url`、`step2_draft_version`；`step2_output_file`（preextract Excel）改为可选兼容产物，过渡期保留 |
| 改动文件 | `app_server.py` 的 `step2_extract_unified`（约 5218 行起）：抽取/融合逻辑不动，落盘段替换；`step2_preextract.py` 降级为可选 Excel 导出 |

### Step 3 知识对齐 —— 专家在 Skill 草稿上裁决，产出修订版 vN

这是改造最重的一步，但**交互协议可以整体平移**：现有 5 条路径（预览/对话/采纳/一键/直通）全部保留，只是修订动作的寻址从 Excel 单元格 `{sheet,row,col}` 换成 IR `{entry_id, field}`。

| 现有端点 | 重构后行为 |
|---|---|
| `/api/step3/align_preview` | LLM 把专家意见解析为修订 JSON：`[{entry_id, field, action: modify\|delete\|add\|supplement, old_value, new_value, note}]`。解析 prompt 中提供的上下文从 Excel 行文本换成 IR 条目文本（`ir_to_records`），prompt 主体可复用 |
| `/api/step3/align_chat` | 多轮累积意见，逻辑不变 |
| `/api/step3/apply_notes` | 专家勾选建议子集 → `skill_ir.apply_revisions()` 产出 vN+1 → 重渲染 md 预览。隐性注释卡片照旧写 `step3_tacit_annotations`，同时回填对应条目的 L2 字段 |
| `/api/step3/finalize` | 一键应用全部解析结果 → vN+1，`status=aligned` |
| `/api/step3/confirm_as_is` | 无意见直通：v1 直接标记 `status=aligned`（`_should_pass_through_preextract` 话术判断保留） |
| `/api/step3/interview/start` + `/convert` | 访谈三法（案例反推/对比追问/极限假设）不变；`interview_answers_to_records` 的产物改为对目标条目的 `supplement` 修订（回填经验判断/适用边界/例外情形），而非追加独立 Excel 行 |
| **新增** `/api/step3/suggestions` (GET) | 统一的「待裁决建议池」：聚合 ①LLM 解析的专家意见 ②Step5 验证回流建议 ③融合信号（冲突/重复 flags）。前端一个界面裁决所有来源的建议 |

| 项 | 内容 |
|---|---|
| 输出 | `skill_draft_*_vN_*.json`（`status=aligned`）+ 渲染 md。**`final_*.xlsx` 不再是主产物** |
| step_data 变更 | 新增 `step3_aligned_file`、`step3_aligned_url`、`step3_aligned_version`、`step3_pending_suggestions`；旧键过渡期保留 |
| 前端改动 | `app.js` Step3 区域：从 Excel 预览改为「条目卡片列表（按子场景/分类分组，含修订历史角标）+ SKILL.md 实时预览 + 建议池侧栏」。`revision_processor.py` 的颜色语义（黄改/红删/绿增/蓝补）平移为卡片角标颜色 |
| 暂缓 | Excel 双向投影编辑（Luckysheet）放到 Phase 5 之后按需做 |

### Step 4 智能转化 —— 按需生成，全部确定性优先

| 项 | 内容 |
|---|---|
| 输入 | `status=aligned` 的最新 IR（替代 `resolve_knowledge_workbook_path` 的 Excel 解析；该函数改为 `resolve_knowledge_ir_path`，候选键顺序：`step3_aligned_file` → `step2_draft_file`(smoke)） |
| 处理 | `/api/step4/compile` 主路径：`ir_to_records()` → 现有 `knowledge_delivery.excel_to_delivery_bundle` 拆成 `records_to_delivery_bundle`（它内部本来就是 records 驱动，只需把 Excel 读取段剥离）。`formats=skill,cot,qa` 按需勾选不变 |
| SKILL 终版 | `render_skill_md(ir)` + `status=published` + 版本号写入 frontmatter；OpenClaw/Hermes manifest 照旧 |
| 质量评分 | `/api/step4/quality`：`quality_report.py` 数据源换成 `ir_to_records()`，五维规则与 `tacit_ratio` 等展示指标全保留 |
| LLM 旁路 | `generate-cot` / `generate-qa` / `generate-executable-skill` 保留为增强选项，输入同样切到 IR |
| step_data | 键名不变（`step4_skill_file` 等），新增 `step4_published_version` |
| **发布入库** | compile 成功且质量分 ≥ `skill_score_threshold`(75) 时，提示专家「发布到知识库」→ 条目级写入 KB（见 §5.4 集成点 B） |

### Step 5 验证（新增步骤）—— 回放 + 回流

| 项 | 内容 |
|---|---|
| 定位 | 流水线第 5 步（UI 新增 tab），也可在 Step4 后自动触发一次冒烟回放 |
| 输入 | ①Step4 渲染的 **SKILL.md 终版文本**（注意：现状 `validation_replay.py` 用的是 Excel 知识文本，必须改为验证最终交付物本身）②测试案例集：上传 / 从 KB 案例库选取（§5.2 `kb_cases`）/ 从 `golden_db.py` 场景种子取 |
| 处理 | 1) 复用 `build_validation_prompt` + `compare_predictions`（命中率、分歧清单、`referenced_rules`）；2) **判官模型与萃取模型分离**：回放调用允许指定独立 model（`llm-config.yaml` 增加 `judge_model` 配置），避免同模型自评偏置；3) **新增** `validation_to_revisions(mismatches, ir)`：对每条分歧，定位 `referenced_rules` 对应的 `entry_id`，由 LLM 生成结构化修订建议（与 Step3 修订 JSON 同协议，`by=validation`），写入 `revision_suggestions_*.json`；4) `golden_db.verify` 包一层 HTTP API（`/api/step5/golden_verify`），P/R/F1 写入 `verification_runs` 表 |
| 回流 | 修订建议推入 Step3 建议池（`step3_pending_suggestions`），前端在 Step3 显示「来自验证的 N 条建议」。专家裁决采纳后产出新版 IR → 可重新 compile → 重新验证，形成 **对齐↔验证小循环** |
| 输出 | `validation_replay_*.md`（报告，沿用）+ `validation_result_*.json`（结构化结果）+ `revision_suggestions_*.json` |
| step_data | 新增第 5 步键组：`step5_replay_file`、`step5_replay_url`、`step5_result_file`、`step5_hit_rate`、`step5_suggestions_file`、`step5_case_source`、`step5_run_id` |
| 新端点 | `POST /api/step5/replay`（改造现有 `/api/validate/replay`，旧路由保留转发）、`POST /api/step5/golden_verify`、`POST /api/step5/feedback`（建议推入 Step3） |
| 验收口径 | 命中率 ≥ 阈值（建议配置在 schema `quality` 段，如 `replay_hit_threshold: 0.8`）才允许标记 `published`；不达标强制走回流 |

---

## 4. 同步契约变更清单（必须三处同步，否则数据静默丢失）

> 这是本项目的已知风险（见 `CLAUDE.md`），重构时**每个 Phase 收尾必须核对**。

### 4.1 `backend/pipeline_artifacts.py`

- `STEP_OUTPUT_KEYS_BY_STEP`：
  - `2:` 增 `step2_draft_file/url/md_file/md_url/version`
  - `3:` 增 `step3_aligned_file/url/version`、`step3_pending_suggestions`
  - `4:` 增 `step4_published_version`
  - **新增 `5:` 键组**（§3 Step5 表）
- `DOWNLOAD_ALLOWED_PREFIXES`：增 `skill_draft_`、`validation_`、`revision_suggestions_`、`scenario_anchor_`、`kb_`
- 新增 `is_skill_draft_filename()` / `is_aligned_draft_filename()` 校验；`validate_step_data_patch` 增加对应检查
- `resolve_knowledge_workbook_path` → 新增 `resolve_knowledge_ir_path`（旧函数过渡期保留）
- **注意**：`auxiliary_step_data_keys()` 中 `range(from_step, 5)` 必须改为 `range(from_step, 6)`，`keys_to_clear_from_step` 才能正确清理第 5 步；rollback 端点 `/api/pipelines/<id>/rollback/<int:step>` 的 step 上界同步放宽

### 4.2 `frontend/js/state.js` 与 `frontend/js/app.js`

- 两处 `DOWNSTREAM_OUTPUT_KEYS` 与后端新键组完全同步
- 两处 step 过滤器（`2:/3:/4:`）增加 `5:` 分支
- `PipelineState` 步骤总数 4 → 5；步骤切换、进度条、rollback 确认文案同步

### 4.3 渲染/解析共用

- `field_aliases.py`：若 IR 引入新字段名，别名表同步
- `config/scenario-schema.yaml`：`quality` 段增加 `replay_hit_threshold`；`compilation` 段增加 `ir_version`

---

## 5. 外部知识库设计

### 5.1 定位：四个角色，一个库

| 角色 | 服务对象 | 说明 |
|---|---|---|
| **知识资产层** | Step1 预检 / Step2 融合 / Step4 发布 | 跨流水线沉淀的条目级知识，带版本与生命周期 |
| **案例库** | Step5 验证 / Step2 案例复盘 / 访谈素材 | 历史案例 + 专家结论，是验证闭环的弹药库 |
| **发布登记处** | Step4 | 每个 published SKILL 的版本、IR 快照、质量分、验证成绩 |
| **检索底座** | Step2 去重 / 未来 RAG | 第一期 LLM 相似度判断，接口预留向量化 |

### 5.2 数据模型（新文件 `backend/knowledge_base.py`，SQLite：`data/kb/knowledge_base.db`）

```sql
-- 知识条目（资产主表）
CREATE TABLE kb_entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entry_uid TEXT UNIQUE NOT NULL,          -- 全局编号 KB-{domain}-{seq}
  domain TEXT NOT NULL,                    -- bank_credit 等
  scenario TEXT, sub_scenario TEXT,
  category TEXT,                           -- 判断规则/操作流程/反模式
  fields_json TEXT NOT NULL,               -- 与 IR entries[].fields 同构
  status TEXT DEFAULT 'active',            -- active | deprecated | superseded
  version INTEGER DEFAULT 1,
  superseded_by TEXT,                      -- 指向新版本 entry_uid
  confidence TEXT, evidence_count INTEGER DEFAULT 0,
  contributed_by TEXT,                     -- 贡献专家（多人逗号分隔，过渡方案）
  source_pipeline_id TEXT, source_skill_slug TEXT,
  created_at TEXT, updated_at TEXT, deprecated_at TEXT
);

-- 条目变更史（版本演化与审计）
CREATE TABLE kb_entry_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entry_uid TEXT NOT NULL,
  version INTEGER NOT NULL,
  change_type TEXT,                        -- create|update|deprecate|supersede
  fields_json TEXT, changed_by TEXT, change_note TEXT, changed_at TEXT
);

-- 案例库（验证弹药 + 萃取素材）
CREATE TABLE kb_cases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  case_uid TEXT UNIQUE NOT NULL,
  domain TEXT, scenario TEXT,
  description TEXT NOT NULL,
  facts_json TEXT,                         -- 结构化案情字段
  expert_conclusion TEXT NOT NULL,         -- 通过|拒绝|条件通过|...
  expert_reasoning TEXT,                   -- 专家推理（出声思维记录沉淀于此）
  difficulty TEXT,                         -- easy|hard|edge（极端/破例案例标记）
  tags TEXT, source TEXT, created_at TEXT
);

-- Skill 发布登记
CREATE TABLE kb_skill_releases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  skill_slug TEXT NOT NULL, version INTEGER NOT NULL,
  pipeline_id TEXT, ir_snapshot_json TEXT NOT NULL,
  skill_md TEXT NOT NULL,
  quality_score REAL, replay_hit_rate REAL,
  entry_uids TEXT,                         -- 本版包含的 KB 条目清单
  released_at TEXT, released_by TEXT,
  UNIQUE(skill_slug, version)
);

-- 验证运行记录（与 golden_db.verification_runs 并存，这里记回放）
CREATE TABLE kb_validation_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pipeline_id TEXT, skill_slug TEXT, skill_version INTEGER,
  case_uids TEXT, total_cases INTEGER, hits INTEGER, hit_rate REAL,
  mismatches_json TEXT, judge_model TEXT, ran_at TEXT
);
```

设计说明：

- **条目生命周期**：`active → superseded`（被新版替代，`superseded_by` 链）/ `deprecated`（政策失效）。「保鲜审计」`knowledge-freshness-audit` 的审计对象从 golden DB 切到 `kb_entries`，过期建议直接生成 `deprecate` 操作单
- **与 golden_db 的关系**：golden 库定位不变 —— 人工精标的**基准答案**（考卷），KB 是**生产资产**（教材）。`golden_db.verify` 衡量「萃取像不像基准」，`kb_validation_runs` 衡量「Skill 判得对不对」，两者互补不合并
- **多专家协同的演进余量**：`contributed_by` 先用文本字段；后续做多专家裁决时加 `kb_entry_votes` 表即可，主表不用动

### 5.3 模块与 API

`backend/knowledge_base.py`（参照 `golden_db.py` 的风格：建表 + 种子 + CLI + 纯函数）：

```
init_db / get_db
publish_entries(ir, pipeline_id, by) -> [entry_uid]     # Step4 发布：IR 条目 → kb_entries（含 supersede 判断）
search_entries(domain, scenario, query, top_k)          # 检索（第一期：分类过滤 + LLM 相似度重排）
import_entries_as_records(entry_uids) -> records        # Step1/2 继承：KB 条目 → IR 种子条目
deprecate_entry(entry_uid, note, by)
add_case / list_cases(domain, scenario, difficulty)
record_validation_run(...)
get_entry_timeline(entry_uid)                           # 演化史
```

HTTP 层（`app_server.py` 新增，全部走 `safe_workspace_path` 之外的独立 KB 路径，注意路径穿越规则不适用 DB 但适用任何文件导入导出）：

```
GET  /api/kb/entries?domain=&scenario=&q=      # 检索/浏览
POST /api/kb/entries/import                    # 选中条目注入当前流水线（返回 records）
POST /api/kb/publish                           # Step4 发布（带 supersede 预检报告）
POST /api/kb/entries/<uid>/deprecate
GET  /api/kb/cases?domain=&difficulty=
POST /api/kb/cases                             # 录入案例（含批量上传 xlsx/json）
GET  /api/kb/skills                            # 发布版本列表
GET  /api/kb/entries/<uid>/timeline
```

### 5.4 与流水线的四个集成点

| 集成点 | 时机 | 行为 |
|---|---|---|
| **A. 继承预检** | Step1 场景创建后 | `search_entries(domain, scenario)` → 前端展示「知识库已有 N 条相关知识」→ 勾选继承 → 作为 Step2 的一个融合源（`origin=kb_import`，融合时与新萃取去重，专家在 Step3 看到「KB 已有 vs 新萃取」的对比信号） |
| **B. 发布入库** | Step4 compile 且质量分+命中率达标 | `publish_entries(ir)`：逐条比对 KB（`entry_uid` 关联或语义匹配）→ 新条目 create / 既有条目 supersede（旧版标 `superseded_by`）→ 登记 `kb_skill_releases` |
| **C. 验证取材** | Step5 | 案例集默认从 `kb_cases` 按 domain+scenario 抽取（优先 `difficulty=hard/edge`），上传的新案例验证后问询「沉淀入案例库？」 |
| **D. 保鲜回流** | 定期/手动 | freshness audit 扫 `kb_entries`，过期条目生成 deprecate 单；被 deprecate 的条目若仍存在于某 active SKILL 的最新发布版中，提示对应流水线重走 Step3 |

### 5.4.1 建设顺序建议（知识库本身）

1. 先建 **案例库 `kb_cases`**——它是验证闭环（P0）的直接依赖，且录入成本低（历史案例+结论）
2. 再建 **发布登记 `kb_skill_releases` + `kb_entries`**——打通 Step4 发布
3. 最后做 **继承预检与检索重排**——依赖条目积累到一定量才有价值

---

## 6. 实施阶段划分（Phase 0–6）

每个 Phase 独立可交付、可回退；**每个 Phase 收尾跑一遍同步契约核对（§4）+ `backend/tests/test_*.py` + ship-check 静态关卡**。

### Phase 0：Skill IR 基建（不动现有流水线）

- 新增 `backend/skill_ir.py`（§2.3 全部函数）+ 单元测试（IR 校验、apply_revisions 版本单调、render 幂等）
- 从 `excel_to_skill.py` 提取渲染主体为 records 驱动的纯函数（`generate_skill_md` 已基本是，剥离 Excel 读取段）
- `knowledge_delivery.py`：`excel_to_delivery_bundle` 拆出 `records_to_delivery_bundle`
- `quality_report.py`：数据入口增加 records/IR 适配
- 验收：用 `data/samples/step2-*` 现成样例数据构造 IR → 渲染 md → 质量评分，全链路纯函数跑通

### Phase 1：Step2 产出 Skill 草稿

- `step2_extract_unified` 落盘段接 `skill_ir.new_draft`；prompt 微调（子场景归位）
- `pipeline_artifacts.py` + `state.js` + `app.js` 三处同步新增 step2 草稿键
- 前端 Step2 结果区：渲染 md 预览 + 条目计数；保留 Excel 导出按钮（兼容）
- 验收：上传 `data/samples/step2-文档萃取` 样例 → 得到 `skill_draft_*_v1.json` + 预览；多源融合信号报告正常

### Phase 2：Step3 对齐切换到 IR

- 5 条对齐路径逐一切换寻址协议（§3 Step3 表）；`revision_processor.py` 的 action 语义平移到 `apply_revisions`
- 访谈 convert 改为 supplement 修订
- 前端条目卡片 + 建议池界面（这是前端工作量最大的部分）
- 验收：专家意见 →预览→选择性采纳→ v2 草稿；修订历史可见；直通路径可用；回滚到 Step2 后键清理干净

### Phase 3：Step4 按需转化 + IR 输入

- `resolve_knowledge_ir_path`；compile/quality/LLM 旁路全部切 IR
- 验收：`formats=skill,cot,qa` 任意组合；质量报告分数与旧 Excel 路径同口径（拿同一份样例双跑对比）

### Phase 4：Step5 验证环节 + 回流（核心增量）

- `/api/step5/replay`（验 SKILL.md 终版文本）+ `judge_model` 配置 + `validation_to_revisions` + `/api/step5/feedback`
- `golden_db.verify` API 化，写 `verification_runs`
- 流水线扩到 5 步：`STEP_OUTPUT_KEYS_BY_STEP[5]`、`auxiliary_step_data_keys` 改 `range(from_step, 6)`、前端第 5 步 tab、rollback 上界
- 验收：构造 10 个带结论的案例 → 回放 → 命中率报告 → 分歧生成建议出现在 Step3 建议池 → 采纳 → v+1 → 重 compile → 重验证，小循环走通

### Phase 5：外部知识库

- `backend/knowledge_base.py` + 建表 + CLI + §5.3 API
- 按 §5.4.1 顺序：案例库 → 发布登记/条目 → 继承预检
- Step5 案例选取接 `kb_cases`；Step4 接发布；Step1 接预检
- 验收：流水线 A 发布 → 流水线 B（同场景）创建时可见可继承；案例沉淀后供第二条流水线验证使用

### Phase 6：收尾与下线旧路径

- 旧 Excel 主路径（preextract/final）标记 deprecated，保留只读下载
- `docs/业务说明文档.md`、`CLAUDE.md`（step data key 契约、关键文件表、流水线描述 4 步→5 步）、`data/samples/` 样例同步更新
- 决定是否做 Luckysheet ⇄ IR 双向投影（视专家实际反馈）

依赖关系：`0 → 1 → 2 → 3 → 4`，Phase 5 中案例库部分可与 Phase 2–3 并行（验证环节 Phase 4 依赖案例库最小版本）。

---

## 7. 风险与规避

| 风险 | 说明 | 规避 |
|---|---|---|
| **LLM 直接产 IR 的结构失控** | 萃取 JSON 不可信是已知风险 | 继续走 `_parse_extracted_items` 六层降级 → records → 程序组装 IR；LLM 永远不直接产 IR 整体 |
| **同模型自评偏置** | Step5 判官 = Step2 萃取模型时命中率虚高 | `judge_model` 独立配置；报告中显式标注判官模型；条件允许时换不同厂商模型 |
| **回流建议轰炸专家** | 验证分歧 + 融合信号 + 意见解析三路建议挤压 Step3 | 建议池分来源分组 + 按置信度排序 + 支持批量驳回；每轮回放限制建议条数上限 |
| **版本链断裂** | IR 多版本 + rollback 交错可能产生孤儿版本 | `validate_ir` 强校验 `parent_version` 链；rollback 时按 §4.1 清理键并删除 dangling 草稿文件 |
| **KB 条目重复膨胀** | 发布时语义匹配不准导致同义条目堆积 | 发布前强制 supersede 预检报告（人审）；定期跑 KB 内部去重审计（复用 `detect_duplicates`，后续升级语义） |
| **Excel 习惯迁移成本** | 专家习惯了表格 | Phase 1–4 全程保留 Excel 只读导出；卡片界面按表格列序呈现字段；双向投影留作后手 |
| **路径/安全** | 新文件前缀与下载白名单 | 所有新前缀进 `DOWNLOAD_ALLOWED_PREFIXES`；KB 文件导入导出一律 `safe_workspace_path`；`validate_step_data_patch` 同步新校验 |
| **MergedCell 等 Excel 坑** | 仅残留在可选导出路径 | 导出函数复用现有解除合并逻辑，不新写 |

---

## 8. 现有资产处置清单

| 资产 | 处置 |
|---|---|
| `step2_extract_unified` 多源抽取/并行/降级解析 | **保留**（落盘段改造） |
| `knowledge_fusion.py` 全部信号检测 | **保留**（输出进 IR flags/signals） |
| `interview_session.py` 三法 | **保留**（convert 目标改 IR supplement） |
| `excel_to_skill.py` 渲染逻辑 | **改造**为 IR 渲染器（Phase 0） |
| `knowledge_delivery.py` COT/QA | **保留**（入口换 records） |
| `quality_report.py` 五维 | **保留**（数据源适配） |
| `revision_processor.py` | **语义平移**到 `apply_revisions`；Excel 落盘部分仅服务可选导出 |
| `validation_replay.py` | **升级**：验证对象换 SKILL 终版 + 新增 `validation_to_revisions` |
| `golden_db.py` | **保留** + verify API 化；定位「基准考卷」不变 |
| `step2_preextract.py` / `step1_template.py` | **降级**为可选 Excel 导出 |
| `pipelines.json` 状态机 / rollback | **扩展**到 5 步 |
| Luckysheet 在线编辑 | **暂缓**，Phase 6 视需求决定 |

---

## 9. 落地时的执行纪律（给 /dev 的提醒)

1. 每个 Phase 一个独立分支/PR，合入前过 ship-check（路由冲突、step key 三处同步、API 前后端同步）
2. 改 `STEP_OUTPUT_KEYS_BY_STEP` 的同一个提交里必须同时改 `state.js` 和 `app.js`，不允许拆开
3. Flask 新路由先 `rg '@app.route' | grep <path>` 防重复定义覆盖
4. 涉及数据契约的 Phase（1/2/4/5）合入前过一次 data-guardian 检查
5. Phase 3 完成后做一次新旧双跑对比（同一样例 Excel 路径 vs IR 路径的质量分、SKILL 内容 diff），确认无回归再进 Phase 4

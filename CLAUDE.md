# 隐性知识显性化 — Claude Code 项目指南

## 将此模板用于新项目

所有 workflow 脚本（`.claude/workflows/*.js`）已通用化改造。迁移到新项目只需：

1. 复制本项目的 `.claude/` 目录到新项目根目录（含 commands/ + workflows/ + settings）
2. 修改 `CLAUDE.md`：写新项目的定位、技术栈、关键文件、风险规则、同步契约
3. 修改 `.claude/settings.json`：更新 `skills` 模型分配和 `dataGuardianTriggers`
4. 修改 `.claude/workflows-config.json`：更新 `project`、`tech`、`consistency`、`riskRules` 等字段
5. 各 workflow 脚本的 `CFG` 块和 commands/*.md 的方法论主体**无需改动**

## Quick Start
```bash
cd backend && python app_server.py --host 127.0.0.1 --port 5000 &
```
浏览器访问 `http://127.0.0.1:5000`

## 项目定位
将银行信贷专家的隐性经验 → 结构化、可交付的 AI Skill，通过 4 步流水线（场景锚定→知识萃取→知识对齐→智能转化）。

## 技术栈
- **后端**: Python Flask (5100+ lines in app_server.py), openpyxl, PyPDF2
- **前端**: Vanilla JS (无框架), Luckysheet (在线 Excel 编辑)
- **存储**: 文件工作空间 (无数据库), 流水线 JSON 持久化
- **LLM**: OpenAI 兼容 / 建行 CCB 网关双模式

## 关键文件
| 文件 | 职责 |
|------|------|
| `backend/app_server.py` | Flask 主服务 (路由, Skill 执行器, LLM 解析, 多源萃取路由) |
| `backend/pipeline_artifacts.py` | 文件命名约束, step data key 定义 |
| `backend/knowledge_fusion.py` | 多源知识融合（去重/冲突检测/跨源合并/访谈转换） |
| `backend/interview_session.py` | 专家访谈追问生成（案例反推/对比追问/极限假设） |
| `backend/step2_preextract.py` | 知识萃取 Excel 生成 |
| `backend/revision_processor.py` | 知识修订处理器 |
| `backend/knowledge_delivery.py` | 智能转化 (SKILL.md/QA/COT 生成) |
| `backend/quality_report.py` | 五维质量评分 |
| `frontend/js/app.js` | 主逻辑 (流水线 CRUD, 步骤切换, Skill 执行, 多源融合 UI) |
| `frontend/js/state.js` | 全局状态管理器 (PipelineState 类) |
| `config/scenario-schema.yaml` | 场景知识结构定义 |

## 天工 Agent 团队（10 人）—— 完整开发流程

```
                  orchestrator（总调度 · 指挥层）
                        ↓ 委派 / 跟踪 / 裁决
规划      实现      审查          测试     验证       通关          文档
plan  →  dev  →  cr →  test  →  vr  →  ship-check  →  doc

bug-hunt ───── 定期全量缺陷巡检（独立触发，不在主线）
data-guardian ─ 数据契约 / 状态完整性专项守护（涉及数据变更时介入）

※ 修复回路：test / cr / bug-hunt / ship-check / vr 发现的所有问题，
  统一交 /dev 落地修复 —— dev 是团队唯一编码者。
```

> 团队代号「天工」，取自「天工开物」—— 各司其职，把隐性经验开出来。
> 两套实现：`~/.claude/commands/*.md`（角色 prompt，当前生效）与 `项目/.claude/workflows/*.js`（编排引擎，带真并行 / 交叉验证 / 模型分配；当前 harness 不加载，作可迁移参考）。

### `/orchestrator` — 总调度（指挥层）
理解高层需求 → 决定调哪些角色、按什么顺序 → 逐个委派并传递精确上下文 → 收产出、驱动修复回路 → 跟踪到完成并汇总。不亲自写码/审查/测试。与 plan 分工：plan 是技术参谋（怎么做），orchestrator 是总指挥（谁做、按什么顺序、驱动跑完）。
用法：`/orchestrator <高层需求>`

### `/plan` — 规划师（需求分析 + 工作计划）
侦察代码库 + 识别风险 + 输出结构化实施计划（影响文件、实施步骤、依赖关系、规避措施）。只分析不写码。
用法：`/plan <需求描述>`

### `/dev` — 开发者（唯一编码者）
接收需求或计划，并行实现后端/前端变更，自动处理 step data key 同步等跨层协调，执行自检。**所有代码变更收口于此**，也承接其他角色报告的问题修复。
用法：`/dev <需求>`

### `/cr` — 审查员（diff 审查 + 安全审查 + 简化建议）
正确性 bug + 安全漏洞 + 简化/可复用性，三大维度排查 + 对抗式交叉验证降假阳性。默认只输出修复方案交 `/dev` 落地；`--fix` 时作为 `/dev` 代理直接应用（唯一编码者原则下的唯一代写例外），`--comment` 发布为 PR 行级评论。
> 已合并原 `/review-changes` 的安全审查维度，不再有独立 review-changes。真多模型并行仍由 `.js` 引擎提供。

### `/bug-hunt` — 缺陷猎人（全量代码扫描）
多维度扫描全库（逻辑/安全/资源/类型）+ 交叉验证后输出优先级排序的缺陷清单。
与 cr 互补：cr 只查 diff，bug-hunt 查全库。问题交 `/dev` 修复。
用法：`/bug-hunt [scope=all|backend|frontend]`

### `/data-guardian` — 数据守护（数据契约 / 状态完整性）
专职守护数据契约一致性（前后端字段/类型对齐）、状态持久化对称性（存取/切换不丢）、关键标识符跨层同步、schema 迁移兼容。代码缺陷归 cr/bug-hunt，数据契约归它。问题交 `/dev` 修复。
用法：`/data-guardian <变更范围或数据层>`

### `/test` — 测试工程师（测试生成）
分析变更代码，自动生成/追加测试脚本（单元/集成/不变量），运行验证结果。失败交 `/dev` 修复。
用法：`/test <需求或范围>`

### `/vr` — 运行验证官（端到端动态验证）
真正启动应用、走一遍受影响的核心用户路径、观察实际运行行为。补 ship-check（静态）与 test（单元）都抓不到的运行时问题（如某步实际报错、LLM 调用降级）。
用法：`/vr <受影响的路径或变更>`

### `/ship-check` — 通关检查官（提交前静态通关）
Python 语法检查 + Flask 路由冲突检测 + JS 一致性 + 前/后端 API 路由同步 + step data key 同步 + CSS 引用同步 + 运行现有单元测试。提交前的最后一道**静态**关卡，必须通过。
> 已合并原 `/consistency-check` 的跨层一致性校验，不再有独立 consistency-check。动态运行验证交 `/vr`。

### `/doc` — 文档维护（文档同步）
对比文档声明与代码事实，标记过时/遗漏内容，支持自动修复。
用法：`/doc [自动检查|同步]`

## 严重度分级（全团队统一）
critical（阻塞合入）/ high（应尽快修）/ medium（建议）/ low（可选）

## step data key 一致性规则
以下三处必须保持同步，否则会出现数据静默丢失：
- `backend/pipeline_artifacts.py` → `STEP_OUTPUT_KEYS_BY_STEP`
- `frontend/js/state.js` → `DOWNSTREAM_OUTPUT_KEYS`
- `frontend/js/app.js` → `DOWNSTREAM_OUTPUT_KEYS`

## 已知风险点
- **路径穿越**: 所有文件访问必须经过 `safe_workspace_path()` / `basename_only()`
- **MergedCell**: openpyxl 写入合并单元格会抛异常，必须在写前解除合并
- **JSON 解析**: LLM 输出不可信，`_parse_extracted_items()` 有 6 层降级
- **innerHTML**: 前端多处使用，需确保内容经过 `escapeHtml()`
- **路由重复**: Flask 不检查重复路由，第二个定义会覆盖第一个
- **多源融合**: `knowledge_fusion.py` 的去重基于词重叠率，可能漏掉语义重复但用词不同的条目；冲突检测仅基于分类内关键词对比，不覆盖跨分类冲突
- **访谈执行**: `execute_interview_session` 需要 LLM 调用，如果 LLM 不可用则整个追问失败；生成的追问质量依赖 prompt 设计
- **融合性能**: multi_source_extract 对每个文件依次调用 LLM，N 个文件会产生 N 次 LLM 调用，注意 token 消耗

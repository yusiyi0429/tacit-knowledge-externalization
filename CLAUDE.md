# 隐性知识提取平台

将领域专家的隐性经验 → 结构化、可交付的 AI Skill，通过 **5 步流水线**（场景锚定→知识萃取→知识对齐→智能转化→验证回放），验证分歧回流第 3 步形成闭环。

## 快速启动

```bash
# 1. 安装依赖
cd backend && pip install -r requirements.txt

# 2. 启动服务
python app_server.py --host 127.0.0.1 --port 5000
# 访问 http://127.0.0.1:5000

# 3. LLM 配置（复制模板后编辑）
cp config/llm-config.local.yaml.example config/llm-config.local.yaml
# 编辑 config/llm-config.local.yaml 填入 API Key

# 4. 前端 vendor 初始化（首次运行或 Luckysheet 更新后）
cd ../frontend && npm install && npm run vendor
# 或：cd ../scripts && ./setup-frontend-vendor.sh

# 5. 运行测试
cd ../backend && python -m pytest scripts/ -v

# Docker 部署（内网）
docker load -i tacit-knowledge-externalization-*.tar
docker compose up -d  # 端口 5000
```

## 架构

```
┌─────────────────┐     HTTP/API     ┌──────────────────────────┐
│   前端 (Vanilla) │ ◄─────────────► │   后端 (Flask)           │
│  Luckysheet     │                 │  app_server.py (路由总线) │
│  index.html     │                 │  skill_ir.py (IR 引擎)   │
│  app.js/state.js│                 │  knowledge_base.py (KB)  │
└─────────────────┘                 │  validation_replay.py    │
                                    │  knowledge_delivery.py   │
                                    └──────────┬───────────────┘
                                               │
                         ┌─────────────────────┼─────────────────────┐
                         ▼                     ▼                     ▼
                    ┌─────────┐         ┌──────────┐          ┌──────────┐
                    │ data/kb │         │ data/golden         │ config/  │
                    │ SQLite  │         │ 黄金数据库          │ llm-config.yaml
                    └─────────┘         └──────────┘          └──────────┘
```

## 目录结构

```
backend/
  app_server.py           # Flask 主服务：路由总线、Skill 执行器、KB API
  skill_ir.py             # Skill IR 引擎：draft/apply_revisions/render_skill_md/版本校验
  pipeline_artifacts.py   # 流水线产物：文件命名、step data key、IR 解析
  knowledge_base.py       # 外部知识库：entries/案例库/发布登记/验证记录
  validation_replay.py    # Step5：决策回放 + 分歧→修订建议
  knowledge_fusion.py     # 多源知识融合：去重/冲突检测/跨源合并/访谈转换
  knowledge_delivery.py   # 智能转化：SKILL.md / QA / COT 生成
  interview_session.py    # 专家访谈追问生成（案例反推/对比追问/极限假设）
  revision_processor.py   # 知识修订处理器（Excel 编辑面）
  step2_preextract.py     # Step2：知识萃取 Excel 生成（过渡期兼容产物）
  quality_report.py       # 五维质量评分
  llm_client.py           # LLM 客户端：OpenAI 兼容 / 建行 CCB 网关双模式
  golden_db.py            # 黄金数据库管理
  shared.py               # 共享工具/配置/全局状态（所有路由导入）
  skill_registry.py       # Skill 注册表定义
  excel_to_skill.py       # Step 4：Excel→SKILL.md 确定性转换
  skill_generator.py      # Meta-skill：从 Step3 + golden DB 生成可执行 SKILL.md
  sandbox_db.py           # 沙盒数据库
  workbook_layout.py      # Excel 工作簿布局
  scripts/                # 测试脚本（test_*.py, e2e_*.py, validate_*.py）
frontend/
  index.html              # 单页应用入口
  js/app.js               # 主逻辑：流水线 CRUD、步骤切换、Skill 执行、Step5 回放 UI
  js/state.js             # 全局状态管理器 (PipelineState, MAX_STEP=5)
  js/utils.js             # 工具函数
  js/excel-luckysheet.js  # Luckysheet Excel 编辑器集成
  css/                    # 样式文件
  vendor/                 # Luckysheet 离线包（npm run vendor 生成）
  package.json            # 前端依赖（Luckysheet, jQuery）

scripts/（根目录）
  build.sh                # 构建脚本
  start.sh                # 启动脚本
  build-docker-*.sh       # Docker 构建（multiarch/arm64）
  setup-frontend-vendor.sh # 前端 vendor 包初始化
  copy-frontend-vendor.js # 复制 Luckysheet 到 vendor/
config/
  llm-config.yaml         # LLM 配置（模型列表、参数）
  llm-config.local.yaml   # 本地覆盖（含 API Key，gitignored）
  scenario-schema.yaml    # 场景知识结构定义（含 replay_hit_threshold）
data/
  kb/knowledge_base.db    # SQLite 知识库
  golden/                 # 黄金数据库文件
  result/                 # 流水线产出物
  samples/                # 样本数据
docs/
  重构实施方案-Skill中心化流水线.md
  PRODUCTION_AUDIT.md     # 生产审计报告
  VERSIONING.md           # 版本管理
  业务说明文档.md
docker/
  Dockerfile              # 构建镜像
  Dockerfile.incremental  # 增量构建
  deploy-run-example.sh   # 部署示例
docker-compose.yml        # 内网部署编排
```

## 关键文件索引

### 核心引擎（修改前必须理解）

| 文件 | 职责 | 修改风险 |
|------|------|----------|
| `backend/skill_ir.py` | Skill IR 单一事实源：draft/apply_revisions/render_skill_md/版本校验 | **critical** |
| `backend/pipeline_artifacts.py` | 文件命名约束、step data key 定义、IR 解析 | **critical** |
| `frontend/js/state.js` | 全局状态：PipelineState、MAX_STEP=5、DOWNSTREAM_OUTPUT_KEYS | **critical** |
| `backend/shared.py` | 共享工具/配置/全局状态，所有路由处理器导入 | **critical** |
| `backend/skill_registry.py` | Skill 注册表：知识萃取等 Skill 定义 | **critical** |

### 流水线步骤模块

| 步骤 | 文件 | 产出 |
|------|------|------|
| Step 1 场景锚定 | `backend/step1_*.py` (builder/schema/template) | 场景骨架 Excel |
| Step 2 知识萃取 | `backend/step2_preextract.py` + `knowledge_fusion.py` | 萃取条目 Excel / IR v1 |
| Step 3 知识对齐 | `backend/revision_processor.py` | 修订稿 IR vN |
| Step 4 智能转化 | `backend/knowledge_delivery.py` | SKILL.md / QA / COT |
| Step 4 增强 | `backend/excel_to_skill.py` | Excel→SKILL.md（确定性程序，不依赖模型） |
| Step 5 验证回放 | `backend/validation_replay.py` | 回放报告 + 修订建议 |

### 支持模块

| 文件 | 职责 |
|------|------|
| `backend/app_server.py` | Flask 路由总线（所有 API 入口） |
| `backend/shared.py` | 共享工具/配置/全局状态（从 app_server.py 拆分） |
| `backend/knowledge_base.py` | 知识库管理（entries/案例/发布/验证） |
| `backend/skill_registry.py` | Skill 注册表定义 |
| `backend/skill_generator.py` | Meta-skill：从 Step3 + golden DB 生成可执行 SKILL.md |
| `backend/interview_session.py` | 专家访谈追问生成 |
| `backend/quality_report.py` | 五维质量评分 |
| `backend/llm_client.py` | LLM 调用（OpenAI / CCB 双模式） |
| `backend/golden_db.py` | 黄金数据库 |
| `backend/sandbox_db.py` | 沙盒数据库 |
| `backend/workbook_layout.py` | Excel 工作簿布局 |
| `frontend/js/app.js` | 前端主逻辑（所有 UI 交互） |

## API 路由速查

后端路由定义在 `app_server.py` 中，Flask 不检查重复路由——**同名路由会静默覆盖**。

主要路由组：
- `/api/pipeline/*` — 流水线 CRUD
- `/api/step/*` — 各步骤执行
- `/api/skill/*` — Skill 执行与 IR 操作
- `/api/kb/*` — 知识库管理
- `/api/interview/*` — 专家访谈
- `/api/validate/*` — Step5 验证回放
- `/api/health` — 健康检查

## 天工 Agent 团队（10 人）

完整 prompt 见 `.claude/commands/*.md`，工作流编排见 `.claude/workflows/*.js`。

`.claude/` 结构：
```
.claude/
├── commands/            # 10 个 Agent prompt（*.md）
├── workflows/           # 工作流编排脚本（*.js）
├── workflows-config.json # 工作流配置
├── skills/              # 项目级 skill 安装目录
├── settings.json        # 项目级配置
└── settings.local.json  # 权限白名单
```

| 角色 | 职责 | 用法 |
|------|------|------|
| `/orchestrator` | 总调度：理解需求 → 委派角色 → 驱动修复回路 | `/orchestrator <高层需求>` |
| `/plan` | 规划师：需求分析 + 结构化实施计划 | `/plan <需求描述>` |
| `/dev` | **唯一编码者**：所有代码变更收口于此 | `/dev <需求>` |
| `/cr` | 审查员：diff 审查 + 安全审查 + 简化建议 | `/cr [--fix \|--comment]` |
| `/bug-hunt` | 缺陷猎人：全量代码扫描 | `/bug-hunt [scope]` |
| `/data-guardian` | 数据守护：数据契约 / 状态完整性 | `/data-guardian <变更范围>` |
| `/test` | 测试工程师：生成并运行测试 | `/test <需求或范围>` |
| `/vr` | 运行验证官：端到端动态验证 | `/vr <受影响的路径>` |
| `/ship-check` | 通关检查官：提交前静态通关 | `/ship-check` |
| `/doc` | 文档维护：文档同步检查 | `/doc [自动检查\|同步]` |

**修复回路**: test / cr / bug-hunt / ship-check / vr 发现的所有问题，统一交 `/dev` 落地修复。

## 项目级 Skill

`.claude/skills/tacit-to-skill/SKILL.md` — 引导领域专家通过 4 步流水线将隐性经验转化为 SKILL.md。触发词：知识萃取、经验沉淀、专家访谈、隐性知识显性化。

## 不变量与风险规则

### Skill IR 不变量

- LLM 永远不直接产 IR 整体；IR 由程序从 records 组装（`_parse_extracted_items` 六层降级之后）
- SKILL.md 永远由 `skill_ir.render_skill_md()` 确定性渲染，不允许反向手改 md 回填
- 修订寻址协议 `{entry_id, field, action, old_value, new_value, note, by}`；删除条目的 entry_id 不得被 add 复用
- 版本链：`parent_version < draft_version` 单调递增；`save_ir` 落盘前强制 `validate_ir`
- 验证回流建议只进 Step3 建议池（`step3_pending_suggestions`），绝不自动应用——裁决权在专家

### step data key 一致性（critical）

以下三处必须保持同步，否则数据静默丢失：
1. `backend/pipeline_artifacts.py` → `STEP_OUTPUT_KEYS_BY_STEP`
2. `frontend/js/state.js` → `DOWNSTREAM_OUTPUT_KEYS`
3. `frontend/js/app.js` → `DOWNSTREAM_OUTPUT_KEYS`

新增产物文件前缀必须同步进 `DOWNLOAD_ALLOWED_PREFIXES`（已含 `skill_draft_`、`validation_`、`revision_suggestions_`、`kb_`），否则下载 403。

### 已知风险点

| 风险 | 严重度 | 说明 |
|------|--------|------|
| 路径穿越 | critical | 所有文件访问必须经过 `safe_workspace_path()` / `basename_only()` |
| XSS | high | 前端 `innerHTML` 内容必须经 `escapeHtml()` 处理 |
| Flask 路由重复 | high | 同名函数/路由会静默覆盖 |
| MergedCell | high | openpyxl 写入合并单元格前必须先解除合并 |
| JSON 解析 | medium | LLM 输出不可信，`_parse_extracted_items()` 有 6 层降级 |
| 多源融合漏重 | medium | 去重基于词重叠率，语义重复但用词不同可能漏掉 |
| 判官偏置 | medium | Step5 回放的 `judge_model` 与萃取模型相同会导致命中率虚高 |
| KB supersede 误判 | low | 基于 bigram 重叠（阈值 0.7），语义相近但表述差异大的条目可能误判 |

## LLM 配置

`config/llm-config.yaml` 定义模型列表和参数，`config/llm-config.local.yaml`（gitignored）覆盖 API Key 和端点。

双模式：
- **OpenAI 兼容**: 标准 OpenAI API 格式
- **建行 CCB 网关**: 内网专有网关，需特殊鉴权

## 部署

### 开发环境
直接 `python app_server.py` 启动 Flask 开发服务器。

### Docker（内网）
```bash
# 构建
docker build -t tacit-knowledge-externalization:2.0.0-arm64 -f docker/Dockerfile .
# 或 ./scripts/build-docker-arm64.sh

# 运行
docker compose up -d
# 健康检查：http://127.0.0.1:5000/api/health
```

### 数据迁移
- `workspace/` 挂载为卷，持久化用户数据
- `logs/` 挂载为卷，持久化日志
- `config/llm-config.yaml` 以只读方式挂载

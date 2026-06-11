# 隐性知识显性化 · Skill 中心化五步流水线

将银行信贷专家的隐性经验（制度文件、案例复盘、会议纪要）转化为结构化、可复用、可审计的知识资产。

---

## 核心管线

```
场景锚定 → 知识萃取 → 知识对齐 → 智能转化 → 验证回放
  Step1      Step2       Step3       Step4       Step5
              │            ↑                       │
              │            └──── 分歧建议回流 ◄─────┘
              ↓
        外部知识库（继承 / 发布 / 案例库）
```

流水线主产物为 **Skill IR（结构化 JSON 草稿）**，SKILL.md 由 IR 确定性渲染；
Excel 工作簿保留为过渡期编辑面与兼容产物。

| 步骤 | 做什么 | 输入 | 输出 |
|------|--------|------|------|
| **Step1 场景锚定** | 定义知识结构，生成 Excel 骨架 | 场景名称、场景说明、子场景、知识列定义 | `template_*.xlsx` |
| **Step2 知识萃取** | 文档/案例 → **Skill 草稿 v1** | 制度文件 / 案例复盘 / 知识库继承 | `skill_draft_*_v1.json` + `preextract_*.xlsx` |
| **Step3 知识对齐** | 专家审核修订 + 建议池裁决 → 对齐版 vN | 专家意见 / 验证回流建议 / 访谈转化 | `skill_draft_*_vN.json`（aligned）+ `final_*.xlsx` |
| **Step4 智能转化** | 从 IR 确定性编译交付包 + 发布入库 | 对齐版 Skill IR | SKILL.md 终版 / QA对 / 思维链 / manifest |
| **Step5 验证回放** | SKILL 终版判历史案例，分歧回流 Step3 | 历史案例（上传 / 知识库） | 回放报告 / 命中率 / `revision_suggestions_*.json` |

---

## 5 个 AI Skill

| Skill | 步骤 | 能力 |
|-------|:---:|------|
| 🔍 **知识萃取** | Step2 | 文档→结构化知识；支持 📄文档模式 和 📋案例复盘模式 |
| 🔬 **跨案例模式发现** | Step2 | 多案例交叉分析，发现反复出现的隐性信号和系统性风险盲区 |
| 🎯 **知识盲区检测** | Step2 | 对比 Schema 与实际填充率，识别「应该知道但还不知道」的内容 |
| 📝 **知识对齐** | Step3 | 专家修订 + 隐性注释追问卡片（自动捕获修订背后的经验判断） |
| 🔄 **知识保鲜度审计** | Step4 | 审计知识时效性，检测被案例突破的规则和置信度衰减 |

---

## 验证闭环与外部知识库

- **决策回放**（`POST /api/step5/replay`）：用 SKILL 终版（或 IR 渲染）逐案判断历史案例，与专家结论比对命中率；**判官模型可独立指定**（`judge_model`），避免同模型自评偏置
- **分歧回流**（`POST /api/step5/feedback`）：分歧自动生成 entry 级修订建议 → 推入 Step3 建议池 → 专家裁决采纳 → IR v+1 → 重编译重验证，形成 **对齐 ↔ 验证小循环**
- **Golden 基准验证**（`POST /api/step5/golden_verify`）：流水线知识 vs 人工精标黄金条目（P/R/F1）
- **外部知识库**（`backend/knowledge_base.py`，SQLite）：
  - 知识资产层 `kb_entries`：条目级版本与生命周期（active / superseded / deprecated）
  - 案例库 `kb_cases`：历史案例 + 专家结论，是 Step5 的验证弹药
  - 发布登记 `kb_skill_releases` + 验证记录 `kb_validation_runs`
  - 集成点：Step2 勾选「继承知识库」参与融合去重；Step4 质量达标后一键发布；Step5 从案例库抽取验证集

---

## 快速启动

```bash
cd backend
pip install -r ../requirements.txt
python app_server.py --host 127.0.0.1 --port 5000
```

浏览器访问 `http://127.0.0.1:5000`

---

## 测试数据

`data/samples/` 按步骤组织，包含科技企业普惠贷款全流程测试数据。

[→ 测试数据使用指南](data/samples/README.md)

---

## 项目结构

```
├── backend/              # Flask API + 业务模块
│   ├── app_server.py     # 主服务（路由 + Skill 执行器）
│   ├── skill_ir.py       # Skill IR（流水线单一事实源：草稿/修订/渲染/版本）
│   ├── knowledge_base.py # 外部知识库（知识资产/案例库/发布登记，SQLite）
│   ├── validation_replay.py   # Step5 决策回放 + 分歧→修订建议
│   ├── llm_client.py     # LLM 调用适配（OpenAI / CCB 网关 + 重试）
│   ├── pipeline_artifacts.py  # 文件命名与安全策略 + step data key 契约
│   ├── step1_*.py        # 场景锚定模块
│   ├── step2_preextract.py    # 知识萃取 Excel 生成（过渡期兼容产物）
│   ├── revision_processor.py  # 知识修订处理器（Excel 编辑面）
│   ├── knowledge_delivery.py  # 智能转化（Skill/QA/COT，records 驱动）
│   └── scripts/          # 测试脚本（含 e2e_ir_pipeline_test.py）
├── frontend/             # 前端（Vanilla JS + Luckysheet）
│   ├── js/
│   │   ├── state.js      # 流水线状态管理器
│   │   ├── utils.js      # 公共工具函数
│   │   ├── app.js        # 主逻辑
│   │   └── excel-luckysheet.js  # Excel 在线编辑器
│   └── vendor/           # 离线静态资源（内网部署）
├── config/               # LLM 配置 + 场景 Schema
├── data/samples/         # 测试数据（按 Step 组织）
└── docker/               # Docker 构建文件
```

---

## LLM 模型配置

支持两种 `api_type`：

| api_type | 说明 |
|----------|------|
| `openai`（默认） | OpenAI 兼容 `/v1/chat/completions`，Bearer 鉴权 |
| `ccb_ainlplm` | 建行内部网关，需配置 `tx_code`、`sec_node_no` |

配置文件：`config/llm-config.yaml`，密钥写入 `config/llm-config.local.yaml`（已 gitignore）。

---

## Docker（ARM64）

```powershell
.\scripts\build-docker-arm64.ps1
```

生成 `tacit-knowledge-externalization-arm64.tar`，详见 [docker/README.md](docker/README.md)。

# 2026-06-13 Kimi 迁移工作进度

## 今日完成项

### 1. 工作空间切换与规范建立

- 确认 Kimi 当前工作空间：`/mnt/d/my-workspace`（对应 Windows `D:\my-workspace`）
- 创建根目录 `AGENTS.md`：将原 `CLAUDE.md` 适配为 Kimi Code CLI 工作空间指南
- 创建 `tacit-knowledge-platform/AGENTS.md`：项目级 Kimi 指南，包含架构、关键文件、流水线、IR 不变量、风险规则

### 2. 全局 Skill 迁移（~/.kimi-code/skills/）

新增 `backend-architecture` 技能包，包含 5 个子技能：

| 子技能 | 来源 |
|--------|------|
| `backend` | ClawHub |
| `backend-patterns` | ClawHub |
| `architecture-designer` | ClawHub（references 已内联） |
| `architecture-patterns` | ClawHub（保留 data/scripts/references/templates） |
| `db` | ClawHub |

已有技能包：
- `dev-workflows`
- `programming-essentials`
- `frontend-design`
- `backend-architecture`（新增）

### 3. 项目级 Agent 团队迁移

将原 Claude Code 的 10 人「天工团队」迁移到 Kimi 项目级技能包：

位置：`.kimi-code/skills/tiangong-team/`

```
.kimi-code/skills/tiangong-team/
├── SKILL.md              # 父包
├── orchestrator/SKILL.md
├── plan/SKILL.md
├── dev/SKILL.md
├── cr/SKILL.md
├── bug-hunt/SKILL.md
├── data-guardian/SKILL.md
├── test/SKILL.md
├── vr/SKILL.md
├── ship-check/SKILL.md
└── doc/SKILL.md
```

适配要点：
- 移除 `model:`、`allowed-tools:`、opus/sonnet/haiku 等 Claude 专属字段
- 将 `/command` 调用改为 `Agent` / `AgentSwarm` 工具调用
- 内联原 `.agents/skills/_roles/<role>/` 中不存在的角色纪律
- 保留项目约束：核心引擎文件、IR 不变量、step data key 一致性、安全规则

### 4. 服务启动

- 启动 `tacit-knowledge-platform` Flask 服务：
  - 地址：http://127.0.0.1:5000
  - 健康检查：`{"status":"ok"}`
- 后台任务 ID：`bash-3p7kz22d`（disable_timeout=true）

## 明日可继续攻关方向

1. **实际运行一次天工团队流水线**
   - 选择一个小的真实需求（如 bug 修复或文档同步）
   - 从 `orchestrator` 开始，完整走 plan → dev → cr/test → vr/doc → ship-check
   - 验证各 Agent skill 在 Kimi 中的实际调度效果

2. **迁移 `.claude/skills/tacit-to-skill/` 到 Kimi**
   - 这是项目级 skill，用于引导专家通过流水线生成 SKILL.md
   - 可迁移到 `.kimi-code/skills/tacit-to-skill/` 或全局 `~/.kimi-code/skills/`

3. **清理/补齐 `.agents/skills/_roles/<role>/` 角色级 skills**
   - 原 prompts 引用这些目录，但当前不存在
   - 可选择创建最小占位 skill，或确认当前内联版本足够使用

4. **深入核心模块源码**
   - `skill_ir.py`：IR 组装、版本链、修订应用、渲染
   - `pipeline_artifacts.py`：step data key、文件命名、IR 解析
   - `frontend/js/state.js` + `app.js`：状态流、自动保存、下游产出清除

5. **运行测试与修复**
   - `cd backend && python -m pytest scripts/ -v`
   - 处理当前未提交的 git 改动

## 当前 Git 状态（tacit-knowledge-platform）

已修改文件：
- `.claude/commands/orchestrator.md`
- `backend/app_server.py`
- `backend/knowledge_base.py`
- `backend/step2_preextract.py`
- `backend/validation_replay.py`
- `config/llm-config.yaml`
- `frontend/css/style.css`
- `frontend/index.html`
- `frontend/js/app.js`

未跟踪文件/目录：
- `.remember/`
- `backend/tools/import_verification_data.py`
- `data/backend.db`
- `docs/superpowers/`

新增文档：
- `AGENTS.md`
- `docs/2026-06-13-kimi-migration-progress.md`
- `.kimi-code/skills/tiangong-team/**/*.md`

---

记录时间：2026-06-13

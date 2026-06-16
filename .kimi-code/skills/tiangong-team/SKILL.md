---
name: tiangong-team
has-sub-skill: true
description: 天工团队 — tacit-knowledge-platform 项目级 10 人 Agent 团队，覆盖规划、开发、审查、测试、数据守护、运行验证、文档、通关检查全流程。
---

# 天工团队（Kimi 版）

本项目级技能包将原 Claude Code 的 10 人「天工团队」迁移到 Kimi Code CLI，使用 `Agent` / `AgentSwarm` 工具实现串行 + 并行调度。

## 子技能

| 子技能 | 角色 | 职责 | 何时使用 |
|--------|------|------|---------|
| `orchestrator` | 总调度 | 解读需求、制定计划、分派 Agent、驱动修复回路、跟踪到完成 | 任何需要多人协作的任务入口 |
| `plan` | 规划师 | 需求分析、方案对比、推荐实施计划、风险评估 | 开始新功能或重大变更前 |
| `dev` | 唯一编码者 | 所有代码变更收口，负责修复回路落地 | 需要写代码或修复问题时 |
| `cr` | 代码审查员 | diff 三维审查（正确性/安全/质量），可代理修复 critical/high | dev 完成后 |
| `bug-hunt` | 缺陷猎人 | 全量代码扫描，发现潜在缺陷 | 定期审计、重大重构后、发布前 |
| `data-guardian` | 数据守护 | 数据契约、状态持久化、schema 一致性 | 涉及数据格式/状态流变更时 |
| `test` | 测试工程师 | 生成并运行测试 | dev 完成后或需要补测试时 |
| `vr` | 运行验证官 | 启动服务做端到端动态验证 | cr + test 通过后 |
| `doc` | 文档维护 | 检查并同步文档 | 与 vr 并行执行 |
| `ship-check` | 通关检查官 | 提交前静态门控 | vr + doc 通过后 |

## 标准流水线

```
plan → dev → [cr ‖ test ‖ data-guardian?] → [vr ‖ doc] → ship-check → 提交
          ↑         │ 发现问题                             │ 不通过        │ 不通过
          └─── dev ←┘ (修复回路，每阶段最多 2 轮)           └── dev ←──────┘
```

### 并行组说明

- **dev 完成后**：`cr` / `test` / `data-guardian` 可并行（三者只读不改，输入相同）
- **审查通过后**：`vr` / `doc` 可并行（vr 验证运行时，doc 检查文档）
- **最后**：`ship-check` 做静态最终门控

### data-guardian 触发条件

满足以下任一条件时，dev 完成后应加入 `data-guardian`：

1. `STEP_OUTPUT_KEYS_BY_STEP` 变更
2. `DOWNSTREAM_OUTPUT_KEYS` / `PIPELINE_OUTPUT_KEYS` 变更
3. API 端点请求/响应 JSON 结构变更
4. 流水线持久化格式变更
5. 流水线步骤新增/删除
6. `scenario-schema.yaml` 变更
7. 跨步骤状态传递逻辑变更

## 调用方式

### 方式一：总入口（推荐）

直接激活 `orchestrator`，由它负责整个调度：

```
用户：我要给 tacit-knowledge-platform 增加 "批量导入验证案例" 功能
→ 调用 orchestrator Agent
  → 它调用 plan Agent 做方案
  → 它调用 dev Agent 写代码
  → 它并行调用 cr / test / data-guardian
  → 它并行调用 vr / doc
  → 它调用 ship-check
  → 汇总结果
```

### 方式二：单独调用某个角色

```
用户：帮我审查这个 diff
→ 调用 cr Agent

用户：生成并运行相关测试
→ 调用 test Agent

用户：验证当前服务是否正常运行
→ 调用 vr Agent
```

## 修复回路规则

1. `dev` 是唯一可以修改业务代码的角色
2. 任何下游角色发现问题，统一交回 `dev` 修复
3. 每阶段修复最多 2 轮；第 3 轮应升级给 orchestrator 或用户决策
4. 原发现者只复检修复点，不复检整个范围

## 与 Claude Code 原版的区别

- 原 `.claude/commands/*.md` + `.claude/workflows/*.js` 继续保留，供 Claude Code 使用
- Kimi 版使用本 `.kimi-code/skills/tiangong-team/` 技能包
- 原 `.agents/skills/_roles/<role>/` 目录不存在，角色核心纪律已内联到各子技能
- 工具约束从 Claude 的 `allowed-tools:` 改为自然语言边界说明 + Kimi 工具名

## 重要项目约束

所有子 Agent 都必须遵守 `tacit-knowledge-platform/AGENTS.md` 中的：

- 核心引擎文件（`skill_ir.py`、`pipeline_artifacts.py`、`state.js`、`shared.py`、`skill_registry.py`）
- Skill IR 不变量（IR 是单一事实源、版本链单调递增、entry ID 不复用）
- step data key 三处同步
- 安全底线（`safe_workspace_path()`、`escapeHtml()`、Flask 路由不重复）

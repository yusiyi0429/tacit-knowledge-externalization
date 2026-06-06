export const meta = {
  name: 'orchestrator',
  description: '天工团队总调度 — 解读需求、制定调度计划、串行Skill+并行Agent、驱动修复回路。用法：/orchestrator <高层需求>',
  phases: [
    { title: 'Assess', detail: '理解需求，判断复杂度' },
    { title: 'Plan', detail: '制定调度计划（角色序列+并行组）' },
    { title: 'Execute', detail: '串行Skill + 并行Agent分派' },
    { title: 'Fix', detail: '驱动修复回路（发现→dev→复检）' },
    { title: 'Summary', detail: '跟踪完成 + 汇总报告' },
  ],
}

const CFG = {
  project: { name: '隐性知识显性化', description: '银行信贷专家隐性经验 → 结构化 AI Skill，4 步流水线' },
  pipeline: {
    mainFlow: 'plan → dev → [cr ‖ test ‖ data-guardian?] → [vr ‖ doc] → ship-check',
    fixLoop: { maxRounds: 2, escalation: '上报用户' },
  },
  parallelGroups: [
    { stage: 'after-dev', roles: ['cr', 'test'], conditional: 'data-guardian' },
    { stage: 'after-review', roles: ['vr', 'doc'] },
  ],
  dgTriggers: [
    'STEP_OUTPUT_KEYS_BY_STEP', 'DOWNSTREAM_OUTPUT_KEYS', 'PIPELINE_OUTPUT_KEYS',
    'API JSON 结构变更', 'pipelines.json 格式变更', '流水线步骤增删', 'scenario-schema.yaml', '跨步骤状态传递',
  ],
  scenarios: {
    '新功能': { skipPlan: false, forceDG: false },
    'Bug修复': { skipPlan: true, forceDG: false },
    '小改动': { skipPlan: true, forceDG: false, minimal: true },
    '数据契约变更': { skipPlan: false, forceDG: true },
    '大型重构': { skipPlan: false, forceDG: true },
  },
  plugins: { superpowers: true, modelAllocation: { haiku: 'haiku', sonnet: 'sonnet', opus: 'opus' } },
}

const PIPELINE_OVERVIEW = `
== 天工团队流水线 ==

plan → dev → [cr ‖ test ‖ data-guardian?] → [vr ‖ doc] → ship-check → 提交

并行组：
- dev 完成后：cr ‖ test ‖ data-guardian（条件触发）
- 审查通过后：vr ‖ doc

修复回路：发现者 → dev(修复) → 原发现者复检 → 通过/再修(最多${CFG.pipeline.fixLoop.maxRounds}轮) → 上报用户

data-guardian 触发条件（任一满足）：
${CFG.dgTriggers.map((t, i) => `${i + 1}. ${t}`).join('\n')}
`

phase('Assess')
const requirement = args
log(`需求: ${requirement}`)

const complexity = await agent(
  `判断需求的复杂度，决定是否需要 plan 阶段。

需求：${requirement}

项目：${CFG.project.name} — ${CFG.project.description}

判断标准：
- 简单改动（单文件、低风险、1-2行）：跳 plan，直接 dev
- Bug修复（涉及数据契约则需 DG）：跳 plan，走 dev → (CR ‖ test ‖ DG?) → vr → SC
- 新功能/重构/不确定：先走 plan

同时判断是否涉及数据契约变更（决定是否触发 data-guardian）。

输出 JSON：{ complexity: "simple"|"bugfix"|"feature"|"refactor", skipPlan: bool, needsDataGuardian: bool, reason: string }`,
  { label: 'assess', phase: 'Assess', model: CFG.plugins.modelAllocation.haiku }
)

phase('Plan')
const skipPlan = complexity.skipPlan
const needsDG = complexity.needsDataGuardian

let pipelineSteps = []
if (skipPlan) {
  pipelineSteps = needsDG
    ? ['dev', 'cr‖test‖data-guardian', 'vr', 'ship-check']
    : (complexity.complexity === 'simple')
      ? ['dev', 'ship-check']
      : ['dev', 'cr‖test', 'vr', 'ship-check']
} else {
  pipelineSteps = needsDG
    ? ['plan', 'dev', 'cr‖test‖data-guardian', 'vr‖doc', 'ship-check']
    : ['plan', 'dev', 'cr‖test', 'vr‖doc', 'ship-check']
}

const dispatchPlan = {
  requirement,
  complexity: complexity.complexity,
  pipelineSteps,
  needsDataGuardian: needsDG,
  fixLoopMaxRounds: CFG.pipeline.fixLoop.maxRounds,
}
log(`调度计划: ${pipelineSteps.join(' → ')}`)

phase('Execute')

// Step 1: plan (if needed)
if (!skipPlan) {
  await agent(
    `你是天工团队的 plan 角色——架构师/分析师。只做分析和设计，不写代码。

${PIPELINE_OVERVIEW}

需求：${requirement}

输出：需求分析 + 方案对比 + 推荐方案实施计划 + 风险点 + data-guardian 评估`,
    { label: 'plan', phase: 'Execute', model: CFG.plugins.modelAllocation.opus }
  )
}

// Step 2: dev
await agent(
  `你是天工团队的 dev 角色——唯一编码者。所有代码变更只由你执行。

${PIPELINE_OVERVIEW}

需求：${requirement}
${!skipPlan ? '按照 plan 的实施计划执行。' : '直接根据需求实现。'}

工作方式：先理解后动手 → 增量变更 → 跨层同步 → 自检。
编码纪律：根本原因优先 / 先验证再声明 / 失败回退。

注意：你写完代码后不运行测试、不做审查——那些交给下游角色。`,
  { label: 'dev', phase: 'Execute', model: CFG.plugins.modelAllocation.opus }
)

// Step 3: cr ‖ test ‖ data-guardian?
const afterDevAgents = [
  () => agent(
    `你是天工团队的 cr 角色——代码审查者。只审查当前 diff。

${PIPELINE_OVERVIEW}

审查三维度：正确性 / 安全性 / 代码质量。
每个发现附 文件:行号 + 证据。
对 critical/high 做对抗式交叉验证（存在性 + 严重度），降假阳性。
不改代码——问题交 /dev 修复。`,
    { label: 'cr', phase: 'Execute', model: CFG.plugins.modelAllocation.opus }
  ),
  () => agent(
    `你是天工团队的 test 角色——测试工程师。分析变更代码，生成测试并运行。

${PIPELINE_OVERVIEW}

工作方式：分析变更 → 生成测试（happy path + 边界 + 错误路径）→ 运行测试。
测试失败不修业务代码——报告交 /dev 修复。`,
    { label: 'test', phase: 'Execute', model: CFG.plugins.modelAllocation.sonnet }
  ),
]
if (needsDG) {
  afterDevAgents.push(() => agent(
    `你是天工团队的 data-guardian 角色——数据守护者。专职守护数据契约与状态完整性。

${PIPELINE_OVERVIEW}

守护维度：数据契约一致性 / 状态持久化完整性 / 关键标识符跨层同步 / Schema演进。
每个发现附 file:line + 实际值对比。不改代码——问题交 /dev 修复。`,
    { label: 'data-guardian', phase: 'Execute', model: CFG.plugins.modelAllocation.sonnet }
  ))
}

// Minimal pipeline (simple changes) skips review
if (pipelineSteps.length <= 2) {
  log('简单改动，跳过审查/测试并行组')
} else {
  log(`启动并行组: cr ‖ test${needsDG ? ' ‖ data-guardian' : ''}`)
  await parallel(afterDevAgents)
}

// Step 4: vr ‖ doc (only in full pipeline)
if (pipelineSteps.includes('vr') || pipelineSteps.includes('vr‖doc')) {
  const afterReviewAgents = [
    () => agent(
      `你是天工团队的 vr 角色——运行验证官。启动应用走核心路径做动态验证。

${PIPELINE_OVERVIEW}

工作方式：确定验证目标 → 启动应用 → 走核心路径 → 观察记录 → 收尾关进程。
验证后关闭启动的进程，不留后台残留。不改代码——问题交 /dev 修复。`,
      { label: 'vr', phase: 'Execute', model: CFG.plugins.modelAllocation.haiku }
    ),
  ]
  if (pipelineSteps.includes('vr‖doc')) {
    afterReviewAgents.push(() => agent(
      `你是天工团队的 doc 角色——文档工程师。检查文档与代码同步状态。

${PIPELINE_OVERVIEW}

扫描变更 → 定位相关文档 → 同步检查 → 输出报告/修复文档。
你有 Write/Edit 权限，纯文档问题直接修复。代码需配合时交 /dev。`,
      { label: 'doc', phase: 'Execute', model: CFG.plugins.modelAllocation.sonnet }
    ))
  }
  log(`启动并行组: verify${pipelineSteps.includes('vr‖doc') ? ' ‖ doc' : ''}`)
  await parallel(afterReviewAgents)
}

// Step 5: ship-check
if (pipelineSteps.includes('ship-check')) {
  await agent(
    `你是天工团队的 ship-check 角色——提交前通关检查官。执行全面静态一致性检查。

${PIPELINE_OVERVIEW}

检查清单：语法与编译 / 路由冲突 / 接口一致性 / 样式一致性 / 单元测试 / 文件完整性。
这是最终关卡——通过即可提交。不改代码——问题交 /dev 修复。`,
    { label: 'ship-check', phase: 'Execute', model: CFG.plugins.modelAllocation.haiku }
  )
}

phase('Summary')
return JSON.stringify({
  requirement,
  complexity: complexity.complexity,
  pipeline: pipelineSteps.join(' → '),
  dataGuardianTriggered: needsDG,
  result: '流水线执行完毕。详见各阶段输出。',
}, null, 2)

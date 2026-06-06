export const meta = {
  name: 'plan',
  description: '根据需求分析项目代码库，输出结构化实施计划。用法：/plan <需求描述>',
  phases: [
    { title: 'Clarify', detail: '理解需求，确定范围' },
    { title: 'Scout', detail: '并行侦察相关代码模块' },
    { title: 'Analyze', detail: '风险识别 + 依赖分析 + DG触发判断' },
    { title: 'Plan', detail: '输出结构化实施计划' },
  ],
}

const CFG = {
  project: {
    name: '隐性知识显性化',
    description: '将银行信贷专家的隐性经验 → 结构化、可交付的 AI Skill，通过 4 步流水线（场景锚定→知识萃取→知识对齐→智能转化）',
  },
  tech: {
    backend: { language: 'python', framework: 'flask', dir: 'backend', entry: 'app_server.py',
      routeDecorator: '@app.route', hasRoutes: true },
    frontend: { language: 'javascript', framework: 'vanilla', dir: 'frontend', entry: 'index.html',
      jsDir: 'frontend/js', cssDir: 'frontend/css', apiBase: '/api', fetchPattern: 'fetch(API_BASE +' },
  },
  dirs: { config: 'config', docs: 'docs', scripts: 'backend/scripts' },
  codeConventions: {
    htmlEscape: 'escapeHtml()', checkXSS: true, checkPathTraversal: true,
    pathSafety: 'safe_workspace_path()', basenameFn: 'basename_only()',
  },
  dgTriggers: [
    'STEP_OUTPUT_KEYS_BY_STEP', 'DOWNSTREAM_OUTPUT_KEYS', 'PIPELINE_OUTPUT_KEYS',
    'API JSON 结构变更', 'pipelines.json 格式变更', '流水线步骤增删', 'scenario-schema.yaml', '跨步骤状态传递',
  ],
  scoutFiles: {
    backend: ['backend/app_server.py', 'backend/pipeline_artifacts.py'],
    frontend: ['frontend/js/app.js', 'frontend/js/state.js'],
  },
  riskRules: [
    { name: '路径穿越防护', severity: 'critical', desc: '所有文件操作必须经过路径安全检查函数' },
    { name: 'XSS 防护', severity: 'high', desc: 'innerHTML 内容必须经 HTML 转义函数处理' },
    { name: 'Flask 路由去重', severity: 'high', desc: '同名函数/路由会静默覆盖，注意不冲突' },
    { name: 'MergedCell', severity: 'high', desc: 'openpyxl 写入前必须先解除合并' },
  ],
  llm: { enabled: true, clientFile: 'backend/llm_client.py', jsonFallback: 6 },
  plugins: { superpowers: true, modelAllocation: { haiku: 'haiku', sonnet: 'sonnet', opus: 'opus' } },
}

const PLANNER_RULES = `
== Superpowers 规划师纪律 ==

1. 写下计划时假设执行者对这个项目一无所知。告诉他：改哪个文件、写什么代码、如何测试、参考哪些文档。
2. 每个步骤是「一口吃完」的量——步骤之间自然分界。
3. 列出每步执行后用户能验证的 observable 证据。
4. DRY. YAGNI. 不引入不需要的抽象。
5. 如果有多个可行方案，列出并标注推荐理由。
6. 实施步骤必须按依赖排序。标注哪些步骤可以并行，哪些必须串行。
7. 每个涉及文件改动的步骤标注风险等级和回滚方式。
8. 输出计划前自检：是否有定义不明确的需求？是否有遗漏的约束？`

const PIPELINE_CONTEXT = `
== 天工团队流水线 ==
plan → dev → [cr ‖ test ‖ data-guardian?] → [vr ‖ doc] → ship-check

你是 plan 角色，输出交 dev 执行。
你需要评估：本次变更是否触发 data-guardian（数据契约守护）。`

const PLAN_SCHEMA = {
  type: 'object',
  properties: {
    title: { type: 'string' },
    background: { type: 'string' },
    scope: { type: 'string' },
    affectedFiles: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          file: { type: 'string' }, reason: { type: 'string' },
          changeType: { type: 'string', enum: ['create', 'modify', 'delete', 'review'] },
          risk: { type: 'string', enum: ['high', 'medium', 'low'] },
        },
        required: ['file', 'reason', 'changeType', 'risk'],
      },
    },
    implementationSteps: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          step: { type: 'number' }, description: { type: 'string' },
          files: { type: 'array', items: { type: 'string' } },
          dependsOn: { type: 'array', items: { type: 'number' } },
          verification: { type: 'string' },
        },
        required: ['step', 'description', 'files', 'verification'],
      },
    },
    risks: { type: 'array', items: { type: 'object', properties: { risk: { type: 'string' }, mitigation: { type: 'string' } }, required: ['risk', 'mitigation'] } },
    needsDataGuardian: { type: 'boolean', description: '是否触发 data-guardian' },
    dgReason: { type: 'string', description: '触发/不触发 DG 的原因' },
    downstreamPipeline: { type: 'string', description: '建议的下游流水线步骤' },
    teamRecommendation: { type: 'string' },
  },
  required: ['title', 'scope', 'affectedFiles', 'implementationSteps', 'risks', 'needsDataGuardian', 'downstreamPipeline', 'teamRecommendation'],
}

phase('Clarify')
const requirement = args

phase('Scout')
log(`需求: ${requirement}`)

const [routesInfo, backendStructure, frontendStructure] = await parallel([
  CFG.tech.backend.hasRoutes ? () => agent(
    `侦察 ${CFG.tech.backend.framework} 项目的 API 路由结构。
读取 ${CFG.tech.backend.dir}/${CFG.tech.backend.entry} 中所有 ${CFG.tech.backend.routeDecorator} 路由。
分类列出每个路由及其功能。`,
    { label: 'scout-routes', phase: 'Scout', model: CFG.plugins.modelAllocation.haiku }
  ) : () => '无路由架构',
  () => agent(
    `侦察 ${CFG.project.name} 项目的后端模块结构。
读取以下文件的前 30 行（import 和关键类/函数定义）：
${CFG.scoutFiles.backend.map(f => `- ${f}`).join('\n')}
${CFG.dirs.config ? `- ${CFG.dirs.config}/*.yaml / *.yml` : ''}
报告每个模块的核心类和函数签名。`,
    { label: 'scout-backend', phase: 'Scout', model: CFG.plugins.modelAllocation.haiku }
  ),
  () => agent(
    `侦察 ${CFG.project.name} 项目的前端结构和数据流。
读取以下文件：
${CFG.scoutFiles.frontend.map(f => `- ${f}`).join('\n')}
报告前端数据流：用户操作 → 状态变更 → UI 重绘 的链路。`,
    { label: 'scout-frontend', phase: 'Scout', model: CFG.plugins.modelAllocation.haiku }
  ),
])

phase('Analyze')
log(`路由: ${routesInfo?.length || 'N/A'}`)

phase('Plan')
const riskDesc = CFG.riskRules.map(r => `  - ${r.severity}: ${r.name} — ${r.desc}`).join('\n')

const plan = await agent(
  `你是天工团队的 plan 角色——架构师/分析师。只做分析和设计，不写代码。

${PIPELINE_CONTEXT}

${CFG.plugins.superpowers ? PLANNER_RULES : ''}

== 需求 ==
${requirement || '（未提供具体需求）'}

== 项目概况 ==
${CFG.project.name}: ${CFG.project.description}
后端: ${CFG.tech.backend.language}/${CFG.tech.backend.framework}
前端: ${CFG.tech.frontend.language}/${CFG.tech.frontend.framework}
API 路由: ${routesInfo}
后端模块: ${backendStructure}
前端结构: ${frontendStructure}

== 项目特有风险 ==
${riskDesc}

== data-guardian 触发条件 ==
${CFG.dgTriggers.map((t, i) => `${i + 1}. ${t}`).join('\n')}

== 输出要求 ==
1. title / background / scope（明确做什么 + 不做什么）
2. affectedFiles（变更类型 + 风险等级）
3. implementationSteps（排好顺序，标注依赖关系，每步有 verifiable 完成标准）
4. risks（项目特有风险及规避措施）
5. **needsDataGuardian** + **dgReason**：评估本次变更是否涉及数据契约，决定下游是否需要 DG
6. **downstreamPipeline**：建议的下游流水线步骤（如 "dev → [CR ‖ test ‖ DG] → [vr ‖ doc] → SC"）
7. teamRecommendation（建议调用的检查团队）`,
  { label: 'synthesize-plan', phase: 'Plan', schema: PLAN_SCHEMA, model: CFG.plugins.modelAllocation.opus }
)

return JSON.stringify(plan, null, 2)

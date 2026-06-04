export const meta = {
  name: 'plan',
  description: '根据需求分析项目代码库，输出结构化实施计划。用法：/plan <需求描述>',
  phases: [
    { title: 'Clarify', detail: '理解需求，确定范围（brainstorming 驱动）' },
    { title: 'Scout', detail: '并行侦察相关代码模块' },
    { title: 'Analyze', detail: '风险识别 + 依赖分析' },
    { title: 'Plan', detail: '输出结构化实施计划（writing-plans 驱动）' },
  ],
}

// ═══════════════════════════════════════════
//  🔧 项目配置 — 新项目修改此区域即可
// ═══════════════════════════════════════════
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
  scoutFiles: {
    backend: ['backend/app_server.py', 'backend/models.py'],
    frontend: ['frontend/index.html', 'frontend/js/main.js', 'frontend/js/utils.js'],
    config: ['config/default.yaml'],
  },
  riskRules: [
    { name: '路径穿越防护', severity: 'critical', desc: '所有文件操作必须经过路径安全检查函数' },
    { name: 'XSS 防护', severity: 'high', desc: 'innerHTML 内容必须经 HTML 转义函数处理' },
    { name: 'Flask 路由去重', severity: 'high', desc: '同名函数/路由会静默覆盖，注意不冲突' },
  ],
  llm: { enabled: true, clientFile: 'backend/llm_client.py', jsonFallback: 6 },
  plugins: { superpowers: true, modelAllocation: { haiku: 'haiku', sonnet: 'sonnet', opus: 'opus' } },
}
// ═══════════════════════════════════════════

// superpowers: writing-plans + brainstorming 精华（注入 synthesize-plan agent）
const PLANNER_RULES = `
== Superpowers 规划师纪律 ==

**writing-plans 原则**：
1. 写下计划时假设执行者对这个项目一无所知。告诉他：改哪个文件、写什么代码、如何测试、参考哪些文档。
2. 每个步骤是「一口吃完」的量——步骤之间自然分界，不会出现一个步骤要改5个不相关的文件。
3. 列出每步执行后用户能验证的 observable 证据（见一个新按钮、打开一个文件、看到一个新的tab等）。
4. DRY. YAGNI. 不引入不需要的抽象。

**brainstorming 原则**：
5. 如果有多个可行方案，列出并标注你的推荐理由。不要把一个方案当唯一解。
6. 实施步骤必须按依赖排序。标注哪些步骤可以并行，哪些必须串行。
7. 每个涉及文件改动的步骤标注风险等级（high/medium/low）和回滚方式。

**verification-before-completion 原则**：
8. 输出计划前自检：是否有定义不明确的需求？是否有遗漏的约束？是否每个步骤都有可验证的完成标准？`

const PLAN_SCHEMA = {
  type: 'object',
  properties: {
    title: { type: 'string' },
    background: { type: 'string' },
    scope: { type: 'string', description: '做什么 + 明确不做什么' },
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
    relevantPatterns: { type: 'array', items: { type: 'string' } },
    teamRecommendation: { type: 'string' },
  },
  required: ['title', 'scope', 'affectedFiles', 'implementationSteps', 'risks', 'teamRecommendation'],
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
读取以下文件的前 30 行（import 和关键类/函数定义），了解架构分层：
${CFG.scoutFiles.backend.map(f => `- ${f}`).join('\n')}
${CFG.dirs.config ? `- ${CFG.dirs.config}/*.yaml / *.yml` : ''}
报告每个模块的核心类和函数签名。`,
    { label: 'scout-backend', phase: 'Scout', model: CFG.plugins.modelAllocation.haiku }
  ),
  () => agent(
    `侦察 ${CFG.project.name} 项目的前端结构和数据流。
读取以下文件，了解前端分层：
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
  `你是软件架构规划师。基于以下信息和用户需求，输出结构化的实施计划。

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
${CFG.codeConventions.checkPathTraversal ? `- 路径穿越防护: ${CFG.codeConventions.pathSafety} / ${CFG.codeConventions.basenameFn}` : ''}
${CFG.codeConventions.checkXSS ? `- XSS: innerHTML 必须经 ${CFG.codeConventions.htmlEscape}` : ''}

== 输出要求 ==
1. title / background / scope（明确做什么 + 不做什么）
2. affectedFiles（变更类型 + 风险等级）
3. implementationSteps（排好顺序，标注依赖关系，每步有 verifiable 完成标准）
4. risks（项目特有风险及规避措施）
5. relevantPatterns（需参考的现有代码模式）
6. teamRecommendation（建议调用的检查团队）`,
  { label: 'synthesize-plan', phase: 'Plan', schema: PLAN_SCHEMA, model: CFG.plugins.modelAllocation.opus }
)

return JSON.stringify(plan, null, 2)

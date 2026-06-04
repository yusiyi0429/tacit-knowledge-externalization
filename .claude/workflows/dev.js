export const meta = {
  name: 'dev',
  description: '根据需求实现代码变更，自动处理跨层同步并验证。用法：/dev <需求>',
  phases: [
    { title: 'Analyze', detail: '理解需求，侦察影响面' },
    { title: 'Implement', detail: '并行实现后端/前端变更（Superpowers 驱动）' },
    { title: 'Sync', detail: '自动处理跨层同步' },
    { title: 'Verify', detail: '一致性检查 + 语法验证' },
  ],
}

// ═══════════════════════════════════════════
//  🔧 项目配置 — 新项目修改此区域即可
// ═══════════════════════════════════════════
const CFG = {
  project: {
    name: '隐性知识显性化',
    description: '将银行信贷专家的隐性经验 → 结构化 AI Skill 的 4 步流水线',
  },
  tech: {
    backend: { language: 'python', framework: 'flask', dir: 'backend', entry: 'app_server.py',
      modules: ['step1_*.py', 'step2_*.py', 'knowledge_delivery.py', 'revision_processor.py', 'llm_client.py'] },
    frontend: { language: 'javascript', framework: 'vanilla', dir: 'frontend', entry: 'index.html',
      jsDir: 'frontend/js', stateFile: 'state.js', mainFile: 'app.js' },
  },
  dirs: { config: 'config' },
  codeConventions: {
    htmlEscape: 'escapeHtml()', pathSafety: 'safe_workspace_path()', basenameFn: 'basename_only()',
    checkXSS: true, checkPathTraversal: true, checkRouteDupes: true,
  },
  consistency: {
    syncGroups: [
      { files: ['backend/pipeline_artifacts.py', 'frontend/js/state.js', 'frontend/js/app.js'],
        pattern: '(STEP_OUTPUT_KEYS_BY_STEP|DOWNSTREAM_OUTPUT_KEYS)',
        desc: 'step data key 三处同步' },
    ],
  },
  riskRules: [
    { name: 'MergedCell 处理', desc: 'openpyxl 写入前必须 unmerge_cells()' },
    { name: 'LLM JSON 降级', desc: 'LLM 输出不可信，JSON 解析必须有 try/catch 降级（当前 6 层）' },
    { name: '文件名约束', desc: '使用 template_/preextract_/revision_/final_ 等前缀系统' },
    { name: '受保护文件', desc: 'pipelines.json / custom_models.json / preset_overrides.json 不可被下载' },
  ],
  llm: { enabled: true, clientFile: 'backend/llm_client.py' },
  // 插件增强 — 子 agent 自动继承这些方法论
  plugins: {
    frontendDesign: true,   // 前端 agent 遵循 frontend-design 设计规范
    superpowers: true,       // 所有 agent 遵循 systematic-debugging / verification-before-completion
    modelAllocation: { haiku: 'haiku', sonnet: 'sonnet', opus: 'opus' },
  },
}
// ═══════════════════════════════════════════

const IMPLEMENT_PLAN_SCHEMA = {
  type: 'object',
  properties: {
    filesToChange: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          file: { type: 'string' }, changeType: { type: 'string', enum: ['create', 'modify', 'delete'] },
          summary: { type: 'string' }, riskAreas: { type: 'array', items: { type: 'string' } },
        },
        required: ['file', 'changeType', 'summary'],
      },
    },
    backendScope: { type: 'string' },
    frontendScope: { type: 'string' },
    needsKeySync: { type: 'boolean', description: '是否涉及 key 定义同步' },
    needsNewRoute: { type: 'boolean' },
  },
  required: ['filesToChange', 'backendScope', 'frontendScope', 'needsKeySync', 'needsNewRoute'],
}

function constraints(cfg) {
  const lines = ['项目特有约束（每项变更必须遵守）：']
  lines.push(`1. 文件路径安全: 所有文件操作必须使用 ${cfg.codeConventions.pathSafety} / ${cfg.codeConventions.basenameFn}`)
  if (cfg.codeConventions.checkXSS) lines.push(`2. XSS 防护: innerHTML 必须经 ${cfg.codeConventions.htmlEscape}`)
  if (cfg.codeConventions.checkRouteDupes) lines.push('3. 路由去重: 添加路由前确认不重复（后定义覆盖前者）')
  if (cfg.consistency.syncGroups.length) {
    lines.push(`4. 同步约束:`)
    cfg.consistency.syncGroups.forEach((g, i) => lines.push(`   ${i + 4}.1. ${g.desc}: ${g.files.join(', ')}`))
  }
  cfg.riskRules.forEach((r, i) => lines.push(`${cfg.consistency.syncGroups.length ? 7 : 5 + i}. ${r.name}: ${r.desc}`))
  return lines.join('\n')
}

// frontend-design 插件方法论（注入前端子 agent）
const FRONTEND_DESIGN_RULES = `
== Frontend-Design 设计规范（必须遵守） ==

你是这个项目的"前端设计工程师"。不要写平淡、千篇一律的 UI 代码。

**设计思维**（写代码前先想清楚）：
- 这个界面的目的是什么？谁在用？
- 选一个明确的**美学方向**：极简克制 / 大胆堆叠 / 工业实用 / 精致克制
- 核心记忆点是什么？用户离开后会对什么留下印象？

**视觉规范**：
- 字体：不使用 Arial / Inter / Roboto / 系统默认字体。选用有辨识度的字体组合。
- 色彩：主导色 + 点缀强调色。避免均匀分布的多色方案。用 CSS 变量保持一致。
- 空间：不对称布局、留白的大胆使用、或控制密度的紧凑感。避免居中对称的平庸排布。
- 动效：关键交互用 CSS 动画做高影响力时刻（staggered reveals, hover 惊喜）。不用零碎的微交互分散注意力。

**禁止事项**：
- 禁止紫色渐变配白色背景
- 禁止 Space Grotesk / Inter 作为默认字体
- 禁止千篇一律的卡片 + 阴影布局
- 禁止 AI 生成风格的平庸配色`

// superpowers 插件方法论（注入所有子 agent）
const SUPERPOWERS_RULES = `
== Superpowers 开发纪律（必须遵守） ==

1. **根本原因优先**：修改代码前必须先定位根本原因。不要掩盖症状。如果你还没找到根因而想写修复代码——停下来继续查。

2. **先验证再声明**：
   - 改完每个文件后验证语法正确
   - 改完前端文件后确认对应的 DOM 元素在 HTML 中确实存在
   - 如果涉及 key 同步，改完后确认三处文件定义一致
   - 永远不要在没有实际运行验证的情况下说"完成了"

3. **失败回退**：如果遇到 ModifyingFileError 或其他编辑失败，先重新读取文件确认最新内容，再做修改。不要盲目重试。

4. **最小改动**：只改必要的。不顺手重构不相关的代码。不添加"可能将来有用"的抽象。`

const requirement = args

phase('Analyze')
const implPlan = await agent(
  `分析以下需求，确定实现范围和影响文件。

需求：${requirement}

项目概况：${CFG.project.name} — ${CFG.project.description}
- 后端: ${CFG.tech.backend.language} ${CFG.tech.backend.framework}，主入口 ${CFG.tech.backend.dir}/${CFG.tech.backend.entry}
- 前端: ${CFG.tech.frontend.language}（${CFG.tech.frontend.framework}），入口 ${CFG.tech.frontend.dir}/${CFG.tech.frontend.entry}
- JS: ${CFG.tech.frontend.jsDir}/（状态管理 ${CFG.tech.frontend.stateFile}、主逻辑 ${CFG.tech.frontend.mainFile}）
${CFG.dirs.config ? `- Config: ${CFG.dirs.config}/` : ''}

${constraints(CFG)}

输出实现范围和影响文件清单。`,
  { label: 'analyze', phase: 'Analyze', schema: IMPLEMENT_PLAN_SCHEMA, model: CFG.plugins.modelAllocation.sonnet }
)

phase('Implement')
log(`影响文件: ${implPlan.filesToChange.map(f => f.file).join(', ')}`)

const backendFiles = implPlan.filesToChange.filter(f => f.file.startsWith(CFG.tech.backend.dir + '/') || f.file.startsWith('config/'))
const frontendFiles = implPlan.filesToChange.filter(f => f.file.startsWith(CFG.tech.frontend.dir + '/'))
const otherFiles = implPlan.filesToChange.filter(f => !f.file.startsWith(CFG.tech.backend.dir + '/') && !f.file.startsWith(CFG.tech.frontend.dir + '/') && !f.file.startsWith('config/'))

const implementors = []
if (backendFiles.length > 0) {
  implementors.push(() => agent(
    `后端 ${CFG.tech.backend.language} 工程师。根据计划实现后端代码变更。

${CFG.plugins.superpowers ? SUPERPOWERS_RULES : ''}

需求：${requirement}
范围：${implPlan.backendScope}

${constraints(CFG)}

文件：
${backendFiles.map(f => `  ${f.changeType}: ${f.file} — ${f.summary}`).join('\n')}

${CFG.llm.enabled ? `LLM 通过 ${CFG.llm.clientFile} 调用` : ''}

请先读现有代码，再做修改。每改完一个文件确认语法正确。`,
    { label: 'impl-backend', phase: 'Implement', model: CFG.plugins.modelAllocation.opus }
  ))
}
if (frontendFiles.length > 0) {
  implementors.push(() => agent(
    `前端 ${CFG.tech.frontend.language} 工程师。根据计划实现前端代码变更。

${CFG.plugins.superpowers ? SUPERPOWERS_RULES : ''}
${CFG.plugins.frontendDesign ? FRONTEND_DESIGN_RULES : ''}

需求：${requirement}
范围：${implPlan.frontendScope}

${constraints(CFG)}

文件：
${frontendFiles.map(f => `  ${f.changeType}: ${f.file} — ${f.summary}`).join('\n')}

前端架构：
- 状态管理: ${CFG.tech.frontend.jsDir}/${CFG.tech.frontend.stateFile}
- 主逻辑: ${CFG.tech.frontend.jsDir}/${CFG.tech.frontend.mainFile}
- API base: ${CFG.tech.frontend.apiBase || '/api'}

请先读现有代码，再做修改。`,
    { label: 'impl-frontend', phase: 'Implement', model: CFG.plugins.modelAllocation.opus }
  ))
}
if (otherFiles.length > 0) {
  implementors.push(() => agent(
    `根据实现计划修改其他文件。

${CFG.plugins.superpowers ? SUPERPOWERS_RULES : ''}

需求：${requirement}

文件：
${otherFiles.map(f => `  ${f.changeType}: ${f.file} — ${f.summary}`).join('\n')}

${constraints(CFG)}
请先读现有代码，再做修改。`,
    { label: 'impl-other', phase: 'Implement', model: CFG.plugins.modelAllocation.sonnet }
  ))
}
await parallel(implementors)

phase('Sync')
if (implPlan.needsKeySync && CFG.consistency.syncGroups.length > 0) {
  for (const group of CFG.consistency.syncGroups) {
    const syncResult = await agent(
      `同步 ${group.desc}。

${constraints(CFG)}

需求：${requirement}

检查以下文件中的 ${group.pattern} 定义是否一致：
${group.files.map(f => `- ${f}`).join('\n')}

修复不一致处。报告修复结果。`,
      { label: `sync-${group.desc.slice(0, 12)}`, phase: 'Sync', model: CFG.plugins.modelAllocation.sonnet }
    )
    log(`同步结果: ${syncResult}`)
  }
}
if (implPlan.needsNewRoute && CFG.tech.backend.hasRoutes) {
  const routeResult = await agent(
    `检查 API 路由一致性。

${CFG.tech.backend.dir}/${CFG.tech.backend.entry} routes vs ${CFG.tech.frontend.jsDir}/ fetch calls.

${constraints(CFG)}

报告不匹配项。`,
    { label: 'sync-routes', phase: 'Sync', model: CFG.plugins.modelAllocation.sonnet }
  )
  log(`路由: ${routeResult}`)
}

phase('Verify')
const verifyResult = await agent(
  `验证代码变更是否引入错误。严格执行"先验证再声明"原则——每项检查都要有实际的输出结果作为证据。

需求：${requirement}

${constraints(CFG)}

${CFG.tech.backend.language === 'python' ? `1. 运行 ${CFG.tech.backend.dir} 目录 Python 语法检查` : ''}
${CFG.tech.frontend.language === 'javascript' ? `2. 检查 ${CFG.tech.frontend.jsDir}/ 中关键定义一致性` : ''}

验证清单（逐项核实，每项标注 PASS/FAIL 并附证据）：
- Python 语法检查实际输出
- JS 关键定义（DOWNSTREAM_OUTPUT_KEYS / PIPELINE_OUTPUT_KEYS）在两个文件中的一致性
- ${CFG.tech.frontend.language === 'javascript' ? 'HTML 中 onclick 引用的函数是否在 JS 文件中存在' : ''}
- 文件引用路径是否有效`,
  { label: 'verify', phase: 'Verify', model: CFG.plugins.modelAllocation.sonnet }
)

return JSON.stringify({
  requirement,
  filesChanged: implPlan.filesToChange,
  keySyncPerformed: implPlan.needsKeySync || implPlan.needsNewRoute,
  verification: verifyResult,
}, null, 2)

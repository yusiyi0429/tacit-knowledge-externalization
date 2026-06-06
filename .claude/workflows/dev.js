export const meta = {
  name: 'dev',
  description: '根据需求实现代码变更，自动处理跨层同步并验证。用法：/dev <需求>',
  phases: [
    { title: 'Analyze', detail: '理解需求，侦察影响面' },
    { title: 'Implement', detail: '并行实现后端/前端变更' },
    { title: 'Sync', detail: '自动处理跨层同步' },
    { title: 'Verify', detail: '一致性检查 + 语法验证' },
  ],
}

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
  plugins: {
    frontendDesign: true,
    superpowers: true,
    modelAllocation: { haiku: 'haiku', sonnet: 'sonnet', opus: 'opus' },
  },
}

const PIPELINE_CONTEXT = `
== 天工团队流水线 ==
plan → dev → [cr ‖ test ‖ data-guardian?] → [vr ‖ doc] → ship-check

你是 dev 角色——唯一编码者。
- 上游：接收 plan 的实施计划（或直接需求）
- 下游：代码变更交 cr / test / data-guardian 检查
- 修复回路：CR/test/DG/vr/SC 发现的问题统一回到你这里修复
- 修复规则：仅修复报告的问题，不做额外改动，最多 2 轮`

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
    needsKeySync: { type: 'boolean' },
    needsNewRoute: { type: 'boolean' },
  },
  required: ['filesToChange', 'backendScope', 'frontendScope', 'needsKeySync', 'needsNewRoute'],
}

function constraints(cfg) {
  const lines = ['项目特有约束（每项变更必须遵守）：']
  lines.push(`1. 文件路径安全: 所有文件操作必须使用 ${cfg.codeConventions.pathSafety} / ${cfg.codeConventions.basenameFn}`)
  if (cfg.codeConventions.checkXSS) lines.push(`2. XSS 防护: innerHTML 必须经 ${cfg.codeConventions.htmlEscape}`)
  if (cfg.codeConventions.checkRouteDupes) lines.push('3. 路由去重: 添加路由前确认不重复')
  if (cfg.consistency.syncGroups.length) {
    lines.push(`4. 同步约束:`)
    cfg.consistency.syncGroups.forEach((g, i) => lines.push(`   ${i + 4}.1. ${g.desc}: ${g.files.join(', ')}`))
  }
  cfg.riskRules.forEach((r, i) => lines.push(`${cfg.consistency.syncGroups.length ? 7 : 5 + i}. ${r.name}: ${r.desc}`))
  return lines.join('\n')
}

const SUPERPOWERS_RULES = `
== Superpowers 开发纪律 ==
1. 根本原因优先：改代码前必须先定位根因。不要掩盖症状。
2. 先验证再声明：改完每个文件验证语法；涉及 key 同步确认三处定义一致；永远不要在没有实际运行验证的情况下说"完成了"。
3. 失败回退：遇到编辑失败先重新读取文件确认最新内容，再做修改。不要盲目重试。
4. 最小改动：只改必要的。不顺手重构不相关的代码。`

const FRONTEND_DESIGN_RULES = `
== Frontend-Design 设计规范 ==
- 字体：不用 Arial/Inter/Roboto/系统默认字体
- 色彩：主导色+点缀强调色，CSS 变量保持一致
- 空间：敢用留白、不对称或紧凑密度
- 动效：关键交互用 CSS 动画做高影响力时刻
- 禁止：紫色渐变配白底；Space Grotesk/Inter 作默认字体；千篇一律的卡片+阴影；AI 味平庸配色`

const requirement = args

phase('Analyze')
const implPlan = await agent(
  `分析以下需求，确定实现范围和影响文件。

${PIPELINE_CONTEXT}

需求：${requirement}

项目概况：${CFG.project.name} — ${CFG.project.description}
- 后端: ${CFG.tech.backend.language} ${CFG.tech.backend.framework}，主入口 ${CFG.tech.backend.dir}/${CFG.tech.backend.entry}
- 前端: ${CFG.tech.frontend.language}（${CFG.tech.frontend.framework}），入口 ${CFG.tech.frontend.dir}/${CFG.tech.frontend.entry}
- JS: ${CFG.tech.frontend.jsDir}/（状态管理 ${CFG.tech.frontend.stateFile}、主逻辑 ${CFG.tech.frontend.mainFile}）

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

${SUPERPOWERS_RULES}
${PIPELINE_CONTEXT}

需求：${requirement}
范围：${implPlan.backendScope}

${constraints(CFG)}

文件：
${backendFiles.map(f => `  ${f.changeType}: ${f.file} — ${f.summary}`).join('\n')}

${CFG.llm.enabled ? `LLM 通过 ${CFG.llm.clientFile} 调用` : ''}

请先读现有代码，再做修改。每改完一个文件确认语法正确。
注意：写完后不运行测试、不做审查——交给下游 cr / test。`,
    { label: 'impl-backend', phase: 'Implement', model: CFG.plugins.modelAllocation.opus }
  ))
}
if (frontendFiles.length > 0) {
  implementors.push(() => agent(
    `前端 ${CFG.tech.frontend.language} 工程师。根据计划实现前端代码变更。

${SUPERPOWERS_RULES}
${CFG.plugins.frontendDesign ? FRONTEND_DESIGN_RULES : ''}
${PIPELINE_CONTEXT}

需求：${requirement}
范围：${implPlan.frontendScope}

${constraints(CFG)}

文件：
${frontendFiles.map(f => `  ${f.changeType}: ${f.file} — ${f.summary}`).join('\n')}

前端架构：
- 状态管理: ${CFG.tech.frontend.jsDir}/${CFG.tech.frontend.stateFile}
- 主逻辑: ${CFG.tech.frontend.jsDir}/${CFG.tech.frontend.mainFile}

请先读现有代码，再做修改。
注意：写完后不运行测试、不做审查——交给下游 cr / test。`,
    { label: 'impl-frontend', phase: 'Implement', model: CFG.plugins.modelAllocation.opus }
  ))
}
if (otherFiles.length > 0) {
  implementors.push(() => agent(
    `根据实现计划修改其他文件。

${SUPERPOWERS_RULES}

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

phase('Verify')
const verifyResult = await agent(
  `验证代码变更是否引入错误。

${PIPELINE_CONTEXT}

需求：${requirement}

${constraints(CFG)}

验证清单（逐项核实，每项标注 PASS/FAIL 并附证据）：
- Python 语法检查实际输出
- JS 关键定义一致性
- HTML 中 onclick 引用的函数是否在 JS 文件中存在
- 文件引用路径是否有效`,
  { label: 'vr', phase: 'Verify', model: CFG.plugins.modelAllocation.sonnet }
)

return JSON.stringify({
  requirement,
  filesChanged: implPlan.filesToChange,
  keySyncPerformed: implPlan.needsKeySync,
  verification: verifyResult,
  nextSteps: '代码已实现并通过自检。建议下一步：/cr ‖ /test' + (implPlan.needsKeySync ? ' ‖ /data-guardian' : ''),
}, null, 2)

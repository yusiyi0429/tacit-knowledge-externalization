export const meta = {
  name: 'doc',
  description: '文档与代码同步检查，标记过时/遗漏内容。用法：/doc [自动检查|同步]',
  phases: [
    { title: 'Collect', detail: '收集文档声明和代码事实' },
    { title: 'Diff', detail: '逐项比对差异（verification-before-completion 驱动）' },
    { title: 'Report', detail: '输出过时/遗漏清单' },
  ],
}

// ═══════════════════════════════════════════
//  🔧 项目配置 — 新项目修改此区域即可
// ═══════════════════════════════════════════
const CFG = {
  project: { name: '隐性知识显性化', description: 'Flask + Vanilla JS 知识萃取项目' },
  tech: {
    backend: { language: 'python', framework: 'flask', dir: 'backend', entry: 'app_server.py' },
    frontend: { language: 'javascript', framework: 'vanilla', dir: 'frontend', entry: 'index.html', jsDir: 'frontend/js' },
  },
  dirs: { config: 'config', docs: 'docs', data: 'data' },
  docFiles: [
    'README.md',
    { file: 'docs/业务说明文档.md', desc: '功能描述和流程说明' },
    { file: 'docs/PRODUCTION_AUDIT.md', desc: '生产审计报告' },
  ],
  codeFacts: {
    routes: { file: 'backend/app_server.py', pattern: '@app.route' },
    keys: { file: 'backend/pipeline_artifacts.py', variable: 'STEP_OUTPUT_KEYS_BY_STEP' },
    config: { file: 'config/scenario-schema.yaml', desc: '场景知识结构定义' },
    frontendPages: { file: 'frontend/index.html', desc: '页面结构和步骤描述' },
    stepTitles: { file: 'frontend/js/app.js', pattern: 'renderStep' },
  },
  plugins: { superpowers: true, modelAllocation: { haiku: 'haiku', sonnet: 'sonnet', opus: 'opus' } },
}
// ═══════════════════════════════════════════

const FINDING_SCHEMA = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          docFile: { type: 'string' }, docClaim: { type: 'string' }, docLine: { type: 'number' },
          reality: { type: 'string' },
          status: { type: 'string', enum: ['outdated', 'missing-from-docs', 'correct', 'unverifiable'] },
          fix: { type: 'string' },
        },
        required: ['docFile', 'docClaim', 'reality', 'status', 'fix'],
      },
    },
  },
  required: ['findings'],
}

// superpowers: verification-before-completion
const DOC_RULES = `
== Superpowers 文档维护纪律 ==

**verification-before-completion 原则**（铁律）：
1. NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE。每项对比必须附证据：文档第几行说了什么 ←→ 代码第几行实际是什么。
2. outdated: 文档写的和代码事实不一致时标注 outdated。不能因为"看起来差不多"就标 correct。
3. missing-from-docs: 代码有功能但文档没提 = 文档遗漏。功能存在但文档没写 = 对用户来说功能不存在。
4. auto-fix 时只改明确过时的内容，不替用户做判断性的编辑。`

phase('Collect')
log('收集文档声明和代码事实...')

const docCollection = await parallel(
  CFG.docFiles.map(d => {
    const path = typeof d === 'string' ? d : d.file
    const desc = typeof d === 'string' ? '项目描述' : d.desc
    return () => agent(
      `读取 ${path}，提取所有关于项目功能、架构、流程、配置的声明性语句。标注每个声明所在的行号。(${desc})`,
      { label: `read-${path.replace(/[/\\]/g, '-').replace(/^./, '').slice(-20)}`, phase: 'Collect', model: CFG.plugins.modelAllocation.haiku }
    )
  })
)

const codeFacts = await agent(
  `从代码中提取可作为对照事实的信息：
${CFG.codeFacts.routes ? `- ${CFG.codeFacts.routes.file} — 所有 ${CFG.codeFacts.routes.pattern} 路由` : ''}
${CFG.codeFacts.keys ? `- ${CFG.codeFacts.keys.file} — ${CFG.codeFacts.keys.variable}` : ''}
${CFG.codeFacts.config ? `- ${CFG.codeFacts.config.file} — ${CFG.codeFacts.config.desc}` : ''}
${CFG.codeFacts.frontendPages ? `- ${CFG.codeFacts.frontendPages.file} — ${CFG.codeFacts.frontendPages.desc}` : ''}
${CFG.codeFacts.stepTitles ? `- ${CFG.codeFacts.stepTitles.file} — ${CFG.codeFacts.stepTitles.pattern} 函数` : ''}
输出结构化事实清单：路由列表、步骤定义、配置项、文件类型。每项标注 file:line。`,
  { label: 'code-facts', phase: 'Collect', model: CFG.plugins.modelAllocation.haiku }
)

phase('Diff')
const diffs = await agent(
  `逐项比对文档声明与代码事实。每项附证据。

${CFG.plugins.superpowers ? DOC_RULES : ''}

文档声明：
${docCollection.map((d, i) => `--- 来源 ${i} ---\n${d}`).join('\n\n')}

代码事实：
${codeFacts}

对比维度：路由声明、步骤描述、功能声明、配置文件声明、文件类型声明
标记：outdated（文档错误）/ missing-from-docs（代码有文档无）/ correct（一致）/ unverifiable（无法确认）
每项附 docLine + 代码行号作为证据。`,
  { label: 'diff', phase: 'Diff', schema: FINDING_SCHEMA, model: CFG.plugins.modelAllocation.sonnet }
)

phase('Report')
const outdated = diffs.findings.filter(f => f.status === 'outdated')
const missing = diffs.findings.filter(f => f.status === 'missing-from-docs')

log(`过期声明: ${outdated.length} 处`)
log(`文档遗漏: ${missing.length} 处`)

if (outdated.length > 0 && args === '同步') {
  log('正在自动同步文档...')
  await parallel(outdated.map(f => () =>
    agent(
      `修复文档过期问题。只改明确过时的内容，不替用户做判断性编辑。

文件: ${f.docFile}
原声明（行号 ${f.docLine}）: ${f.docClaim}
代码实际: ${f.reality}
修复: ${f.fix}

读取该文件，找到对应位置更新。保留其余部分不动。`,
      { label: `fix-${f.docFile.replace(/[\/\\:]/g, '-').slice(-20)}`, phase: 'Report', model: CFG.plugins.modelAllocation.sonnet }
    )
  ))
  log('文档同步完成')
}

return JSON.stringify({
  summary: {
    total: diffs.findings.length,
    outdated: outdated.length, missingFromDocs: missing.length,
    correct: diffs.findings.filter(f => f.status === 'correct').length,
  },
  details: diffs.findings,
  autoFixed: args === '同步' ? outdated.length : 0,
  tip: outdated.length > 0 && args !== '同步' ? '运行 /doc 同步 可自动修复过期文档' : undefined,
}, null, 2)

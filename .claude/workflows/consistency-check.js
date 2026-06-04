export const meta = {
  name: 'consistency-check',
  description: '前端/后端一致性校验：API路由、关键定义、CSS引用、JS模块同步。用法：/consistency-check',
  phases: [
    { title: 'Collect', detail: '收集路由、关键定义、引用' },
    { title: 'Cross-check', detail: '并行比对' },
    { title: 'Report', detail: '不一致项清单（verification-before-completion）' },
  ],
}

// ═══════════════════════════════════════════
//  🔧 项目配置 — 新项目修改此区域即可
// ═══════════════════════════════════════════
const CFG = {
  project: { name: '隐性知识显性化', description: 'Flask + Vanilla JS 知识萃取应用' },
  tech: {
    backend: { language: 'python', framework: 'flask', dir: 'backend', entry: 'app_server.py' },
    frontend: {
      language: 'javascript', framework: 'vanilla', dir: 'frontend', entry: 'index.html',
      jsDir: 'frontend/js', cssDir: 'frontend/css',
      mainFile: 'app.js', stateFile: 'state.js',
      fetchPattern: 'fetch(API_BASE +', apiBase: '/api',
    },
  },
  routeCheck: {
    backend: { decorated: '@app.route', methods: '/api/', file: 'backend/app_server.py' },
    frontend: { urls: 'frontend/js/app.js', pattern: '/api/' },
    skipPatterns: ['/api/health', '/api/llm/'],
  },
  keySync: {
    groups: [
      {
        label: 'step data keys',
        files: ['backend/pipeline_artifacts.py', 'frontend/js/state.js', 'frontend/js/app.js'],
        backendVar: 'STEP_OUTPUT_KEYS_BY_STEP',
        frontendVar: 'DOWNSTREAM_OUTPUT_KEYS',
      },
    ],
  },
  cssCheck: {
    enabled: true,
    htmlFile: 'frontend/index.html',
    cssDir: 'frontend/css',
    stepClassPrefix: 's',
  },
  plugins: { superpowers: true, modelAllocation: { haiku: 'haiku', sonnet: 'sonnet', opus: 'opus' } },
}
// ═══════════════════════════════════════════

// superpowers: verification-before-completion
const CONSISTENCY_RULES = `
== Superpowers 校验纪律 ==

**verification-before-completion 原则**（铁律）：
1. NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE。每一个"一致"或"不一致"的判断必须附实际的对比依据——你读了哪个文件的哪一行、看到了什么值、对比后的结果。
2. 不一致项必须标注：
   - 具体的不一致点（不能只说"不一致"，要说"state.js:line28 有 key X，但 app.js:line117 没有"）
   - 影响的严重程度（数据丢失 > 功能异常 > 代码冗余）
   - 修复建议（具体到改哪个文件的哪一行）
3. CRITICAL 规则：如果 state.js 和 app.js 的 DOWNSTREAM_OUTPUT_KEYS 不同 → CRITICAL BUG。这两个必须逐字符相同。`

phase('Collect')
const routeFile = CFG.routeCheck.backend?.file || `${CFG.tech.backend.dir}/${CFG.tech.backend.entry}`
const frontendFetchFile = CFG.routeCheck.frontend?.urls || `${CFG.tech.frontend.jsDir}/${CFG.tech.frontend.mainFile}`
const skip = (CFG.routeCheck.skipPatterns || []).map(s => `'${s}'`).join(', ')
const routePat = CFG.routeCheck.backend?.decorated || '@app.route'
const fetchPat = CFG.routeCheck.frontend?.pattern || '/api/'

const routeCheck = await agent(
  `Read and compare API route definitions. 每项对比附实际证据。

1. Read ${routeFile} — grep for '${routePat}' lines, extract all ${fetchPat} routes
2. Read ${frontendFetchFile} — grep for '${fetchPat}' patterns, extract all fetch URLs
3. List routes in backend but NOT called by frontend (dead code) — 标注具体函数名和行号
4. List routes called by frontend but NOT in backend (broken feature) — 标注具体调用位置
Skip: ${skip}

${CFG.plugins.superpowers ? CONSISTENCY_RULES : ''}`,
  { label: 'routes', phase: 'Collect', model: CFG.plugins.modelAllocation.sonnet }
)

const keyResults = []
for (const group of CFG.keySync?.groups || []) {
  const kr = await agent(
    `Check key definition consistency. 逐文件逐行对比，附实际内容。

${CFG.plugins.superpowers ? CONSISTENCY_RULES : ''}

Check that these files define the same set of keys:
${group.files.map(f => `- ${f}`).join('\n')}

Backend variable: ${group.backendVar || 'N/A'}
Frontend variable: ${group.frontendVar || 'N/A'}

CRITICAL rule: 如果 state.js 和 app.js 的 DOWNSTREAM_OUTPUT_KEYS 不逐字符相同 → CRITICAL BUG。

Report each mismatch with file:line and severity.`,
    { label: `keys-${group.label.replace(/\s+/g, '-')}`, phase: 'Collect', model: CFG.plugins.modelAllocation.sonnet }
  )
  keyResults.push({ group: group.label, result: kr })
}

const cssResult = CFG.cssCheck?.enabled ? await agent(
  `Check CSS class naming consistency. 每项附实际行号。

${CFG.plugins.superpowers ? CONSISTENCY_RULES : ''}

1. Read ${CFG.cssCheck.htmlFile || `${CFG.tech.frontend.dir}/${CFG.tech.frontend.entry}`} — extract class="${CFG.cssCheck.stepClassPrefix}N-" patterns
2. Read ${CFG.cssCheck.cssDir || `${CFG.tech.frontend.cssDir}/style.css`} or equivalent — CSS rules for those classes
3. Read ${CFG.tech.frontend.jsDir}/${CFG.tech.frontend.mainFile} — element IDs referencing those classes

Report orphaned rules, missing IDs, and step numbering inconsistencies with exact file:line.`,
  { label: 'css', phase: 'Collect', model: CFG.plugins.modelAllocation.haiku }
) : '(CSS check disabled)'

phase('Cross-check')
log(`Routes: ${routeCheck?.length || 'N/A'}`)
keyResults.forEach(kr => log(`Keys ${kr.group}: ${kr.result?.length || 'OK'}`))
log(`CSS: ${cssResult?.length || 'N/A'}`)

phase('Report')
return JSON.stringify({ routes: routeCheck, keys: keyResults, css: cssResult }, null, 2)

export const meta = {
  name: 'bug-hunt',
  description: '全量代码库扫描，多维度并行查找潜在缺陷。用法：/bug-hunt [scope=all|backend|frontend]',
  phases: [
    { title: 'Discover', detail: '多维度并行扫描代码库' },
    { title: 'Verify', detail: '交叉验证发现（降假阳性）' },
    { title: 'Report', detail: '优先级排序输出' },
  ],
}

const CFG = {
  project: { name: '隐性知识显性化', description: 'Flask + Vanilla JS 知识萃取流水线应用' },
  tech: {
    backend: { language: 'python', framework: 'flask', dir: 'backend', glob: 'backend/**/*.py' },
    frontend: { language: 'javascript', framework: 'vanilla', dir: 'frontend', jsDir: 'frontend/js', glob: 'frontend/js/*.js' },
  },
  dirs: { config: 'config' },
  codeConventions: {
    htmlEscape: 'escapeHtml()', checkXSS: true, checkPathTraversal: true,
    pathSafety: 'safe_workspace_path()', basenameFn: 'basename_only()', checkSQLInjection: false,
  },
  riskRules: [
    { name: '路径穿越', severity: 'critical', desc: '文件操作必须使用安全路径函数' },
    { name: '数据 key 同步', severity: 'critical', desc: '关键 key 在前端/后端三处定义需一致' },
    { name: 'MergedCell', severity: 'high', desc: 'openpyxl 写入前必须先解除合并' },
    { name: 'LLM JSON 降级', severity: 'medium', desc: 'LLM 输出解析需要多层 try/catch（至少 6 层降级）' },
    { name: '路由覆盖', severity: 'high', desc: '同名函数/路由静默覆盖' },
  ],
  specialPatterns: ['MergedCell', 'unmerge_cells', 'innerHTML', 'escapeHtml', 'shell=True', 'subprocess'],
  plugins: { superpowers: true, modelAllocation: { haiku: 'haiku', sonnet: 'sonnet', opus: 'opus' } },
}

const PIPELINE_CONTEXT = `
== 天工团队流水线（独立巡检模式）==

[bug-hunt ‖ data-guardian] → 发现问题 → dev 修复 → cr → ship-check

你是 bug-hunt 角色——独立触发，不在主线流水线内。
- 与 cr 互补：你查全量，CR 只查 diff
- 可与 data-guardian 并行
- 发现的问题交 /dev 修复，修复后由 cr 检查（不是你复检）`

const BUG_SCHEMA = {
  type: 'object',
  properties: {
    bugs: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          file: { type: 'string' }, line: { type: 'number' },
          severity: { type: 'string', enum: ['critical', 'high', 'medium', 'low', 'info'] },
          category: { type: 'string', enum: ['logic', 'security', 'async', 'type', 'edge-case', 'resource', 'consistency'] },
          title: { type: 'string' }, detail: { type: 'string' },
          code: { type: 'string' }, fix: { type: 'string' },
        },
        required: ['file', 'severity', 'category', 'title', 'detail'],
      },
    },
  },
  required: ['bugs'],
}

const VERDICT_SCHEMA = {
  type: 'object',
  properties: {
    isReal: { type: 'boolean' }, confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
    actualSeverity: { type: 'string', enum: ['critical', 'high', 'medium', 'low', 'info'] },
    explanation: { type: 'string' },
  },
  required: ['isReal', 'confidence', 'explanation'],
}

const HUNTER_RULES = `
== Superpowers 缺陷猎手纪律 ==

1. NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST.
2. 每个发现必须回答「为什么这里会出问题？」而不仅是「这里看起来不对」。
3. 如果一个现象背后可能有多个原因，逐个分析排除条件。
4. 每个发现标注你读了哪段代码（exact file:line）得出结论。
5. 对 critical/high 发现，从「bug是否真实存在」和「用户是否会实际触发」两个角度独立确认。
6. 任一角度存疑 → 降级。宁可漏报低优，不可误报高优。`

function buildContext(cfg) {
  const lines = [`项目：${cfg.project.name}（${cfg.project.description}）`]
  lines.push(`后端: ${cfg.tech.backend.language}/${cfg.tech.backend.framework} (${cfg.tech.backend.dir}/)`)
  lines.push(`前端: ${cfg.tech.frontend.language} (${cfg.tech.frontend.jsDir}/)`)
  lines.push('\n关键风险:')
  cfg.riskRules.forEach(r => lines.push(`- ${r.severity}: ${r.name} — ${r.desc}`))
  return lines.join('\n')
}

const CTX = buildContext(CFG)

phase('Discover')
const scope = args || 'all'
log(`扫描范围: ${scope}`)

const [backends, fronts, security, resources] = await parallel([
  () => agent(
    `全量扫描后端 ${CFG.tech.backend.language} 代码，查找逻辑缺陷。

${CFG.plugins.superpowers ? HUNTER_RULES : ''}
${PIPELINE_CONTEXT}

${CTX}

文件范围：${scope === 'frontend' ? '跳过' : `${CFG.tech.backend.glob}`}

重点：
1. 空值处理 — None 引用、dict.get() 缺省值
2. 异常捕获 — try/catch 是否过于宽泛、遗漏关键异常
3. 资源泄漏 — 文件句柄、workbook 未 close
4. 并发 — 全局变量修改（${CFG.tech.backend.framework} 默认线程不安全）
5. 逻辑 — 条件取反、越界、类型误判
6. LLM 解析 — JSON 降级路径是否兜底

对 high/critical 发现必须追溯到上游调用链。`,
    { label: 'bugs-backend', phase: 'Discover', schema: BUG_SCHEMA, model: CFG.plugins.modelAllocation.sonnet }
  ),
  () => agent(
    `全量扫描前端 ${CFG.tech.frontend.language} 代码，查找逻辑缺陷。

${CFG.plugins.superpowers ? HUNTER_RULES : ''}
${PIPELINE_CONTEXT}

${CTX}

文件范围：${scope === 'backend' ? '跳过' : `${CFG.tech.frontend.glob}`}

重点：状态管理、DOM 操作、事件绑定、异步错误、数据一致性、渲染性能
对 high/critical 发现必须追溯到数据流上游。`,
    { label: 'bugs-frontend', phase: 'Discover', schema: BUG_SCHEMA, model: CFG.plugins.modelAllocation.sonnet }
  ),
  () => agent(
    `安全扫描全量代码。${CFG.plugins.superpowers ? HUNTER_RULES : ''}

${PIPELINE_CONTEXT}
${CTX}
文件范围：全部
${CFG.codeConventions.checkXSS ? '\nXSS: innerHTML/outerHTML/insertAdjacentHTML 未转义' : ''}
${CFG.codeConventions.checkPathTraversal ? '\n路径穿越: 文件路径拼接' : ''}
命令注入: subprocess/os.system/shell=True
密钥泄露、JSON 注入、SSRF
每发现标注攻击向量和触发条件。`,
    { label: 'bugs-security', phase: 'Discover', schema: BUG_SCHEMA, model: CFG.plugins.modelAllocation.opus }
  ),
  () => agent(
    `检查资源管理和配置问题。${CFG.plugins.superpowers ? HUNTER_RULES : ''}

${PIPELINE_CONTEXT}
${CTX}
范围：${CFG.dirs.config}/、${CFG.tech.backend.dir}/
重点：配置降级、硬编码、临时文件清理、依赖缺失、平台兼容、限流缺失`,
    { label: 'bugs-resource', phase: 'Discover', schema: BUG_SCHEMA, model: CFG.plugins.modelAllocation.haiku }
  ),
])

phase('Verify')
const allBugs = [backends, fronts, security, resources].filter(Boolean).flatMap(r => r?.bugs || [])
log(`发现 ${allBugs.length} 个潜在问题`)

const criticalHigh = allBugs.filter(b => b.severity === 'critical' || b.severity === 'high')
const verified = criticalHigh.length > 0
  ? (await parallel(criticalHigh.map((b, i) => () =>
      agent(
        `Adversarially verify this bug from TWO angles:

ANGLE 1 - 「这个 bug 真实存在吗？」：读代码确认调用链。有没有已经被处理了？

ANGLE 2 - 「触发条件用户实际会遇到吗？」：需要什么输入/操作才能触发？在实际使用中概率多大？

File: ${b.file}:${b.line}
Title: ${b.title}
Detail: ${b.detail}
Code: ${b.code || 'N/A'}

两个角度都确认属实才设 isReal=true。任一角度存疑 → isReal=false。`,
        { label: `verify-${i}`, phase: 'Verify', schema: VERDICT_SCHEMA, model: CFG.plugins.modelAllocation.sonnet }
      )
    ))).filter(Boolean)
  : []

const confirmedCritical = verified.filter(v => v.isReal && v.actualSeverity === 'critical')
const confirmedHigh = verified.filter(v => v.isReal && (v.actualSeverity === 'high' || v.actualSeverity === 'critical'))

phase('Report')
const byCat = {}
allBugs.forEach(b => { byCat[b.category] = (byCat[b.category] || 0) + 1 })

return JSON.stringify({
  summary: {
    total: allBugs.length,
    bySeverity: {
      critical: confirmedCritical.length, high: confirmedHigh.length,
      medium: allBugs.filter(b => b.severity === 'medium').length,
      low: allBugs.filter(b => b.severity === 'low').length,
    },
    byCategory: byCat,
  },
  blockers: confirmedCritical.map(v => ({
    finding: criticalHigh[verified.indexOf(v)]?.title || '',
    explanation: v.explanation,
  })),
  allBugs: allBugs.map(b => {
    const vIdx = criticalHigh.indexOf(b)
    const v = vIdx >= 0 ? verified[vIdx] : null
    return { ...b, verified: v ? v.isReal : null, verificationNote: v ? v.explanation : '(not verified)' }
  }),
  nextSteps: confirmedCritical.length > 0 || confirmedHigh.length > 0
    ? '发现 blocker → 交 /dev 修复 → /cr 检查修复 → /ship-check'
    : '无 blocker。low/medium 可选修复。',
}, null, 2)

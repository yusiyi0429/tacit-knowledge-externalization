export const meta = {
  name: 'review-changes',
  description: 'Git diff 变更全面审查：并行代码检查 + 安全审查 + 简化建议，输出优先级报告。用法：/review-changes',
  phases: [
    { title: 'Diff', detail: '获取并分段工作树变更' },
    { title: 'Review', detail: '并行：Bug / 安全 / 简化（requesting-code-review 驱动）' },
    { title: 'Verdict', detail: '交叉验证 + 优先级排序（verification-before-completion）' },
  ],
}

// ═══════════════════════════════════════════
//  🔧 项目配置 — 新项目修改此区域即可
// ═══════════════════════════════════════════
const CFG = {
  project: {
    name: '隐性知识显性化',
    description: 'Flask + Vanilla JS 全栈应用，4 步流水线实现知识萃取与转化',
  },
  tech: {
    backend: { language: 'python', framework: 'flask', dir: 'backend', entry: 'app_server.py' },
    frontend: { language: 'javascript', framework: 'vanilla', dir: 'frontend', jsDir: 'frontend/js' },
  },
  codeConventions: {
    htmlEscape: 'escapeHtml()', checkXSS: true, checkPathTraversal: true,
    pathSafety: 'safe_workspace_path()', basenameFn: 'basename_only()',
  },
  riskRules: [
    { name: '数据键同步', severity: 'critical', backend: 'pipeline_artifacts.py STEP_OUTPUT_KEYS_BY_STEP',
      frontendKeys: ['state.js: DOWNSTREAM_OUTPUT_KEYS', 'app.js: DOWNSTREAM_OUTPUT_KEYS'] },
    { name: '路由覆盖', severity: 'high', desc: 'Flask 不检查重复 route，后定义的静默覆盖前一个' },
    { name: 'LLM JSON 降级', severity: 'medium', desc: 'LLM 输出不可信，JSON 解析需要多层 try/catch 降级' },
  ],
  checkRouteConsistency: true,
  checkFileRefs: true,
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
          file: { type: 'string' }, line: { type: 'number' },
          severity: { type: 'string', enum: ['critical', 'high', 'medium', 'low', 'info'] },
          category: { type: 'string', enum: ['bug', 'security', 'simplification', 'style', 'consistency'] },
          title: { type: 'string' }, detail: { type: 'string' },
        },
        required: ['file', 'severity', 'title', 'detail'],
      },
    },
  },
  required: ['findings'],
}

const VERDICT_SCHEMA = {
  type: 'object',
  properties: {
    isReal: { type: 'boolean' },
    confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
    actualSeverity: { type: 'string', enum: ['critical', 'high', 'medium', 'low', 'info'] },
    explanation: { type: 'string' },
  },
  required: ['isReal', 'confidence', 'explanation'],
}

// superpowers: requesting-code-review + receiving-code-review + verification-before-completion
const REVIEWER_RULES = `
== Superpowers 审查纪律 ==

**requesting-code-review 原则**：
1. Review early, review often。每个变更在进入下一个阶段前必须经过审查。
2. 审查者只看工作产物，不看思考过程。给他精确构造的上下文，不要把你自己的会话历史喂进去。

**verification-before-completion 原则**：
3. 铁律：没有验证证据 = 没有完成。每个 claiming 都附上实际的命令输出。
4. Verdict 阶段的交叉验证：对每个 critical/high 发现，分别从「这个发现确实存在吗？」和「严重程度真的这么高吗？」两个角度独立验证。两个角度都确认才标记为 confirmed。

**系统化审查**：
5. 发现的每个问题标注：file + line + severity + evidence（你读了哪段代码得出这个结论）
6. 未找到的问题不如一个假阳性危害大——宁可漏报低优，不可误报高优。`

function buildProjectContext(cfg) {
  const lines = [
    `项目：${cfg.project.name}（${cfg.project.description}）`,
    `后端: ${cfg.tech.backend.language}/${cfg.tech.backend.framework} 在 ${cfg.tech.backend.dir}/`,
    `前端: ${cfg.tech.frontend.language}（${cfg.tech.frontend.framework}）在 ${cfg.tech.frontend.dir}/${cfg.tech.frontend.jsDir}/`,
  ]
  const checks = []
  if (cfg.codeConventions.checkXSS) checks.push(`XSS in render functions，使用 ${cfg.codeConventions.htmlEscape}`)
  if (cfg.codeConventions.checkPathTraversal) checks.push(`路径穿越防护 in file ops，使用 ${cfg.codeConventions.pathSafety} / ${cfg.codeConventions.basenameFn}`)
  if (cfg.riskRules.length) checks.push(...cfg.riskRules.map(r => `${r.severity}: ${r.name} — ${r.desc}`))
  if (checks.length) lines.push('关键检查项:', ...checks.map(c => `- ${c}`))
  return lines.join('\n')
}

const PROJECT = buildProjectContext(CFG)

phase('Diff')
const diffResult = await agent(
  `Run "git diff" and "git diff --cached" to get all working tree changes in ${CFG.project.name}.

${PROJECT}

List each changed file with a 1-sentence summary of what changed.
Also check: are there files that should NOT be changed (secrets, .local configs)?
Report the file list and summaries.`,
  { label: 'get-diff', phase: 'Diff', model: CFG.plugins.modelAllocation.haiku }
)

phase('Review')
const [bugs, security, simplify] = await parallel([
  () => agent(
    `审查 ${CFG.project.name} 代码变更。这是 ${CFG.tech.backend.framework} + ${CFG.tech.frontend.framework} 项目。

${CFG.plugins.superpowers ? REVIEWER_RULES : ''}

${PROJECT}

Review ALL changed files for:
1. Logic bugs — null handling, edge cases, async/await errors, state management issues
2. Regression risks — could this change break existing functionality?
3. ${CFG.tech.backend.language}-specific: error handling, resource management, thread safety
4. ${CFG.tech.frontend.language}-specific: DOM checks, async errors, event binding
5. Route/file consistency — frontend fetch URLs must match backend definitions

每个发现必须标注 file + line + 证据（你读了哪段代码得出结论）。
Focus on REAL bugs, not style preferences. 宁可漏报低优，不可误报高优。`,
    { label: 'code-review', phase: 'Review', schema: FINDING_SCHEMA, model: CFG.plugins.modelAllocation.opus }
  ),
  () => agent(
    `Security audit on ${CFG.project.name}（${CFG.tech.backend.framework} + ${CFG.tech.frontend.framework}）.

${CFG.plugins.superpowers ? REVIEWER_RULES : ''}

${PROJECT}

Check ALL changed files for:
${CFG.codeConventions.checkPathTraversal ? '1. Path traversal: file path sanitization, directory traversal via "../"' : ''}
${CFG.codeConventions.checkXSS ? '2. XSS: innerHTML assignments, unescaped user content, lack of HTML escaping' : ''}
3. Command injection: subprocess calls, shell=True, unsanitized user input
4. File operations: validation, size limits, temp file cleanup
5. Secret exposure: API keys in logs, error messages, or client responses
6. Injection: untrusted input fed to parsers without sanitization

每个发现标注具体的攻击向量和 file + line。`,
    { label: 'security-review', phase: 'Review', schema: FINDING_SCHEMA, model: CFG.plugins.modelAllocation.opus }
  ),
  () => agent(
    `Review ${CFG.project.name} changes for simplification and reuse.

${CFG.plugins.superpowers ? REVIEWER_RULES : ''}

${PROJECT}

Look for:
1. Duplicated logic that could be extracted
2. Overly complex conditionals
3. Dead code or unreachable branches
4. Over-abstraction — helpers used only once
5. Commented-out code to remove
6. Magic numbers/strings that should be constants

Only flag issues in CHANGED files. Be actionable and specific.`,
    { label: 'simplify', phase: 'Review', schema: FINDING_SCHEMA, model: CFG.plugins.modelAllocation.sonnet }
  ),
])

phase('Verdict')
const allFindings = [bugs, security, simplify].filter(Boolean).flatMap(r => r?.findings || [])
const criticalAndHigh = allFindings.filter(f => f.severity === 'critical' || f.severity === 'high')

// 交叉验证：分别从 existence 和 severity 两个角度独立验证
const verified = criticalAndHigh.length > 0
  ? (await parallel(criticalAndHigh.map(f => () =>
      agent(
        `Adversarially verify this finding from TWO independent angles:

ANGLE 1 - 「这个发现真实存在吗？」：读相关代码确认描述是否准确。有没有可能代码已经被 else 分支/guard clause/catch block 处理了？

ANGLE 2 - 「严重程度真是 ${f.severity} 吗？」：在用户实际使用中触发这个问题的概率有多大？即使触发了，用户感知到的伤害是什么？

Finding: ${f.title}
File: ${f.file}:${f.line}
Detail: ${f.detail}

两个角度都确认属实才设 isReal=true 和 actualSeverity。
任一角度存疑就设 isReal=false。
Default to isReal=false if uncertain.`,
        { label: `verify-${f.file}`, phase: 'Verdict', schema: VERDICT_SCHEMA, model: CFG.plugins.modelAllocation.sonnet }
      )
    ))).filter(Boolean)
  : []

const confirmedCritical = verified.filter(v => v.isReal && v.actualSeverity === 'critical')
const confirmedHigh = verified.filter(v => v.isReal && (v.actualSeverity === 'high' || v.actualSeverity === 'critical'))

const report = {
  summary: {
    total: allFindings.length,
    critical: confirmedCritical.length, high: confirmedHigh.length,
    medium: allFindings.filter(f => f.severity === 'medium').length,
    low: allFindings.filter(f => f.severity === 'low').length,
    sources: {
      bugs: bugs?.findings?.length || 0,
      security: security?.findings?.length || 0,
      simplify: simplify?.findings?.length || 0,
    },
  },
  blockers: confirmedCritical.map(v => v.explanation),
  confirmedHigh: confirmedHigh.map(v => v.explanation),
  allFindings: allFindings.map(f => ({
    ...f,
    verified: verified.find(v => v.explanation?.includes(f.title?.slice(0, 20)))?.isReal ?? null,
    verificationNote: verified.find(v => v.explanation?.includes(f.title?.slice(0, 20)))?.explanation ?? '',
  })),
}

return JSON.stringify(report, null, 2)

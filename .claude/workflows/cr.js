export const meta = {
  name: 'cr',
  description: 'diff 三维审查 + 对抗式交叉验证。用法：/cr [--fix] [--comment]',
  phases: [
    { title: 'Collect', detail: '收集当前 diff' },
    { title: 'Review', detail: '三维度并行审查（正确性 ‖ 安全性 ‖ 质量）' },
    { title: 'Verify', detail: '对抗式交叉验证（降假阳性）' },
    { title: 'Report', detail: '输出审查结论' },
  ],
}

const CFG = {
  project: { name: '隐性知识显性化', description: 'Flask + Vanilla JS 知识萃取流水线' },
  tech: {
    backend: { language: 'python', framework: 'flask', dir: 'backend', entry: 'app_server.py' },
    frontend: { language: 'javascript', framework: 'vanilla', dir: 'frontend', jsDir: 'frontend/js' },
  },
  codeConventions: {
    htmlEscape: 'escapeHtml()', checkXSS: true, checkPathTraversal: true,
    pathSafety: 'safe_workspace_path()', basenameFn: 'basename_only()',
  },
  plugins: { superpowers: true, modelAllocation: { haiku: 'haiku', sonnet: 'sonnet', opus: 'opus' } },
}

const FINDING_SCHEMA = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          file: { type: 'string' }, line: { type: 'number' },
          severity: { type: 'string', enum: ['critical', 'high', 'medium', 'low'] },
          dimension: { type: 'string', enum: ['correctness', 'security', 'quality'] },
          title: { type: 'string' }, detail: { type: 'string' }, fix: { type: 'string' },
          evidence: { type: 'string' },
        },
        required: ['file', 'severity', 'dimension', 'title', 'detail', 'evidence'],
      },
    },
  },
  required: ['findings'],
}

const VERDICT_SCHEMA = {
  type: 'object',
  properties: {
    isReal: { type: 'boolean' }, confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
    actualSeverity: { type: 'string', enum: ['critical', 'high', 'medium', 'low'] },
    explanation: { type: 'string' },
  },
  required: ['isReal', 'confidence', 'explanation'],
}

const PIPELINE_CONTEXT = `
流水线位置：dev → [cr ‖ test ‖ data-guardian?] → [vr ‖ doc] → ship-check
你在 dev 之后，与 test / data-guardian 并行。问题交 /dev 修复。`

phase('Collect')
const diffInfo = await agent(
  `收集当前 git diff 的摘要信息。

运行 git diff --stat 和 git diff，输出：
1. 变更文件列表
2. 每个文件的变更行数
3. diff 完整内容`,
  { label: 'collect-diff', phase: 'Collect', model: CFG.plugins.modelAllocation.haiku }
)

phase('Review')
const [correctness, security, quality] = await parallel([
  () => agent(
    `审查 diff 的**正确性**维度。

${CFG.plugins.superpowers ? 'superpowers: 根本原因优先，先验证再声明。' : ''}

${PIPELINE_CONTEXT}

diff 内容：
${diffInfo}

重点检查：
1. 逻辑正确性：条件判断、边界情况(null/undefined/空集/极值)、类型错误
2. 竞态条件：async/await 时序、并发安全
3. 跨文件一致性：新增/修改的 API 接口前后端是否匹配
4. 数据流：值从哪来、传到哪去、中间是否丢失

每个发现附 file:line + 证据（你读了哪段代码得出结论）。`,
    { label: 'review-correctness', phase: 'Review', schema: FINDING_SCHEMA, model: CFG.plugins.modelAllocation.opus }
  ),
  () => agent(
    `审查 diff 的**安全性**维度。

${CFG.plugins.superpowers ? 'superpowers: 根本原因优先，先验证再声明。' : ''}

${PIPELINE_CONTEXT}

diff 内容：
${diffInfo}

重点检查：
1. 注入风险：SQL、XSS(innerHTML)、命令注入
2. 敏感数据泄露：日志、错误消息、响应体
3. 权限校验：未受保护的操作
4. 第三方输入是否验证清理

每个发现附 file:line + 攻击向量 + 触发条件。`,
    { label: 'review-security', phase: 'Review', schema: FINDING_SCHEMA, model: CFG.plugins.modelAllocation.opus }
  ),
  () => agent(
    `审查 diff 的**代码质量**维度。

${PIPELINE_CONTEXT}

diff 内容：
${diffInfo}

重点检查：
1. 重复逻辑可复用？过度设计可简化？
2. 不必要的抽象或依赖？
3. 命名清晰准确？
4. 代码是否符合项目约定（${CFG.codeConventions.htmlEscape}, ${CFG.codeConventions.pathSafety}）

每个发现附 file:line + 改进建议。`,
    { label: 'review-quality', phase: 'Review', schema: FINDING_SCHEMA, model: CFG.plugins.modelAllocation.sonnet }
  ),
])

phase('Verify')
const allFindings = [correctness, security, quality].filter(Boolean).flatMap(r => r?.findings || [])
const criticalHigh = allFindings.filter(f => f.severity === 'critical' || f.severity === 'high')
log(`发现 ${allFindings.length} 个问题，其中 critical/high ${criticalHigh.length} 个`)

const verified = criticalHigh.length > 0
  ? (await parallel(criticalHigh.map((f, i) => () =>
      agent(
        `对抗式交叉验证。从两个独立角度判断此发现是否真实：

角度1 - 存在性：读代码确认描述准确——是否已被 else/guard/catch 处理？
角度2 - 严重度：实际触发概率多大？触发后用户可感知伤害？

File: ${f.file}:${f.line}
Title: ${f.title}
Detail: ${f.detail}
Evidence: ${f.evidence}

两个角度都确认才设 isReal=true。任一存疑 → isReal=false 或降级。`,
        { label: `verify-${i}`, phase: 'Verify', schema: VERDICT_SCHEMA, model: CFG.plugins.modelAllocation.sonnet }
      )
    ))).filter(Boolean)
  : []

phase('Report')
const confirmedFindings = allFindings.map(f => {
  const idx = criticalHigh.indexOf(f)
  const v = idx >= 0 ? verified[idx] : null
  return { ...f, verified: v ? v.isReal : null, adjustedSeverity: v ? v.actualSeverity : f.severity }
})

const blockers = confirmedFindings.filter(f => f.verified !== false && (f.adjustedSeverity === 'critical' || f.adjustedSeverity === 'high'))

return JSON.stringify({
  summary: {
    total: allFindings.length,
    byDimension: {
      correctness: allFindings.filter(f => f.dimension === 'correctness').length,
      security: allFindings.filter(f => f.dimension === 'security').length,
      quality: allFindings.filter(f => f.dimension === 'quality').length,
    },
    bySeverity: {
      critical: confirmedFindings.filter(f => f.adjustedSeverity === 'critical').length,
      high: confirmedFindings.filter(f => f.adjustedSeverity === 'high').length,
      medium: confirmedFindings.filter(f => f.adjustedSeverity === 'medium').length,
      low: confirmedFindings.filter(f => f.adjustedSeverity === 'low').length,
    },
    blockers: blockers.length,
  },
  findings: confirmedFindings,
  verdict: blockers.length === 0 ? '通过' : `需修复后通过（${blockers.length} 个 blocker）→ 修复交 /dev`,
}, null, 2)

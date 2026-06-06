export const meta = {
  name: 'data-guardian',
  description: '数据契约/状态持久化/schema 一致性专职守护。用法：/data-guardian <变更范围或数据层>',
  phases: [
    { title: 'Scope', detail: '锁定变更涉及的数据流' },
    { title: 'Audit', detail: '并行审计四维度' },
    { title: 'Verify', detail: '交叉确认不一致点' },
    { title: 'Report', detail: '输出守护报告' },
  ],
}

const CFG = {
  project: { name: '隐性知识显性化', description: 'Flask + Vanilla JS 知识萃取流水线' },
  tech: {
    backend: { language: 'python', dir: 'backend' },
    frontend: { language: 'javascript', dir: 'frontend', jsDir: 'frontend/js' },
  },
  contractFiles: {
    stepKeys: ['backend/pipeline_artifacts.py', 'frontend/js/state.js', 'frontend/js/app.js'],
    keyPatterns: ['STEP_OUTPUT_KEYS_BY_STEP', 'DOWNSTREAM_OUTPUT_KEYS', 'PIPELINE_OUTPUT_KEYS'],
  },
  plugins: { modelAllocation: { haiku: 'haiku', sonnet: 'sonnet', opus: 'opus' } },
}

const FINDING_SCHEMA = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          fileA: { type: 'string' }, lineA: { type: 'number' },
          fileB: { type: 'string' }, lineB: { type: 'number' },
          severity: { type: 'string', enum: ['critical', 'high', 'medium', 'low'] },
          dimension: { type: 'string', enum: ['contract', 'persistence', 'identifier', 'schema'] },
          title: { type: 'string' },
          valueA: { type: 'string' }, valueB: { type: 'string' },
          fix: { type: 'string' },
        },
        required: ['severity', 'dimension', 'title', 'valueA', 'valueB'],
      },
    },
  },
  required: ['findings'],
}

const PIPELINE_CONTEXT = `
流水线位置：dev → [cr ‖ test ‖ data-guardian?] → [vr ‖ doc] → ship-check
你在 dev 之后，与 cr / test 并行（条件触发）。数据契约问题交 /dev 修复。`

phase('Scope')
const scope = args || 'full'
log(`审计范围: ${scope}`)

const scopeInfo = await agent(
  `锁定本次变更涉及的数据流。

范围：${scope}

项目：${CFG.project.name}

1. 读取 git diff --stat 了解变更文件
2. 识别哪些数据字段/状态/存储被读写
3. 列出需要对比的跨文件数据契约点

关键契约文件：
${CFG.contractFiles.stepKeys.map(f => `- ${f}`).join('\n')}
Key 模式：${CFG.contractFiles.keyPatterns.join(', ')}

输出：数据流清单 + 需要对比的契约点`,
  { label: 'scope', phase: 'Scope', model: CFG.plugins.modelAllocation.haiku }
)

phase('Audit')
const [contract, persistence, identifiers, schema] = await parallel([
  () => agent(
    `审计数据契约一致性。

${PIPELINE_CONTEXT}

范围信息：
${scopeInfo}

重点：
1. 前后端字段名、类型、结构是否对齐（API 请求/响应）
2. 一处改了字段名，所有读写方是否同步更新
3. 可选/必填、默认值在生产方与消费方是否一致

每个发现附：file:line + 实际值对比。不一致导致数据静默丢失标 critical。`,
    { label: 'audit-contract', phase: 'Audit', schema: FINDING_SCHEMA, model: CFG.plugins.modelAllocation.sonnet }
  ),
  () => agent(
    `审计状态持久化完整性。

${PIPELINE_CONTEXT}

范围信息：
${scopeInfo}

重点：
1. 保存与恢复是否对称（存了什么就能取回什么）
2. 切换/刷新/重入后状态是否丢失
3. 自动保存是否覆盖了不该覆盖的字段

每个发现附：file:line + 实际值对比。`,
    { label: 'audit-persistence', phase: 'Audit', schema: FINDING_SCHEMA, model: CFG.plugins.modelAllocation.sonnet }
  ),
  () => agent(
    `审计关键标识符跨层同步。

${PIPELINE_CONTEXT}

关键契约文件：
${CFG.contractFiles.stepKeys.map(f => `- ${f}`).join('\n')}
Key 模式：${CFG.contractFiles.keyPatterns.join(', ')}

任务：逐文件读取 key 定义，逐字符对比是否一致。
不一致会导致数据静默丢失 → 标 critical。

每个发现附：fileA:lineA ↔ fileB:lineB + 实际值。`,
    { label: 'audit-identifiers', phase: 'Audit', schema: FINDING_SCHEMA, model: CFG.plugins.modelAllocation.sonnet }
  ),
  () => agent(
    `审计 Schema 演进与迁移兼容性。

${PIPELINE_CONTEXT}

范围信息：
${scopeInfo}

重点：
1. 存储结构变更是否向后兼容（老数据能否读）
2. 是否有迁移路径，或对缺失字段的降级处理
3. 持久化文件的损坏/并发写防护

每个发现附：file:line + 风险说明。`,
    { label: 'audit-schema', phase: 'Audit', schema: FINDING_SCHEMA, model: CFG.plugins.modelAllocation.haiku }
  ),
])

phase('Verify')
const allFindings = [contract, persistence, identifiers, schema].filter(Boolean).flatMap(r => r?.findings || [])
const criticals = allFindings.filter(f => f.severity === 'critical')
log(`发现 ${allFindings.length} 个数据风险，其中 critical ${criticals.length} 个`)

const verifiedCriticals = criticals.length > 0
  ? (await parallel(criticals.map((f, i) => () =>
      agent(
        `确认此 critical 发现是否真实：数据静默丢失/契约断裂是否确实会发生？

${f.title}
A: ${f.fileA || ''}:${f.lineA || ''} → ${f.valueA}
B: ${f.fileB || ''}:${f.lineB || ''} → ${f.valueB}

读代码确认：1) 对比值是否确实不同 2) 不同是否真的导致数据丢失

输出：{ confirmed: bool, explanation: string }`,
        { label: `verify-critical-${i}`, phase: 'Verify', model: CFG.plugins.modelAllocation.sonnet }
      )
    ))).filter(Boolean)
  : []

phase('Report')
return JSON.stringify({
  summary: {
    total: allFindings.length,
    byDimension: {
      contract: allFindings.filter(f => f.dimension === 'contract').length,
      persistence: allFindings.filter(f => f.dimension === 'persistence').length,
      identifier: allFindings.filter(f => f.dimension === 'identifier').length,
      schema: allFindings.filter(f => f.dimension === 'schema').length,
    },
    bySeverity: {
      critical: criticals.length,
      high: allFindings.filter(f => f.severity === 'high').length,
      medium: allFindings.filter(f => f.severity === 'medium').length,
      low: allFindings.filter(f => f.severity === 'low').length,
    },
  },
  findings: allFindings,
  verdict: criticals.length > 0
    ? `发现 ${criticals.length} 处 critical（数据静默丢失/契约断裂）→ 修复交 /dev`
    : allFindings.filter(f => f.severity === 'high').length > 0
      ? `发现 ${allFindings.filter(f => f.severity === 'high').length} 处 high 风险 → 修复交 /dev`
      : '契约一致',
}, null, 2)

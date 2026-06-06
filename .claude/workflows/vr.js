export const meta = {
  name: 'vr',
  description: '启动应用走核心路径做动态验证。用法：/vr <受影响的路径或变更>',
  phases: [
    { title: 'Target', detail: '确定验证目标（受影响的用户路径）' },
    { title: 'Start', detail: '启动应用，确认无启动错误' },
    { title: 'Run', detail: '走核心路径，记录实际行为' },
    { title: 'Report', detail: '输出运行验证报告' },
  ],
}

const CFG = {
  project: { name: '隐性知识显性化', description: 'Flask + Vanilla JS 知识萃取流水线' },
  tech: {
    backend: { language: 'python', dir: 'backend', entry: 'app_server.py', port: 5000 },
    frontend: { dir: 'frontend', entry: 'index.html' },
  },
  corePaths: [
    { name: '4步流水线', steps: ['场景锚定(Step1)', '知识萃取(Step2)', '知识对齐(Step3)', '智能转化(Step4)'] },
  ],
  plugins: { modelAllocation: { haiku: 'haiku', sonnet: 'sonnet', opus: 'opus' } },
}

const VERIFY_SCHEMA = {
  type: 'object',
  properties: {
    target: { type: 'string' },
    startSuccess: { type: 'boolean' },
    startError: { type: 'string' },
    observations: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          step: { type: 'string' }, passed: { type: 'boolean' },
          expected: { type: 'string' }, actual: { type: 'string' }, logs: { type: 'string' },
        },
        required: ['step', 'passed'],
      },
    },
  },
  required: ['target', 'startSuccess', 'observations'],
}

const PIPELINE_CONTEXT = `
流水线位置：[cr ‖ test] → [vr ‖ doc] → ship-check
你在 CR+test 之后，与 doc 并行。运行时问题交 /dev 修复。`

phase('Target')
const verifyTarget = args || '全部核心路径'
log(`验证目标: ${verifyTarget}`)

phase('Start')
const startResult = await agent(
  `启动应用并确认无启动错误。

启动命令：cd ${CFG.tech.backend.dir} && python ${CFG.tech.backend.entry} --host 127.0.0.1 --port ${CFG.tech.backend.port}

步骤：
1. 先确认端口 ${CFG.tech.backend.port} 未被占用（lsof 或 netstat）
2. 启动应用
3. 等待启动完成（curl health endpoint）
4. 确认无启动错误

输出：启动成功/失败 + 任何启动日志中的错误/警告`,
  { label: 'start-app', phase: 'Start', model: CFG.plugins.modelAllocation.haiku }
)

phase('Run')
const verifyResult = await agent(
  `走核心路径，观察实际运行行为。

${PIPELINE_CONTEXT}

验证目标：${verifyTarget}

应用已启动在 http://127.0.0.1:${CFG.tech.backend.port}

核心路径参考：
${CFG.corePaths.map(p => `- ${p.name}: ${p.steps.join(' → ')}`).join('\n')}

使用 curl 走 API 端点验证关键路径：
1. 检查 /api/health 返回正常
2. 检查 /api/pipelines 返回流水线列表
3. 针对本次变更涉及的路径逐一测试
4. 检查每个步骤的 API 是否正常响应

对每个步骤记录：实际行为 vs 预期行为，控制台/日志有无报错。

验证完毕后关闭启动的进程！`,
  { label: 'run-paths', phase: 'Run', schema: VERIFY_SCHEMA, model: CFG.plugins.modelAllocation.haiku }
)

phase('Report')
const hasFailures = verifyResult?.observations?.some(o => !o.passed) || false

return JSON.stringify({
  target: verifyTarget,
  startSuccess: verifyResult?.startSuccess,
  observations: verifyResult?.observations || [],
  verdict: hasFailures
    ? `发现 ${verifyResult.observations.filter(o => !o.passed).length} 个运行时问题 → 交 /dev 修复`
    : '通过 — 所有验证路径行为符合预期',
}, null, 2)

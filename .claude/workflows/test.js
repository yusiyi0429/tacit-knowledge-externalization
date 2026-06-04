export const meta = {
  name: 'test',
  description: '为新增/变更代码自动生成测试用例并运行验证。用法：/test <需求或范围>',
  phases: [
    { title: 'Analyze', detail: '分析代码，确定测试策略' },
    { title: 'Generate', detail: '生成测试脚本（TDD 驱动：先写测试，再验证失败，再确认通过）' },
    { title: 'Run', detail: '运行测试并报告（verification-before-completion）' },
  ],
}

// ═══════════════════════════════════════════
//  🔧 项目配置 — 新项目修改此区域即可
// ═══════════════════════════════════════════
const CFG = {
  project: { name: '隐性知识显性化', description: 'Flask + Vanilla JS 知识萃取流水线' },
  tech: {
    backend: { language: 'python', framework: 'flask', dir: 'backend', entry: 'app_server.py' },
    frontend: { language: 'javascript', framework: 'vanilla', dir: 'frontend', jsDir: 'frontend/js' },
  },
  test: {
    dir: 'backend/scripts',
    prefix: 'test_',
    runner: 'python',
    runCommand: 'python {file}',
    pattern: {
      ok: 'def ok(msg): print(f"[OK] {msg}")',
      fail: 'def fail(msg): print(f"[FAIL] {msg}"); return False',
      assertFn: 'assert',
      testFn: 'def test_',
      main: `if __name__ == '__main__':
    import inspect, sys
    tests = [fn for name, fn in inspect.getmembers(sys.modules[__name__]) if name.startswith('test_')]
    for t in tests: t()`,
    },
    needsServer: false,
  },
  keyModules: [
    { name: 'pipeline_artifacts', file: 'backend/pipeline_artifacts.py', priority: 'high', testType: 'unit' },
    { name: 'step2_preextract', file: 'backend/step2_preextract.py', priority: 'medium', testType: 'unit' },
    { name: 'revision_processor', file: 'backend/revision_processor.py', priority: 'medium', testType: 'unit' },
  ],
  codeConventions: { pathSafety: 'safe_workspace_path', basenameFn: 'basename_only' },
  plugins: { superpowers: true, modelAllocation: { haiku: 'haiku', sonnet: 'sonnet', opus: 'opus' } },
}
// ═══════════════════════════════════════════

const TEST_PLAN_SCHEMA = {
  type: 'object',
  properties: {
    testStrategy: { type: 'string' },
    testFiles: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          name: { type: 'string' }, path: { type: 'string' },
          target: { type: 'string' }, type: { type: 'string', enum: ['unit', 'integration', 'invariant'] },
          priority: { type: 'string', enum: ['must', 'should', 'nice'] },
        },
        required: ['name', 'path', 'target', 'type', 'priority'],
      },
    },
    needsServer: { type: 'boolean' },
  },
  required: ['testStrategy', 'testFiles', 'needsServer'],
}

// superpowers: test-driven-development + verification-before-completion
const TESTER_RULES = `
== Superpowers 测试工程师纪律 ==

**test-driven-development 原则**（铁律）：
1. NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST. 先写测试、确认测试失败、再写实现代码。
2. 如果没亲眼看到测试失败，你就不知道这个测试是否测了正确的东西。
3. 违反字面规定 = 违反精神。没有任何"这次就跳过 TDD"的例外。

**verification-before-completion 原则**（铁律）：
4. NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE。测试通过不是猜的，是跑出来的。Run 阶段的输出必须包含实际的命令执行结果——stdout、exit code、PASS/FAIL 计数。
5. 每个测试函数验证一个关注点。不要一个测试函数里塞多个无关的 assert。

**TDD 循环**（编写每个测试时遵循）：
6. RED: 先写一个会失败的测试，运行确认它失败
7. GREEN: 写最小代码让测试通过
8. REFACTOR: 消除重复，优化结构，确认测试仍然通过`

const testReq = args || '为最近变更的代码生成测试'
const testDir = CFG.test.dir

phase('Analyze')
const testPlan = await agent(
  `分析代码变更，制定测试策略。

测试需求：${testReq}

项目测试约定：测试脚本放在 ${testDir}/ 下，${CFG.test.prefix} 前缀。无框架 assert 模式。

${CFG.plugins.superpowers ? TESTER_RULES : ''}

${CFG.keyModules.filter(m => m.priority === 'high').map(m => `- ${m.name}（${m.file}）→ 高优先级单元测试`).join('\n')}

输出测试策略和文件清单。标注每个测试文件的 TDD 循环预期（RED/GREEN/REFACTOR）。`,
  { label: 'analyze', phase: 'Analyze', schema: TEST_PLAN_SCHEMA, model: CFG.plugins.modelAllocation.sonnet }
)

phase('Generate')
log(`生成 ${testPlan.testFiles.length} 个测试文件...`)

await parallel(testPlan.testFiles.map(tf => () =>
  agent(
    `生成测试脚本。遵循 TDD 方法论。

${CFG.plugins.superpowers ? TESTER_RULES : ''}

需求：${testReq}
目标：${tf.target}
类型：${tf.type}
路径：${tf.path}

风格（必须遵守）：
def ok(msg): print(f"[OK] {msg}")
def fail(msg): print(f"[FAIL] {msg}"); return False
def test_xxx():
    assert your_condition
    ok("描述")
if __name__ == '__main__':
    import inspect, sys
    tests = [fn for name, fn in inspect.getmembers(sys.modules[__name__]) if name.startswith('test_')]
    for t in tests: t()

约束：${CFG.codeConventions.pathSafety ? '文件操作使用 from pipeline_artifacts import safe_workspace_path' : ''}
路径用 pathlib.Path，临时文件用 tempfile.mkdtemp()，测试后清理。

如果 ${tf.path} 已存在，读现有内容后追加新测试。不要覆盖已有测试。`,
    { label: `gen-${tf.name.replace(/\.py$/, '')}`, phase: 'Generate', model: CFG.plugins.modelAllocation.opus }
  )
))

phase('Run')
log('运行测试...')

const mustTests = testPlan.testFiles.filter(tf => tf.priority === 'must')
const results = mustTests.length > 0
  ? await parallel(mustTests.map(tf => () =>
      agent(
        `运行测试并报告完整输出。铁律：没有验证证据 = 不能声称通过。

命令：cd ${CFG.test.dir}/.. && ${CFG.test.runCommand.replace('{file}', tf.path)}

输出必须包含：
1. 完整的 stdout/stderr
2. exit code
3. PASS/FAIL 逐项计数
4. 如果有 FAIL，标注具体哪个断言、哪一行、实际值 vs 期望值`,
        { label: `run-${tf.name.replace(/\.py$/, '')}`, phase: 'Run', model: CFG.plugins.modelAllocation.haiku }
      )
    ))
  : []

const allPassed = results.every(r => r && !r.includes('[FAIL]') && !r.includes('Error') && !r.includes('Traceback'))

return JSON.stringify({
  testPlan: { strategy: testPlan.testStrategy, files: testPlan.testFiles },
  runResults: results.length > 0 ? {
    total: results.length, evidence: results,
    passed: results.filter(r => r && r.includes('[OK]')).length,
    failed: results.filter(r => r && (r.includes('[FAIL]') || r.includes('Error'))).length,
  } : '(no must-priority tests)',
  verdict: allPassed ? 'ALL TESTS PASSED — 有验证证据' : 'SOME TESTS FAILED — 查看上述输出',
}, null, 2)

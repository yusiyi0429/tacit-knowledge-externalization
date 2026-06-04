export const meta = {
  name: 'ship-check',
  description: '提交前全面验证：语法检查、架构冲突、测试、一致性问题，输出 Go/No-Go 决策。用法：/ship-check',
  phases: [
    { title: 'Syntax', detail: '语法检查' },
    { title: 'Structure', detail: '架构冲突、重复键、文件引用' },
    { title: 'Tests', detail: '运行测试脚本' },
    { title: 'Verdict', detail: 'Go/No-Go 决策（verification-before-completion + finishing-a-development-branch）' },
  ],
}

// ═══════════════════════════════════════════
//  🔧 项目配置 — 新项目修改此区域即可
// ═══════════════════════════════════════════
const CFG = {
  project: { name: '隐性知识显性化' },
  tech: {
    backend: {
      language: 'python', framework: 'flask', dir: 'backend', entry: 'app_server.py',
      syntaxCheck: 'python -c "import py_compile; py_compile.compile(\'{file}\', doraise=True)"',
      importCheck: 'python -c "import app_server; print(len(app_server.app.url_map._rules))"',
    },
    frontend: {
      language: 'javascript', framework: 'vanilla', dir: 'frontend', entry: 'index.html',
      jsDir: 'frontend/js',
    },
  },
  dirs: { scripts: 'backend/scripts', vendor: 'frontend/vendor' },
  test: {
    files: ['test_artifact_invariants.py'],
    runner: 'python', runDir: 'backend',
    singleCommand: 'python {dir}/scripts/{file}',
  },
  routeCheck: { file: 'backend/app_server.py', routesByStep: '/api/step{1,2,3,4}/', basePattern: '/api/step' },
  keySync: { label: 'DOWNSTREAM_OUTPUT_KEYS', files: ['frontend/js/state.js', 'frontend/js/app.js'] },
  consistency: {
    syncGroups: [{ label: 'step data keys', files: ['backend/pipeline_artifacts.py', 'frontend/js/state.js', 'frontend/js/app.js'] }],
  },
  protectedRefs: ['pipelines.json', 'custom_models.json', 'preset_overrides.json'],
  vendorFiles: [],
  plugins: { superpowers: true, modelAllocation: { haiku: 'haiku', sonnet: 'sonnet', opus: 'opus' } },
}
// ═══════════════════════════════════════════

// superpowers: verification-before-completion + finishing-a-development-branch
const SHIPPER_RULES = `
== Superpowers 通关纪律 ==

**verification-before-completion 原则**（铁律）：
1. NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE。每项检查必须附实际的命令输出。不是"应该没问题"，是"实际跑出来是这个结果"。
2. Verdic 阶段：如果任何一个检查项没有验证证据，整个检查算 FAIL。

**finishing-a-development-branch 原则**：
3. Verify tests → Detect environment → Present options → Execute choice。
4. 最终裁决只有两个：ALL CHECKS PASSED（所有验证都有证据）或 FOUND N ISSUE(S)（每个 issue 都有具体描述和位置）。
5. 不存在"应该没问题，但不确定"这种中间状态。不确定 = NOT PASSED。`

phase('Syntax')

const pythonCheck = await agent(
  `Verify ${CFG.tech.backend.language} syntax for all files in ${CFG.tech.backend.dir}/.

运行以下命令并在输出中附实际结果：
  cd ${CFG.tech.backend.dir}
  python -c "
import py_compile, os, sys
errors = []
for root, dirs, files in os.walk('.'):
    dirs[:] = [d for d in dirs if d not in ('__pycache__',)]
    for f in files:
        if not f.endswith('.py'): continue
        path = os.path.join(root, f)
        try:
            py_compile.compile(path, doraise=True)
        except py_compile.PyCompileError as e:
            errors.append(f'{path}: {e}')
if errors:
    for e in errors: print('SYNTAX ERROR:', e)
    sys.exit(1)
else:
    print('All files compile OK')
  "
铁律：报告中必须包含命令的实际 stdout/stderr，不能只说"通过了"。`,
  { label: 'python-syntax', phase: 'Syntax', model: CFG.plugins.modelAllocation.haiku }
)

const jsCheck = await agent(
  `Verify ${CFG.tech.frontend.language} consistency for ${CFG.tech.frontend.dir}/.

1. Check ${CFG.keySync.files.join(' and ')} define the same ${CFG.keySync.label} — compare exact array contents
2. Check ${CFG.tech.frontend.dir}/${CFG.tech.frontend.entry} script tag order
3. Check for accidental globals, duplicate function definitions, orphaned onclick references

${CFG.plugins.superpowers ? SHIPPER_RULES : ''}
每项检查附证据。`,
  { label: 'js-check', phase: 'Syntax', model: CFG.plugins.modelAllocation.haiku }
)

phase('Structure')

const routeCheck = await agent(
  `Check for route conflicts in ${CFG.tech.backend.dir}/${CFG.tech.backend.entry}.

${CFG.plugins.superpowers ? SHIPPER_RULES : ''}

1. Extract all routes — check duplicate URL paths, duplicate function names
2. Verify step numbering consistency (${CFG.routeCheck?.basePattern || '/api/'}N/)
Report duplicates or suspicious patterns with line numbers.`,
  { label: 'flask-routes', phase: 'Structure', model: CFG.plugins.modelAllocation.sonnet }
)

const fileRefs = CFG.protectedRefs?.length ? await agent(
  `Check file references.
1. ${CFG.tech.frontend.dir}/${CFG.tech.frontend.entry} — verify each <script src> and <link href>
2. Check ${CFG.tech.backend.dir}/${CFG.tech.backend.entry}'s frontend path
3. Verify protected files blocked: ${CFG.protectedRefs.join(', ')}
${CFG.plugins.superpowers ? SHIPPER_RULES : ''}`,
  { label: 'file-refs', phase: 'Structure', model: CFG.plugins.modelAllocation.haiku }
) : '(no protected files)'

phase('Tests')

const testResult = await agent(
  `Run test scripts and report with evidence.

${CFG.plugins.superpowers ? SHIPPER_RULES : ''}

Test files: ${CFG.test.files.map(f => `  - ${CFG.test.dir || CFG.dirs.scripts}/${f}`).join('\n')}

Run each with:
  cd ${CFG.test.runDir || '.'}
  ${CFG.test.files.map(f => `${CFG.test.runner || 'python'} ${CFG.test.dir || CFG.dirs.scripts}/${f}`).join('\n')}

Report pass/fail per test. Include actual stdout for any failures.`,
  { label: 'unit-tests', phase: 'Tests', model: CFG.plugins.modelAllocation.haiku }
)

phase('Verdict')
const allResults = [pythonCheck, jsCheck, routeCheck, fileRefs, testResult].filter(Boolean)
const issues = allResults.filter(r =>
  typeof r === 'string' && (r.includes('ERROR') || r.includes('FAIL') || r.includes('fail') || r.includes('error') || r.includes('duplicate') || r.includes('missing')))

const verdict = issues.length === 0
  ? 'ALL CHECKS PASSED — safe to ship（所有验证均有实际证据）'
  : `FOUND ${issues.length} ISSUE(S) — review before shipping（详见 details 中的验证证据）`

return JSON.stringify({
  verdict,
  details: { python: pythonCheck, javascript: jsCheck, flaskRoutes: routeCheck, fileReferences: fileRefs, tests: testResult },
}, null, 2)

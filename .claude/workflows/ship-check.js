export const meta = {
  name: 'ship-check',
  description: '提交前全面验证：语法检查、架构冲突、测试、一致性问题，输出 Go/No-Go 决策。用法：/ship-check',
  phases: [
    { title: 'Syntax', detail: '语法检查' },
    { title: 'Structure', detail: '架构冲突、重复键、文件引用' },
    { title: 'Tests', detail: '运行测试脚本' },
    { title: 'Verdict', detail: 'Go/No-Go 决策' },
  ],
}

const CFG = {
  project: { name: '隐性知识显性化', description: 'Flask + Vanilla JS 知识萃取流水线' },
  tech: {
    backend: { language: 'python', framework: 'flask', dir: 'backend', entry: 'app_server.py' },
    frontend: { language: 'javascript', framework: 'vanilla', dir: 'frontend', jsDir: 'frontend/js' },
  },
  checks: {
    syntax: { python: true, javascript: true },
    routes: true,
    keySync: {
      files: ['backend/pipeline_artifacts.py', 'frontend/js/state.js', 'frontend/js/app.js'],
      patterns: ['STEP_OUTPUT_KEYS_BY_STEP', 'DOWNSTREAM_OUTPUT_KEYS'],
    },
    css: true,
  },
  plugins: { modelAllocation: { haiku: 'haiku', sonnet: 'sonnet', opus: 'opus' } },
}

const PIPELINE_CONTEXT = `
== 天工团队流水线 ==
plan → dev → [cr ‖ test ‖ data-guardian?] → [vr ‖ doc] → ship-check

你是 ship-check 角色——最终静态关卡。
- 必须等 vr + doc 完成后才触发
- 通过即可提交；不通过交 /dev 修复后重来
- 修复后仅复检修复项（最多 2 轮）`

phase('Syntax')
const [pySyntax, jsSyntax] = await parallel([
  () => agent(
    `Python 语法检查。对 backend/ 目录下所有修改过的 .py 文件执行语法编译。

命令：cd backend && python -c "import py_compile; py_compile.compile('文件路径', doraise=True)"

1. 先用 git diff --name-only 找出修改的 .py 文件
2. 对每个文件执行语法编译
3. 记录通过/失败 + 错误信息`,
    { label: 'syntax-python', phase: 'Syntax', model: CFG.plugins.modelAllocation.haiku }
  ),
  () => agent(
    `JavaScript 基础检查。检查 frontend/js/ 下修改的 .js 文件。

1. 用 git diff --name-only 找出修改的 .js 文件
2. 检查是否有明显的语法问题（括号不匹配等）
3. 检查 import/require 路径是否存在`,
    { label: 'syntax-js', phase: 'Syntax', model: CFG.plugins.modelAllocation.haiku }
  ),
])

phase('Structure')
const [routeCheck, keySyncCheck, cssCheck] = await parallel([
  () => agent(
    `Flask 路由冲突检测。

${CFG.tech.backend.framework} 不报重复路由——后定义静默覆盖前者。

1. 从 ${CFG.tech.backend.dir}/${CFG.tech.backend.entry} 提取所有 @app.route 定义
2. 检查是否有重复路径
3. 检查前端 fetch 调用的 API 路径是否在后端都有对应路由
4. 报告重复和缺失`,
    { label: 'check-routes', phase: 'Structure', model: CFG.plugins.modelAllocation.sonnet }
  ),
  () => agent(
    `step data key 三处同步检查。

关键文件：
${CFG.checks.keySync.files.map(f => `- ${f}`).join('\n')}

检查模式：${CFG.checks.keySync.patterns.join(', ')}

逐文件读取 key 定义，逐字符对比是否一致。
不一致会导致数据静默丢失 → 标 critical。`,
    { label: 'check-key-sync', phase: 'Structure', model: CFG.plugins.modelAllocation.sonnet }
  ),
  () => agent(
    `CSS 引用同步检查。

1. 从 HTML 和 JS 文件中提取引用的 CSS class
2. 检查这些 class 是否在样式表中存在
3. 报告缺失的 CSS class`,
    { label: 'check-css', phase: 'Structure', model: CFG.plugins.modelAllocation.haiku }
  ),
])

phase('Tests')
const testResult = await agent(
  `运行现有单元测试，确认无回归。

${PIPELINE_CONTEXT}

在 backend/tests/ 目录下找到 test_*.py 文件并执行。
记录：通过数 / 失败数 / 失败详情。`,
  { label: 'run-tests', phase: 'Tests', model: CFG.plugins.modelAllocation.haiku }
)

phase('Verdict')
const allResults = { pySyntax, jsSyntax, routeCheck, keySyncCheck, cssCheck, testResult }

const verdict = await agent(
  `综合所有检查结果，输出 Go/No-Go 决策。

${PIPELINE_CONTEXT}

检查结果：
- Python 语法: ${pySyntax}
- JS 语法: ${jsSyntax}
- 路由冲突: ${routeCheck}
- Key 同步: ${keySyncCheck}
- CSS 引用: ${cssCheck}
- 测试: ${testResult}

决策标准：
- 任何 critical/high 问题 → No-Go，交 /dev 修复
- 仅有 medium/low → Go with warnings

输出格式：
## 通关检查报告
### ✅ 通过项
### ❌ 未通过项（阻塞合入）
### ⚠️ 警告项
## 通关结论
可以合入 / 需修复 X 项后合入 → 修复交 /dev`,
  { label: 'verdict', phase: 'Verdict', model: CFG.plugins.modelAllocation.haiku }
)

return verdict

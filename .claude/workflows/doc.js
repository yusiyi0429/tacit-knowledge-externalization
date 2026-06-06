export const meta = {
  name: 'doc',
  description: '文档与代码同步检查，标记过时/遗漏内容。用法：/doc [自动检查|同步]',
  phases: [
    { title: 'Collect', detail: '收集文档声明和代码事实' },
    { title: 'Diff', detail: '逐项比对差异' },
    { title: 'Fix', detail: '修复文档（你有 Write/Edit 权限）' },
    { title: 'Report', detail: '输出同步报告' },
  ],
}

const CFG = {
  project: { name: '隐性知识显性化', description: 'Flask + Vanilla JS 知识萃取流水线' },
  tech: {
    backend: { language: 'python', dir: 'backend', entry: 'app_server.py' },
    frontend: { language: 'javascript', dir: 'frontend' },
  },
  docFiles: ['README.md', 'CLAUDE.md', 'docs/**/*.md'],
  plugins: { modelAllocation: { haiku: 'haiku', sonnet: 'sonnet', opus: 'opus' } },
}

const PIPELINE_CONTEXT = `
== 天工团队流水线 ==
plan → dev → [cr ‖ test ‖ data-guardian?] → [vr ‖ doc] → ship-check

你是 doc 角色，与 vr 并行。
- 纯文档问题由你直接修复（你有 Write/Edit 权限）
- 只有代码需配合时才交 /dev
- 你修复后不需要其他角色复检`

phase('Collect')
const mode = args || '自动检查'

const [docContent, codeChanges] = await parallel([
  () => agent(
    `收集项目文档内容。

扫描以下文档文件：
${CFG.docFiles.map(f => `- ${f}`).join('\n')}

以及代码中的文档注释（docstring、JSDoc 等）。

输出：每个文档文件的内容摘要 + 代码中发现的文档注释列表。`,
    { label: 'collect-docs', phase: 'Collect', model: CFG.plugins.modelAllocation.haiku }
  ),
  () => agent(
    `收集当前代码变更事实。

1. git diff --stat 了解变更范围
2. 提取变更涉及的公开 API / 函数签名
3. 识别新增、修改、删除的接口

输出：代码变更事实清单。`,
    { label: 'collect-code', phase: 'Collect', model: CFG.plugins.modelAllocation.haiku }
  ),
])

phase('Diff')
const syncReport = await agent(
  `逐项比对文档声明与代码事实。

${PIPELINE_CONTEXT}

文档内容摘要：
${docContent}

代码变更事实：
${codeChanges}

比对维度：
1. 新增的公开 API/函数 → 文档中是否有说明？
2. 修改的函数签名 → 文档是否已更新？
3. 废弃的方法 → 文档中是否标记？
4. 文档中的代码示例 → 是否仍然可运行？
5. README/CLAUDE.md 中的架构描述 → 是否与当前代码一致？

对每个不一致标注：文件:行号 + 文档描述 vs 实际代码行为`,
  { label: 'diff', phase: 'Diff', model: CFG.plugins.modelAllocation.sonnet }
)

phase('Fix')
if (mode === '同步') {
  const fixResult = await agent(
    `修复文档中的过时/遗漏内容。

${PIPELINE_CONTEXT}

同步报告：
${syncReport}

你有 Write/Edit 权限，直接修复文档。仅修复文档，不改代码。

修复后列出：修改了哪些文件 + 修改了什么。`,
    { label: 'fix-docs', phase: 'Fix', model: CFG.plugins.modelAllocation.sonnet }
  )
}

phase('Report')
return JSON.stringify({
  mode,
  syncReport,
  docFixed: mode === '同步',
  verdict: '文档同步检查完毕。详见同步报告。',
  nextSteps: mode === '同步' ? '文档已修复。' : '如需修复文档，使用 /doc 同步。',
}, null, 2)

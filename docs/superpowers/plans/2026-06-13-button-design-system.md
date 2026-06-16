# 按钮设计系统改造实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `tacit-knowledge-platform` 前端所有按钮统一为红色品牌设计系统，包含 5 种变体、3 种尺寸、5 种状态，并引入 Lucide 图标库。

**Architecture:** 在 `style.css` 中新增一套以 `.btn` 为核心的 BEM 设计系统，替换旧的 `.action-btn`、`.nav-action-btn` 等分散样式；在 `index.html` 中统一按钮 HTML 结构；在 `js/app.js` 中集成 Lucide 图标初始化与动态刷新。

**Tech Stack:** HTML / CSS (Vanilla) / Lucide Icons / Flask (仅作静态文件服务)

---

## File Structure

| 文件 | 职责 | 操作 |
|------|------|------|
| `frontend/vendor/lucide/lucide.min.js` | Lucide 图标库本地文件 | 创建 |
| `frontend/index.html` | 所有按钮 HTML 结构、Lucide 脚本引入 | 修改 |
| `frontend/css/style.css` | 按钮设计系统 CSS、删除旧按钮样式 | 修改 |
| `frontend/js/app.js` | Lucide 初始化、动态内容渲染后刷新图标 | 修改 |
| `docs/superpowers/specs/2026-06-13-button-design-system-design.md` | 设计文档（已确认） | 只读参考 |

---

## Task 1: 引入 Lucide 图标库

**Files:**
- Create: `frontend/vendor/lucide/lucide.min.js`
- Modify: `frontend/index.html`
- Modify: `frontend/js/app.js`

- [ ] **Step 1: 下载 Lucide 生产包**

```bash
cd /mnt/d/my-workspace/tacit-knowledge-platform/frontend
mkdir -p vendor/lucide
curl -L -o vendor/lucide/lucide.min.js https://unpkg.com/lucide@latest/dist/umd/lucide.min.js
ls -la vendor/lucide/lucide.min.js
```

Expected: 文件大小约 80-120KB。

- [ ] **Step 2: 在 index.html 引入 Lucide**

在 `frontend/index.html` 中，找到 `<!-- Luckysheet 离线资源 -->` 下方的 script 标签区域，在 `app.js` 之前添加：

```html
<script src="vendor/lucide/lucide.min.js"></script>
```

具体位置在 `js/state.js` 等脚本之前或之后均可，只要确保在 `js/app.js` 执行前加载完成。

- [ ] **Step 3: 在 app.js 添加图标刷新辅助函数**

在 `frontend/js/app.js` 顶部（紧接全局常量定义之后）添加：

```javascript
/* ===== Lucide Icons ===== */
function refreshIcons() {
  if (window.lucide && typeof lucide.createIcons === 'function') {
    lucide.createIcons();
  }
}
```

- [ ] **Step 4: Commit**

```bash
cd /mnt/d/my-workspace/tacit-knowledge-platform
git add frontend/vendor/lucide/lucide.min.js frontend/index.html frontend/js/app.js
git commit -m "feat(ui): introduce Lucide icons for button design system"
```

---

## Task 2: 建立 CSS 按钮设计系统

**Files:**
- Modify: `frontend/css/style.css`

- [ ] **Step 1: 在 :root 添加按钮 token**

在 `frontend/css/style.css` 的 `:root` 中（约第 3-23 行）追加：

```css
  /* Button tokens */
  --btn-radius: 6px;
  --btn-shadow: 0 1px 2px rgba(0,0,0,0.05);
  --btn-shadow-hover: 0 4px 12px rgba(199,0,11,0.18);
  --btn-primary-bg: var(--red);
  --btn-primary-hover: #b0000e;
  --btn-primary-active: #9e0008;
  --btn-secondary-bg: #fef2f2;
  --btn-secondary-color: var(--red);
  --btn-secondary-hover-bg: #fee2e2;
  --btn-secondary-active-bg: #fecaca;
  --btn-outline-border: var(--red);
  --btn-outline-color: var(--red);
  --btn-outline-hover-bg: #fef2f2;
  --btn-outline-active-bg: #fee2e2;
  --btn-ghost-color: var(--text-secondary);
  --btn-ghost-hover-bg: var(--border-light);
  --btn-ghost-active-bg: var(--border);
  --btn-danger-bg: var(--error);
  --btn-danger-hover: #dc2626;
  --btn-danger-active: #b91c1c;
  --btn-danger-color: var(--error);
```

- [ ] **Step 2: 添加 .btn 基础与变体样式**

在 `frontend/css/style.css` 中找到 `/* ===== Action Buttons ===== */` 区域（约第 610 行），在其上方新增：

```css
/* ===== Button Design System ===== */
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border: 1px solid transparent;
  border-radius: var(--btn-radius);
  font-family: var(--font-cn);
  font-weight: 500;
  line-height: 1;
  cursor: pointer;
  transition: all 0.2s ease;
  white-space: nowrap;
  text-decoration: none;
  background: transparent;
  color: var(--text);
  box-shadow: var(--btn-shadow);
}
.btn:hover { transform: translateY(-1px); }
.btn:active { transform: translateY(0); }
.btn:disabled,
.btn.is-disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none !important;
  box-shadow: none !important;
}
.btn.is-loading {
  pointer-events: none;
  cursor: wait;
  transform: none !important;
}
.btn.is-loading .btn__icon,
.btn.is-loading .btn__icon--left,
.btn.is-loading .btn__icon--right {
  animation: spin 0.8s linear infinite;
}

/* Variants */
.btn--primary {
  background: var(--btn-primary-bg);
  color: #fff;
  border-color: var(--btn-primary-bg);
}
.btn--primary:hover {
  background: var(--btn-primary-hover);
  border-color: var(--btn-primary-hover);
  box-shadow: var(--btn-shadow-hover);
}
.btn--primary:active {
  background: var(--btn-primary-active);
  border-color: var(--btn-primary-active);
}

.btn--secondary {
  background: var(--btn-secondary-bg);
  color: var(--btn-secondary-color);
  border-color: var(--btn-secondary-bg);
}
.btn--secondary:hover {
  background: var(--btn-secondary-hover-bg);
  border-color: var(--btn-secondary-hover-bg);
}
.btn--secondary:active {
  background: var(--btn-secondary-active-bg);
  border-color: var(--btn-secondary-active-bg);
}

.btn--outline {
  background: #fff;
  color: var(--btn-outline-color);
  border-color: var(--btn-outline-border);
}
.btn--outline:hover {
  background: var(--btn-outline-hover-bg);
}
.btn--outline:active {
  background: var(--btn-outline-active-bg);
}

.btn--ghost {
  background: transparent;
  color: var(--btn-ghost-color);
  border-color: transparent;
  box-shadow: none;
}
.btn--ghost:hover {
  background: var(--btn-ghost-hover-bg);
}
.btn--ghost:active {
  background: var(--btn-ghost-active-bg);
}

.btn--danger {
  background: var(--btn-danger-bg);
  color: #fff;
  border-color: var(--btn-danger-bg);
}
.btn--danger:hover {
  background: var(--btn-danger-hover);
  border-color: var(--btn-danger-hover);
  box-shadow: 0 4px 12px rgba(245,63,63,0.18);
}
.btn--danger:active {
  background: var(--btn-danger-active);
  border-color: var(--btn-danger-active);
}

/* Sizes */
.btn--sm {
  height: 28px;
  padding: 4px 10px;
  font-size: 12px;
  gap: 4px;
}
.btn--sm .btn__icon,
.btn--sm .btn__icon--left,
.btn--sm .btn__icon--right {
  width: 14px;
  height: 14px;
}

.btn--md {
  height: 36px;
  padding: 8px 16px;
  font-size: 13px;
  gap: 6px;
}
.btn--md .btn__icon,
.btn--md .btn__icon--left,
.btn--md .btn__icon--right {
  width: 16px;
  height: 16px;
}

.btn--lg {
  height: 44px;
  padding: 12px 24px;
  font-size: 14px;
  gap: 8px;
}
.btn--lg .btn__icon,
.btn--lg .btn__icon--left,
.btn--lg .btn__icon--right {
  width: 18px;
  height: 18px;
}

/* Icon layout */
.btn__icon,
.btn__icon--left,
.btn__icon--right {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.btn__text {
  display: inline-flex;
  align-items: center;
}
```

- [ ] **Step 3: 删除旧的 action-btn / nav-action-btn 等样式**

在 `frontend/css/style.css` 中删除以下旧样式块（可注释或删除）：

1. `/* ===== Action Buttons ===== */` 到 `/* ===== Output Area ===== */` 之间的 `.action-btn` 相关样式。
2. `/* ===== Nav Actions ===== */` 到 `/* Save / Clear pipeline buttons */` 之间的 `.nav-action-btn`、`.nav-config-btn`、`.nav-back-btn` 相关样式。
3. `.excel-btn`、`.md-btn` 中可保留弹窗外壳样式，但将按钮样式迁移到 `.btn` 变体。

注意：删除前先备份，确保不影响非按钮元素。

- [ ] **Step 4: 验证 CSS 无语法错误**

```bash
cd /mnt/d/my-workspace/tacit-knowledge-platform/frontend/css
python -c "import re; css=open('style.css').read(); print('braces balanced:', css.count('{') == css.count('}'))"
```

Expected: `braces balanced: True`

- [ ] **Step 5: Commit**

```bash
cd /mnt/d/my-workspace/tacit-knowledge-platform
git add frontend/css/style.css
git commit -m "feat(ui): add button design system CSS and remove legacy button styles"
```

---

## Task 3: 重构顶部导航按钮

**Files:**
- Modify: `frontend/index.html`

- [ ] **Step 1: 替换返回按钮**

将：

```html
<button class="nav-back-btn" onclick="goBackToOverview()" title="返回总览">
  <span class="back-arrow">‹</span> 返回
</button>
```

改为：

```html
<button class="btn btn--ghost btn--sm" onclick="goBackToOverview()" title="返回总览">
  <span class="btn__icon btn__icon--left" data-lucide="chevron-left"></span>
  <span class="btn__text">返回</span>
</button>
```

- [ ] **Step 2: 替换步骤切换按钮**

将每个 `.step-btn`：

```html
<button class="step-btn" data-step="1"><span class="btn-num">01</span>场景锚定</button>
```

改为：

```html
<button class="step-btn" data-step="1">
  <span class="btn__text"><span class="btn-num">01</span>场景锚定</span>
</button>
```

保持 `.step-btn` 的现有特殊样式不变，但将文字包入 `.btn__text` 以便后续统一。

- [ ] **Step 3: 替换顶部操作按钮（保存/清空）**

将：

```html
<button class="nav-action-btn" id="save-pipeline-btn" ...>
  <svg ...></svg>
  保存
</button>
<button class="nav-action-btn nav-action-btn-danger" id="clear-pipeline-btn" ...>
  <svg ...></svg>
  清空
</button>
```

改为：

```html
<button class="btn btn--ghost btn--sm" id="save-pipeline-btn" onclick="saveCurrentPipeline()" title="保存当前流水线">
  <span class="btn__icon btn__icon--left" data-lucide="save"></span>
  <span class="btn__text">保存</span>
</button>
<button class="btn btn--danger btn--sm" id="clear-pipeline-btn" onclick="clearCurrentPipeline()" title="清空当前流水线">
  <span class="btn__icon btn__icon--left" data-lucide="trash-2"></span>
  <span class="btn__text">清空</span>
</button>
```

- [ ] **Step 4: 替换顶部配置按钮**

将 `Skill配置`、`模型配置`、`验证知识库` 三个 `.nav-config-btn` 改为 `.btn.btn--ghost.btn--sm`，并使用对应 Lucide 图标：

- Skill配置: `data-lucide="sparkles"`
- 模型配置: `data-lucide="settings"`
- 验证知识库: `data-lucide="clipboard-check"`

- [ ] **Step 5: Commit**

```bash
cd /mnt/d/my-workspace/tacit-knowledge-platform
git add frontend/index.html
git commit -m "feat(ui): refactor top navigation buttons with design system"
```

---

## Task 4: 重构首页 Banner 与流水线列表按钮

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/js/app.js`

- [ ] **Step 1: 替换 Banner CTA 按钮**

将：

```html
<button class="overview-banner-action" onclick="showNewPipelineForm()">
  <span class="banner-action-icon">+</span> 新建流水线
</button>
```

改为：

```html
<button class="btn btn--secondary btn--lg" onclick="showNewPipelineForm()">
  <span class="btn__icon btn__icon--left" data-lucide="plus"></span>
  <span class="btn__text">新建流水线</span>
</button>
```

- [ ] **Step 2: 在 app.js 中刷新流水线列表图标**

找到 `renderPipelineList` 函数末尾，在 DOM 插入后添加：

```javascript
refreshIcons();
```

- [ ] **Step 3: Commit**

```bash
cd /mnt/d/my-workspace/tacit-knowledge-platform
git add frontend/index.html frontend/js/app.js
git commit -m "feat(ui): refactor homepage banner and pipeline list buttons"
```

---

## Task 5: 重构新建流水线表单按钮

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/js/app.js`

- [ ] **Step 1: 定位新建表单按钮 HTML**

在 `frontend/index.html` 中搜索 `.new-pipeline-form`，确认取消与创建按钮位置。

- [ ] **Step 2: 替换表单按钮**

将取消按钮改为：

```html
<button class="btn btn--secondary btn--md" type="button" onclick="hideNewPipelineForm()">取消</button>
```

将创建按钮改为：

```html
<button class="btn btn--primary btn--md" type="button" onclick="createPipelineAndStart()">
  <span class="btn__icon btn__icon--left" data-lucide="arrow-right"></span>
  <span class="btn__text">创建并开始</span>
</button>
```

- [ ] **Step 3: 在表单显示/隐藏时刷新图标**

在 `showNewPipelineForm` 和 `hideNewPipelineForm` 函数末尾添加：

```javascript
refreshIcons();
```

- [ ] **Step 4: Commit**

```bash
cd /mnt/d/my-workspace/tacit-knowledge-platform
git add frontend/index.html frontend/js/app.js
git commit -m "feat(ui): refactor new-pipeline form buttons"
```

---

## Task 6: 重构 Step 1 操作区按钮

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/js/app.js`

- [ ] **Step 1: 替换 Step 1 主按钮**

将：

```html
<button class="action-btn" id="s1-generate" onclick="step1Generate()">
  <span class="action-icon">&#9654;</span> 生成场景骨架
</button>
```

改为：

```html
<button class="btn btn--primary btn--md" id="s1-generate" onclick="step1Generate()">
  <span class="btn__icon btn__icon--left" data-lucide="play"></span>
  <span class="btn__text">生成场景骨架</span>
</button>
```

- [ ] **Step 2: 替换 Step 1 次要按钮**

将 `.s1-add-sub-btn` 和 `.s1-k-col-reset` 替换为：

```html
<button type="button" class="btn btn--outline btn--sm" onclick="step1AddSubScenario()">
  <span class="btn__icon btn__icon--left" data-lucide="plus"></span>
  <span class="btn__text">添加子场景</span>
</button>
```

以及：

```html
<button type="button" class="btn btn--ghost btn--sm" onclick="step1ResetKnowledgeColumns()">恢复默认列</button>
```

- [ ] **Step 3: 在动态生成区域刷新图标**

在 `step1AddSubScenario`、`step1AddKnowledgeColumn` 等动态添加 DOM 的函数末尾添加：

```javascript
refreshIcons();
```

- [ ] **Step 4: Commit**

```bash
cd /mnt/d/my-workspace/tacit-knowledge-platform
git add frontend/index.html frontend/js/app.js
git commit -m "feat(ui): refactor step 1 action buttons"
```

---

## Task 7: 重构 Step 2 操作区按钮

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/js/app.js`

- [ ] **Step 1: 替换模式切换按钮**

将：

```html
<button class="s2-mode-tab active" data-mode="doc" onclick="switchStep2Mode('doc')">📄 文档萃取</button>
<button class="s2-mode-tab" data-mode="case" onclick="switchStep2Mode('case')">📋 案例复盘</button>
```

改为：

```html
<button class="btn btn--primary btn--sm s2-mode-tab active" data-mode="doc" onclick="switchStep2Mode('doc')">
  <span class="btn__icon btn__icon--left" data-lucide="file-text"></span>
  <span class="btn__text">文档萃取</span>
</button>
<button class="btn btn--ghost btn--sm s2-mode-tab" data-mode="case" onclick="switchStep2Mode('case')">
  <span class="btn__icon btn__icon--left" data-lucide="clipboard-list"></span>
  <span class="btn__text">案例复盘</span>
</button>
```

- [ ] **Step 2: 替换文本来源增删按钮**

将 `.s2-text-input-remove` 改为 `.btn.btn--ghost.btn--sm`，图标 `x`：

```html
<button type="button" class="btn btn--ghost btn--sm s2-text-input-remove" onclick="this.parentElement.remove();updateStep2Readiness()" title="移除">
  <span class="btn__icon" data-lucide="x"></span>
</button>
```

将"+ 添加更多文本来源"按钮改为 `.btn.btn--outline.btn--sm`。

- [ ] **Step 3: 替换 Skill 卡片选择器样式**

保持 `.s2-skill-card` 卡片结构，但将内部图标改为 Lucide：`search`、`microscope`、`target`。

- [ ] **Step 4: 替换文件列表清空按钮**

将 `.s2-pattern-filelist-clear` 改为 `.btn.btn--ghost.btn--sm`。

- [ ] **Step 5: 替换 Step 2 主按钮**

将：

```html
<button class="action-btn" id="s2-skill-extract" onclick="step2Execute()">
  <span class="action-icon">&#9654;</span> <span id="s2-btn-text">执行知识萃取</span>
</button>
```

改为：

```html
<button class="btn btn--primary btn--md" id="s2-skill-extract" onclick="step2Execute()">
  <span class="btn__icon btn__icon--left" data-lucide="play"></span>
  <span class="btn__text" id="s2-btn-text">执行知识萃取</span>
</button>
```

- [ ] **Step 6: Commit**

```bash
cd /mnt/d/my-workspace/tacit-knowledge-platform
git add frontend/index.html frontend/js/app.js
git commit -m "feat(ui): refactor step 2 action buttons"
```

---

## Task 8: 重构 Step 3 操作区按钮

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/js/app.js`

- [ ] **Step 1: 替换主修订按钮**

将：

```html
<button class="action-btn" id="s3-revise-btn" onclick="step3GeneratePreview()">
  <span class="action-icon">&#9881;</span> 发送并智能修订
</button>
```

改为：

```html
<button class="btn btn--primary btn--md" id="s3-revise-btn" onclick="step3GeneratePreview()">
  <span class="btn__icon btn__icon--left" data-lucide="settings-2"></span>
  <span class="btn__text">发送并智能修订</span>
</button>
```

- [ ] **Step 2: 替换过滤按钮**

将 `.align-filter-btn` 全部改为 `.btn.btn--ghost.btn--sm`。

- [ ] **Step 3: 替换批量操作按钮**

将"全部采纳"改为 `.btn.btn--outline.btn--sm`，图标 `check`；
将"全部驳回"改为 `.btn.btn--outline.btn--sm`，图标 `x`；
将"返回修改"改为 `.btn.btn--ghost.btn--sm`。

- [ ] **Step 4: 替换底部操作条按钮**

将"在线编辑底稿"改为 `.btn.btn--outline.btn--md`，图标 `pencil`；
将"确认并生成对齐稿"改为 `.btn.btn--primary.btn--md`，图标 `check`。

- [ ] **Step 5: 替换建议池按钮**

将"采纳勾选建议"、"驳回勾选建议"、"刷新"分别映射为 primary/outline/ghost sm。

- [ ] **Step 6: Commit**

```bash
cd /mnt/d/my-workspace/tacit-knowledge-platform
git add frontend/index.html frontend/js/app.js
git commit -m "feat(ui): refactor step 3 alignment buttons"
```

---

## Task 9: 重构 Step 4 操作区按钮

**Files:**
- Modify: `frontend/index.html`

- [ ] **Step 1: 替换 Step 4 主按钮组**

将"一键编译交付包"、"生成思维链"、"生成 QA 对"、"生成可执行 Agent Skill" 均改为 `.btn.btn--primary.btn--md`，并分别使用图标：`zap`、`lightbulb`、`message-circle`、`bot`。

- [ ] **Step 2: 替换次要按钮**

将"知识保鲜度审计"、"显性化校验回放"、"执行校验" 映射为 outline 或 ghost sm/md。

- [ ] **Step 3: Commit**

```bash
cd /mnt/d/my-workspace/tacit-knowledge-platform
git add frontend/index.html
git commit -m "feat(ui): refactor step 4 delivery buttons"
```

---

## Task 10: 重构 Step 5 操作区按钮

**Files:**
- Modify: `frontend/index.html`

- [ ] **Step 1: 替换 Step 5 主按钮**

将"执行决策回放"改为 `.btn.btn--primary.btn--md`，图标 `zap`。

- [ ] **Step 2: 替换 Golden 基准验证按钮**

改为 `.btn.btn--outline.btn--md`，图标 `award`。

- [ ] **Step 3: Commit**

```bash
cd /mnt/d/my-workspace/tacit-knowledge-platform
git add frontend/index.html
git commit -m "feat(ui): refactor step 5 validation buttons"
```

---

## Task 11: 重构侧滑面板与弹窗按钮

**Files:**
- Modify: `frontend/index.html`

- [ ] **Step 1: 面板关闭按钮**

将 Skill/Model/Verify 三个面板的关闭按钮 `.skill-panel-close`、`.model-panel-close`、`.verify-panel-close` 均改为：

```html
<button class="btn btn--ghost btn--sm" onclick="closeSkillPanel()">
  <span class="btn__icon" data-lucide="x"></span>
</button>
```

- [ ] **Step 2: 模型配置面板内按钮**

将"+ 添加模型"改为 `.btn.btn--outline.btn--sm`；
将"取消"、"添加"改为 `.btn.btn--secondary.btn--sm` / `.btn.btn--primary.btn--sm`。

- [ ] **Step 3: 验证知识库面板内按钮**

将"导入 result 数据"、"+ 新增用例"、"运行全部用例" 分别映射为 outline/primary/primary sm/md。

- [ ] **Step 4: Excel 编辑器按钮**

将 `.excel-btn-save` 改为 `.btn.btn--primary.btn--sm`；
将 `.excel-btn-close` 改为 `.btn.btn--ghost.btn--sm`；
保留 `.excel-btn-add-row`、`.excel-btn-del-row` 但映射到 outline/danger sm。

- [ ] **Step 5: Markdown 编辑器按钮**

将保存/下载/复制/关闭映射为 primary/outline/ghost/ghost sm，并使用 Lucide 图标。

- [ ] **Step 6: Commit**

```bash
cd /mnt/d/my-workspace/tacit-knowledge-platform
git add frontend/index.html
git commit -m "feat(ui): refactor panel and modal buttons"
```

---

## Task 12: 验证与回归测试

**Files:**
- Read: `frontend/css/style.css`
- Read: `frontend/index.html`

- [ ] **Step 1: 启动服务**

```bash
cd /mnt/d/my-workspace/tacit-knowledge-platform/backend
../.venv/bin/python app_server.py --host 127.0.0.1 --port 5000
```

- [ ] **Step 2: 检查首页**

访问 `http://127.0.0.1:5000`，确认：

1. 顶部导航按钮样式统一；
2. "新建流水线"按钮为 secondary lg；
3. 无 404 资源错误。

- [ ] **Step 3: 检查新建流水线表单**

点击"新建流水线"，确认取消/创建按钮样式正确。

- [ ] **Step 4: 检查 Step 1-5**

创建流水线后进入各步骤，确认主操作按钮、次要按钮、图标均正确渲染。

- [ ] **Step 5: 检查面板与弹窗**

打开 Skill配置、模型配置、验证知识库、Excel 编辑器，确认关闭按钮与内部按钮样式正确。

- [ ] **Step 6: 运行后端测试**

```bash
cd /mnt/d/my-workspace/tacit-knowledge-platform/backend
../.venv/bin/python -m pytest scripts/ -v
```

Expected: 所有测试通过（与前端无关，确保服务正常）。

- [ ] **Step 7: Commit**

```bash
cd /mnt/d/my-workspace/tacit-knowledge-platform
git commit --allow-empty -m "chore(ui): verify button design system across all pages"
```

---

## Spec Coverage Checklist

| 设计文档要求 | 对应任务 |
|--------------|----------|
| 5 种变体 primary/secondary/outline/ghost/danger | Task 2 |
| 3 种尺寸 sm/md/lg | Task 2 |
| 5 种状态 default/hover/active/disabled/loading | Task 2 |
| 引入 Lucide 图标库 | Task 1 |
| 顶部导航按钮统一 | Task 3 |
| 首页 Banner 与列表按钮 | Task 4 |
| 新建表单按钮 | Task 5 |
| Step 1-5 按钮 | Task 6-10 |
| 面板与弹窗按钮 | Task 11 |
| 验证与回归测试 | Task 12 |

## Placeholder Scan

- 无 TBD / TODO / "later" / "fill in details"。
- 每个任务均给出具体 class、图标名、函数名。
- 所有命令与预期输出明确。

# 前端按钮设计系统改造方案

## 1. 背景与目标

当前 `tacit-knowledge-platform` 前端存在按钮样式不统一的问题：

- 顶部导航按钮、各步骤主操作按钮、弹窗小按钮各自使用不同的 class 与样式；
- 状态反馈不完整，缺少标准的 `hover`/`active`/`disabled`/`loading` 规范；
- 图标与文字混排无统一间距，部分按钮使用 emoji，部分使用内联 SVG；
- 没有可复用的按钮变体，新增按钮时容易破坏视觉一致性。

本方案旨在建立一套**红色品牌为主、现代简洁扁平**的按钮设计系统，覆盖所有按钮场景，降低后续维护成本。

## 2. 设计原则

1. **统一语义**：所有按钮使用同一套 BEM class，语义清晰（变体 + 尺寸 + 状态）。
2. **现代扁平**：微圆角、克制阴影、清晰的层级对比，符合当前整体 UI 风格。
3. **状态完整**：`default`、`hover`、`active`、`disabled`、`loading` 五种状态均有明确视觉反馈。
4. **图标一致**：引入 Lucide 图标库，统一图标尺寸、与文字间距、loading 动画。
5. **渐进可用**：改造不阻塞现有功能，保持所有 `onclick` 事件与 DOM id 不变。

## 3. 按钮变体

| 变体 | class | 用途 | 视觉 |
|------|-------|------|------|
| primary | `.btn--primary` | 主要操作：生成、执行、保存、创建 | 红色填充 + 白色文字 |
| secondary | `.btn--secondary` | 次要操作：取消、返回、重置 | 浅红/浅灰填充 + 深色文字 |
| outline | `.btn--outline` | 辅助操作：添加、导入、刷新 | 白色填充 + 红色边框 |
| ghost | `.btn--ghost` | 低强调操作：关闭、更多、收起 | 透明填充 + 灰色文字 |
| danger | `.btn--danger` | 破坏性操作：清空、删除 | 红色文字/填充，提示风险 |

## 4. 按钮尺寸

| 尺寸 | class | 高度 | padding | 字号 | 图标尺寸 | 典型场景 |
|------|-------|------|---------|------|----------|----------|
| sm | `.btn--sm` | 28px | 4px 10px | 12px | 14px | 面板内小按钮、工具栏按钮 |
| md | `.btn--md` | 36px | 8px 16px | 13px | 16px | 步骤主按钮、表单提交 |
| lg | `.btn--lg` | 44px | 12px 24px | 14px | 18px | 首页 banner CTA |

## 5. 按钮状态

### 5.1 通用状态样式

- **default**：按变体基准色渲染。
- **hover**：背景色加深 8%，出现轻微上移 `translateY(-1px)` 与阴影。
- **active**：背景色加深 12%，无位移，阴影收缩。
- **disabled**：opacity 0.5，cursor not-allowed，无 hover 效果。
- **loading**：添加旋转图标，pointer-events none，保持原有底色。

### 5.2 Loading 状态实现

```html
<button class="btn btn--primary btn--md is-loading">
  <span class="btn__icon btn__icon--left" data-lucide="loader-2"></span>
  <span class="btn__text">执行中...</span>
</button>
```

通过 `.is-loading` 触发旋转动画，不依赖 JS 动态替换图标。

## 6. HTML 结构规范

```html
<button class="btn btn--{variant} btn--{size} [is-loading|is-disabled]" id="..." onclick="...">
  <span class="btn__icon btn__icon--left" data-lucide="icon-name"></span>
  <span class="btn__text">按钮文字</span>
  <span class="btn__icon btn__icon--right" data-lucide="icon-name"></span>
</button>
```

- 图标统一放在 `.btn__icon` 内，`data-lucide` 指定 Lucide 图标名。
- 文字统一放在 `.btn__text` 内，确保 flex 布局下间距可控。
- 无图标按钮可省略 `.btn__icon`。

## 7. 图标库引入

引入 **Lucide** 图标库，原因：

- 体积极小（~18KB gzipped），无需构建工具；
- 支持 `data-lucide` 属性自动替换为 SVG，侵入性低；
- 与现有内联 SVG 风格一致（2px 描边、24x24 viewBox）。

引入方式：

1. 下载 `lucide.min.js` 到 `frontend/vendor/lucide/lucide.min.js`；
2. 在 `index.html` 末尾与其他 vendor 脚本一起引入；
3. 在 `js/app.js` 初始化及每次动态渲染后调用 `lucide.createIcons()`。

## 8. 现有按钮迁移映射

| 原 class / 场景 | 新 class | 说明 |
|-----------------|----------|------|
| `.action-btn` | `.btn.btn--primary.btn--md` | 各步骤主操作按钮 |
| `.action-btn.secondary` / `.secondary-btn` | `.btn.btn--secondary.btn--md` 或 `.btn--outline` | 次要操作 |
| `.action-btn.small` / `.small-btn` | `.btn.btn--primary.btn--sm` | 小尺寸主按钮 |
| `.nav-action-btn` | `.btn.btn--ghost.btn--sm` | 顶部保存/清空 |
| `.nav-config-btn` | `.btn.btn--ghost.btn--sm` | 顶部 Skill/模型/验证配置 |
| `.nav-back-btn` | `.btn.btn--ghost.btn--sm` | 返回总览 |
| `.s1-add-sub-btn`, `.s1-k-col-reset` | `.btn.btn--outline.btn--sm` | Step1 添加/恢复默认 |
| `.align-filter-btn` | `.btn.btn--ghost.btn--sm` | 对齐审核过滤 |
| `.align-batch-btn` | `.btn.btn--outline.btn--sm` / `.btn--danger` | 批量采纳/驳回 |
| `.skill-panel-close`, `.model-panel-close`, `.verify-panel-close` | `.btn.btn--ghost.btn--sm` | 面板关闭 |
| `.pipeline-delete-btn` | `.btn.btn--ghost.btn--sm` | 流水线删除 |
| `.excel-btn` / `.md-btn` | 按用途映射到 `.btn--primary` / `.btn--secondary` / `.btn--ghost` | 弹窗操作按钮 |
| `.s2-mode-tab` | `.btn.btn--ghost.btn--sm` / `.btn--primary` | 模式切换标签 |
| `.s2-skill-card` | 保持卡片样式，内部操作按钮映射 | Skill 选择卡片 |

## 9. CSS 实现要点

1. 在 `style.css` 顶部 `:root` 追加按钮专用 token：
   - `--btn-primary-bg`, `--btn-primary-hover`, `--btn-primary-active`
   - `--btn-secondary-bg`, `--btn-secondary-color`
   - `--btn-outline-border`, `--btn-outline-color`
   - `--btn-ghost-color`, `--btn-ghost-hover-bg`
   - `--btn-danger-bg`, `--btn-danger-color`
   - `--btn-radius: 6px`, `--btn-shadow`

2. 新增 `.btn` 基础样式：
   - `display: inline-flex; align-items: center; justify-content: center; gap: 6px;`
   - `border: 1px solid transparent; border-radius: var(--btn-radius);`
   - `font-family: var(--font-cn); font-weight: 500; line-height: 1;`
   - `transition: all 0.2s ease; white-space: nowrap;`

3. 删除或废弃旧的 `.action-btn`、`.nav-action-btn`、`.nav-config-btn`、`.nav-back-btn` 等重复/冲突样式，避免被新样式覆盖。

## 10. JS 配合

1. 在 `js/app.js` 顶部添加：
   ```javascript
   function refreshIcons() {
     if (window.lucide) lucide.createIcons();
   }
   ```
2. 在所有动态渲染按钮的函数末尾调用 `refreshIcons()`（如 `renderPipelineList`、`renderModelList`、`renderSkillPanel` 等）。
3. loading 状态由业务逻辑通过 `classList.add('is-loading')` / `remove('is-loading')` 控制。

## 11. 风险与不变量

- **不修改业务逻辑**：所有 `onclick`、`id`、`data-*` 保持不变。
- **不修改后端 API**：纯前端样式改造。
- **路径安全**：新增 vendor 文件仍通过 `vendor/` 目录 served。
- **回归风险**：需要人工检查 Luckysheet 弹窗、模型配置面板、验证面板内的按钮是否被意外覆盖。
- **可访问性**：保留 `<button>` 语义，disabled 状态使用 `disabled` 属性或 `.is-disabled`。

## 12. 验收标准

- [ ] 首页、Step 1-5、所有侧滑面板、弹窗内的按钮均使用新 class。
- [ ] 5 种变体、3 种尺寸、5 种状态在页面上可直接观察。
- [ ] 所有原有图标替换为 Lucide 图标，且无 emoji。
- [ ] 按钮在 hover/active/disabled/loading 下反馈正确。
- [ ] 响应式布局下按钮不溢出、不换行异常。
- [ ] 服务启动后页面无 404，功能正常。

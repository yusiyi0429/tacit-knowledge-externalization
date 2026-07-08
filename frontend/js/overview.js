(function (global) {
  'use strict';

  // Depends on globals: currentPipeline
  // Depends on globals: currentStep
  // Depends on globals: MAX_STEP
  // Depends on globals: getStepName
  // Depends on globals: escapeHtml
  // Depends on globals: refreshIcons
  // Depends on globals: renderBtn
  // Depends on globals: switchPanel
  // Depends on globals: showToast
  // Depends on globals: recallStep1Output
  // Depends on globals: restoreAllStepsFormData
  // Depends on globals: apiCallJSON
  const API_BASE = global.location.origin;
  const t = function (key, fallback) { return App.I18n.t(key, fallback); };

async function loadPipelineOverview() {
  const container = document.getElementById('pipeline-list-container');
  if (!container) return;

  container.innerHTML = '<div class="pipeline-overview"><div style="text-align:center;padding:40px"><div class="spinner"></div>加载中...</div></div>';

  try {
    const resp = await fetch(API_BASE + '/api/pipelines');
    const data = await resp.json();
    if (data.status !== 'ok') throw new Error(data.error || '加载失败');

    const pipelines = data.pipelines || [];

    const PIPELINES_PER_PAGE = 20;
    if (typeof overviewPage === 'undefined') { overviewPage = 1; }
    let currentPage = overviewPage;
    const sorted = [...pipelines].sort(function(a, b) {
      var aDone = (Object.values(resolveStepStatus(a.step_status, a.step_data)).filter(function(v) { return v === 'done'; }).length >= MAX_STEP);
      var bDone = (Object.values(resolveStepStatus(b.step_status, b.step_data)).filter(function(v) { return v === 'done'; }).length >= MAX_STEP);
      return aDone ? (bDone ? 0 : 1) : (bDone ? -1 : 0);
    });
    const totalPages = Math.ceil(sorted.length / PIPELINES_PER_PAGE) || 1;
    const pageStart = (currentPage - 1) * PIPELINES_PER_PAGE;
    const pageItems = sorted.slice(pageStart, pageStart + PIPELINES_PER_PAGE);

    let html = '<div class="pipeline-overview">';

    // Banner
    html += '<div class="overview-banner">';
    html += '<div class="overview-banner-accent"></div>';
    html += '<div class="overview-banner-inner">';
    html += '<div class="overview-banner-text">';
    html += '<div class="overview-banner-label">Tacit Knowledge Platform</div>';
    html += '<div class="overview-banner-title">隐性知识显性化 · 五步法萃取流水线</div>';
    html += '<div class="overview-banner-desc">将领域专家的隐性经验系统性显性化为 AI 可加载的结构化知识，通过五步法流水线，从场景定义到智能转化，层层递进、步步可追溯。</div>';
    html += '<div class="overview-banner-highlights">';
    html += '<div class="overview-banner-highlight"><i data-lucide="layers" width="18" height="18"></i><span>' + t('banner_highlight_1', '五步闭环') + '</span></div>';
    html += '<div class="overview-banner-highlight"><i data-lucide="shield-check" width="18" height="18"></i><span>' + t('banner_highlight_2', '专家对齐') + '</span></div>';
    html += '<div class="overview-banner-highlight"><i data-lucide="zap" width="18" height="18"></i><span>' + t('banner_highlight_3', 'AI 驱动') + '</span></div>';
    html += '</div>';
    html += '</div>';
    html += '<div class="overview-banner-cta">';
    html += '<button type="button" class="btn btn--primary btn--lg" onclick="showNewPipelineForm()">';
    html += '<span class="btn__icon btn__icon--left" data-lucide="plus"></span>';
    html += '<span class="btn__text">新建流水线</span>';
    html += '</button>';
    html += '</div>';
    html += '</div>';
    html += '<div class="overview-banner-visual">';
    html += '<div class="banner-visual-orb banner-visual-orb--1"></div>';
    html += '<div class="banner-visual-orb banner-visual-orb--2"></div>';
    html += '<div class="banner-visual-orb banner-visual-orb--3"></div>';
    html += '<div class="banner-visual-ring banner-visual-ring--1"></div>';
    html += '<div class="banner-visual-ring banner-visual-ring--2"></div>';
    html += '</div>';
    html += '</div>';

    // Steps Roadmap - vertical layout with timeline
    const stepCards = [
      { num: '01', title: '场景锚定', desc: '定义知识模板骨架，确定领域边界与字段规范，生成场景配置文件', icon: 'target' },
      { num: '02', title: '知识萃取', desc: '从已有文档中提取知识条目，AI 辅助生成待审稿', icon: 'file-search' },
      { num: '03', title: '知识对齐', desc: '融合修订与确认，完成专家意见对齐并生成最终可发布稿', icon: 'check-check' },
      { num: '04', title: '智能转化', desc: '生成思维链、QA 对、OpenClaw Skill 三类交付物', icon: 'cpu' },
      { num: '05', title: '验证回放', desc: '用 SKILL 终版判历史案例，分歧回流第3步形成闭环', icon: 'refresh-ccw' },
    ];
    html += '<div class="overview-roadmap">';
    html += '<div class="roadmap-header"><span class="roadmap-header-line"></span><span class="roadmap-header-text">五步法流程概览</span><span class="roadmap-header-line"></span></div>';
    html += '<div class="roadmap-cards">';
    stepCards.forEach((s, i) => {
      html += '<div class="roadmap-step" data-step="' + s.num + '">';
      html += '<div class="roadmap-step-track">';
      html += '<div class="roadmap-step-node"><i data-lucide="' + s.icon + '" width="22" height="22"></i></div>';
      if (i < stepCards.length - 1) html += '<div class="roadmap-step-connector"></div>';
      html += '</div>';
      html += '<div class="roadmap-step-body">';
      html += '<div class="roadmap-step-num">STEP ' + s.num + '</div>';
      html += '<div class="roadmap-step-title">' + s.title + '</div>';
      html += '<div class="roadmap-step-desc">' + s.desc + '</div>';
      html += '</div>';
      html += '</div>';
    });
    html += '</div>';
    html += '</div>';

    // New Pipeline Form (hidden)
    html += '<div class="new-pipeline-form" id="new-pipeline-form" style="display:none">';
    html += '<h3>新建流水线</h3>';
    html += '<div class="form-row">';
    html += '<div class="form-group half"><label>流水线名称</label><input type="text" id="np-name" placeholder="如：信贷审批知识萃取"></div>';
    html += '<div class="form-group half"><label>场景名称</label>';
    html += '<select id="np-scenario" onchange="if(this.value===\'custom\'){document.getElementById(\'np-scenario-custom\').classList.remove(\'hidden\')}else{document.getElementById(\'np-scenario-custom\').classList.add(\'hidden\')}">';
    html += '<option value="">-- 选择预设场景 --</option>';
    html += '<option value="信贷审批">信贷审批</option>';
    html += '<option value="风控">风控</option>';
    html += '<option value="营销">营销</option>';
    html += '<option value="custom">自定义</option>';
    html += '</select>';
    html += '<input type="text" id="np-scenario-custom" class="hidden" placeholder="输入自定义场景名称">';
    html += '</div>';
    html += '</div>';
    html += '<div class="form-group"><label>业务领域</label><input type="text" id="np-domain" placeholder="如：信贷、风控、营销（默认同场景名称）"></div>';
    html += '<div class="form-actions">';
    html += '<button type="button" class="btn btn--secondary btn--md" onclick="hideNewPipelineForm()"><span class="btn__text">取消</span></button>';
    html += '<button type="button" class="btn btn--primary btn--md" onclick="createPipeline()"><span class="btn__icon btn__icon--left" data-lucide="arrow-right"></span><span class="btn__text">创建并开始</span></button>';
    html += '</div>';
    html += '</div>';

    // Pipeline History
    html += '<div class="overview-history-header">';
    html += '<div class="overview-history-title">历史流水线</div>';
    html += '<div class="overview-history-count">共 ' + sorted.length + ' 条</div>';
    html += '</div>';

    // Search / filter bar
    html += '<div class="pipeline-search-bar">';
    html += '<input type="text" id="pipeline-search-input" placeholder="搜索流水线名称、场景..." oninput="filterPipelineList(this.value)" class="pipeline-search-input">';
    html += '</div>';

    if (sorted.length > 0 && pageItems.length > 0) {
      html += '<div class="pipeline-list">';
      pageItems.forEach(function(p) {
        html += renderPipelineItem(p);
      });
      html += '</div>';

      // Pagination controls
      if (totalPages > 1) {
        html += '<div class="pagination">';
        html += '<button class="pagination-btn" onclick="changePage(' + Math.max(1, currentPage - 1) + ')\"' + (currentPage <= 1 ? ' disabled' : '') + '>&#9664; 上一页</button>';
        html += '<span class="pagination-info">第 ' + currentPage + ' / ' + totalPages + ' 页</span>';
        html += '<button class="pagination-btn" onclick="changePage(' + Math.min(totalPages, currentPage + 1) + ')\"' + (currentPage >= totalPages ? ' disabled' : '') + '>下一页 &#9654;</button>';
        html += '</div>';
      }
    } else {
      html += '<div class="pipeline-empty">';
      html += '<div class="pipeline-empty-icon">📋</div>';
      html += '<div class="pipeline-empty-text">暂无历史流水线，点击上方"新建流水线"开始</div>';
      html += '</div>';
    }

    html += '</div>';
    container.innerHTML = html;
    refreshIcons();
  } catch (e) {
    container.innerHTML = '<div class="pipeline-overview"><div class="error-list"><div class="error-item">加载失败: ' + escapeHtml(e.message) + '</div></div></div>';
  }
}

// ── Pagination & Search for Pipeline Overview ──
var overviewPage = 1;

function changePage(page) {
  overviewPage = page;
  loadPipelineOverview();
}

function filterPipelineList(query) {
  const container = document.getElementById('pipeline-list-container');
  if (!container) return;
  const items = container.querySelectorAll('.pipeline-item');
  query = query.toLowerCase().trim();
  items.forEach(function(item) {
    const name = (item.querySelector('.pipeline-item-name') || {}).textContent || '';
    const scenario = (item.querySelector('.pipeline-item-scenario') || {}).textContent || '';
    const match = !query || name.toLowerCase().indexOf(query) !== -1 || scenario.toLowerCase().indexOf(query) !== -1;
    item.style.display = match ? '' : 'none';
  });
}

function stepHasProduct(sd, step) {
  if (!sd) return false;
  switch (step) {
    case 1: return !!sd.step1_output_file;
    case 2: return !!(sd.step2_output_file || sd.step2_extracted_count > 0);
    case 3: return !!sd.step3_final_file;
    case 4: return !!(sd.step4_skill_file || sd.step4_cot_file || sd.step4_qa_file);
    default: return false;
  }
}

function resolveStepStatus(stepStatus, stepData) {
  var result = {};
  for (var i = 1; i <= MAX_STEP; i++) {
    var s = String(i);
    var fromStatus = (stepStatus || {})[s] || 'pending';
    if (fromStatus !== 'pending') {
      result[s] = fromStatus;
    } else if (stepHasProduct(stepData, i)) {
      result[s] = 'done';
    } else {
      result[s] = 'pending';
    }
  }
  return result;
}

function renderPipelineItem(p) {
  const ss = resolveStepStatus(p.step_status, p.step_data);
  const doneCount = Object.values(ss).filter(v => v === 'done').length;
  const shownDoneCount = Math.min(doneCount, MAX_STEP);
  const isComplete = shownDoneCount >= MAX_STEP;
  const activeStep = p.current_step || 1;
  const updatedAt = p.updated_at ? p.updated_at.slice(0, 16).replace('T', ' ') : '-';

  const statusClass = isComplete ? 'completed' : 'in-progress';
  const statusLabel = isComplete ? '已完成' : '进行中';
  const statusIcon = isComplete ? '&#10003;' : '&#9679;';

  let html = '<div class="pipeline-item ' + statusClass + '" onclick="enterPipeline(\'' + p.id + '\')">';
  html += '<div class="pipeline-item-top">';
  html += '<div class="pipeline-item-left">';
  html += '<span class="pipeline-item-status ' + statusClass + '">' + statusIcon + ' ' + statusLabel + '</span>';
  html += '<span class="pipeline-item-name">' + escapeHtml(p.name) + '</span>';
  html += '</div>';
  html += '<div class="pipeline-item-right">';
  if (!isComplete) {
    html += '<button type="button" class="btn btn--outline btn--sm"><span class="btn__icon btn__icon--left" data-lucide="arrow-right"></span><span class="btn__text">继续</span></button>';
  }
  html += '<button type="button" class="btn btn--ghost btn--sm" onclick="event.stopPropagation();deletePipeline(\'' + p.id + '\', this)" title="删除"><span class="btn__icon btn__icon--left" data-lucide="trash-2"></span><span class="btn__text">删除</span></button>';
  html += '</div>';
  html += '</div>';
  html += '<div class="pipeline-item-meta">';
  html += '<span class="pipeline-item-scenario">' + escapeHtml(p.scenario || '-') + '</span>';
  html += '<span>进度 ' + shownDoneCount + '/' + MAX_STEP + '</span>';
  html += '<span class="pipeline-item-time">' + updatedAt + '</span>';
  html += '</div>';

  // Progress bar
  html += '<div class="pipeline-progress">';
  for (let i = 1; i <= MAX_STEP; i++) {
    const status = ss[String(i)] || 'pending';
    html += '<div class="pipeline-progress-step ' + status + '" title="' + escapeHtml(getStepName(i)) + '"></div>';
  }
  html += '</div>';

  // Step mini labels
  html += '<div class="pipeline-step-badges">';
  for (let i = 1; i <= MAX_STEP; i++) {
    const status = ss[String(i)] || 'pending';
    const label = String(i).padStart(2, '0') + ' ' + getStepName(i);
    const icon = status === 'done' ? '&#10003;' : status === 'active' ? '&#9654;' : '&#9675;';
    html += '<span class="pipeline-step-badge ' + status + '">' + icon + ' ' + label + '</span>';
  }
  html += '</div>';

  html += '</div>';
  return html;
}

function showNewPipelineForm() {
  const form = document.getElementById('new-pipeline-form');
  const roadmap = document.querySelector('.overview-roadmap');
  if (form) { form.style.display = 'block'; }
  if (roadmap) { roadmap.style.display = 'none'; }
}

function hideNewPipelineForm() {
  const form = document.getElementById('new-pipeline-form');
  const roadmap = document.querySelector('.overview-roadmap');
  if (form) { form.style.display = 'none'; }
  if (roadmap) { roadmap.style.display = ''; }
  // Clear form
  const nameEl = document.getElementById('np-name');
  const domainEl = document.getElementById('np-domain');
  if (nameEl) nameEl.value = '';
  if (domainEl) domainEl.value = '';
}

async function createPipeline() {
  const name = (document.getElementById('np-name') || {}).value || '';
  let scenario = (document.getElementById('np-scenario') || {}).value || '';
  if (scenario === 'custom') {
    scenario = (document.getElementById('np-scenario-custom') || {}).value || '';
  }
  const domain = (document.getElementById('np-domain') || {}).value || scenario;

  if (!name.trim()) { alert('请输入流水线名称'); return; }
  if (!scenario.trim()) { alert('请选择或输入场景名称'); return; }

  try {
    const result = await apiCallJSON('/api/pipelines', {
      name: name.trim(),
      scenario: scenario.trim(),
      domain: domain.trim() || scenario.trim()
    });
    if (result.status === 'ok' && result.pipeline) {
      currentPipeline = result.pipeline;
      // 清空旧流水线表单内容，避免污染新流水线
      resetAllStepFormInputs();
      // Pre-fill Step 1 form for new pipeline
      const nameEl = document.getElementById('s1-scenario-name');
      if (nameEl) nameEl.value = scenario;
      switchPanel(1);
    } else {
      alert(result.error || '创建失败');
    }
  } catch (e) {
    alert('创建失败: ' + e.message);
  }
}

async function enterPipeline(pipelineId) {
  try {
    const resp = await fetch(API_BASE + '/api/pipelines/' + pipelineId);
    const data = await resp.json();
    if (data.status === 'ok' && data.pipeline) {
      currentPipeline = data.pipeline;
      currentPipeline.step_data = currentPipeline.step_data || {};
      const recalled = recallStep1Output(currentPipeline.id);
      if (recalled?.file_name && !currentPipeline.step_data.step1_output_file) {
        currentPipeline.step_data.step1_output_file = recalled.file_name;
        currentPipeline.step_data.step1_download_url = recalled.download_url;
      }
      restoreAllStepsFormData();
      const step = Math.min(MAX_STEP, Math.max(1, currentPipeline.current_step || 1));
      switchPanel(step);
    } else {
      alert(data.error || '加载流水线失败');
    }
  } catch (e) {
    alert('加载失败: ' + e.message);
  }
}

async function deletePipeline(pipelineId, btnEl) {
  if (!confirm('确定删除该流水线？删除后不可恢复。')) return;
  if (btnEl) { btnEl.textContent = '...'; btnEl.disabled = true; }
  try {
    const resp = await fetch(API_BASE + '/api/pipelines/' + pipelineId, { method: 'DELETE' });
    const data = await resp.json();
    if (data.status === 'ok') {
      loadPipelineOverview();
    } else {
      alert(data.error || '删除失败');
    }
  } catch (e) {
    alert('删除失败: ' + e.message);
  }
}



  global.App = global.App || {};
  const Overview = {
    loadPipelineOverview,
    changePage,
    filterPipelineList,
    stepHasProduct,
    resolveStepStatus,
    renderPipelineItem,
    showNewPipelineForm,
    hideNewPipelineForm,
    createPipeline,
    enterPipeline,
    deletePipeline,
  };
  global.App.Overview = Overview;
})(window);

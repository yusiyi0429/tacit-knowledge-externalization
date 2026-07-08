(function (global) {
  'use strict';

  // Depends on globals: currentPipeline
  // Depends on globals: API_BASE
  // Depends on globals: escapeHtml
  // Depends on globals: renderOutput
  // Depends on globals: renderLoading
  // Depends on globals: showToast
  // Depends on globals: refreshCurrentPipeline
  // Depends on globals: renderStepReadiness
  // Depends on globals: getCurrentPipelineId
  const API_BASE = global.location.origin;
  const t = function (key, fallback) { return App.I18n.t(key, fallback); };

/* ===== Step5: 验证回放与回流 ===== */
var _s5LastSuggestions = [];

function getCurrentPipelineId() {
  if (!currentPipeline || !currentPipeline.id) {
    console.error('No current pipeline available');
    return null;
  }
  return currentPipeline.id;
}

function step5OnCaseSourceChange() {
  // No-op: deprecated in favor of test_customers-based verification
  return;
}

function loadStep5Context() {
  var infoEl = document.getElementById('s5-prev-info');
  var readinessEl = document.getElementById('s5-readiness');
  if (!infoEl) return;
  var sd = currentPipeline?.step_data || {};
  var html = '';
  if (sd.step4_skill_file) {
    html += '<div class="s2-prev-name">&#9989; SKILL 终版：' + escapeHtml(sd.step4_skill_file) + '</div>';
    html += '<div class="s2-prev-meta">验证对象 = Step4 编译的最终交付物</div>';
    if (readinessEl) renderStepReadiness('s5-readiness', '已就绪：可执行决策回放', 'ok');
  } else if (sd.step3_aligned_file) {
    html += '<div class="s2-prev-name">&#128260; 对齐稿 Skill 草稿 v' + (sd.step3_aligned_version || '?') + '</div>';
    html += '<div class="s2-prev-meta">尚未编译 SKILL 终版，将以 IR 渲染结果作为验证对象</div>';
    if (readinessEl) renderStepReadiness('s5-readiness', '可执行（建议先在第 4 步编译 SKILL 终版）', 'ok');
  } else if (sd.step2_draft_file) {
    html += '<div class="s2-prev-name">&#128221; 萃取稿 Skill 草稿 v' + (sd.step2_draft_version || 1) + '</div>';
    html += '<div class="s2-prev-meta">尚未对齐，仅可做冒烟验证</div>';
    if (readinessEl) renderStepReadiness('s5-readiness', '可冒烟验证（建议先完成知识对齐与转化）', 'warn');
  } else {
    html += '<div class="s2-prev-meta">暂无可验证的 SKILL/草稿，请先完成前序步骤</div>';
    if (readinessEl) renderStepReadiness('s5-readiness', '请先完成知识萃取', 'warn');
  }
  if (sd.step5_hit_rate != null && sd.step5_run_id) {
    html += '<div class="s2-prev-meta" style="margin-top:6px;">上次回放命中率：<strong>' + Math.round(sd.step5_hit_rate * 100) + '%</strong>';
    if (sd.step5_replay_url) html += ' · <a href="' + API_BASE + sd.step5_replay_url + '" target="_blank">查看报告</a>';
    html += '</div>';
  }
  infoEl.innerHTML = html;
}

async function loadStep5PrevOutput() {
  const pid = getCurrentPipelineId();
  if (!pid) return;

  const card = document.getElementById('s5-prev-draft');
  const empty = document.getElementById('s5-prev-empty');
  const info = document.getElementById('s5-prev-info');
  const tags = document.getElementById('s5-prev-tags');
  const actions = document.getElementById('s5-prev-actions');

  try {
    const resp = await fetch(API_BASE + '/api/step5/prev_output?pipeline_id=' + pid);
    const data = await resp.json();

    if (data.has_output) {
      if (card) card.style.display = '';
      if (empty) empty.style.display = 'none';
      if (info) {
        let infoHtml = '<div class="s2-prev-name">Agent-Skill 交付包 v' + (data.published_version || '?') + '</div>';
        infoHtml += '<div class="s2-prev-meta">编译完成，可供验证回放</div>';
        info.innerHTML = infoHtml;
      }
      if (tags) {
        let tagHtml = '';
        if (data.step5_input_file) tagHtml += '<span class="s2-tag">验证输入 (.json)</span>';
        tags.innerHTML = tagHtml;
      }
      if (actions) {
        let actionHtml = '';
        if (data.step5_input_url) {
          actionHtml += '<button type="button" class="btn btn--primary btn--sm" onclick="previewStep5InputJSON(\'' + escapeHtml(data.step5_input_url) + '\')">预览验证输入</button>';
        }
        actions.innerHTML = actionHtml;
      }
    } else {
      if (card) card.style.display = 'none';
      if (empty) empty.style.display = '';
    }
  } catch (e) {
    console.error('loadStep5PrevOutput failed:', e);
  }
}

async function previewStep5InputJSON(url) {
  try {
    const resp = await fetch(API_BASE + url);
    const data = await resp.json();
    var html = '<div class="modal-overlay" onclick="if(event.target===this)closeModal()">';
    html += '<div class="modal-dialog modal-lg">';
    html += '<div class="modal-header"><span>验证输入 JSON（' + (data.count || 0) + ' 条 QA）</span><button class="modal-close" onclick="closeModal()">×</button></div>';
    html += '<div class="modal-body"><pre class="s5-json-body" style="max-height:70vh;">' + escapeHtml(JSON.stringify(data, null, 2)) + '</pre></div>';
    html += '</div></div>';
    document.body.insertAdjacentHTML('beforeend', html);
  } catch (e) {
    showToast('加载 JSON 失败: ' + e.message, 'error');
  }
}
function closeModal() {
  var overlay = document.querySelector('.modal-overlay');
  if (overlay) overlay.remove();
}

async function step5RunReplay() {
  const btn = document.getElementById('s5-replay-btn');
  if (btn._locked) return;
  btn._locked = true;
  btn.disabled = true;
  try {
    const pipelineId = getCurrentPipelineId();
    if (!pipelineId) { showToast('请先进入一条流水线', 'error'); return; }
    const testSource = document.getElementById('s5-source')?.value || '';

    const formData = new FormData();
    formData.append('pipeline_id', pipelineId);
    formData.append('test_source', testSource);

    renderOutput('s5-output', '<div class="loading">验证中...</div>');
    try {
      const resp = await fetch(API_BASE + '/api/step5/replay', { method: 'POST', body: formData });
      const data = await resp.json();
      if (data.status !== 'ok') {
        renderOutput('s5-output', '<div class="error-list"><div class="error-item">' + escapeHtml(data.error || '验证失败') + '</div></div>');
        return;
      }
      const m = data.metrics || {};
      let html = '<div class="s5-metrics">';
      html += '<div class="s5-metric"><span class="s5-metric-label">Precision</span><span class="s5-metric-value">' + m.precision + '</span></div>';
      html += '<div class="s5-metric"><span class="s5-metric-label">Recall</span><span class="s5-metric-value">' + m.recall + '</span></div>';
      html += '<div class="s5-metric"><span class="s5-metric-label">F1</span><span class="s5-metric-value">' + m.f1 + '</span></div>';
      html += '<div class="s5-metric"><span class="s5-metric-label">TP</span><span class="s5-metric-value">' + (m.tp || 0) + '</span></div>';
      html += '<div class="s5-metric"><span class="s5-metric-label">FP</span><span class="s5-metric-value">' + (m.fp || 0) + '</span></div>';
      html += '<div class="s5-metric"><span class="s5-metric-label">FN</span><span class="s5-metric-value">' + (m.fn || 0) + '</span></div>';
      html += '</div>';

      if (data.mismatches && data.mismatches.length > 0) {
        html += '<div class="s5-mismatches"><div class="s5-mismatch-header">分歧详情 (' + data.mismatches.length + ')</div>';
        data.mismatches.forEach(function (mm) {
          html += '<div class="s5-mismatch-item">';
          html += '<span class="s5-mm-cid">' + escapeHtml(mm.customer_id) + '</span>';
          html += ' 期望: ' + escapeHtml(JSON.stringify(mm.expected));
          html += ' → 预测: ' + escapeHtml(JSON.stringify(mm.predicted));
          html += '</div>';
        });
        html += '</div>';
      }

      if (m.f1 >= 0.5) {
        html += '<button type="button" class="btn btn--primary btn--md" onclick="step5Finalize()" style="margin-top:12px;">生成最终版 Agent-Skill</button>';
      }

      window._s5_metrics = m;

      renderOutput('s5-output', html);

      await refreshCurrentPipeline();
    } catch (e) {
      console.error('step5RunReplay failed:', e);
      renderOutput('s5-output', '<div class="error-list"><div class="error-item">验证失败: ' + escapeHtml(e.message) + '</div></div>');
    }
  } finally {
    btn._locked = false;
    btn.disabled = false;
  }
}

async function step5PushFeedback() {
  if (!currentPipeline) return;
  try {
    var result = await apiCallJSON('/api/step5/feedback', {
      pipeline_id: currentPipeline.id,
      suggestions: _s5LastSuggestions,
    });
    if (result.status !== 'ok') { showToast(result.error || '回流失败', 'error'); return; }
    showToast(result.message || ('已回流 ' + result.pushed + ' 条建议'));
  } catch (e) {
    showToast('回流失败: ' + e.message, 'error');
  }
}

async function step5RunFeedback() {
  const pipelineId = getCurrentPipelineId();
  if (!pipelineId) { showToast('请先进入一条流水线', 'error'); return; }
  try {
    const resp = await fetch(API_BASE + '/api/step5/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pipeline_id: pipelineId }),
    });
    const data = await resp.json();
    if (data.status === 'ok') {
      showToast('已反馈 ' + (data.suggestions_count || 0) + ' 条建议到 Step3', 'ok');
    } else {
      showToast(data.error || '反馈失败', 'error');
    }
  } catch (e) {
    console.error('step5RunFeedback failed:', e);
    showToast('反馈失败: ' + e.message, 'error');
  }
}

async function step5GoldenVerify() {
  step5RunReplay();
}

async function step5Finalize() {
  var pid = getCurrentPipelineId();
  if (!pid) return;
  try {
    var resp = await fetch(API_BASE + '/api/step5/finalize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: 'pipeline_id=' + encodeURIComponent(pid),
    });
    var data = await resp.json();
    if (data.status === 'ok') {
      showToast('最终版已生成', 'ok');
      var a = document.createElement('a');
      a.href = API_BASE + data.final_zip_url;
      a.download = data.final_zip_file;
      a.click();
    } else {
      showToast(data.error || '生成失败', 'error');
    }
  } catch (e) {
    showToast('生成失败: ' + e.message, 'error');
  }
}

  global.App = global.App || {};

function restoreStep5Output() {
  if (!currentPipeline || !currentPipeline.id) return;
  var sd = currentPipeline.step_data || {};

  // New contract: step5_report_file + step5_precision/recall/f1
  if (sd.step5_report_file) {
    var html = '<div class="s5-metrics">';
    html += '<div class="s5-metric"><span class="s5-metric-label">Precision</span><span class="s5-metric-value">' + (sd.step5_precision != null ? sd.step5_precision : '-') + '</span></div>';
    html += '<div class="s5-metric"><span class="s5-metric-label">Recall</span><span class="s5-metric-value">' + (sd.step5_recall != null ? sd.step5_recall : '-') + '</span></div>';
    html += '<div class="s5-metric"><span class="s5-metric-label">F1</span><span class="s5-metric-value">' + (sd.step5_f1 != null ? sd.step5_f1 : '-') + '</span></div>';
    html += '</div>';
    var reportUrl = sd.step5_report_url || ('/downloads/' + sd.step5_report_file);
    html += '<a class="s4-download-link" href="' + API_BASE + reportUrl + '" download>验证报告 (.json)</a>';
    document.getElementById('s5-output').innerHTML = html;
    return;
  }

  // Fallback: old hit_rate contract
  if (sd.step5_run_id && sd.step5_hit_rate != null) {
    document.getElementById('s5-output').innerHTML = '<div class="s2-result-success">已执行验证回放（旧版）</div>';
    return;
  }
}

  const Step5 = {
    step5OnCaseSourceChange,
    loadStep5Context,
    loadStep5PrevOutput,
    previewStep5InputJSON,
    closeModal,
    step5RunReplay,
    step5PushFeedback,
    step5RunFeedback,
    step5GoldenVerify,
    step5Finalize,
    restoreStep5Output,
  };
  global.App.Step5 = Step5;
})(window);

(function (global) {
  'use strict';

  // Depends on globals: currentPipeline
  // Depends on globals: API_BASE
  // Depends on globals: escapeHtml
  // Depends on globals: renderOutput
  // Depends on globals: renderLoading
  // Depends on globals: showToast
  // Depends on globals: clearDownstreamOutputs
  // Depends on globals: persistPipeline
  // Depends on globals: refreshCurrentPipeline
  // Depends on globals: resolveModelName
  // Depends on globals: getCurrentPipelineId
  // Depends on globals: prefersMarkdownFlow
  // Depends on globals: step3LooksLikeNoOpinion
  // Depends on globals: renderStepReadiness
  // Depends on globals: renderBtnChildren
  // Depends on globals: refreshIcons
  const API_BASE = global.location.origin;
  const t = function (key, fallback) { return App.I18n.t(key, fallback); };

let _alignNotes = [];
let _alignNoteStates = {};
let _alignEditedValues = {};
let _alignCurrentFilter = 'all';
let _alignChatHistory = [];

const ALIGN_ACTION_LABELS = { modify: '修改', delete: '删除', add: '新增', supplement: '补充' };
const ALIGN_ACTION_COLORS = { modify: '#faad14', delete: '#ff4d4f', add: '#52c41a', supplement: '#1890ff' };

// ── 修订经验批注 / 追问卡片 ──
const TACIT_FOLLOWUP_QUESTIONS = {
  modify: '请补充您对本条的经验批注，以完善最终校验',
  delete: '请说明本条在什么情况下可能产生误导，便于后续核查',
  add: '请补充新增内容背后的判断经验，帮助其他人理解',
  supplement: '请补充您的经验批注，说明补充内容的依据'
};

function showTacitFollowup(noteEl, noteId, actionType) {
  // 已有追问卡片则跳过
  if (noteEl.querySelector('.tacit-followup')) return;
  var question = TACIT_FOLLOWUP_QUESTIONS[actionType] || '能分享一下这次修订背后的经验吗？';
  var safeNoteId = String(noteId).replace(/[^\w-]/g, '');
  var safeActionType = String(actionType).replace(/[^\w-]/g, '');
  var safeQuestion = String(question).replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '&quot;').replace(/</g, '&lt;');
  var card = document.createElement('div');
  card.className = 'tacit-followup';
  card.innerHTML =
    '<div class="tacit-followup-label">💡 ' + escapeHtml(question) + '</div>' +
    '<textarea id="tacit-answer-' + safeNoteId + '" placeholder="简要记录您的修订经验与判断依据..."></textarea>' +
    '<div class="tacit-followup-actions">' +
      '<button type="button" class="btn btn--ghost btn--sm tacit-followup-skip" onclick="dismissTacitFollowup(this)"><span class="btn__text">跳过</span></button>' +
      '<button type="button" class="btn btn--primary btn--sm tacit-followup-save" data-note-id="' + safeNoteId + '" data-action-type="' + safeActionType + '" data-question="' + safeQuestion + '"><span class="btn__text">保存经验批注</span></button>' +
    '</div>';
  card.querySelector('.tacit-followup-save').addEventListener('click', function() {
    saveTacitAnnotation(this.dataset.noteId, this.dataset.actionType, this.dataset.question);
  });
  noteEl.appendChild(card);
  refreshIcons();
}

function dismissTacitFollowup(btn) {
  var card = btn.closest('.tacit-followup');
  if (card) card.remove();
}

function saveTacitAnnotation(noteId, actionType, question) {
  var ta = document.getElementById('tacit-answer-' + noteId);
  var answer = ta ? ta.value.trim() : '';
  if (!answer) { dismissTacitFollowup(ta); return; }
  _alignTacitAnnotations[noteId] = { action: actionType, question: question, answer: answer };
  // 视觉反馈
  var card = ta.closest('.tacit-followup');
  if (card) {
    card.innerHTML = '<div style="color:var(--green);font-size:12px;padding:4px 0">✓ 经验批注已记录 — 将在生成定稿时一并保存</div>';
    setTimeout(function () { if (card.parentNode) card.remove(); }, 2000);
  }
  showToast('经验批注已保存');
}

function getTacitAnnotationsPayload() {
  var list = [];
  Object.keys(_alignTacitAnnotations).forEach(function (id) {
    var a = _alignTacitAnnotations[id];
    if (a && a.answer) list.push({ note_id: id, action: a.action, question: a.question, answer: a.answer });
  });
  return list;
}

async function loadStep3PrevOutput() {
  const pid = currentPipeline ? currentPipeline.id : null;
  if (!pid) return;
  try {
    const resp = await fetch(API_BASE + `/api/step3/prev_output?pipeline_id=${pid}`);
    const data = await resp.json();
    const card = document.getElementById('s3-prev-draft');
    const empty = document.getElementById('s3-prev-empty');
    const info = document.getElementById('s3-prev-info');
    const tags = document.getElementById('s3-prev-tags');
    _alignChatHistory = Array.isArray(currentPipeline?.step_data?._align_chat_history)
      ? currentPipeline.step_data._align_chat_history
      : [];
    renderStep3ChatHistory();
    if (data.has_output) {
      card.style.display = '';
      empty.style.display = 'none';
      const extractedCount = data.extracted_count || (data.fields_info && data.fields_info[0] ? data.fields_info[0].rows : 0);
      info.textContent = `${data.file_name}` + (data.scenario ? ` · ${data.scenario}` : '') + (data.style ? ` · ${data.style}` : '') + (extractedCount > 0 ? ` · 萃取${extractedCount}条知识` : '');

      // 深挖补充记录 badge
      var interviewRecordsStr = currentPipeline?.step_data?.step2_interview_records;
      if (interviewRecordsStr) {
        try {
          var interviewRecords = JSON.parse(interviewRecordsStr);
          if (Array.isArray(interviewRecords) && interviewRecords.length > 0) {
            info.innerHTML += ' · <span class="s2-prev-card-badge" style="background:#fef3c7;color:#92400e;">含深挖补充 ' + interviewRecords.length + ' 条</span>';
          }
        } catch (_) { /* ignore parse error */ }
      }
      if (data.fields_info && data.fields_info.length > 0) {
        const mainSheet = data.fields_info[0];
        const tagHtml = mainSheet.headers.slice(0, 6).map(h => `<span class="s2-prev-tag">${escapeHtml(h)}</span>`).join('');
        tags.innerHTML = tagHtml + `<span class="s2-prev-tag">共${mainSheet.rows}行</span>`;
        const mdFlow = prefersMarkdownFlow();
        let actionBtns = '';
        // Markdown group
        if (data.markdown_file) {
          actionBtns += `<button type="button" class="btn btn--outline btn--sm" onclick="previewStep4File('${escapeHtml(data.markdown_file)}','Step2 萃取 Markdown 预览')">预览/编辑 Markdown</button>`;
        }
        if (data.markdown_download_url) {
          actionBtns += `<a class="btn btn--outline btn--sm" href="${API_BASE + data.markdown_download_url}" download>下载 Markdown</a>`;
        }
        var actionsEl = document.getElementById('s3-prev-actions');
        if (actionsEl) actionsEl.innerHTML = actionBtns;
      }
    } else {
      card.style.display = 'none';
      empty.style.display = '';
    }

    // 加载信号报告数据
    var signalReportFile = currentPipeline?.step_data?.step2_signal_report_file;
    if (signalReportFile) {
      try {
        var sigResp = await fetch(API_BASE + '/downloads/' + signalReportFile);
        if (sigResp.ok) {
          var signalData = await sigResp.json();
          document.getElementById('s3-signal-blur').textContent = signalData.boundary_blur != null ? signalData.boundary_blur : '-';
          document.getElementById('s3-signal-island').textContent = signalData.island != null ? signalData.island : '-';
          document.getElementById('s3-signal-lowconf').textContent = signalData.low_consensus != null ? signalData.low_consensus : '-';
          document.getElementById('s3-signal-conflict').textContent = signalData.conflict != null ? signalData.conflict : '-';
          var infoEl = document.getElementById('s3-signal-info');
          if (infoEl && signalData.summary) infoEl.textContent = signalData.summary;
        }
      } catch (_) { /* 文件不存在或解析失败，保持默认值"—" */ }
    }
  } catch (e) {
    console.error('加载Step2输出失败:', e);
    const card2 = document.getElementById('s3-prev-draft');
    const empty2 = document.getElementById('s3-prev-empty');
    if (card2) card2.style.display = 'none';
    if (empty2) empty2.style.display = '';
  }
}

async function loadStep3IRForAlignment() {
  const pid = getCurrentPipelineId();
  if (!pid) return;
  const listEl = document.getElementById('s3-ir-list');
  if (!listEl) return; // Markdown 流面板没有 IR 列表
  try {
    const resp = await fetch(API_BASE + '/api/pipelines/' + pid);
    const data = await resp.json();
    if (data.status !== 'ok' || !data.pipeline) return;
    const sd = data.pipeline.step_data || {};
    const irName = sd.step3_aligned_file || sd.step2_draft_file;
    if (!irName) {
      listEl.innerHTML = '<div class="output-placeholder">请先完成 Step2 萃取</div>';
      return;
    }
    // Markdown 流产物是 .md，不需要 IR 解析
    if (!irName.endsWith('.json')) {
      listEl.innerHTML = '<div class="output-placeholder">Markdown 流无需 IR 对齐</div>';
      return;
    }
    const irResp = await fetch(API_BASE + '/downloads/' + irName);
    const ir = await irResp.json();
    renderStep3IRDualView(ir);
  } catch (e) {
    console.error('loadStep3IRForAlignment failed:', e);
    listEl.innerHTML = '<div class="output-placeholder">加载 IR 失败: ' + escapeHtml(e.message) + '</div>';
  }
}

/* ===== Step3: Markdown editor + revision ===== */
async function loadStep3SkillMd() {
  var pid = getCurrentPipelineId();
  if (!pid) return;
  var editor = document.getElementById('s3-md-editor');
  if (!editor) return; // 当前面板未渲染 Markdown 编辑器
  try {
    var resp = await fetch(API_BASE + '/api/pipelines/' + pid);
    var data = await resp.json();
    var sd = (data.pipeline || {}).step_data || {};
    var mdFile = sd.step3_skill_md_file || sd.step2_skill_md_file || sd.step2_draft_file;
    if (!mdFile) {
      editor.value = '请先完成 Step2 知识萃取';
      return;
    }
    var mdResp = await fetch(API_BASE + '/downloads/' + mdFile);
    var md = await mdResp.text();
    editor.value = md;
    if (typeof marked !== 'undefined') {
    }
  } catch (e) {
    console.error('loadStep3SkillMd:', e);
  }
}

function step3AIRevise() {
  document.getElementById('s3-expert-input-area').style.display = 'block';
}

async function step3SubmitFeedback() {
  var pid = getCurrentPipelineId();
  var feedback = document.getElementById('s3-expert-feedback').value;
  var model = resolveModelName('s3-model');
  if (!feedback) { showToast('请输入修订意见', 'error'); return; }

  var formData = new FormData();
  formData.append('pipeline_id', pid);
  formData.append('model', model);
  formData.append('expert_feedback', feedback);

  renderLoading('s3-output');
  try {
    var resp = await fetch(API_BASE + '/api/step3/revision_with_expert', { method: 'POST', body: formData });
    var data = await resp.json();
    if (data.status === 'ok') {
      document.getElementById('s3-md-editor').value = data.skill_md;
      if (typeof marked !== 'undefined') {
      }
      document.getElementById('s3-expert-input-area').style.display = 'none';
      document.getElementById('s3-expert-feedback').value = '';
      showToast('修订完成，请检查后再保存', 'ok');
    } else {
      showToast(data.error || '修订失败', 'error');
    }
  } catch (e) {
    showToast('修订失败: ' + e.message, 'error');
  }
}

async function step3SaveMd() {
  var pid = getCurrentPipelineId();
  var md = document.getElementById('s3-md-editor').value;
  if (!md) { showToast('没有可保存的内容', 'error'); return; }
  try {
    var resp = await fetch(API_BASE + '/api/step3/save_skill_md', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pipeline_id: pid, skill_md: md }),
    });
    var data = await resp.json();
    if (data.status === 'ok') {
      showToast('已保存', 'ok');
    } else {
      showToast(data.error || '保存失败', 'error');
    }
  } catch (e) {
    showToast('保存失败: ' + e.message, 'error');
  }
}

async function step3ConfirmMd() {
  var pid = getCurrentPipelineId();
  var md = document.getElementById('s3-md-editor').value;
  if (!md) { showToast('无内容可确认', 'error'); return; }
  try {
    var resp = await fetch(API_BASE + '/api/step3/confirm_skill_md', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pipeline_id: pid, skill_md: md }),
    });
    var data = await resp.json();
    if (data.status === 'ok') {
      showToast('对齐确认完成', 'ok');
      await refreshCurrentPipeline();
    } else {
      showToast(data.error || '确认失败', 'error');
    }
  } catch (e) {
    showToast('确认失败: ' + e.message, 'error');
  }
}

function renderStep3ChatHistory() {
  const box = document.getElementById('s3-chat-history');
  if (!box) return;
  if (!Array.isArray(_alignChatHistory) || _alignChatHistory.length === 0) {
    box.innerHTML = '<div class="align-chat-empty">暂无对话。请先输入一条修订意见并发送。</div>';
    return;
  }
  let html = '';
  _alignChatHistory.forEach((item) => {
    const role = item?.role === 'assistant' ? 'assistant' : 'user';
    const roleText = role === 'assistant' ? '模型' : '专家';
    const ts = item?.ts ? String(item.ts) : '';
    html += `<div class="align-chat-item role-${role}">`;
    html += `<div class="align-chat-meta"><span class="align-chat-role">${roleText}</span><span>${escapeHtml(ts)}</span></div>`;
    html += `<div class="align-chat-content">${escapeHtml(String(item?.content || ''))}</div>`;
    html += '</div>';
  });
  box.innerHTML = html;
  box.scrollTop = box.scrollHeight;
}

/* ===== 修订上下文侧栏 ===== */
async function loadStep3RevisionContext() {
  var ctxEl = document.getElementById('s3-revision-context');
  var bodyEl = document.getElementById('s3-revision-context-body');
  if (!ctxEl || !bodyEl) return;
  var pid = currentPipeline ? currentPipeline.id : null;
  if (!pid) { ctxEl.style.display = 'none'; return; }

  try {
    var resp = await fetch(API_BASE + '/api/step3/revision_context?pipeline_id=' + pid);
    var data = await resp.json();
    if (data.status !== 'ok') { ctxEl.style.display = 'none'; return; }
    var insights = data.insights || [];
    var warnings = data.warnings || [];
    if (!insights.length && !warnings.length) { ctxEl.style.display = 'none'; return; }

    var html = '';
    warnings.forEach(function(w) {
      html += '<div class="rc-warning"><div class="rc-title">' + (w.icon || '') + ' ' + escapeHtml(w.source) + '</div>';
      if (w.text) html += '<div class="rc-text">' + escapeHtml(w.text) + '</div>';
      if (w.details && w.details.length) {
        html += '<ul class="rc-list">';
        w.details.forEach(function(d) { html += '<li>' + escapeHtml(String(d)) + '</li>'; });
        html += '</ul>';
      }
      html += '</div>';
    });
    insights.forEach(function(i) {
      html += '<div class="rc-insight"><div class="rc-title">' + (i.icon || '') + ' ' + escapeHtml(i.source) + '</div>';
      html += '<div class="rc-text">' + escapeHtml(i.text) + '</div>';
      if (i.details && i.details.length) {
        html += '<ul class="rc-list">';
        i.details.forEach(function(d) { html += '<li>' + escapeHtml(String(d)) + '</li>'; });
        html += '</ul>';
      }
      html += '</div>';
    });
    bodyEl.innerHTML = html;
    ctxEl.style.display = '';
  } catch (e) { ctxEl.style.display = 'none'; }
}

/* ===== Step3 建议池（验证回流 / 访谈转化）===== */
var _s3SuggestionPool = [];

async function loadStep3SuggestionPool() {
  var panel = document.getElementById('s3-suggestion-panel');
  var listEl = document.getElementById('s3-suggestion-list');
  var countEl = document.getElementById('s3-suggestion-count');
  if (!panel || !listEl) return;
  var pid = currentPipeline ? currentPipeline.id : null;
  if (!pid) { panel.classList.add('hidden'); return; }
  try {
    var resp = await fetch(API_BASE + '/api/step3/suggestions?pipeline_id=' + pid);
    var data = await resp.json();
    if (data.status !== 'ok') { panel.classList.add('hidden'); return; }
    _s3SuggestionPool = data.suggestions || [];
    if (!_s3SuggestionPool.length) { panel.classList.add('hidden'); return; }
    panel.classList.remove('hidden');
    if (countEl) {
      var srcParts = [];
      var bySrc = data.by_source || {};
      var srcNames = { validation: '验证回流', interview: '访谈转化' };
      Object.keys(bySrc).forEach(function (k) { srcParts.push((srcNames[k] || k) + ' ' + bySrc[k]); });
      countEl.textContent = '共 ' + _s3SuggestionPool.length + ' 条' + (srcParts.length ? '（' + srcParts.join(' · ') + '）' : '');
    }
    var actionNames = { modify: '修改', supplement: '补充', delete: '清空字段', delete_entry: '删除条目', add: '新增条目' };
    var srcNames2 = { validation: '🔁 验证回流', interview: '🎙 访谈转化' };
    var html = '';
    _s3SuggestionPool.forEach(function (s) {
      html += '<div class="rc-insight" style="margin-bottom:8px;">';
      html += '<label style="display:flex;gap:8px;align-items:flex-start;cursor:pointer;">';
      html += '<input type="checkbox" class="s3-suggestion-check" value="' + escapeHtml(String(s.id)) + '" style="margin-top:3px;">';
      html += '<div style="flex:1;">';
      html += '<div class="rc-title">' + escapeHtml(srcNames2[s.source] || s.source || '') + ' · ' + escapeHtml(actionNames[s.action] || s.action || '');
      if (s.entry_id) html += ' · <strong>' + escapeHtml(s.entry_id) + '</strong>';
      if (s.field) html += ' / ' + escapeHtml(s.field);
      html += '</div>';
      if (s.new_value) html += '<div class="rc-text">新值：' + escapeHtml(String(s.new_value).slice(0, 200)) + '</div>';
      if (s.fields && s.fields['知识描述']) html += '<div class="rc-text">' + escapeHtml(String(s.fields['知识描述']).slice(0, 200)) + '</div>';
      if (s.note) html += '<div class="rc-text" style="opacity:.75;">' + escapeHtml(String(s.note).slice(0, 160)) + '</div>';
      html += '</div></label></div>';
    });
    listEl.innerHTML = html;
    // Reset select-all checkbox when pool reloads
    var sa = document.getElementById('s3-suggestion-select-all');
    if (sa) sa.checked = false;
  } catch (e) { panel.classList.add('hidden'); }
}

function _s3CheckedSuggestionIds() {
  var ids = [];
  document.querySelectorAll('.s3-suggestion-check:checked').forEach(function (c) { ids.push(c.value); });
  return ids;
}

function step3ToggleSelectAll() {
  var sa = document.getElementById('s3-suggestion-select-all');
  var checked = sa ? sa.checked : false;
  document.querySelectorAll('.s3-suggestion-check').forEach(function (c) { c.checked = checked; });
}

async function step3ApplySuggestions() {
  var pid = currentPipeline ? currentPipeline.id : null;
  if (!pid) return;
  var ids = _s3CheckedSuggestionIds();
  if (!ids.length) { showToast('请先勾选要采纳的建议', 'error'); return; }

  var btn = document.getElementById('s3-suggestion-apply');
  if (btn) btn.disabled = true;

  try {
    // Build feedback text from selected suggestions
    var feedbackLines = [];
    var suggestions = _s3SuggestionPool || [];
    for (var i = 0; i < suggestions.length; i++) {
      var s = suggestions[i];
      if (ids.indexOf(String(s.id)) !== -1) {
        var line = '建议 #' + s.id + '：';
        if (s.note) line += s.note;
        if (s.new_value) line += ' 修改为：' + s.new_value;
        feedbackLines.push(line);
      }
    }
    if (!feedbackLines.length) { showToast('未找到选中建议的内容', 'error'); return; }

    var feedback = feedbackLines.join('\n');
    var model = resolveModelName('s3-model');
    var formData = new FormData();
    formData.append('pipeline_id', pid);
    formData.append('model', model);
    formData.append('expert_feedback', feedback);

    renderLoading('s3-output');
    var resp = await fetch(API_BASE + '/api/step3/revision_with_expert', { method: 'POST', body: formData });
    var result = await resp.json();

    if (result.status === 'ok') {
      // Recreate editor structure (renderLoading destroyed it)
      var s3out = document.getElementById('s3-output');
      s3out.innerHTML = '<div id="s3-md-editor-area" style="margin-bottom:12px;"><label style="font-size:12px;color:#6b7280;">修订 SKILL.md（可直接编辑代码块中的 SQL）：</label><textarea id="s3-md-editor" rows="20" style="width:100%;font-family:monospace;font-size:12px;border:1px solid #d1d5db;border-radius:4px;padding:8px;">' + escapeHtml(result.skill_md) + '</textarea></div>';
      showToast('已应用 ' + ids.length + ' 条建议，修订稿已更新', 'ok');
      loadStep3SuggestionPool();
      refreshCurrentPipeline();
    } else {
      showToast(result.error || '应用建议失败', 'error');
    }
  } catch (e) {
    showToast('应用建议失败: ' + e.message, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function step3RejectSuggestions() {
  var pid = currentPipeline ? currentPipeline.id : null;
  if (!pid) return;
  var ids = _s3CheckedSuggestionIds();
  if (!ids.length) { showToast('请先勾选要驳回的建议', 'error'); return; }
  // Remove selected suggestions from pool via rejection API
  try {
    var result = await apiCallJSON('/api/step3/apply_suggestions', { pipeline_id: pid, rejected_ids: ids });
    showToast('已驳回 ' + ids.length + ' 条建议', 'ok');
    loadStep3SuggestionPool();
  } catch (e) {
    showToast('驳回失败: ' + e.message, 'error');
  }
}

// Phase 1: Generate alignment preview (AI suggestions only)
async function step3GeneratePreview() {
  const pid = currentPipeline ? currentPipeline.id : null;
  if (!pid) { showToast('请先进入流水线', 'error'); return; }
  const expertText = (document.getElementById('s3-expert-text')?.value || '').trim();
  const model = document.getElementById('s3-model')?.value || resolveModelName('s3-model');

  const btn = document.getElementById('s3-revise-btn');
  btn._locked = true; btn.disabled = true; btn.classList.add('loading');
  btn.innerHTML = '<span class="btn__text">处理中...</span>';
  renderLoading('s3-output');

  try {
    // "无意见" or empty → confirm as-is
    if (!expertText || expertText === '无意见' || expertText === '暂无意见') {
      const resp = await fetch(API_BASE + '/api/step3/confirm_as_is', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pipeline_id: pid }),
      });
      const data = await resp.json();
      if (data.status === 'ok') {
        renderOutput('s3-output', '<div class="s2-result-success"><div class="s2-result-header">已确认对齐（无修订）</div></div>');
        if (currentPipeline) {
          currentPipeline.step_status = currentPipeline.step_status || {};
          currentPipeline.step_status['3'] = 'done';
          currentPipeline.step_status['4'] = 'active';
          currentPipeline.current_step = 4;
          try {
            await persistPipeline({}, { current_step: 4, step_status: currentPipeline.step_status });
            await refreshCurrentPipeline();
          } catch (e) { console.error('advance step after confirm_as_is failed:', e); }
        }
      } else {
        renderOutput('s3-output', '<div class="error-list"><div class="error-item">' + escapeHtml(data.error || '确认失败') + '</div></div>');
      }
    } else {
      // Has expert feedback → call LLM revision
      const formData = new FormData();
      formData.append('pipeline_id', pid);
      formData.append('model', model);
      formData.append('expert_feedback', expertText);

      const resp = await fetch(API_BASE + '/api/step3/revision_with_expert', { method: 'POST', body: formData });
      const data = await resp.json();
      if (data.status === 'ok') {
        // Recreate editor after renderLoading destroyed output
        var s3out = document.getElementById('s3-output');
        s3out.innerHTML = '<div id="s3-md-editor-area" style="margin-bottom:12px;"><label style="font-size:12px;color:#6b7280;">修订 SKILL.md（可直接编辑代码块中的 SQL）：</label><textarea id="s3-md-editor" rows="20" style="width:100%;font-family:monospace;font-size:12px;border:1px solid #d1d5db;border-radius:4px;padding:8px;">' + escapeHtml(data.skill_md) + '</textarea></div>';
        showToast('修订完成，请检查后点击保存', 'ok');
        if (currentPipeline) {
          currentPipeline.step_status = currentPipeline.step_status || {};
          currentPipeline.step_status['3'] = 'done';
          currentPipeline.step_status['4'] = 'active';
          currentPipeline.current_step = 4;
          try {
            await persistPipeline({}, { current_step: 4, step_status: currentPipeline.step_status });
            await refreshCurrentPipeline();
          } catch (e) { console.error('advance step after revision failed:', e); }
        }
      } else {
        renderOutput('s3-output', '<div class="error-list"><div class="error-item">' + escapeHtml(data.error || '修订失败') + '</div></div>');
      }
    }
  } catch (e) {
    renderOutput('s3-output', '<div class="error-list"><div class="error-item">' + escapeHtml(e.message) + '</div></div>');
  } finally {
    btn._locked = false; btn.disabled = false;
    btn.classList.remove('loading');
    btn.innerHTML = '<span class="btn__icon btn__icon--left" data-lucide="settings-2"></span><span class="btn__text">发送并智能修订</span>';
  }
}

function step3BackToInput() {
  document.getElementById('s3-input-section').style.display = '';
  document.getElementById('s3-review-section').style.display = 'none';
  document.getElementById('s3-result-section').style.display = 'none';
}

function renderAlignNotesList() {
  const container = document.getElementById('s3-notes-list');
  const countEl = document.getElementById('s3-review-count');
  if (countEl) countEl.textContent = `共 ${_alignNotes.length} 条`;

  let html = '';
  _alignNotes.forEach((n, i) => {
    if (_alignCurrentFilter !== 'all' && n.action !== _alignCurrentFilter) return;

    const state = _alignNoteStates[n.id] || 'pending';
    const stateClass = `note-${state}`;
    const actionTag = ALIGN_ACTION_LABELS[n.action] || n.action;
    const actionClass = `action-${n.action}`;
    const editedVal = _alignEditedValues[n.id];

    html += `<div class="align-note-card ${stateClass}" id="align-note-${n.id}">`;
    html += `<div class="align-note-header">`;
    html += `<span class="align-note-idx">#${i + 1}</span>`;
    html += `<span class="align-note-action-tag ${actionClass}">${escapeHtml(actionTag)}</span>`;
    html += `<span class="align-note-location">${escapeHtml(n.sheet || '')} · 行${n.row || '?'} · 列${n.col || '?'}</span>`;
    if (n.note) html += `<span class="align-note-reason" title="${escapeHtml(n.note)}">${escapeHtml(n.note)}</span>`;
    html += `</div>`;

    // Diff display
    html += `<div class="align-note-diff">`;
    if (n.action === 'add' || n.action === 'supplement') {
      html += `<div class="align-diff-add">${escapeHtml(editedVal || n.new_value || '')}</div>`;
    } else if (n.action === 'delete') {
      html += `<div class="align-diff-old">${escapeHtml(n.old_value || '(原值)')}</div>`;
    } else {
      html += `<div class="align-diff-old">${escapeHtml(n.old_value || '(原值)')}</div>`;
      html += `<div class="align-diff-new">${escapeHtml(editedVal || n.new_value || '')}</div>`;
    }
    html += `</div>`;

    // Action buttons
    html += `<div class="align-note-actions">`;
    html += `<button type="button" class="btn btn--ghost btn--sm align-note-btn align-note-btn-accept ${state === 'accepted' || state === 'edited' ? 'active' : ''}" onclick="alignSetState(${n.id}, 'accepted')"><span class="btn__text">采纳</span></button>`;
    html += `<button type="button" class="btn btn--ghost btn--sm align-note-btn align-note-btn-reject ${state === 'rejected' ? 'active' : ''}" onclick="alignSetState(${n.id}, 'rejected')"><span class="btn__text">驳回</span></button>`;
    if (n.action !== 'delete') {
      html += `<button type="button" class="btn btn--ghost btn--sm align-note-btn align-note-btn-edit" onclick="alignToggleEdit(${n.id})"><span class="btn__text">编辑</span></button>`;
    }
    html += `</div>`;

    // Inline editor
    if (n.action !== 'delete') {
      html += `<div class="align-inline-editor" id="align-editor-${n.id}">`;
      html += `<textarea class="align-inline-textarea" id="align-textarea-${n.id}" placeholder="修改后的内容">${escapeHtml(editedVal || n.new_value || '')}</textarea>`;
      html += `<button type="button" class="btn btn--primary btn--sm align-inline-save" onclick="alignSaveEdit(${n.id})"><span class="btn__icon btn__icon--left" data-lucide="check"></span><span class="btn__text">保存修改</span></button>`;
      html += `</div>`;
    }

    html += `</div>`;
  });

  if (!html) {
    html = '<div style="text-align:center;padding:40px;color:var(--text-muted);">无匹配的对齐建议</div>';
  }
  container.innerHTML = html;
  refreshIcons();
}

function alignSetState(id, state) {
  const current = _alignNoteStates[id];
  if (current === state) {
    _alignNoteStates[id] = 'pending';
  } else {
    _alignNoteStates[id] = state;
  }
  renderAlignNotesList();
  updateAlignStats();

  // 当专家「采纳」或「编辑」修订建议时，弹出经验批注追问卡片
  if (state === 'accepted' || state === 'edited') {
    var note = (_alignNotes || []).find(function (n) { return n.id === id; });
    if (note) {
      setTimeout(function () {
        var noteEl = document.getElementById('align-note-' + id);
        if (noteEl) showTacitFollowup(noteEl, id, note.action || 'modify');
      }, 200);
    }
  }
}

function alignToggleEdit(id) {
  const editor = document.getElementById('align-editor-' + id);
  if (!editor) return;
  editor.classList.toggle('visible');
  if (editor.classList.contains('visible')) {
    const ta = document.getElementById('align-textarea-' + id);
    if (ta) ta.focus();
  }
}

function alignSaveEdit(id) {
  const ta = document.getElementById('align-textarea-' + id);
  if (!ta) return;
  const val = ta.value.trim();
  if (!val) return;
  _alignEditedValues[id] = val;
  _alignNoteStates[id] = 'edited';
  renderAlignNotesList();
  updateAlignStats();
}

function alignFilterNotes(filter) {
  _alignCurrentFilter = filter;
  document.querySelectorAll('.align-filter-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.filter === filter);
  });
  renderAlignNotesList();
}

function alignBatchAcceptAll() {
  _alignNotes.forEach(n => {
    if (_alignCurrentFilter === 'all' || n.action === _alignCurrentFilter) {
      if (_alignNoteStates[n.id] !== 'edited') _alignNoteStates[n.id] = 'accepted';
    }
  });
  renderAlignNotesList();
  updateAlignStats();
}

function alignBatchRejectAll() {
  _alignNotes.forEach(n => {
    if (_alignCurrentFilter === 'all' || n.action === _alignCurrentFilter) {
      _alignNoteStates[n.id] = 'rejected';
    }
  });
  renderAlignNotesList();
  updateAlignStats();
}

function updateAlignStats() {
  let accepted = 0, rejected = 0, pending = 0, edited = 0;
  for (const [id, st] of Object.entries(_alignNoteStates)) {
    if (st === 'accepted') accepted++;
    else if (st === 'rejected') rejected++;
    else if (st === 'edited') { edited++; accepted++; }
    else pending++;
  }
  const total = _alignNotes.length;
  const processed = accepted + rejected;
  document.getElementById('s3-accepted-count').textContent = accepted;
  document.getElementById('s3-rejected-count').textContent = rejected;
  document.getElementById('s3-pending-count').textContent = pending;
  document.getElementById('s3-edited-count').textContent = edited;

  // Update toolbar progress
  var reviewTitle = document.getElementById('s3-review-title');
  if (reviewTitle) reviewTitle.textContent = `审核进度 ${processed}/${total}`;
  var reviewCount = document.getElementById('s3-review-count');
  if (reviewCount) reviewCount.textContent = `共 ${total} 条`;

  const applyBtn = document.getElementById('s3-apply-btn');
  if (applyBtn) applyBtn.disabled = (accepted === 0);
}

async function showStep3AlignComplete(result, options) {
  const opts = options || {};
  clearDownstreamOutputs(3);
  const dlName = result.download_name || result.output_file || '';
  const dlUrl = result.download_url
    ? (result.download_url.startsWith('http') ? result.download_url : API_BASE + result.download_url)
    : '';
  const mdName = result.markdown_file || '';
  const mdUrl = result.markdown_download_url
    ? (result.markdown_download_url.startsWith('http') ? result.markdown_download_url : API_BASE + result.markdown_download_url)
    : '';

  // 无条件保存对齐结果，不依赖 isStep4FinalFile 校验（文件名约定由后端保证）
  if (currentPipeline && dlName) {
    currentPipeline.step_data = currentPipeline.step_data || {};
    currentPipeline.step_data.step3_final_file = dlName;
    currentPipeline.step_data.step3_final_download_url = result.download_url || ('/downloads/' + dlName);
    currentPipeline.step_data.step3_final_md_file = mdName;
    currentPipeline.step_data.step3_final_md_download_url = result.markdown_download_url || '';
    currentPipeline.step_data.step3_final_count = result.revision_count || 0;
    try {
      await persistPipeline({
        step3_final_file: dlName,
        step3_final_download_url: currentPipeline.step_data.step3_final_download_url,
        step3_final_md_file: mdName,
        step3_final_md_download_url: currentPipeline.step_data.step3_final_md_download_url,
        step3_final_count: result.revision_count || 0,
      });
      await refreshCurrentPipeline();
    } catch (e) {
      console.error('showStep3AlignComplete persist failed:', e);
    }
  }

  // 强制推进到 Step4
  if (currentPipeline) {
    currentPipeline.step_status = currentPipeline.step_status || {};
    currentPipeline.step_status['3'] = 'done';
    currentPipeline.step_status['4'] = 'active';
    currentPipeline.current_step = 4;
    try {
      await persistPipeline({}, {
        current_step: 4,
        step_status: currentPipeline.step_status,
      });
    } catch (e) {
      console.error('showStep3AlignComplete step advance failed:', e);
    }
  }

  document.getElementById('s3-input-section').style.display = 'none';
  document.getElementById('s3-review-section').style.display = 'none';
  document.getElementById('s3-result-section').style.display = '';

  const mdFlow = prefersMarkdownFlow();
  let html = '';
  if (opts.noRevision) {
    html += '<div class="align-result-header"><span>&#10003;</span> 已确认（无修订）</div>';
    html += '<div class="align-result-meta">' + escapeHtml(result.message || '当前稿已作为对齐稿') + '</div>';
  } else {
    html += '<div class="align-result-header"><span>&#10003;</span> 知识对齐完成</div>';
    html += '<div class="align-result-meta">采纳 <strong>' + (result.accepted_count || 0) + '</strong> / ' +
      (result.total_suggested || _alignNotes.length) + ' 条建议 · 共处理 <strong>' +
      (result.revision_count || 0) + '</strong> 处修订</div>';
  }
  html += '<div class="align-result-actions">';
  // Markdown group
  if (mdFlow && mdName) html += '<button class="btn btn--primary btn--sm" onclick="previewStep4File(\'' + escapeHtml(mdName) + '\',\'Step3 对齐 Markdown 预览\')">预览/编辑 Markdown</button>';
  if (mdName) html += '<a href="' + escapeHtml(mdUrl) + '" class="btn btn--outline btn--sm" download>下载 Markdown</a>';
  html += '<button class="btn btn--outline btn--sm" onclick="step3BackToInput()">重新对齐</button>';
  html += '</div>';
  document.getElementById('s3-result-card').innerHTML = html;
  updateStepProgress();
}

// Phase 2: Apply selected notes to generate final
async function step3ApplyNotes() {
  const pid = currentPipeline ? currentPipeline.id : null;
  if (!pid) { alert('请先进入流水线'); return; }

  const acceptedIds = [];
  const editedNotes = [];
  for (const [id, st] of Object.entries(_alignNoteStates)) {
    const nid = parseInt(id);
    if (st === 'accepted' || st === 'edited') {
      acceptedIds.push(nid);
      if (st === 'edited' && _alignEditedValues[nid] !== undefined) {
        editedNotes.push({ id: nid, new_value: _alignEditedValues[nid] });
      }
    }
  }

  if (acceptedIds.length === 0) { alert('请至少采纳一条对齐建议'); return; }

  const btn = document.getElementById('s3-apply-btn');
  const origBtnHtml = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<span class="btn__text">生成中...</span>';

  try {
    const resp = await fetch(API_BASE + '/api/step3/apply_notes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pipeline_id: pid, accepted_ids: acceptedIds, edited_notes: editedNotes, tacit_annotations: getTacitAnnotationsPayload() }),
    });
    const result = await resp.json();

    if (result.status === 'ok') {
      result.accepted_count = result.accepted_count || acceptedIds.length;
      result.total_suggested = result.total_suggested || _alignNotes.length;
      await showStep3AlignComplete(result, { noRevision: false });
    } else {
      alert(result.error || '生成对齐稿失败');
    }
  } catch (e) {
    alert('生成对齐稿出错: ' + e.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = origBtnHtml;
    refreshIcons();
  }
}

function renderStep3IRDualView(ir) {
  window.currentStep3IR = ir;
  const list = document.getElementById('s3-ir-list');
  if (!list) return;
  if (!ir || !ir.entries || !ir.entries.length) {
    list.innerHTML = '<div class="output-placeholder">暂无 IR 条目</div>';
    return;
  }
  let html = '';
  ir.entries.forEach(function (e) {
    const fields = e.fields || {};
    const dataLogic = fields.data_logic || {};
    html += '<div class="s3-ir-card" data-entry-id="' + escapeHtml(e.entry_id) + '">';
    html += '<div class="s3-ir-header">';
    html += '<span class="s3-ir-id">' + escapeHtml(e.entry_id) + '</span>';
    html += '<span class="s3-ir-phase">' + escapeHtml(e.step_phase) + '</span>';
    html += '<span class="s3-ir-sub">' + escapeHtml(e.sub_scenario) + '</span>';
    html += '</div>';
    html += '<div class="s3-ir-row"><label>业务描述</label><textarea class="s3-field" data-field="knowledge_desc" rows="2">' + escapeHtml(fields.knowledge_desc || '') + '</textarea></div>';
    html += '<div class="s3-ir-row"><label>数据来源</label><input type="text" class="s3-field" data-field="knowledge_ref" value="' + escapeHtml(fields.knowledge_ref || '') + '"></div>';
    html += '<div class="s3-ir-row"><label>规则引用</label><textarea class="s3-field" data-field="rule_ref" rows="2">' + escapeHtml(fields.rule_ref || '') + '</textarea></div>';
    html += '<div class="s3-ir-row"><label>SQL</label><textarea class="s3-field s3-sql" data-field="data_logic.sql" rows="3">' + escapeHtml(dataLogic.sql || '') + '</textarea></div>';
    html += '<div class="s3-ir-actions">';
    html += '<button type="button" class="btn btn--secondary btn--sm" onclick="step3SaveEntryRevision(\'' + escapeJsString(e.entry_id) + '\')">保存修订</button>';
    html += '<button type="button" class="btn btn--outline btn--sm" onclick="step3RegenerateEntrySQL(\'' + escapeJsString(e.entry_id) + '\')">重新生成 SQL</button>';
    html += '</div>';
    html += '</div>';
  });
  list.innerHTML = html;
}

async function step3SaveEntryRevision(entryId) {
  const pipelineId = getCurrentPipelineId();
  if (!pipelineId) { showToast('流水线未加载', 'error'); return; }
  const card = document.querySelector('.s3-ir-card[data-entry-id="' + entryId + '"]');
  if (!card) return;
  const updates = [];
  card.querySelectorAll('.s3-field').forEach(function (el) {
    const field = el.getAttribute('data-field');
    updates.push({ field: field, value: el.value });
  });
  try {
    let errors = [];
    for (let u of updates) {
      const r = await apiCallJSON('/api/step3/align_ir', {
        pipeline_id: pipelineId,
        entry_id: entryId,
        field: u.field,
        new_value: u.value,
      });
      if (r.status !== 'ok') errors.push(u.field);
    }
    if (errors.length) {
      showToast('部分字段保存失败: ' + errors.join(', '), 'error');
    } else {
      showToast('修订已保存', 'ok');
    }
  } catch (e) {
    console.error('step3SaveEntryRevision failed:', e);
    showToast('保存失败: ' + e.message, 'error');
  }
}

async function step3RegenerateEntrySQL(entryId) {
  const pipelineId = getCurrentPipelineId();
  const model = resolveModelName('s3-model');
  const entry = (window.currentStep3IR.entries.find(function (e) { return e.entry_id === entryId; }) || {});
  const result = await apiCallJSON('/api/step3/align_ir', {
    pipeline_id: pipelineId,
    entry_id: entryId,
    field: 'rule_ref',
    new_value: entry.fields ? entry.fields.rule_ref : '',
    regenerate_sql: true,
    model: model,
  });
  if (result.status === 'ok') {
    if (result.entry && window.currentStep3IR && window.currentStep3IR.entries) {
      const idx = window.currentStep3IR.entries.findIndex(function (e) { return e.entry_id === entryId; });
      if (idx >= 0) window.currentStep3IR.entries[idx] = result.entry;
    }
    renderStep3IRDualView(window.currentStep3IR);
    showToast('SQL 已重新生成', 'ok');
  } else {
    showToast(result.error || '生成失败', 'error');
  }
}

async function step3ConfirmAsIs() {
  const pipelineId = getCurrentPipelineId();
  if (!pipelineId) { showToast('流水线未加载', 'error'); return; }
  try {
    const result = await apiCallJSON('/api/step3/confirm_as_is', { pipeline_id: pipelineId });
    if (result.status === 'ok') {
      await showStep3AlignComplete(result, { noRevision: true });
    } else {
      document.getElementById('s3-result-card').innerHTML = '<div class="error-list"><div class="error-item">' + escapeHtml(result.error || '确认失败') + '</div></div>';
    }
  } catch (e) {
    console.error('step3ConfirmAsIs failed:', e);
    document.getElementById('s3-result-card').innerHTML = '<div class="error-list"><div class="error-item">确认失败: ' + escapeHtml(e.message) + '</div></div>';
  }
}


  global.App = global.App || {};

function restoreStep3Output() {
  if (!currentPipeline) return;
  const sd = currentPipeline.step_data || {};
  const resultSection = document.getElementById('s3-result-section');
  const resultCard = document.getElementById('s3-result-card');
  const inputSection = document.getElementById('s3-input-section');
  const reviewSection = document.getElementById('s3-review-section');
  if (!sd.step3_final_file || !resultSection || !resultCard) return;

  const dlName = sd.step3_final_file || '';
  const dlUrl = sd.step3_final_download_url || '/downloads/' + dlName;
  const mdName = sd.step3_final_md_file || '';
  const mdUrl = sd.step3_final_md_download_url || '';
  const mdFlow = prefersMarkdownFlow();

  // Keep input section visible so IR dual view is still shown
  if (resultSection) {
    resultSection.style.display = '';
  }

  let html = '';
  html += '<div class="align-result-header"><span>&#10003;</span> 知识对齐完成</div>';
  html += '<div class="align-result-meta">已生成对齐稿（共处理 ' + (sd.step3_final_count || 0) + ' 处修订）</div>';
  html += '<div class="align-result-actions">';
  if (mdFlow && mdName) html += '<button class="btn btn--primary btn--sm" onclick="previewStep4File(\'' + escapeHtml(mdName) + '\',\'Step3 对齐 Markdown 预览\')">预览/编辑 Markdown</button>';
  if (!mdFlow && mdName) html += '<button class="btn btn--outline btn--sm" onclick="previewStep4File(\'' + escapeHtml(mdName) + '\',\'Step3 对齐 Markdown 预览\')">预览/编辑 Markdown</button>';
  if (mdUrl) html += '<a href="' + escapeHtml(mdUrl) + '" class="btn btn--outline btn--sm" download>下载 Markdown</a>';
  html += '<button class="btn btn--outline btn--sm" onclick="step3BackToInput()">重新对齐</button>';
  html += '</div>';
  resultCard.innerHTML = html;
}

  const Step3 = {
    showTacitFollowup,
    dismissTacitFollowup,
    saveTacitAnnotation,
    getTacitAnnotationsPayload,
    loadStep3PrevOutput,
    loadStep3IRForAlignment,
    loadStep3SkillMd,
    step3AIRevise,
    step3SubmitFeedback,
    step3SaveMd,
    step3ConfirmMd,
    renderStep3ChatHistory,
    loadStep3RevisionContext,
    loadStep3SuggestionPool,
    _s3CheckedSuggestionIds,
    step3ToggleSelectAll,
    step3ApplySuggestions,
    step3RejectSuggestions,
    step3GeneratePreview,
    step3BackToInput,
    renderAlignNotesList,
    alignSetState,
    alignToggleEdit,
    alignSaveEdit,
    alignFilterNotes,
    alignBatchAcceptAll,
    alignBatchRejectAll,
    updateAlignStats,
    showStep3AlignComplete,
    step3ApplyNotes,
    renderStep3IRDualView,
    step3SaveEntryRevision,
    step3RegenerateEntrySQL,
    step3ConfirmAsIs,
    restoreStep3Output,
  };
  global.App.Step3 = Step3;
})(window);

(function (global) {
  'use strict';

  // Depends on globals: currentPipeline
  // Depends on globals: allModels
  // Depends on globals: t
  // Depends on globals: escapeHtml
  // Depends on globals: refreshIcons
  // Depends on globals: renderBtn
  // Depends on globals: renderBtnChildren
  // Depends on globals: showToast
  // Depends on globals: apiCallJSON
  // Depends on globals: apiCall
  const API_BASE = global.location.origin;
  const t = function (key, fallback) { return App.I18n.t(key, fallback); };

function openModelPanel() {
  closeSkillPanel();
  document.getElementById('model-panel').classList.add('open');
  document.getElementById('model-overlay').classList.remove('hidden');
  document.getElementById('model-nav-btn').classList.add('active');
  loadModels();
}
function closeModelPanel() {
  document.getElementById('model-panel').classList.remove('open');
  document.getElementById('model-overlay').classList.add('hidden');
  document.getElementById('model-nav-btn').classList.remove('active');
}

// ─── Skill Panel ─────────────────────────────────────────────────

async function openSkillPanel() {
  closeModelPanel();
  document.getElementById('skill-panel').classList.add('open');
  document.getElementById('model-overlay').classList.remove('hidden');
  document.getElementById('skill-nav-btn').classList.add('active');
  await loadSkills();
}
function closeSkillPanel() {
  document.getElementById('skill-panel').classList.remove('open');
  document.getElementById('model-overlay').classList.add('hidden');
  document.getElementById('skill-nav-btn').classList.remove('active');
}


let allSkills = [];

const SKILL_META = {
  'knowledge-extraction': { icon: '🔍', iconCls: 'icon-purple', step: 2 },
  'knowledge-revision': { icon: '📝', iconCls: 'icon-orange', step: 3 },
  'skill-generator': { icon: '🤖', iconCls: 'icon-teal', step: 4 },
};

async function loadSkills() {
  const body = document.getElementById('skill-panel-body');
  body.innerHTML = '<div class="skill-loading">加载中...</div>';
  try {
    const resp = await fetch(API_BASE + '/api/skills');
    const data = await resp.json();
    if (data.status === 'ok') {
      allSkills = data.skills || [];
      renderSkills(body);
    } else {
      body.innerHTML = '<div class="skill-error">加载失败</div>';
    }
  } catch (e) {
    body.innerHTML = '<div class="skill-error">网络错误</div>';
  }
}

function renderSkills(container) {
  if (allSkills.length === 0) {
    container.innerHTML = '<div class="skill-empty">暂无已注册的 Skill</div>';
    return;
  }
  let html = '<div class="skill-section"><div class="skill-section-header"><span>已注册技能</span><span style="font-weight:400;color:#aaa">' + allSkills.length + ' 个</span></div>';
  for (const skill of allSkills) {
    const enabled = skill.enabled !== false;
    const meta = SKILL_META[skill.id] || { icon: '⚡', iconCls: 'icon-blue' };
    html += `
      <div class="skill-card ${enabled ? '' : 'skill-card-disabled'}" id="skill-item-${skill.id}" data-skill-id="${skill.id}">
        <div class="skill-card-row" onclick="toggleSkillDetail('${skill.id}')">
          <div class="skill-card-icon ${meta.iconCls}">${meta.icon}</div>
          <div class="skill-card-info">
            <div class="skill-card-name">${escapeHtml(skill.name)}</div>
            <div class="skill-card-brief">${enabled ? '已启用' : '已禁用'}</div>
          </div>
          <div class="skill-card-controls">
            <div class="skill-toggle ${enabled ? 'on' : ''}" onclick="event.stopPropagation(); toggleSkill('${skill.id}', ${!enabled})">
              <div class="skill-toggle-knob"></div>
            </div>
            <span class="skill-card-arrow" id="skill-arrow-${skill.id}">▾</span>
          </div>
        </div>
        <div class="skill-card-detail hidden" id="skill-detail-${skill.id}">
          <div class="skill-loading">加载详情...</div>
        </div>
      </div>
    `;
  }
  html += '</div>';
  container.innerHTML = html;
}

async function toggleSkillDetail(skillId) {
  const detail = document.getElementById('skill-detail-' + skillId);
  const card = document.getElementById('skill-item-' + skillId);

  if (!detail.classList.contains('hidden')) {
    detail.classList.add('hidden');
    card.classList.remove('skill-card-expanded');
    return;
  }

  detail.classList.remove('hidden');
  card.classList.add('skill-card-expanded');

  if (detail.querySelector('.skill-loading')) {
    try {
      const resp = await fetch(API_BASE + '/api/skills/' + skillId);
      const data = await resp.json();
      if (data.status === 'ok') {
        renderSkillDetail(detail, data.skill);
      } else {
        detail.innerHTML = '<div class="skill-error">加载失败</div>';
      }
    } catch (e) {
      detail.innerHTML = '<div class="skill-error">网络错误</div>';
    }
  }
}

function renderSkillDetail(container, s) {
  const tagGroup = (label, items, cls) => {
    if (!items || !items.length) return '';
    return '<div class="skill-detail-group"><div class="skill-detail-label">' + label + '</div><div class="skill-detail-tags">' + items.map(function(i) { return '<span class="skill-tag ' + (cls || '') + '">' + escapeHtml(i) + '</span>'; }).join('') + '</div></div>';
  };
  const section = (title, content) => {
    if (!content) return '';
    return '<div class="skill-detail-section"><div class="skill-detail-section-title">' + title + '</div><div class="skill-detail-section-body">' + content + '</div></div>';
  };
  const listSection = (title, items) => {
    if (!items || !items.length) return '';
    return section(title, '<ul class="skill-detail-list">' + items.map(function(i) { return '<li>' + escapeHtml(i) + '</li>'; }).join('') + '</ul>');
  };
  const formatText = function(text) {
    return escapeHtml(text).replace(/\n\n/g, '</p><p>').replace(/\n/g, '<br>');
  };

  let html = '';

  // 详细描述
  if (s.detailed_description) {
    html += section('📖 详细说明', '<p>' + formatText(s.detailed_description) + '</p>');
  }

  // 业务价值
  if (s.business_value) {
    html += section('💡 业务价值', '<p>' + formatText(s.business_value) + '</p>');
  }

  // 使用指南
  if (s.usage_guide) {
    html += section('📋 使用步骤', '<p>' + formatText(s.usage_guide) + '</p>');
  }

  // 输入输出示例
  if (s.input_example || s.output_example) {
    let ioHtml = '';
    if (s.input_example) {
      ioHtml += '<div class="skill-io-item"><div class="skill-io-label skill-io-label-in">📥 输入示例</div><div class="skill-io-content">' + escapeHtml(s.input_example) + '</div></div>';
    }
    if (s.output_example) {
      ioHtml += '<div class="skill-io-item"><div class="skill-io-label skill-io-label-out">📤 输出示例</div><div class="skill-io-content">' + formatText(s.output_example) + '</div></div>';
    }
    html += section('🔧 输入 / 输出', ioHtml);
  }

  // 适用场景
  html += listSection('✅ 适用场景', s.applicable_scenarios);

  // 能力标签
  html += tagGroup('🏷️ 核心能力', s.capabilities, 'capability');
  html += tagGroup('📂 支持格式', s.supported_formats, '');
  html += tagGroup('🎨 输出风格', s.output_styles, '');

  // 触发条件
  html += tagGroup('🔍 触发条件', s.triggers, '');

  // 局限性
  html += listSection('⚠️ 局限性', s.limitations);

  // 文件限制 + 版本
  var metaHtml = '';
  if (s.max_file_size_mb) {
    metaHtml += '<div class="skill-detail-meta-item">📦 最大文件：<strong>' + s.max_file_size_mb + ' MB</strong></div>';
  }
  if (s.version) {
    metaHtml += '<div class="skill-detail-meta-item">🔖 版本：<strong>' + escapeHtml(s.version) + '</strong></div>';
  }
  if (s.related_step) {
    metaHtml += '<div class="skill-detail-meta-item">📌 关联步骤：<strong>Step ' + s.related_step + '</strong></div>';
  }
  if (metaHtml) {
    html += '<div class="skill-detail-meta">' + metaHtml + '</div>';
  }

  container.innerHTML = html;
}

async function toggleSkill(skillId, enable) {
  try {
    const resp = await fetch(API_BASE + '/api/skills/' + skillId, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: enable }),
    });
    const data = await resp.json();
    if (data.status === 'ok') {
      await loadSkills();
    } else {
      alert('操作失败: ' + (data.error || '未知错误'));
    }
  } catch (e) {
    alert('网络错误');
  }
}

let editingModelName = null;

function toggleCcbModelFields() {
  const apiType = document.getElementById('new-model-api-type')?.value || 'openai';
  const ccbBlock = document.getElementById('ccb-model-fields');
  const openaiTuning = document.getElementById('openai-model-tuning');
  if (ccbBlock) ccbBlock.classList.toggle('hidden', apiType !== 'ccb_ainlplm');
  if (openaiTuning) openaiTuning.classList.toggle('hidden', apiType === 'ccb_ainlplm');
}

function showAddModelForm() {
  editingModelName = null;
  const titleEl = document.getElementById('model-form-title');
  const saveBtn = document.getElementById('model-form-save-btn');
  const saveBtnText = saveBtn ? saveBtn.querySelector('.btn__text') : null;
  if (titleEl) titleEl.textContent = '添加自定义模型';
  if (saveBtnText) saveBtnText.textContent = '添加';
  document.getElementById('new-model-name').readOnly = false;
  ['new-model-name','new-model-model','new-model-url','new-model-apikey','new-model-desc','new-model-tx-code','new-model-sec-node'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  const apiTypeEl = document.getElementById('new-model-api-type');
  if (apiTypeEl) apiTypeEl.value = 'openai';
  document.getElementById('new-model-maxtokens').value = '4096';
  document.getElementById('new-model-temp').value = '0.7';
  toggleCcbModelFields();
  document.getElementById('add-model-form').classList.remove('hidden');
}

function hideAddModelForm() {
  editingModelName = null;
  document.getElementById('add-model-form').classList.add('hidden');
}

async function editModel(name) {
  try {
    const resp = await fetch(API_BASE + '/api/llm/models/' + encodeURIComponent(name));
    const data = await resp.json();
    if (data.status !== 'ok' || !data.model) {
      alert(data.error || '加载模型失败');
      return;
    }
    const m = data.model;
    editingModelName = name;
    document.getElementById('model-form-title').textContent = m.is_preset ? '编辑预设模型' : '编辑自定义模型';
    const editSaveBtn = document.getElementById('model-form-save-btn');
    const editSaveBtnText = editSaveBtn ? editSaveBtn.querySelector('.btn__text') : null;
    if (editSaveBtnText) editSaveBtnText.textContent = '保存';
    document.getElementById('new-model-name').value = m.name || '';
    document.getElementById('new-model-name').readOnly = true;
    document.getElementById('new-model-model').value = m.model || '';
    document.getElementById('new-model-url').value = m.url || '';
    document.getElementById('new-model-apikey').value = m.api_key || '';
    document.getElementById('new-model-maxtokens').value = m.max_tokens || 4096;
    document.getElementById('new-model-temp').value = m.temperature != null ? m.temperature : 0.7;
    document.getElementById('new-model-desc').value = m.description || '';
    const apiTypeEl = document.getElementById('new-model-api-type');
    if (apiTypeEl) apiTypeEl.value = m.api_type || 'openai';
    const txEl = document.getElementById('new-model-tx-code');
    const secEl = document.getElementById('new-model-sec-node');
    if (txEl) txEl.value = m.tx_code || '';
    if (secEl) secEl.value = m.sec_node_no || '';
    toggleCcbModelFields();
    document.getElementById('add-model-form').classList.remove('hidden');
  } catch (e) {
    alert('加载模型失败: ' + e.message);
  }
}

async function loadModels() {
  try {
    const resp = await fetch(API_BASE + '/api/llm/models');
    const data = await resp.json();
    if (data.status === 'ok') {
      allModels = data.models || [];
      renderModelList();
      refreshModelSelects();
    }
  } catch (e) {
    console.error('Failed to load models:', e);
  }
}

function renderModelList() {
  const container = document.getElementById('model-list');
  if (!allModels.length) {
    container.innerHTML = '<div style="color:var(--text-muted);font-size:12px;padding:12px">暂无模型配置</div>';
    return;
  }
  let html = '';
  allModels.forEach((m, idx) => {
    const cls = m.is_preset ? 'preset' : 'custom';
    const badge = m.is_preset ? '<span style="font-size:10px;padding:1px 5px;background:var(--red);color:#fff;border-radius:2px">预设</span>' : '<span style="font-size:10px;padding:1px 5px;background:#3491fa;color:#fff;border-radius:2px">自定义</span>';
    const apiBadge = (m.api_type === 'ccb_ainlplm')
      ? '<span style="font-size:10px;padding:1px 5px;background:#6b4;border-radius:2px;color:#fff">建行</span>'
      : '<span style="font-size:10px;padding:1px 5px;background:#888;border-radius:2px;color:#fff">OpenAI</span>';
    html += '<div class="model-card ' + cls + '">';
    html += '<div class="model-card-name">' + escapeHtml(m.name) + ' ' + badge + ' ' + apiBadge + '</div>';
    html += '<div class="model-card-model">' + escapeHtml(m.model) + '</div>';
    if (m.description) html += '<div class="model-card-desc">' + escapeHtml(m.description) + '</div>';
    html += '<div class="model-card-url">' + escapeHtml(m.url) + '</div>';
    html += '<div class="model-card-key">Key: ' + escapeHtml(m.api_key || m.api_key_masked || '') + '</div>';
    html += '<div class="model-card-actions">';
    html += renderBtn({ variant: 'outline', size: 'sm', icon: 'pencil', text: '编辑', cls: 'model-card-btn', attrs: 'data-action="edit" data-model-index="' + idx + '"' });
    html += renderBtn({ variant: 'ghost', size: 'sm', icon: 'activity', text: '测试连接', cls: 'model-card-btn', attrs: 'data-action="test" data-model-index="' + idx + '"' });
    html += renderBtn({ variant: 'ghost', size: 'sm', icon: 'activity', text: '流式测试', cls: 'model-card-btn', attrs: 'data-action="stream" data-model-index="' + idx + '"' });
    if (!m.is_preset) {
      html += renderBtn({ variant: 'danger', size: 'sm', icon: 'trash-2', text: '删除', cls: 'model-card-btn', attrs: 'data-action="delete" data-model-index="' + idx + '"' });
    }
    html += '</div>';
    html += '<div class="model-card-status" id="model-status-' + idx + '"></div>';
    html += '<div class="model-card-stream hidden" id="model-stream-' + idx + '"></div>';
    html += '</div>';
  });
  container.innerHTML = html;
  refreshIcons();
}

function initModelListEvents() {
  const container = document.getElementById('model-list');
  if (!container || container._modelEventsBound) return;
  container._modelEventsBound = true;
  container.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-action]');
    if (!btn) return;
    e.preventDefault();
    e.stopPropagation();
    const idx = parseInt(btn.dataset.modelIndex, 10);
    const m = allModels[idx];
    if (!m) return;
    const action = btn.dataset.action;
    if (action === 'test') testModel(m.name, idx, btn);
    else if (action === 'stream') testModelStream(m.name, idx, btn);
    else if (action === 'edit') editModel(m.name);
    else if (action === 'delete') deleteModel(m.name);
  });
}

function resolveModelName(selectId) {
  const el = document.getElementById(selectId);
  if (el && el.value) return el.value;
  if (allModels && allModels.length) return allModels[0].name;
  return '';
}

function refreshModelSelects() {
  const selects = ['s2-model', 's3-model', 's4-model', 's5-model'];
  selects.forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    const cur = el.value;
    el.innerHTML = '<option value="">-- 选择模型 --</option>';
    allModels.forEach(m => {
      const opt = document.createElement('option');
      opt.value = m.name;
      opt.textContent = m.name + (m.is_preset ? ' (预设)' : '');
      el.appendChild(opt);
    });
    if (cur) el.value = cur;
  });
}

// Skill step mapping: which skills are relevant to which step
const SKILL_STEP_MAP = {
  2: ['knowledge-extraction'],
  3: ['knowledge-revision'],
};

async function loadStepSkillSelects(step) {
  const selectId = 's' + step + '-skill-select';
  const el = document.getElementById(selectId);
  if (!el) return;

  el.innerHTML = '<option value="">-- 选择 Skill --</option>';

  try {
    const resp = await fetch(API_BASE + '/api/skills');
    const data = await resp.json();
    if (data.status !== 'ok') return;

    const skills = data.skills || [];
    const relevantIds = SKILL_STEP_MAP[step] || [];

    skills.forEach(s => {
      if (s.enabled === false) return;
      // If step has specific skill mapping, filter by it
      if (relevantIds.length > 0 && !relevantIds.includes(s.id)) return;

      const opt = document.createElement('option');
      opt.value = s.id;
      opt.textContent = s.name + ' - ' + (s.description || '').substring(0, 30);
      el.appendChild(opt);
    });
  } catch (e) {
    console.error('Failed to load skills:', e);
  }
}

function setModelTestStatus(statusEl, state, message) {
  if (!statusEl) return;
  statusEl.className = 'model-card-status ' + (state || '');
  statusEl.textContent = message || '';
}

async function testModelStream(name, modelIndex, btnEl) {
  const statusEl = document.getElementById('model-status-' + modelIndex);
  const streamEl = document.getElementById('model-stream-' + modelIndex);
  if (streamEl) {
    streamEl.classList.remove('hidden');
    streamEl.textContent = '';
  }
  if (btnEl) {
    btnEl.disabled = true;
    btnEl.innerHTML = renderBtnChildren({ icon: 'activity', text: '流式中...' });
    refreshIcons();
  }
  setModelTestStatus(statusEl, 'testing', '流式连接 ' + name + ' ...');
  let fullText = '';
  try {
    const resp = await fetch(API_BASE + '/api/llm/stream-test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name, prompt: '你好，请用一句话介绍你自己。' }),
    });
    if (!resp.ok || !resp.body) {
      throw new Error('流式请求失败 HTTP ' + resp.status);
    }
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split('\n\n');
      buffer = parts.pop() || '';
      for (const part of parts) {
        const line = part.split('\n').find(l => l.startsWith('data:'));
        if (!line) continue;
        try {
          const payload = JSON.parse(line.replace(/^data:\s*/, ''));
          if (payload.error) throw new Error(payload.error);
          if (payload.delta) {
            fullText += payload.delta;
            if (streamEl) streamEl.textContent = fullText;
          }
          if (payload.done) break;
        } catch (parseErr) {
          if (parseErr.message && parseErr.message !== 'Unexpected end of JSON input') throw parseErr;
        }
      }
    }
    setModelTestStatus(statusEl, 'ok', '流式完成: ' + (fullText.slice(0, 80) || '(空)'));
  } catch (e) {
    setModelTestStatus(statusEl, 'fail', e.message || '流式失败');
    if (streamEl) streamEl.textContent = '错误: ' + (e.message || '流式失败');
  }
  if (btnEl) {
    btnEl.disabled = false;
    btnEl.innerHTML = renderBtnChildren({ icon: 'activity', text: '流式测试' });
    refreshIcons();
  }
}

async function testModel(name, modelIndex, btnEl) {
  const statusEl = document.getElementById('model-status-' + modelIndex);
  if (btnEl) {
    btnEl.disabled = true;
    btnEl.innerHTML = renderBtnChildren({ icon: 'activity', text: '测试中...' });
    refreshIcons();
  }
  setModelTestStatus(statusEl, 'testing', '正在连接 ' + name + ' ...');
  try {
    const result = await apiCallJSON('/api/llm/test', { name: name }, 'POST', 25000);
    if (result.status === 'ok') {
      setModelTestStatus(statusEl, 'ok', result.message || '连接成功');
    } else {
      setModelTestStatus(statusEl, 'fail', result.error || '连接失败');
    }
  } catch (e) {
    setModelTestStatus(statusEl, 'fail', e.message || '连接失败');
  }
  if (btnEl) {
    btnEl.disabled = false;
    btnEl.innerHTML = renderBtnChildren({ icon: 'activity', text: '测试连接' });
    refreshIcons();
  }
}

async function saveModel() {
  const name = document.getElementById('new-model-name').value.trim();
  const model = document.getElementById('new-model-model').value.trim();
  const url = document.getElementById('new-model-url').value.trim();
  const apiKey = document.getElementById('new-model-apikey').value.trim();
  const apiType = document.getElementById('new-model-api-type')?.value || 'openai';
  const maxTokens = parseInt(document.getElementById('new-model-maxtokens').value) || 4096;
  const temp = parseFloat(document.getElementById('new-model-temp').value) || 0.7;
  const desc = document.getElementById('new-model-desc').value.trim();
  const txCode = document.getElementById('new-model-tx-code')?.value.trim() || '';
  const secNode = document.getElementById('new-model-sec-node')?.value.trim() || '';

  if (!name || !model || !url) {
    alert('名称、模型标识、API 地址均为必填');
    return;
  }
  if (!editingModelName && !apiKey) {
    alert('添加模型时 API Key 为必填');
    return;
  }
  if (apiType === 'ccb_ainlplm' && (!txCode || !secNode)) {
    alert('建行接口需填写 Tx-Code 与 Sec-Node-No');
    return;
  }

  const payload = {
    name, model, url, api_type: apiType,
    max_tokens: maxTokens, temperature: temp, description: desc
  };
  if (apiKey) payload.api_key = apiKey;
  if (apiType === 'ccb_ainlplm') {
    payload.tx_code = txCode;
    payload.sec_node_no = secNode;
  }

  try {
    let result;
    if (editingModelName) {
      result = await apiCallJSON(
        '/api/llm/models/' + encodeURIComponent(editingModelName),
        payload,
        'PUT'
      );
    } else {
      result = await apiCallJSON('/api/llm/models', payload, 'POST');
    }
    if (result.status === 'ok') {
      hideAddModelForm();
      loadModels();
    } else {
      alert(result.error || (editingModelName ? '保存失败' : '添加失败'));
    }
  } catch (e) {
    alert((editingModelName ? '保存失败: ' : '添加失败: ') + e.message);
  }
}

async function deleteModel(name) {
  if (!confirm('确定删除模型 "' + name + '"？')) return;
  try {
    const resp = await fetch(API_BASE + '/api/llm/models/' + encodeURIComponent(name), { method: 'DELETE' });
    const result = await resp.json();
    if (result.status === 'ok') {
      loadModels();
    } else {
      alert(result.error || '删除失败');
    }
  } catch (e) {
    alert('删除失败: ' + e.message);
  }
}

// Load models on startup
initModelListEvents();
loadModels();



  global.App = global.App || {};
  const Panels = {
    openModelPanel,
    closeModelPanel,
    openSkillPanel,
    closeSkillPanel,
    loadSkills,
    renderSkills,
    toggleSkillDetail,
    renderSkillDetail,
    toggleSkill,
    toggleCcbModelFields,
    showAddModelForm,
    hideAddModelForm,
    editModel,
    loadModels,
    renderModelList,
    initModelListEvents,
    resolveModelName,
    refreshModelSelects,
    loadStepSkillSelects,
    setModelTestStatus,
    testModelStream,
    testModel,
    saveModel,
    deleteModel,
  };
  global.App.Panels = Panels;
})(window);

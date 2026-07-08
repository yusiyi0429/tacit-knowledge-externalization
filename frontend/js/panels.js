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

const SKILL_CONTENT_EN = {
  'knowledge-extraction': {
    name: 'Knowledge Extraction',
    description: 'Generate the initial Agent SKILL.md draft from the scenario skeleton and knowledge documents via LLM.',
    detailed_description: 'Knowledge Extraction is the core entry point of the tacit-knowledge pipeline. It receives the scenario skeleton produced in Step 1 (business domain, customer profile, marketing goals) and expert-provided knowledge documents (policies, case reviews, training materials), then uses an LLM to distill a structured Agent SKILL.md.\n\nSKILL.md contains role definition, core workflow, decision rules, data access logic, and serves as the input for subsequent steps.',
    business_value: 'Transform expert experience scattered across documents, policies, and cases into machine-executable Agent Skills, significantly reducing the manual cost of knowledge accumulation. One extraction covers a complete business scenario and can be iterated through the pipeline.',
    usage_guide: '1. Ensure Step 1 Scenario Anchoring is complete and the skeleton is generated.\n2. Prepare knowledge documents (.txt / .docx / .pdf, or paste text directly).\n3. Select Markdown pipeline mode in the UI.\n4. Choose a model and click Run Knowledge Extraction.\n5. Wait for the LLM to generate the SKILL.md draft, then preview and confirm.',
    input_example: 'Scenario: marketing potential of public-fund inclusive customers\nKnowledge document: a .txt file containing customer screening rules, data tags, and decision suggestions.',
    output_example: 'A SKILL.md file containing: role definition (you are a public-fund account manager), core workflow, data table references, and decision rules.',
    applicable_scenarios: ['Public-fund customer potential mining', 'Inclusive loan product recommendation', 'Customer segmentation and precision marketing', 'New customer admission assessment'],
    capabilities: ['Scenario skeleton parsing', 'Knowledge document understanding', 'Rule and logic extraction', 'Agent SKILL.md generation'],
    supported_formats: ['.txt', '.docx', '.pdf', 'Plain-text paste'],
    output_styles: ['Structured SKILL.md', 'With role / workflow / rules / data'],
    triggers: ['After Step 1 Scenario Anchoring is complete', 'When user uploads documents and selects Knowledge Extraction'],
    limitations: ['Output quality depends on input document quality', 'LLM-generated draft needs expert confirmation in Step 3', 'Deep parsing of image/table documents is not supported']
  },
  'knowledge-revision': {
    name: 'Knowledge Alignment',
    description: 'Revise and align SKILL.md based on expert natural-language feedback via LLM.',
    detailed_description: 'Knowledge Alignment is the expert-in-the-loop revision stage. It takes the SKILL.md draft produced in Step 2 and combines it with expert natural-language feedback (e.g., "add a founded-year check to customer screening", "fix the limit calculation according to policy XX"). The LLM performs semantic-level revision and produces a new SKILL.md.\n\nMulti-round revision is supported: each round of feedback generates an independent revision version without overwriting history, and experts can preview differences in the UI.',
    business_value: 'Bridges the gap between LLM drafts and actual expert experience. Through natural-language interaction instead of manual editing, tacit judgments ("how to handle normal cases", "what are the boundary conditions") are quickly incorporated into the knowledge system to ensure outputs match business reality.',
    usage_guide: '1. Review the SKILL.md draft generated in Step 2.\n2. Describe the required changes in natural language in the Expert Feedback box.\n3. Choose a model and click Send & Smart Revise.\n4. Preview the revised SKILL.md; provide further feedback if needed.\n5. After confirmation, proceed to Step 4.',
    input_example: 'Expert feedback: "For customer screening, tech enterprises must also be checked for valid patents; those without patents should not be prioritized even if they have qualification tags. For limit calculation, add a rule: if the customer has an on-track credit loan from another bank, the limit can be moderately increased."',
    output_example: 'A revised SKILL.md that: 1) adds a "valid patent" branch to customer screening rules; 2) adds an uplift rule for "on-track credit loan from another bank"; 3) keeps the logic consistent.',
    applicable_scenarios: ['LLM draft needs expert review', 'Business rules or policies change', 'Multi-round iterative optimization'],
    capabilities: ['Natural-language feedback understanding', 'SKILL.md semantic revision', 'Multi-round revision versioning', 'Revision log and diff tracking'],
    supported_formats: ['Full SKILL.md revision'],
    output_styles: ['Revised SKILL.md', 'With revision metadata'],
    triggers: ['After Step 2 Knowledge Extraction', 'Expert submits feedback in Step 3 UI'],
    limitations: ['Focus each feedback on one topic to avoid quality loss', 'Revision scope is limited by LLM context window', 'Automatic logic verification is not guaranteed; expert confirmation is required']
  },
  'skill-generator': {
    name: 'Skill Generator',
    description: 'Generate QA pairs, chain-of-thought, and a pending Agent-Skill package from the finalized SKILL.md.',
    detailed_description: 'Skill Generator is the delivery stage of the pipeline. It transforms the expert-confirmed SKILL.md into a directly distributable Agent Skill package.\n\nOutputs include three parts: 1) QA pairs for accuracy evaluation; 2) Chain-of-Thought (step-by-step reasoning for core decisions); 3) Agent-Skill executable package (zip with SKILL.md, manifest.json, execution scripts, conforming to agentskills.io standards).\n\nThe generated Agent-Skill can be validated in Step 5 with P/R/F1 metrics before final release.',
    business_value: 'One-click packaging from human knowledge to distributable, executable Agent Skills. QA pairs can be used for regression testing, CoT helps new users understand model reasoning, and the zip can be distributed to frontline account managers.',
    usage_guide: '1. Ensure Step 3 Knowledge Alignment is complete and SKILL.md is confirmed.\n2. In the Step 4 UI select Build Skill.\n3. Wait for the LLM to generate the three deliverables: QA pairs, CoT, and Agent-Skill zip.\n4. Preview the QA pairs and chain-of-thought.\n5. Proceed to Step 5 for validation replay.',
    input_example: 'Input: the Step-3 expert-confirmed SKILL.md for public-fund inclusive customer potential marketing (including customer screening rules, limit calculation logic, product recommendation strategy, etc.).',
    output_example: 'Three files: 1) qa_*.json — about 10-20 QA pairs covering admission judgment, product recommendation, rejection reasons, etc.; 2) cot_*.md — step-by-step reasoning from customer information to marketing recommendation; 3) SKILL_VERIFY_*.zip — deployable Agent Skill package.',
    applicable_scenarios: ['After SKILL.md is finalized', 'QA validation dataset needed', 'Chain-of-thought explanation needed'],
    capabilities: ['SKILL.md parsing and restructuring', 'QA validation set generation', 'Chain-of-thought generation', 'Agent-Skill zip packaging'],
    supported_formats: ['SKILL.md → QA JSON + CoT Markdown + Skill zip'],
    output_styles: ['Structured QA pairs', 'Markdown chain-of-thought', 'agentskills.io standard zip'],
    triggers: ['After Step 3 Knowledge Alignment is confirmed'],
    limitations: ['QA coverage depends on SKILL.md completeness', 'CoT is LLM-derived and may have reasoning blind spots', 'Zip must pass Step 5 P/R/F1 validation before release']
  }
};

const MODEL_DESC_EN = {
  'DeepSeek-V4-Flash': 'DeepSeek V4 Flash official API, supports thinking + reasoning_effort.',
  'CCB-ainlplm-示例': 'CCB internal ainlplm gateway (called with Access_Key_Id / Tx-Code / Sec-Node-No).',
  'Minimax-M2.7': 'Minimax M2.7 with strong long-text capability, suitable for document analysis.',
  'Qwen3.5-35B': 'Qwen 3.5 35B with balanced capability, suitable for dialogue and generation.'
};

async function loadSkills() {
  const body = document.getElementById('skill-panel-body');
  body.innerHTML = '<div class="skill-loading">' + t('loading', '加载中...') + '</div>';
  try {
    const resp = await fetch(API_BASE + '/api/skills');
    const data = await resp.json();
    if (data.status === 'ok') {
      allSkills = data.skills || [];
      renderSkills(body);
    } else {
      body.innerHTML = '<div class="skill-error">' + t('load_failed', '加载失败') + '</div>';
    }
  } catch (e) {
    body.innerHTML = '<div class="skill-error">' + t('network_error', '网络错误') + '</div>';
  }
}

function renderSkills(container) {
  const lang = App.I18n.getLang();
  if (allSkills.length === 0) {
    container.innerHTML = '<div class="skill-empty">' + t('skill_no_registered', '暂无已注册的 Skill') + '</div>';
    return;
  }
  let html = '<div class="skill-section"><div class="skill-section-header"><span>' + t('skill_registered', '已注册技能') + '</span><span style="font-weight:400;color:#aaa">' + allSkills.length + '</span></div>';
  for (const skill of allSkills) {
    const enabled = skill.enabled !== false;
    const meta = SKILL_META[skill.id] || { icon: '⚡', iconCls: 'icon-blue' };
    const en = lang === 'en' ? SKILL_CONTENT_EN[skill.id] : null;
    const name = en && en.name ? en.name : escapeHtml(skill.name);
    const brief = enabled ? t('skill_enabled', '已启用') : t('skill_disabled', '已禁用');
    html += `
      <div class="skill-card ${enabled ? '' : 'skill-card-disabled'}" id="skill-item-${skill.id}" data-skill-id="${skill.id}">
        <div class="skill-card-row" onclick="toggleSkillDetail('${skill.id}')">
          <div class="skill-card-icon ${meta.iconCls}">${meta.icon}</div>
          <div class="skill-card-info">
            <div class="skill-card-name">${name}</div>
            <div class="skill-card-brief">${brief}</div>
          </div>
          <div class="skill-card-controls">
            <div class="skill-toggle ${enabled ? 'on' : ''}" onclick="event.stopPropagation(); toggleSkill('${skill.id}', ${!enabled})">
              <div class="skill-toggle-knob"></div>
            </div>
            <span class="skill-card-arrow" id="skill-arrow-${skill.id}">▾</span>
          </div>
        </div>
        <div class="skill-card-detail hidden" id="skill-detail-${skill.id}">
          <div class="skill-loading">${t('skill_loading_detail', '加载详情...')}</div>
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
        detail.innerHTML = '<div class="skill-error">' + t('skill_load_failed', '加载失败') + '</div>';
      }
    } catch (e) {
      detail.innerHTML = '<div class="skill-error">' + t('skill_network_error', '网络错误') + '</div>';
    }
  }
}

function renderSkillDetail(container, s) {
  const lang = App.I18n.getLang();
  const en = lang === 'en' && SKILL_CONTENT_EN[s.id] ? SKILL_CONTENT_EN[s.id] : null;
  const skill = en ? Object.assign({}, s, en) : s;

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
  if (skill.detailed_description) {
    html += section(t('skill_detail_detailed_description', '📖 详细说明'), '<p>' + formatText(skill.detailed_description) + '</p>');
  }

  // 业务价值
  if (skill.business_value) {
    html += section(t('skill_detail_business_value', '💡 业务价值'), '<p>' + formatText(skill.business_value) + '</p>');
  }

  // 使用指南
  if (skill.usage_guide) {
    html += section(t('skill_detail_usage_guide', '📋 使用步骤'), '<p>' + formatText(skill.usage_guide) + '</p>');
  }

  // 输入输出示例
  if (skill.input_example || skill.output_example) {
    let ioHtml = '';
    if (skill.input_example) {
      ioHtml += '<div class="skill-io-item"><div class="skill-io-label skill-io-label-in">' + t('skill_detail_input_example', '📥 输入示例') + '</div><div class="skill-io-content">' + escapeHtml(skill.input_example) + '</div></div>';
    }
    if (skill.output_example) {
      ioHtml += '<div class="skill-io-item"><div class="skill-io-label skill-io-label-out">' + t('skill_detail_output_example', '📤 输出示例') + '</div><div class="skill-io-content">' + formatText(skill.output_example) + '</div></div>';
    }
    html += section(t('skill_detail_input_output', '🔧 输入 / 输出'), ioHtml);
  }

  // 适用场景
  html += listSection(t('skill_detail_applicable_scenarios', '✅ 适用场景'), skill.applicable_scenarios);

  // 能力标签
  html += tagGroup(t('skill_detail_capabilities', '🏷️ 核心能力'), skill.capabilities, 'capability');
  html += tagGroup(t('skill_detail_supported_formats', '📂 支持格式'), skill.supported_formats, '');
  html += tagGroup(t('skill_detail_output_styles', '🎨 输出风格'), skill.output_styles, '');

  // 触发条件
  html += tagGroup(t('skill_detail_triggers', '🔍 触发条件'), skill.triggers, '');

  // 局限性
  html += listSection(t('skill_detail_limitations', '⚠️ 局限性'), skill.limitations);

  // 文件限制 + 版本
  var metaHtml = '';
  if (skill.max_file_size_mb) {
    metaHtml += '<div class="skill-detail-meta-item">' + t('skill_detail_max_file', '📦 最大文件') + '：<strong>' + skill.max_file_size_mb + ' MB</strong></div>';
  }
  if (skill.version) {
    metaHtml += '<div class="skill-detail-meta-item">' + t('skill_detail_version', '🔖 版本') + '：<strong>' + escapeHtml(skill.version) + '</strong></div>';
  }
  if (skill.related_step) {
    metaHtml += '<div class="skill-detail-meta-item">' + t('skill_detail_related_step', '📌 关联步骤') + '：<strong>Step ' + skill.related_step + '</strong></div>';
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
      alert(t('operation_failed', '操作失败') + ': ' + (data.error || t('unknown_error', '未知错误')));
    }
  } catch (e) {
    alert(t('network_error', '网络错误'));
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
  if (titleEl) titleEl.textContent = t('add_model_title', '添加自定义模型');
  if (saveBtnText) saveBtnText.textContent = t('add', '添加');
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
      alert(data.error || t('load_model_failed', '加载模型失败'));
      return;
    }
    const m = data.model;
    editingModelName = name;
    document.getElementById('model-form-title').textContent = m.is_preset ? t('edit_preset_model', '编辑预设模型') : t('edit_custom_model', '编辑自定义模型');
    const editSaveBtn = document.getElementById('model-form-save-btn');
    const editSaveBtnText = editSaveBtn ? editSaveBtn.querySelector('.btn__text') : null;
    if (editSaveBtnText) editSaveBtnText.textContent = t('save', '保存');
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
  const lang = App.I18n.getLang();
  if (!allModels.length) {
    container.innerHTML = '<div style="color:var(--text-muted);font-size:12px;padding:12px">' + t('model_no_config', '暂无模型配置') + '</div>';
    return;
  }
  let html = '';
  allModels.forEach((m, idx) => {
    const cls = m.is_preset ? 'preset' : 'custom';
    const badge = m.is_preset
      ? '<span style="font-size:10px;padding:1px 5px;background:var(--red);color:#fff;border-radius:2px">' + t('model_badge_preset', '预设') + '</span>'
      : '<span style="font-size:10px;padding:1px 5px;background:#3491fa;color:#fff;border-radius:2px">' + t('model_badge_custom', '自定义') + '</span>';
    const apiBadge = (m.api_type === 'ccb_ainlplm')
      ? '<span style="font-size:10px;padding:1px 5px;background:#6b4;border-radius:2px;color:#fff">' + t('model_badge_ccb', '建行') + '</span>'
      : '<span style="font-size:10px;padding:1px 5px;background:#888;border-radius:2px;color:#fff">' + t('model_badge_openai', 'OpenAI') + '</span>';
    const desc = lang === 'en' && MODEL_DESC_EN[m.name] ? MODEL_DESC_EN[m.name] : m.description;
    html += '<div class="model-card ' + cls + '">';
    html += '<div class="model-card-name">' + escapeHtml(m.name) + ' ' + badge + ' ' + apiBadge + '</div>';
    html += '<div class="model-card-model">' + escapeHtml(m.model) + '</div>';
    if (desc) html += '<div class="model-card-desc">' + escapeHtml(desc) + '</div>';
    html += '<div class="model-card-url">' + escapeHtml(m.url) + '</div>';
    html += '<div class="model-card-key">' + t('model_key', 'Key:') + ' ' + escapeHtml(m.api_key || m.api_key_masked || '') + '</div>';
    html += '<div class="model-card-actions">';
    html += renderBtn({ variant: 'outline', size: 'sm', icon: 'pencil', text: t('model_edit', '编辑'), cls: 'model-card-btn', attrs: 'data-action="edit" data-model-index="' + idx + '"' });
    html += renderBtn({ variant: 'ghost', size: 'sm', icon: 'activity', text: t('model_test_connection', '测试连接'), cls: 'model-card-btn', attrs: 'data-action="test" data-model-index="' + idx + '"' });
    html += renderBtn({ variant: 'ghost', size: 'sm', icon: 'activity', text: t('model_stream_test', '流式测试'), cls: 'model-card-btn', attrs: 'data-action="stream" data-model-index="' + idx + '"' });
    if (!m.is_preset) {
      html += renderBtn({ variant: 'danger', size: 'sm', icon: 'trash-2', text: t('model_delete', '删除'), cls: 'model-card-btn', attrs: 'data-action="delete" data-model-index="' + idx + '"' });
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
    el.innerHTML = '<option value="">' + t('model_select_placeholder', '-- 选择模型 --') + '</option>';
    allModels.forEach(m => {
      const opt = document.createElement('option');
      opt.value = m.name;
      opt.textContent = m.name + (m.is_preset ? ' (' + t('model_badge_preset', '预设') + ')' : '');
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
  const lang = App.I18n.getLang();

  el.innerHTML = '<option value="">' + t('model_select_skill_placeholder', '-- 选择 Skill --') + '</option>';

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

      const en = lang === 'en' && SKILL_CONTENT_EN[s.id] ? SKILL_CONTENT_EN[s.id] : null;
      const sName = en && en.name ? en.name : s.name;
      const sDesc = en && en.description ? en.description : (s.description || '');
      const opt = document.createElement('option');
      opt.value = s.id;
      opt.textContent = sName + ' - ' + sDesc.substring(0, 30);
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
    btnEl.innerHTML = renderBtnChildren({ icon: 'activity', text: t('model_streaming', '流式中...') });
    refreshIcons();
  }
  setModelTestStatus(statusEl, 'testing', t('model_stream_connect_prefix', '流式连接') + ' ' + name + ' ...');
  let fullText = '';
  try {
    const resp = await fetch(API_BASE + '/api/llm/stream-test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: name,
        prompt: App.I18n.getLang() === 'en' ? 'Hello, please introduce yourself in one sentence.' : '你好，请用一句话介绍你自己。',
        lang: App.I18n.getLang()
      }),
    });
    if (!resp.ok || !resp.body) {
      throw new Error(t('model_stream_request_failed', '流式请求失败') + ' HTTP ' + resp.status);
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
    setModelTestStatus(statusEl, 'ok', t('model_stream_complete_prefix', '流式完成: ') + (fullText.slice(0, 80) || t('model_empty_response', '(空)')));
  } catch (e) {
    setModelTestStatus(statusEl, 'fail', e.message || t('model_stream_failed', '流式失败'));
    if (streamEl) streamEl.textContent = t('model_error_prefix', '错误: ') + (e.message || t('model_stream_failed', '流式失败'));
  }
  if (btnEl) {
    btnEl.disabled = false;
    btnEl.innerHTML = renderBtnChildren({ icon: 'activity', text: t('model_stream_test', '流式测试') });
    refreshIcons();
  }
}

async function testModel(name, modelIndex, btnEl) {
  const statusEl = document.getElementById('model-status-' + modelIndex);
  if (btnEl) {
    btnEl.disabled = true;
    btnEl.innerHTML = renderBtnChildren({ icon: 'activity', text: t('model_testing', '测试中...') });
    refreshIcons();
  }
  setModelTestStatus(statusEl, 'testing', t('model_connecting_prefix', '正在连接') + ' ' + name + ' ...');
  try {
    const result = await apiCallJSON('/api/llm/test', { name: name, lang: App.I18n.getLang() }, 'POST', 25000);
    if (result.status === 'ok') {
      setModelTestStatus(statusEl, 'ok', result.message || t('model_connection_ok', '连接成功'));
    } else {
      setModelTestStatus(statusEl, 'fail', result.error || t('model_connection_failed', '连接失败'));
    }
  } catch (e) {
    setModelTestStatus(statusEl, 'fail', e.message || t('model_connection_failed', '连接失败'));
  }
  if (btnEl) {
    btnEl.disabled = false;
    btnEl.innerHTML = renderBtnChildren({ icon: 'activity', text: t('model_test_connection', '测试连接') });
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
    alert(t('model_required_fields', '名称、模型标识、API 地址均为必填'));
    return;
  }
  if (!editingModelName && !apiKey) {
    alert(t('model_api_key_required', '添加模型时 API Key 为必填'));
    return;
  }
  if (apiType === 'ccb_ainlplm' && (!txCode || !secNode)) {
    alert(t('model_ccb_required', '建行接口需填写 Tx-Code 与 Sec-Node-No'));
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
      alert(result.error || (editingModelName ? t('model_save_failed', '保存失败') : t('model_add_failed', '添加失败')));
    }
  } catch (e) {
    alert((editingModelName ? t('model_save_failed', '保存失败') + ': ' : t('model_add_failed', '添加失败') + ': ') + e.message);
  }
}

async function deleteModel(name) {
  if (!confirm(t('model_delete_confirm', '确定删除模型 "{name}"？').replace('{name}', name))) return;
  try {
    const resp = await fetch(API_BASE + '/api/llm/models/' + encodeURIComponent(name), { method: 'DELETE' });
    const result = await resp.json();
    if (result.status === 'ok') {
      loadModels();
    } else {
      alert(result.error || t('model_delete_failed', '删除失败'));
    }
  } catch (e) {
    alert(t('model_delete_failed', '删除失败') + ': ' + e.message);
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

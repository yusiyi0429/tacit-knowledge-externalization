/* ===== State ===== */
let currentStep = 0;
const API_BASE = window.location.origin;
let allModels = [];
let currentPipeline = null; // { id, name, scenario, domain, current_step, step_status, step_data }
const MAX_STEP = 5;
const MAX_FORM_STEP = 3;
const STEP_NAMES = { 1: "场景锚定", 2: "知识萃取", 3: "知识对齐", 4: "智能转化", 5: "验证回放" };
let _formSaveTimer = null;
let _lastStep2ExtractedText = '';
let _step2InputMode = 'doc'; // 'doc' | 'case'
let _step2ActiveSkill = 'knowledge-extraction'; // 当前选中的 Skill
let _alignTacitAnnotations = {}; // { noteId: { question, answer } } — Step3 修订经验批注缓存

/* ===== Lucide icons helper ===== */
function refreshIcons() {
  if (window.lucide && typeof window.lucide.createIcons === 'function') {
    window.lucide.createIcons();
  }
}

/* ===== Button markup helper ===== */
function renderBtn(opts) {
  opts = opts || {};
  const variant = opts.variant || 'primary';
  const size = opts.size || 'md';
  const classes = ['btn', 'btn--' + variant, 'btn--' + size];
  if (opts.cls) classes.push(opts.cls);
  const iconHtml = opts.icon ? '<span class="btn__icon btn__icon--' + (opts.iconPosition || 'left') + '" data-lucide="' + escapeHtml(opts.icon) + '"></span>' : '';
  const textHtml = opts.text ? '<span class="btn__text">' + escapeHtml(opts.text) + '</span>' : '';
  const idAttr = opts.id ? ' id="' + opts.id + '"' : '';
  const typeAttr = opts.type !== false ? ' type="' + (opts.type || 'button') + '"' : '';
  const attrs = opts.attrs ? ' ' + opts.attrs : '';
  return '<button' + typeAttr + ' class="' + classes.join(' ') + '"' + idAttr + attrs + '>' + iconHtml + textHtml + '</button>';
}

function renderBtnChildren(opts) {
  opts = opts || {};
  const iconHtml = opts.icon ? '<span class="btn__icon btn__icon--' + (opts.iconPosition || 'left') + '" data-lucide="' + escapeHtml(opts.icon) + '"></span>' : '';
  const textHtml = opts.text ? '<span class="btn__text">' + escapeHtml(opts.text) + '</span>' : '';
  return iconHtml + textHtml;
}

/* ===== Step2 Skill 卡片选择 ===== */
function selectStep2Skill(skillId) {
  _step2ActiveSkill = skillId;
  // 更新卡片选中态
  document.querySelectorAll('.s2-skill-card').forEach(function (c) {
    c.classList.toggle('active', c.dataset.skill === skillId);
  });
  // 同步隐藏下拉框
  var sel = document.getElementById('s2-skill-select');
  if (sel) sel.value = skillId;

  // 显示/隐藏条件元素
  var isExtraction = (skillId === 'knowledge-extraction');
  var isPattern = (skillId === 'knowledge-pattern-mining');
  var isGap = (skillId === 'knowledge-gap-analysis');

  // 萃取风格（仅知识萃取）
  var styleGroup = document.getElementById('s2-group-style');
  if (styleGroup) styleGroup.classList.toggle('hidden', !isExtraction);

  // 模式发现多文件
  var patternFiles = document.getElementById('s2-group-pattern-files');
  var patternText = document.getElementById('s2-group-pattern-text');
  if (patternFiles) patternFiles.classList.toggle('hidden', !isPattern);
  if (patternText) patternText.classList.toggle('hidden', !isPattern);

  // 盲区检测说明
  var gapInfo = document.getElementById('s2-group-gap-info');
  if (gapInfo) gapInfo.classList.toggle('hidden', !isGap);

  // 模式切换 Tab（仅知识萃取时显示）
  var modeTabs = document.getElementById('s2-mode-tabs');
  if (modeTabs) modeTabs.classList.toggle('hidden', !isExtraction);

  // 文档输入面板（非知识萃取时隐藏文档/案例面板，使用skill自有输入）
  var docPanel = document.getElementById('s2-panel-doc');
  var casePanel = document.getElementById('s2-panel-case');
  if (docPanel) docPanel.classList.toggle('hidden', !isExtraction);
  if (casePanel) casePanel.classList.toggle('hidden', !isExtraction || _step2InputMode !== 'case');

  // 更新按钮文字
  var btnText = document.getElementById('s2-btn-text');
  var labels = {
    'knowledge-extraction': '执行知识萃取',
    'knowledge-pattern-mining': '执行模式发现',
    'knowledge-gap-analysis': '执行盲区检测'
  };
  if (btnText) btnText.textContent = labels[skillId] || '执行';

  updateStep2Readiness();
}

/* ===== 模式发现：文件列表展示 ===== */
function refreshPatternFileList() {
  var input = document.getElementById('s2-pattern-files');
  var list = document.getElementById('s2-pattern-filelist');
  var items = document.getElementById('s2-pattern-fileitems');
  var count = document.getElementById('s2-pattern-filecount');
  var status = document.getElementById('s2-pattern-filestatus');
  if (!input || !list || !items) return;

  var files = input.files || [];
  if (files.length === 0) { list.classList.add('hidden'); return; }
  list.classList.remove('hidden');

  count.textContent = files.length + ' 个文件';
  var html = '';
  for (var i = 0; i < files.length; i++) {
    var size = files[i].size > 1024 ? (files[i].size / 1024).toFixed(1) + ' KB' : files[i].size + ' B';
    html += '<div class="s2-pattern-fileitem"><span class="s2-pattern-fileitem-icon">📄</span><span class="s2-pattern-fileitem-name">' + escapeHtml(files[i].name) + '</span><span class="s2-pattern-fileitem-size">' + size + '</span></div>';
  }
  items.innerHTML = html;

  if (status) {
    if (files.length >= 2) { status.className = 's2-pattern-filelist-status ok'; status.textContent = '✅ 已满足最低要求（≥2个案例）'; }
    else { status.className = 's2-pattern-filelist-status warn'; status.textContent = '⚠️ 至少需要 2 个案例文件，请继续添加'; }
  }
  updateStep2Readiness();
}

function clearPatternFiles() {
  var input = document.getElementById('s2-pattern-files');
  if (input) input.value = '';
  refreshPatternFileList();
}

/** 各步骤产出物字段：保存表单时不得覆盖丢失 */
const PIPELINE_OUTPUT_KEYS = [
  'step1_output_file', 'step1_download_url', 'step1_md_file', 'step1_md_download_url', 'step1_output_format',
  'step1_knowledge_columns', 'step1_template_source', 'step1_template_name',
  'step2_output_file', 'step2_download_url', 'step2_md_file', 'step2_md_download_url', 'step2_extracted_count',
  'skill_extract_result', 'skill_extract_style',
  'step2_fusion_file', 'step2_fusion_download_url', 'step2_fusion_count', 'step2_fusion_conflicts', 'step2_fusion_sources',
  'step2_interview_file', 'step2_interview_count',
  'step2_signal_report_file', 'step2_signal_report_url', 'step2_source_count', 'step2_dedup_count',
  'step2_draft_file', 'step2_draft_url', 'step2_draft_md_file', 'step2_draft_md_url', 'step2_draft_version',
  'step3_revision_file', 'step3_download_url', 'step3_md_file', 'step3_md_download_url', 'step3_revision_notes', 'step3_revision_style', 'step3_revision_count', 'step3_excel_path',
  'step3_final_file', 'step3_final_download_url', 'step3_final_md_file', 'step3_final_md_download_url', 'step3_final_notes', 'step3_final_style', 'step3_final_count',
  'step3_aligned_file', 'step3_aligned_url', 'step3_aligned_md_file', 'step3_aligned_md_url', 'step3_aligned_version', 'step3_pending_suggestions',
  'step4_skill_file', 'step4_download_url',
  'step4_cot_file', 'step4_cot_download_url',
  'step4_qa_file', 'step4_qa_download_url', 'step4_qa_md_file', 'step4_qa_md_download_url',
  'step4_manifest_file', 'step4_manifest_url',
  'step4_quality_file', 'step4_quality_url',
  'step4_published_version',
  'step5_replay_file', 'step5_replay_url', 'step5_result_file', 'step5_result_url',
  'step5_suggestions_file', 'step5_suggestions_url', 'step5_hit_rate', 'step5_case_source', 'step5_run_id',
  'step5_golden_report_file', 'step5_golden_report_url',
];

const DOWNSTREAM_OUTPUT_KEYS = [
  'step2_output_file', 'step2_download_url', 'step2_md_file', 'step2_md_download_url', 'step2_extracted_count', 'skill_extract_result', 'skill_extract_style',
  'step2_fusion_file', 'step2_fusion_download_url', 'step2_fusion_count', 'step2_fusion_conflicts', 'step2_fusion_sources',
  'step2_interview_file', 'step2_interview_count',
  'step2_signal_report_file', 'step2_signal_report_url', 'step2_source_count', 'step2_dedup_count',
  'step2_draft_file', 'step2_draft_url', 'step2_draft_md_file', 'step2_draft_md_url', 'step2_draft_version',
  'step3_revision_file', 'step3_download_url', 'step3_md_file', 'step3_md_download_url', 'step3_revision_notes', 'step3_revision_style', 'step3_revision_count', 'step3_excel_path',
  'step3_final_file', 'step3_final_download_url', 'step3_final_md_file', 'step3_final_md_download_url', 'step3_final_notes', 'step3_final_style', 'step3_final_count',
  'step3_aligned_file', 'step3_aligned_url', 'step3_aligned_md_file', 'step3_aligned_md_url', 'step3_aligned_version', 'step3_pending_suggestions',
  'step4_skill_file', 'step4_download_url',
  'step4_cot_file', 'step4_cot_download_url',
  'step4_qa_file', 'step4_qa_download_url', 'step4_qa_md_file', 'step4_qa_md_download_url',
  'step4_manifest_file', 'step4_manifest_url',
  'step4_quality_file', 'step4_quality_url',
  'step4_published_version',
  'step5_replay_file', 'step5_replay_url', 'step5_result_file', 'step5_result_url',
  'step5_suggestions_file', 'step5_suggestions_url', 'step5_hit_rate', 'step5_case_source', 'step5_run_id',
  'step5_golden_report_file', 'step5_golden_report_url',
];

function mergeStepDataPreserveOutputs(serverData, localData, options) {
  const preferServer = options?.preferServer === true;
  const server = serverData || {};
  const local = localData || {};
  const merged = preferServer ? { ...local, ...server } : { ...server, ...local };
  for (const key of PIPELINE_OUTPUT_KEYS) {
    const v = preferServer ? (server[key] || local[key]) : (local[key] || server[key]);
    if (v) merged[key] = v;
  }
  return merged;
}

function isStep3RevisionFile(fileName) {
  const n = String(fileName || '').toLowerCase();
  return n.endsWith('.xlsx') && (n.startsWith('revision_') || n.startsWith('edited_step3_'));
}

function isStep4FinalFile(fileName) {
  const n = String(fileName || '').toLowerCase();
  return n.endsWith('.xlsx') && (n.startsWith('final_') || n.startsWith('edited_step3_'));
}

function prefersMarkdownFlow() {
  const sd = currentPipeline?.step_data || {};
  const direct = String(sd.step1_output_format || '').toLowerCase();
  if (direct) return direct === 'markdown';
  const formFmt = String(sd.step1_form_data?.output_format || '').toLowerCase();
  return formFmt === 'markdown';
}

function resolveArtifact(result) {
  const name = result?.download_name || result?.output_file || result?.file_name || '';
  let url = result?.download_url || '';
  if (name && !url) url = '/downloads/' + name;
  if (url && !/^https?:\/\//i.test(url)) url = url.startsWith('/') ? url : ('/downloads/' + url);
  return { name, url };
}

function clearDownstreamOutputs(fromStep) {
  if (!currentPipeline?.step_data) return;
  const start = fromStep <= 1 ? 2 : (fromStep + 1);
  const keysByStep = {
    2: DOWNSTREAM_OUTPUT_KEYS.filter(k => k.startsWith('step2_') || k.startsWith('skill_')),
    3: DOWNSTREAM_OUTPUT_KEYS.filter(k => k.startsWith('step3_')),
    4: DOWNSTREAM_OUTPUT_KEYS.filter(k => k.startsWith('step4_')),
    5: DOWNSTREAM_OUTPUT_KEYS.filter(k => k.startsWith('step5_')),
  };
  for (let s = start; s <= 5; s++) {
    (keysByStep[s] || []).forEach(k => delete currentPipeline.step_data[k]);
  }
  if (fromStep <= 1) _lastStep2ExtractedText = '';
}

function rememberStep1Output(pipelineId, fileName, downloadUrl) {
  if (!pipelineId || !fileName) return;
  try {
    sessionStorage.setItem('step1_output:' + pipelineId, JSON.stringify({
      file_name: fileName,
      download_url: downloadUrl || ('/downloads/' + fileName),
    }));
  } catch (_) { /* ignore */ }
}

function recallStep1Output(pipelineId) {
  if (!pipelineId) return null;
  try {
    const raw = sessionStorage.getItem('step1_output:' + pipelineId);
    return raw ? JSON.parse(raw) : null;
  } catch (_) {
    return null;
  }
}

let _s1DefaultKnowledgeColumns = [];
let _s1RichMarkdownColumns = [];
let _s1KnowledgeColumnSeq = 0;

function step1IsAbstractColumn(name) {
  const s = String(name || '').trim();
  if (!s) return true;
  return /^(列[a-zA-Z0-9]{1,3}|(column|field|字段)\s*\d+|[a-zA-Z]\d?)$/i.test(s);
}

function step1MergeRichColumnsForMarkdown() {
  const rich = (_s1RichMarkdownColumns.length ? _s1RichMarkdownColumns : _s1DefaultKnowledgeColumns).slice();
  const current = step1GetKnowledgeColumns();
  const substantive = current.filter(c => !step1IsAbstractColumn(c));
  const seen = new Set();
  const merged = [];
  substantive.forEach(c => {
    if (!seen.has(c)) { seen.add(c); merged.push(c); }
  });
  rich.forEach(c => {
    if (!seen.has(c)) { seen.add(c); merged.push(c); }
  });
  if (merged.length) step1RenderKnowledgeColumns(merged);
  return merged;
}

function step1OnOutputFormatChange() {
  const fmt = document.getElementById('s1-output-format')?.value || 'excel';
  if (fmt === 'markdown') step1MergeRichColumnsForMarkdown();
  scheduleFormSave(1);
}

function step1AddKnowledgeColumn(name, idx) {
  const container = document.getElementById('s1-knowledge-columns');
  if (!container) return;
  const i = idx != null ? idx : (++_s1KnowledgeColumnSeq);
  const div = document.createElement('div');
  div.className = 's1-k-col-row';
  div.id = 's1-k-col-' + i;
  div.innerHTML =
    '<input type="text" class="s1-k-col-input" placeholder="如：具体方法、判断逻辑" value="' + escapeHtml(name || '') + '">' +
    '<button type="button" class="btn btn--ghost btn--sm s1-k-col-remove" onclick="step1RemoveKnowledgeColumn(' + i + ')" title="删除"><span class="btn__icon" data-lucide="x"></span></button>';
  container.appendChild(div);
  refreshIcons();
}

function step1RemoveKnowledgeColumn(idx) {
  const el = document.getElementById('s1-k-col-' + idx);
  if (el) el.remove();
}

function step1GetKnowledgeColumns() {
  const cols = [];
  document.querySelectorAll('.s1-k-col-input').forEach(el => {
    const v = el.value.trim();
    if (v) cols.push(v);
  });
  return cols;
}

function step1RenderKnowledgeColumns(columns) {
  const container = document.getElementById('s1-knowledge-columns');
  if (!container) return;
  container.innerHTML = '';
  _s1KnowledgeColumnSeq = 0;
  const list = (columns && columns.length) ? columns : _s1DefaultKnowledgeColumns;
  if (!list.length) {
    step1AddKnowledgeColumn('具体方法', 1);
    return;
  }
  list.forEach((name, i) => step1AddKnowledgeColumn(name, i + 1));
  _s1KnowledgeColumnSeq = list.length;
}

function step1ResetKnowledgeColumns() {
  const fmt = document.getElementById('s1-output-format')?.value || 'excel';
  if (fmt === 'markdown' && _s1RichMarkdownColumns.length) {
    step1RenderKnowledgeColumns(_s1RichMarkdownColumns);
  } else {
    step1RenderKnowledgeColumns(_s1DefaultKnowledgeColumns);
  }
  scheduleFormSave(1);
}

async function loadStep1SchemaAndTemplates(preferredLegacyTemplate, preferredKnowledgeColumns) {
  const legacySelect = document.getElementById('s1-legacy-template');
  try {
    const resp = await fetch(API_BASE + '/api/step1/templates');
    const data = await resp.json();
    if (data.status === 'ok' && Array.isArray(data.schema?.knowledge_columns)) {
      _s1DefaultKnowledgeColumns = data.schema.knowledge_columns.slice();
    }
    if (data.status === 'ok' && Array.isArray(data.schema?.rich_markdown_columns)) {
      _s1RichMarkdownColumns = data.schema.rich_markdown_columns.slice();
    } else if (_s1DefaultKnowledgeColumns.length) {
      _s1RichMarkdownColumns = _s1DefaultKnowledgeColumns.slice();
    }
    if (legacySelect) {
      legacySelect.innerHTML = '<option value="">不使用（按上方自定义列生成）</option>';
      (data.templates || []).forEach(t => {
        const opt = document.createElement('option');
        opt.value = t.name || '';
        opt.textContent = t.label || t.name || '未命名模板';
        legacySelect.appendChild(opt);
      });
      if (preferredLegacyTemplate && Array.from(legacySelect.options).some(o => o.value === preferredLegacyTemplate)) {
        legacySelect.value = preferredLegacyTemplate;
      }
    }
  } catch (e) {
    console.warn('load step1 schema/templates failed:', e);
  }
  if (preferredKnowledgeColumns && preferredKnowledgeColumns.length) {
    step1RenderKnowledgeColumns(preferredKnowledgeColumns);
  } else if (!document.querySelector('.s1-k-col-input')) {
    step1RenderKnowledgeColumns(_s1DefaultKnowledgeColumns);
  }
  if (document.getElementById('s1-output-format')?.value === 'markdown') {
    step1MergeRichColumnsForMarkdown();
  }
}

/** @deprecated 兼容旧调用 */
async function loadStep1DefaultTemplates(preferredTemplate) {
  return loadStep1SchemaAndTemplates(preferredTemplate, null);
}

async function cacheUploadedFile(step, inputEl, fileNameEl) {
  if (!currentPipeline || !inputEl || !inputEl.files || !inputEl.files[0]) return;
  const file = inputEl.files[0];
  const fd = new FormData();
  fd.append('file', file);
  fd.append('pipeline_id', currentPipeline.id);
  fd.append('step', String(step));
  try {
    const resp = await fetch(API_BASE + '/api/files/cache_upload', { method: 'POST', body: fd });
    const data = await resp.json();
    if (data.status === 'ok') {
      currentPipeline.step_data = currentPipeline.step_data || {};
      currentPipeline.step_data['step' + step + '_cached_file'] = data.file_name;
      currentPipeline.step_data['step' + step + '_cached_name'] = file.name;
      await persistPipeline({
        ['step' + step + '_cached_file']: data.file_name,
        ['step' + step + '_cached_name']: file.name,
      });
      if (fileNameEl) fileNameEl.textContent = file.name + '（已缓存）';
    }
  } catch (e) {
    console.warn('cache upload failed:', e);
  }
}

function refreshCachedUploadLabels(step) {
  if (!currentPipeline?.step_data) return;
  const sd = currentPipeline.step_data;
  if (!step || step === 2) {
    const el = document.getElementById('s2-file-name');
    if (el && !el.textContent && sd.step2_cached_name) el.textContent = sd.step2_cached_name + '（已缓存）';
  }
  if (!step || step === 3) {
    const el = document.getElementById('s3-file-name');
    if (el && !el.textContent && sd.step3_cached_name) el.textContent = sd.step3_cached_name + '（已缓存）';
  }
}

async function refreshCurrentPipeline() {
  if (!currentPipeline?.id) return null;
  try {
    const resp = await fetch(API_BASE + '/api/pipelines/' + currentPipeline.id);
    const data = await resp.json();
    if (data.status === 'ok' && data.pipeline) {
      currentPipeline.current_step = Math.max(currentPipeline.current_step || 1, Math.min(MAX_STEP, Math.max(1, data.pipeline.current_step || 1)));
      currentPipeline.step_status = Object.assign({}, data.pipeline.step_status, currentPipeline.step_status);
      currentPipeline.step_data = mergeStepDataPreserveOutputs(
        data.pipeline.step_data,
        currentPipeline.step_data,
        { preferServer: true }
      );
    }
    return currentPipeline;
  } catch (e) {
    console.warn('refreshCurrentPipeline failed:', e);
    return currentPipeline;
  }
}

/* ===== Form Auto-Save & Restore ===== */

function collectAllStepsFormData() {
  const merged = {};
  for (let step = 1; step <= MAX_FORM_STEP; step++) {
    merged['step' + step + '_form_data'] = collectStepFormData(step);
  }
  return merged;
}

function restoreAllStepsFormData() {
  if (!currentPipeline?.step_data) return;
  for (let step = 1; step <= MAX_FORM_STEP; step++) {
    const key = 'step' + step + '_form_data';
    if (currentPipeline.step_data[key]) {
      restoreStepFormData(step, currentPipeline.step_data[key]);
    }
  }
}

async function persistPipeline(extraStepData, extraFields) {
  if (!currentPipeline) return;
  const payload = {
    current_step: currentPipeline.current_step,
    step_status: currentPipeline.step_status,
    step_data: mergeStepDataPreserveOutputs(currentPipeline.step_data, extraStepData || {}),
    ...(extraFields || {}),
  };
  currentPipeline.step_data = payload.step_data;
  const result = await apiCallJSON('/api/pipelines/' + currentPipeline.id, payload, 'PUT');
  if (result.pipeline) {
    currentPipeline.step_data = mergeStepDataPreserveOutputs(
      result.pipeline.step_data,
      currentPipeline.step_data
    );
    if (result.pipeline.current_step != null) {
      const serverStep = Math.min(MAX_STEP, Math.max(1, result.pipeline.current_step || 1));
      currentPipeline.current_step = Math.max(currentPipeline.current_step || 1, serverStep);
    }
    if (result.pipeline.step_status) {
      currentPipeline.step_status = Object.assign({}, result.pipeline.step_status, currentPipeline.step_status);
    }
  }
  return result;
}

function applyStep1GenerateResult(result) {
  if (!currentPipeline) return;
  const excelFile = result.excel_file || result.file_name;
  if (!excelFile) return;
  currentPipeline.step_data = currentPipeline.step_data || {};
  clearDownstreamOutputs(1);
  currentPipeline.step_data.step1_output_file = excelFile;
  currentPipeline.step_data.step1_download_url = result.excel_download_url || ('/downloads/' + excelFile);
  if (result.markdown_file) {
    currentPipeline.step_data.step1_md_file = result.markdown_file;
    currentPipeline.step_data.step1_md_download_url = result.markdown_download_url || ('/downloads/' + result.markdown_file);
  }
  if (result.knowledge_columns) {
    currentPipeline.step_data.step1_knowledge_columns = result.knowledge_columns;
  }
  if (result.output_format) currentPipeline.step_data.step1_output_format = result.output_format;
  if (result.scenario) currentPipeline.scenario = result.scenario;
  rememberStep1Output(
    currentPipeline.id,
    excelFile,
    currentPipeline.step_data.step1_download_url
  );
}

function syncPipelineFromStep1Response(result) {
  if (!currentPipeline || !result?.pipeline) return;
  currentPipeline.step_data = mergeStepDataPreserveOutputs(
    result.pipeline.step_data,
    currentPipeline.step_data
  );
  if (result.pipeline.scenario) currentPipeline.scenario = result.pipeline.scenario;
  if (result.pipeline.domain) currentPipeline.domain = result.pipeline.domain;
}

function collectStepFormData(step) {
  const data = {};
  if (step === 1) {
    data.scenario_name = document.getElementById('s1-scenario-name')?.value || '';
    data.scenario_content = document.getElementById('s1-scenario-content')?.value || '';
    data.sub_scenarios = step1GetSubScenarios();
    data.output_format = document.getElementById('s1-output-format')?.value || 'excel';
    data.knowledge_columns = step1GetKnowledgeColumns();
    data.legacy_template = document.getElementById('s1-legacy-template')?.value || '';
  } else if (step === 2) {
    data.doc_text = document.getElementById('s2-doc-text')?.value || '';
    data.extract_style = document.getElementById('s2-extract-style')?.value || '';
    data.output_format = document.getElementById('s2-output-format')?.value || 'excel';
  } else if (step === 3) {
    data.expert_text = document.getElementById('s3-expert-text')?.value || '';
    data.revision_style = document.getElementById('s3-revision-style')?.value || '';
  } else if (step === 4) {
    // Step 4 (智能转化) has no form data to collect
  }
  return data;
}

function restoreStepFormData(step, data) {
  if (!data) return;
  if (step === 1) {
    const nameEl = document.getElementById('s1-scenario-name');
    const contentEl = document.getElementById('s1-scenario-content');
    const outputFmtEl = document.getElementById('s1-output-format');
    const legacyTplEl = document.getElementById('s1-legacy-template');
    if (nameEl && data.scenario_name) nameEl.value = data.scenario_name;
    if (contentEl && data.scenario_content) contentEl.value = data.scenario_content;
    if (outputFmtEl && data.output_format) outputFmtEl.value = data.output_format;
    const leg = data.legacy_template || (data.default_template && data.default_template !== '__schema__' ? data.default_template : '');
    loadStep1SchemaAndTemplates(leg, data.knowledge_columns);
    if (legacyTplEl && leg) {
      const hasOption = Array.from(legacyTplEl.options || []).some(o => o.value === leg);
      if (hasOption) legacyTplEl.value = leg;
    }
    // Clear existing sub-scenarios before restoring
    const subContainer = document.getElementById('s1-sub-scenarios');
    if (subContainer) subContainer.innerHTML = '';
    _s1SubScenarioCount = 0;
    if (data.sub_scenarios && data.sub_scenarios.length) {
      data.sub_scenarios.forEach(sub => {
        step1AddSubScenario();
        const items = document.querySelectorAll('.s1-sub-item');
        const last = items[items.length - 1];
        if (last) {
          last.querySelector('.s1-sub-name').value = sub.name || '';
          last.querySelector('.s1-sub-content').value = sub.content || '';
        }
      });
    }
  } else if (step === 2) {
    const docEl = document.getElementById('s2-doc-text');
    const styleEl = document.getElementById('s2-extract-style');
    const fmtEl = document.getElementById('s2-output-format');
    if (docEl) docEl.value = data.doc_text || '';
    if (styleEl) styleEl.value = data.extract_style || '';
    if (fmtEl) fmtEl.value = data.output_format || 'excel';
  } else if (step === 3) {
    const expertEl = document.getElementById('s3-expert-text');
    const styleEl = document.getElementById('s3-revision-style');
    if (expertEl && data.expert_text) expertEl.value = data.expert_text;
    if (styleEl && data.revision_style) styleEl.value = data.revision_style;
  } else if (step === 4) {
    // Step 4 (智能转化) has no form data to restore
  }
}

function scheduleFormSave(step) {
  if (!currentPipeline) return;
  clearTimeout(_formSaveTimer);
  _autoSaveUI('saving');
  _formSaveTimer = setTimeout(async () => {
    try {
      const allForm = collectAllStepsFormData();
      currentPipeline.step_data = currentPipeline.step_data || {};
      let changed = false;
      for (const [key, formData] of Object.entries(allForm)) {
        if (JSON.stringify(currentPipeline.step_data[key]) !== JSON.stringify(formData)) {
          currentPipeline.step_data[key] = formData;
          changed = true;
        }
      }
      if (!changed) { _autoSaveUI('idle'); return; }
      await persistPipeline(allForm);
      _autoSaveUI('saved');
    } catch (e) {
      console.error('Auto-save failed:', e);
      _autoSaveUI('failed');
    }
  }, 1000);
}

let _autoSaveTimer = null;
function _autoSaveUI(state) {
  var el = document.getElementById('auto-save-indicator');
  var txt = document.getElementById('auto-save-text');
  if (!el || !txt) return;
  clearTimeout(_autoSaveTimer);
  el.className = 'auto-save-indicator ' + state + ' visible';
  if (state === 'saving') { txt.textContent = '保存中...'; }
  else if (state === 'saved') {
    var now = new Date();
    txt.textContent = '已保存 ' + now.getHours().toString().padStart(2,'0') + ':' + now.getMinutes().toString().padStart(2,'0');
    _autoSaveTimer = setTimeout(function () { el.classList.remove('visible'); }, 3000);
  }
  else if (state === 'failed') {
    txt.textContent = '保存失败，点击重试';
    el.onclick = function () { scheduleFormSave(currentStep); };
  }
  else {
    el.classList.remove('visible');
    el.onclick = null;
  }
}

function renderStepReadiness(elId, text, level) {
  const el = document.getElementById(elId);
  if (!el) return;
  const lv = level || 'info';
  el.className = `step-readiness ${lv}`;
  el.textContent = text || '';
}

function step3LooksLikeNoOpinion(text) {
  const t = String(text || '').trim();
  if (!t) return true;
  return /(暂无意见|无意见|无需修订|无需修改|保持不变|确认通过|没有意见|无异议)/.test(t);
}

/* ===== Step2 文本输入行管理 ===== */
function addStep2TextRow() {
  var container = document.getElementById('s2-text-inputs');
  if (!container) return;
  var row = document.createElement('div');
  row.className = 's2-text-input-row';
  row.innerHTML = '<input class="s2-text-input-label" placeholder="来源标注（如：制度文件A）">'
    + '<textarea class="s2-text-input-content" rows="2" placeholder="粘贴文档内容..."></textarea>'
    + renderBtn({ variant: 'ghost', size: 'sm', icon: 'x', cls: 's2-text-input-remove', attrs: 'onclick="this.parentElement.remove();updateStep2Readiness()" title="移除"' });
  container.appendChild(row);
  refreshIcons();
}

/* ===== Step3 信号审核面板 ===== */
function toggleSignalPanel() {
  var panel = document.getElementById('s3-signal-panel');
  var body = document.getElementById('s3-signal-body');
  var toggle = document.getElementById('s3-signal-toggle');
  if (!panel) return;
  var isHidden = body ? body.classList.contains('hidden') : panel.classList.contains('hidden');
  if (body) body.classList.toggle('hidden', !isHidden);
  if (toggle) toggle.style.transform = isHidden ? '' : 'rotate(180deg)';
}

/* ===== Step2 输入模式切换（文档萃取 / 案例复盘） ===== */
function switchStep2Mode(mode) {
  _step2InputMode = mode;
  var tabs = document.querySelectorAll('.s2-mode-tab');
  tabs.forEach(function (t) {
    var isActive = t.dataset.mode === mode;
    t.classList.toggle('active', isActive);
    t.classList.toggle('btn--primary', isActive);
    t.classList.toggle('btn--ghost', !isActive);
  });
  var panelDoc = document.getElementById('s2-panel-doc');
  var panelCase = document.getElementById('s2-panel-case');
  if (panelDoc) panelDoc.classList.toggle('hidden', mode !== 'doc');
  if (panelCase) panelCase.classList.toggle('hidden', mode !== 'case');
  updateStep2Readiness();
}

/* ===== Step2 执行 ===== */
function step2Execute() {
  var btn = document.getElementById('s2-skill-extract');
  if (!btn || btn._locked) return;
  var model = resolveModelName('s2-model');
  if (!currentPipeline || !model) { updateStep2Readiness(); showToast('请先补全执行条件', 'error'); return; }

  btn._locked = true;
  btn.disabled = true;
  var origBtnHtml = btn.innerHTML;
  btn.classList.add('loading');
  btn.innerHTML = '执行中<span class="btn-estimate">· 通常 10-60s</span>';
  clearTimeout(_formSaveTimer);
  renderLoading('s2-output');

  var fd = new FormData();
  fd.append('pipeline_id', currentPipeline.id);
  fd.append('model', model);

  // 收集多文件
  var sourceFiles = document.getElementById('s2-source-files');
  var hasFiles = false;
  if (sourceFiles && sourceFiles.files && sourceFiles.files.length > 0) {
    for (var i = 0; i < sourceFiles.files.length; i++) { fd.append('files', sourceFiles.files[i]); }
    hasFiles = true;
  }

  // 收集文本输入行
  var textRows = document.querySelectorAll('#s2-text-inputs .s2-text-input-row');
  var textInputs = [];
  textRows.forEach(function (row) {
    var label = (row.querySelector('.s2-text-input-label') || {}).value || '';
    var content = (row.querySelector('.s2-text-input-content') || {}).value || '';
    if (content.trim()) textInputs.push({ source_label: label, content: content.trim() });
  });
  if (textInputs.length > 0) {
    fd.append('text_inputs', JSON.stringify(textInputs));
  }

  var outputFmt = document.getElementById('s2-output-format')?.value || 'excel';
  fd.append('output_format', outputFmt);

  // 知识库继承
  if (document.getElementById('s2-kb-inherit')?.checked) {
    fd.append('kb_inherit', '1');
  }

  if (!hasFiles && textInputs.length === 0) {
    showToast('请至少上传一个文件或填入文本来源', 'error');
    btn.disabled = false; btn.innerHTML = origBtnHtml; btn._locked = false;
    return;
  }

  fetch(API_BASE + '/api/step2/extract', { method: 'POST', body: fd })
    .then(function (r) { return r.text(); })
    .then(async function (text) {
      var result;
      try { result = JSON.parse(text); } catch (e) { result = { raw: text }; }

      if (result.status !== 'ok') {
        showToast(result.error || '萃取失败', 'error');
        renderOutput('s2-output', '<div class="error-list"><div class="error-item">' + escapeHtml(result.error || '萃取失败') + '</div></div>');
        return;
      }

      clearDownstreamOutputs(2);
      var dlName = result.preextract_file || result.excel_file || result.file_name || '';
      var dlUrl = result.preextract_download_url || result.excel_download_url || ('/downloads/' + dlName);
      var extractedCount = result.extracted_count || 0;
      var sourceCount = result.source_count || 0;
      var dedupCount = result.dedup_count || 0;
      var mdFile = result.markdown_file || '';
      var mdUrl = result.markdown_download_url || '';

      if (currentPipeline) {
        currentPipeline.step_data = currentPipeline.step_data || {};
        currentPipeline.step_data.step2_output_file = dlName;
        currentPipeline.step_data.step2_download_url = dlUrl;
        currentPipeline.step_data.step2_md_file = mdFile;
        currentPipeline.step_data.step2_md_download_url = mdUrl;
        currentPipeline.step_data.step2_extracted_count = extractedCount;
        currentPipeline.step_data.step2_source_count = sourceCount;
        currentPipeline.step_data.step2_dedup_count = dedupCount;
        if (result.signal_report_file) {
          currentPipeline.step_data.step2_signal_report_file = result.signal_report_file;
          currentPipeline.step_data.step2_signal_report_url = result.signal_report_url || ('/downloads/' + result.signal_report_file);
        }
        if (result.skill_draft_file) {
          currentPipeline.step_data.step2_draft_file = result.skill_draft_file;
          currentPipeline.step_data.step2_draft_url = result.skill_draft_url || ('/downloads/' + result.skill_draft_file);
          currentPipeline.step_data.step2_draft_version = result.skill_draft_version || 1;
          if (result.skill_draft_md_file) {
            currentPipeline.step_data.step2_draft_md_file = result.skill_draft_md_file;
            currentPipeline.step_data.step2_draft_md_url = result.skill_draft_md_url || ('/downloads/' + result.skill_draft_md_file);
          }
        }
      }

      var html = '<div class="s2-result-success">';
      html += '<div class="s2-result-header">知识萃取完成</div>';
      html += '<div class="s2-result-meta">共提取 <strong>' + extractedCount + '</strong> 条知识';
      if (sourceCount > 1) html += ' · ' + sourceCount + ' 源 · 去重 ' + dedupCount;
      if (result.skill_draft_file) html += ' · 已生成 <strong>Skill 草稿 v' + (result.skill_draft_version || 1) + '</strong>';
      html += '</div>';

      // Skill 草稿卡片（流水线主产物）
      if (result.skill_draft_file) {
        html += '<div class="signal-review-panel" style="margin-top:12px;display:block;border:1px solid var(--border);border-radius:var(--radius);padding:12px;">';
        html += '<div style="font-size:13px;font-weight:700;margin-bottom:8px;">&#129518; Skill 草稿 v' + (result.skill_draft_version || 1) + '（初版，待专家对齐）</div>';
        html += '<div class="s2-result-actions">';
        if (result.skill_draft_md_file) html += '<button class="btn btn--primary btn--sm" onclick="previewStep4File(\'' + escapeHtml(result.skill_draft_md_file) + '\',\'Skill 草稿预览 (v' + (result.skill_draft_version || 1) + ')\')">预览 Skill 草稿</button>';
        if (result.skill_draft_md_url) html += '<a class="btn btn--outline btn--sm" href="' + API_BASE + result.skill_draft_md_url + '" download>下载草稿 Markdown</a>';
        if (result.skill_draft_url) html += '<a class="btn btn--outline btn--sm" href="' + API_BASE + result.skill_draft_url + '" download>下载草稿 JSON (IR)</a>';
        html += '</div></div>';
      }

      // 信号报告概览卡片
      if (result.signal_report && typeof result.signal_report === 'object') {
        var sr = result.signal_report;
        html += '<div class="signal-review-panel" style="margin-top:12px;display:block;border:1px solid var(--border);border-radius:var(--radius);padding:12px;">';
        html += '<div class="signal-review-header" style="margin-bottom:8px;"><div class="signal-review-title" style="font-size:13px;font-weight:700;">&#128226; 信号报告</div></div>';
        html += '<div class="signal-stats-grid">';
        html += '<div class="signal-stat-card"><span class="signal-stat-num">' + (sr.boundary_blur != null ? sr.boundary_blur : '-') + '</span><span class="signal-stat-label">边界模糊</span></div>';
        html += '<div class="signal-stat-card"><span class="signal-stat-num">' + (sr.island != null ? sr.island : '-') + '</span><span class="signal-stat-label">知识孤岛</span></div>';
        html += '<div class="signal-stat-card"><span class="signal-stat-num">' + (sr.low_consensus != null ? sr.low_consensus : '-') + '</span><span class="signal-stat-label">共识度低</span></div>';
        html += '<div class="signal-stat-card"><span class="signal-stat-num">' + (sr.conflict != null ? sr.conflict : '-') + '</span><span class="signal-stat-label">冲突</span></div>';
        html += '</div></div>';
      }

      html += '<div class="s2-result-actions" style="margin-top:12px;">';
      var step2Fmt = document.getElementById('s2-output-format')?.value || 'excel';
      var mdFlow = step2Fmt === 'markdown';
      // Markdown group
      if (mdFlow && mdFile) html += '<button class="btn btn--primary btn--sm" onclick="previewStep4File(\'' + escapeHtml(mdFile) + '\',\'Step2 萃取 Markdown 预览\')">预览/编辑 Markdown</button>';
      if (!mdFlow && mdFile) html += '<button class="btn btn--outline btn--sm" onclick="previewStep4File(\'' + escapeHtml(mdFile) + '\',\'Step2 萃取 Markdown 预览\')">预览/编辑 Markdown</button>';
      if (mdUrl) html += '<a class="btn btn--outline btn--sm" href="' + API_BASE + mdUrl + '" download>下载 Markdown</a>';
      // Excel group
      if (!mdFlow && dlName) html += '<button class="btn btn--primary btn--sm" onclick="step1PreviewExcel(\'' + escapeHtml(dlName) + '\')">预览 Excel</button>';
      if (mdFlow && dlName) html += '<button class="btn btn--outline btn--sm" onclick="step1PreviewExcel(\'' + escapeHtml(dlName) + '\')">预览 Excel</button>';
      if (dlUrl) html += '<a class="btn btn--outline btn--sm" href="' + API_BASE + dlUrl + '" download>下载 Excel</a>';
      html += '</div>';
      html += '</div>';

      renderOutput('s2-output', html);
      try { await markStepDone(2); } catch(e) { console.error('markStepDone failed:', e); }
    })
    .catch(function (e) {
      showToast('网络错误: ' + e.message, 'error');
      renderOutput('s2-output', '<div class="error-list"><div class="error-item">' + escapeHtml(e.message) + '</div></div>');
    })
    .finally(function () {
      btn.disabled = false;
      btn._locked = false;
      btn.innerHTML = origBtnHtml;
      btn.classList.remove('loading');
      refreshIcons();
    });
}

function updateStep2Readiness() {
  var btn = document.getElementById('s2-skill-extract');
  if (!btn) return;

  var model = resolveModelName('s2-model');

  // 检测是否有输入源
  var sourceFiles = document.getElementById('s2-source-files');
  var hasFiles = sourceFiles && sourceFiles.files && sourceFiles.files.length > 0;
  var hasText = false;
  document.querySelectorAll('#s2-text-inputs .s2-text-input-row').forEach(function (row) {
    var content = (row.querySelector('.s2-text-input-content') || {}).value || '';
    if (content.trim()) hasText = true;
  });

  var ready = !!currentPipeline && !!model && (hasFiles || hasText);
  btn.disabled = !ready;

  if (!currentPipeline) { renderStepReadiness('s2-readiness', '请先从总览进入一条流水线后再执行', 'warn'); return; }
  if (!model)           { renderStepReadiness('s2-readiness', '请先配置并选择模型', 'warn'); return; }
  if (!hasFiles && !hasText) { renderStepReadiness('s2-readiness', '请至少上传一个文件或填入文本来源', 'warn'); return; }
  renderStepReadiness('s2-readiness', '已就绪：可执行知识萃取', 'ok');
}

async function loadStep2KbHint() {
  var hintEl = document.getElementById('s2-kb-inherit-hint');
  if (!hintEl || !currentPipeline) return;
  try {
    var params = new URLSearchParams({
      domain: currentPipeline.domain || '',
      scenario: currentPipeline.scenario || '',
      top_k: '20',
    });
    var resp = await fetch(API_BASE + '/api/kb/entries?' + params.toString());
    var data = await resp.json();
    if (data.status === 'ok' && data.total > 0) {
      hintEl.textContent = '知识库已有 ' + data.total + ' 条相关知识，勾选后将与新萃取结果融合去重';
    } else {
      hintEl.textContent = '知识库暂无相关沉淀（首条流水线发布后可供后续继承）';
    }
  } catch (e) { hintEl.textContent = ''; }
}

function updateStep3AlignModeHint() {
  const text = document.getElementById('s3-expert-text')?.value || '';
  const hasUpload = !!(document.getElementById('s3-expert-file')?.files?.length);
  const hasCached = !!(currentPipeline?.step_data?.step3_cached_file);
  const hasMaterial = hasUpload || hasCached;
  const btn = document.getElementById('s3-revise-btn');
  if (!btn) return;
  if (!text.trim() && !hasMaterial) {
    btn.innerHTML = renderBtnChildren({ icon: 'check', text: '无意见直通生成对齐稿' });
    renderStepReadiness('s3-align-hint', '未填写意见：将直接按预萃稿生成对齐稿（无修订）', 'info');
    refreshIcons();
    return;
  }
  if (step3LooksLikeNoOpinion(text) && !hasMaterial) {
    btn.innerHTML = renderBtnChildren({ icon: 'check', text: '按当前稿生成对齐稿' });
    renderStepReadiness('s3-align-hint', '检测到“无修订”表达：将自动确认当前稿为对齐稿', 'info');
    refreshIcons();
    return;
  }
  btn.innerHTML = renderBtnChildren({ icon: 'settings-2', text: '发送并智能修订' });
  renderStepReadiness('s3-align-hint', '已检测到专家意见/材料：将按意见生成修订建议', 'ok');
  refreshIcons();
}

function setupFormAutoSave() {
  const bind = (id, step) => {
    const el = document.getElementById(id);
    if (!el) return;
    const evt = el.tagName === 'SELECT' ? 'change' : 'input';
    el.addEventListener(evt, () => scheduleFormSave(step));
  };
  ['s1-scenario-name', 's1-scenario-content', 's1-legacy-template'].forEach(id => bind(id, 1));
  const s1Fmt = document.getElementById('s1-output-format');
  if (s1Fmt) {
    s1Fmt.addEventListener('change', step1OnOutputFormatChange);
    bind('s1-output-format', 1);
  }
  const subBox = document.getElementById('s1-sub-scenarios');
  if (subBox) subBox.addEventListener('input', () => scheduleFormSave(1));
  const kBox = document.getElementById('s1-knowledge-columns');
  if (kBox) kBox.addEventListener('input', () => scheduleFormSave(1));
  ['s2-doc-text', 's2-extract-style', 's2-output-format'].forEach(id => bind(id, 2));
  ['s3-expert-text', 's3-revision-style'].forEach(id => bind(id, 3));
  const s2Model = document.getElementById('s2-model');
  const s2SourceFiles = document.getElementById('s2-source-files');
  const s2TextInputs = document.getElementById('s2-text-inputs');
  const s2OutputFormat = document.getElementById('s2-output-format');
  const s3Expert = document.getElementById('s3-expert-text');
  const s3File = document.getElementById('s3-expert-file');
  if (s2Model) s2Model.addEventListener('change', updateStep2Readiness);
  if (s2SourceFiles) s2SourceFiles.addEventListener('change', updateStep2Readiness);
  if (s2TextInputs) s2TextInputs.addEventListener('input', updateStep2Readiness);
  if (s3Expert) s3Expert.addEventListener('input', updateStep3AlignModeHint);
  if (s3File) s3File.addEventListener('change', updateStep3AlignModeHint);
  // 模式发现文件列表
  var pfInput = document.getElementById('s2-pattern-files');
  if (pfInput) pfInput.addEventListener('change', refreshPatternFileList);
}

/* ===== File upload name display ===== */
document.addEventListener('DOMContentLoaded', () => {
  [['s1-template-file', 's1-template-file-name'], ['s2-source-files', 's2-file-name'], ['s3-expert-file', 's3-file-name']].forEach(([inputId, nameId]) => {
    const input = document.getElementById(inputId);
    const nameEl = document.getElementById(nameId);
    if (input && nameEl) {
      input.addEventListener('change', async () => {
        nameEl.textContent = input.files.length ? (input.files.length + ' 个文件') : '';
        if (!input.files.length) return;
        if (inputId === 's2-source-files') updateStep2Readiness();
        if (inputId === 's3-expert-file') await cacheUploadedFile(3, input, nameEl);
        if (inputId === 's3-expert-file') updateStep3AlignModeHint();
      });
    }
  });
  loadStep1SchemaAndTemplates();
  setupFormAutoSave();
  loadModels();
  refreshIcons();
  // 初始化列宽拖动调节
  if (App.initResizableColumns) { setTimeout(App.initResizableColumns, 300); }
});

/* ===== Navigation ===== */
document.querySelectorAll('.step-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    if (!currentPipeline) return;
    const targetStep = parseInt(btn.dataset.step);
    const farthestStep = currentPipeline.current_step || 1;
    // 向前或查看已完成步骤：直接切换面板（只读查看，不回退）
    // 如果用户在早期步骤执行操作，生成/执行处理器会自动清除下游数据
    if (targetStep <= farthestStep) {
      switchPanel(targetStep);
    } else {
      // 跳过未完成的步骤：不允许
      showToast('请先完成第 ' + farthestStep + ' 步', 'error');
    }
  });
});

function updateStepProgress() {
  if (!currentPipeline) return;
  const status = currentPipeline.step_status || {};
  const cur = Math.min(MAX_STEP, Math.max(1, currentPipeline.current_step || 1));
  document.querySelectorAll('.step-btn').forEach(b => {
    const s = parseInt(b.dataset.step);
    b.classList.remove('active', 'done');
    if (s === currentStep) {
      b.classList.add('active');
    } else if (status[s] === 'done') {
      b.classList.add('done');
    }
  });
  document.querySelectorAll('.step-connector').forEach((c, i) => {
    const stepNum = i + 1;
    c.classList.remove('done', 'reached');
    if (status[stepNum] === 'done') c.classList.add('done');
    else if (stepNum < cur) c.classList.add('reached');
  });
}

function renderPipelineProgressSummary(currentPanelStep) {
  if (!currentPipeline || currentPanelStep === 0) {
    document.querySelectorAll('.pipeline-progress-summary').forEach(function (el) { el.remove(); });
    return;
  }
  const status = currentPipeline.step_status || {};
  const steps = [
    { n: 1, label: '场景锚定' },
    { n: 2, label: '知识萃取' },
    { n: 3, label: '知识对齐' },
    { n: 4, label: '智能转化' },
    { n: 5, label: '验证回放' },
  ];
  var html = '<div class="pipeline-progress-summary">';
  steps.forEach(function (s, i) {
    if (i > 0) html += '<span class="pp-arrow">&gt;</span>';
    var cls = 'pp-step';
    if (s.n === currentPanelStep) cls += ' current';
    else if (status[s.n] === 'done') cls += ' done';
    html += '<span class="' + cls + '">' + s.label + '</span>';
  });
  html += '</div>';

  var activePanel = document.getElementById('panel-' + currentPanelStep);
  if (!activePanel) return;
  var threeCol = activePanel.querySelector('.three-col, .three-col-wide');
  if (!threeCol) return;
  var existing = activePanel.querySelector('.pipeline-progress-summary');
  if (existing) existing.remove();
  threeCol.insertAdjacentHTML('beforebegin', html);
}

/* ===== Restore completed outputs when switching steps ===== */
function restoreStep2Output() {
  if (!currentPipeline) return;
  const sd = currentPipeline.step_data || {};
  const out = document.getElementById('s2-output');
  if (!out) return;
  if (!sd.step2_output_file) {
    out.innerHTML = '';
    return;
  }
  const dlName = sd.step2_output_file || '';
  const dlUrl = sd.step2_download_url || '/downloads/' + dlName;
  const mdFile = sd.step2_md_file || '';
  const mdUrl = sd.step2_md_download_url || '';
  const extractedCount = sd.step2_extracted_count || 0;
  const sourceCount = sd.step2_source_count || 0;
  const dedupCount = sd.step2_dedup_count || 0;
  const draftFile = sd.step2_draft_file || '';
  const draftUrl = sd.step2_draft_url || '';
  const draftMdFile = sd.step2_draft_md_file || '';
  const draftMdUrl = sd.step2_draft_md_url || '';
  const draftVersion = sd.step2_draft_version || 1;

  let html = '<div class="s2-result-success">';
  html += '<div class="s2-result-header">知识萃取完成</div>';
  html += '<div class="s2-result-meta">共提取 <strong>' + extractedCount + '</strong> 条知识';
  if (sourceCount > 1) html += ' · ' + sourceCount + ' 源 · 去重 ' + dedupCount;
  if (draftFile) html += ' · 已生成 <strong>Skill 草稿 v' + draftVersion + '</strong>';
  html += '</div>';

  if (draftFile) {
    html += '<div class="signal-review-panel" style="margin-top:12px;display:block;border:1px solid var(--border);border-radius:var(--radius);padding:12px;">';
    html += '<div style="font-size:13px;font-weight:700;margin-bottom:8px;">&#129518; Skill 草稿 v' + draftVersion + '（初版，待专家对齐）</div>';
    html += '<div class="s2-result-actions">';
    if (draftMdFile) html += '<button class="btn btn--primary btn--sm" onclick="previewStep4File(\'' + escapeHtml(draftMdFile) + '\',\'Skill 草稿预览 (v' + draftVersion + ')\')">预览 Skill 草稿</button>';
    if (draftMdUrl) html += '<a class="btn btn--outline btn--sm" href="' + API_BASE + draftMdUrl + '" download>下载草稿 Markdown</a>';
    if (draftUrl) html += '<a class="btn btn--outline btn--sm" href="' + API_BASE + draftUrl + '" download>下载草稿 JSON (IR)</a>';
    html += '</div></div>';
  }

  html += '<div class="s2-result-actions" style="margin-top:12px;">';
  const step2Fmt = document.getElementById('s2-output-format')?.value || 'excel';
  const mdFlow = step2Fmt === 'markdown';
  if (mdFlow && mdFile) html += '<button class="btn btn--primary btn--sm" onclick="previewStep4File(\'' + escapeHtml(mdFile) + '\',\'Step2 萃取 Markdown 预览\')">预览/编辑 Markdown</button>';
  if (!mdFlow && mdFile) html += '<button class="btn btn--outline btn--sm" onclick="previewStep4File(\'' + escapeHtml(mdFile) + '\',\'Step2 萃取 Markdown 预览\')">预览/编辑 Markdown</button>';
  if (mdUrl) html += '<a class="btn btn--outline btn--sm" href="' + API_BASE + mdUrl + '" download>下载 Markdown</a>';
  if (!mdFlow && dlName) html += '<button class="btn btn--primary btn--sm" onclick="step1PreviewExcel(\'' + escapeHtml(dlName) + '\')">预览 Excel</button>';
  if (mdFlow && dlName) html += '<button class="btn btn--outline btn--sm" onclick="step1PreviewExcel(\'' + escapeHtml(dlName) + '\')">预览 Excel</button>';
  if (dlUrl) html += '<a class="btn btn--outline btn--sm" href="' + API_BASE + dlUrl + '" download>下载 Excel</a>';
  html += '</div></div>';

  renderOutput('s2-output', html);
}

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

  if (inputSection) inputSection.style.display = 'none';
  if (reviewSection) reviewSection.style.display = 'none';
  resultSection.style.display = '';

  let html = '';
  html += '<div class="align-result-header"><span>&#10003;</span> 知识对齐完成</div>';
  html += '<div class="align-result-meta">已生成对齐稿（共处理 ' + (sd.step3_final_count || 0) + ' 处修订）</div>';
  html += '<div class="align-result-actions">';
  if (mdFlow && mdName) html += '<button class="btn btn--primary btn--sm" onclick="previewStep4File(\'' + escapeHtml(mdName) + '\',\'Step3 对齐 Markdown 预览\')">预览/编辑 Markdown</button>';
  if (!mdFlow && mdName) html += '<button class="btn btn--outline btn--sm" onclick="previewStep4File(\'' + escapeHtml(mdName) + '\',\'Step3 对齐 Markdown 预览\')">预览/编辑 Markdown</button>';
  if (mdUrl) html += '<a href="' + escapeHtml(mdUrl) + '" class="btn btn--outline btn--sm" download>下载 Markdown</a>';
  if (!mdFlow && dlName) html += '<button class="btn btn--primary btn--sm" onclick="step1PreviewExcel(\'' + escapeHtml(dlName) + '\')">预览 Excel</button>';
  if (dlUrl) html += '<a href="' + escapeHtml(dlUrl) + '" class="btn btn--outline btn--sm" download>下载 Excel</a>';
  html += '<button class="btn btn--outline btn--sm" onclick="step3BackToInput()">重新对齐</button>';
  html += '</div>';
  resultCard.innerHTML = html;
}

function restoreStep4Output() {
  if (!currentPipeline) return;
  const sd = currentPipeline.step_data || {};
  const panel = document.getElementById('s4-output-compile');
  if (!sd.step4_download_url || !panel) return;

  // Compile 结果主面板
  let html = '<div class="s4-compile-result">';
  html += '<div class="s4-compile-header"><div class="s4-compile-icon">&#127919;</div><div class="s4-compile-title">交付包编译完成</div>';
  html += '<div class="s4-compile-subtitle">输入：Skill 草稿 v' + (sd.step4_published_version || '?') + '（IR） · 已生成交付物</div></div>';
  html += '<div class="s2-result-actions" style="margin-top:8px;">';
  if (sd.step4_download_url) html += '<a class="btn btn--primary btn--sm" href="' + API_BASE + sd.step4_download_url + '" download>下载 SKILL.md 终版</a>';
  if (sd.step4_cot_download_url) html += '<a class="btn btn--outline btn--sm" href="' + API_BASE + sd.step4_cot_download_url + '" download>下载思维链</a>';
  if (sd.step4_qa_download_url) html += '<a class="btn btn--outline btn--sm" href="' + API_BASE + sd.step4_qa_download_url + '" download>下载 QA 对</a>';
  if (sd.step4_manifest_url) html += '<a class="btn btn--outline btn--sm" href="' + API_BASE + sd.step4_manifest_url + '" download>下载 manifest</a>';
  if (sd.step4_skill_dir_zip_url) html += '<a class="btn btn--outline btn--sm" href="' + API_BASE + sd.step4_skill_dir_zip_url + '" download>下载 Skill 目录 zip</a>';
  html += '</div></div>';
  panel.style.display = 'block';
  panel.innerHTML = html;

  // 同步更新右侧 Skill/COT/QA 独立面板，与后端产物一一对应
  const skillPanel = document.getElementById('s4-output-skill');
  const cotPanel = document.getElementById('s4-output-cot');
  const qaPanel = document.getElementById('s4-output-qa');

  if (skillPanel && sd.step4_skill_file) {
    skillPanel.style.display = 'block';
    skillPanel.innerHTML = '<div class="s4-artifact-panel"><div class="panel-header"><span>可执行 Agent Skill</span><span style="font-weight:400;font-size:11px;color:var(--text-muted);">一键编译生成</span></div>' +
      '<div class="s2-result-success"><div class="s2-result-header">SKILL.md 终版</div>' +
      '<div class="s2-result-meta">文件：' + escapeHtml(sd.step4_skill_file) + '</div>' +
      '<div class="s2-result-actions">' +
      '<button class="btn btn--outline btn--sm" onclick="previewStep4File(\'' + escapeHtml(sd.step4_skill_file) + '\',\'SKILL.md 终版\')">&#128065; 预览</button>' +
      '<a class="btn btn--outline btn--sm" href="' + API_BASE + sd.step4_download_url + '" download>下载</a>' +
      '</div></div></div>';
  }
  if (cotPanel && sd.step4_cot_file) {
    cotPanel.style.display = 'block';
    cotPanel.innerHTML = '<div class="s4-artifact-panel"><div class="panel-header"><span>思维链 (COT)</span><span style="font-weight:400;font-size:11px;color:var(--text-muted);">一键编译生成</span></div>' +
      '<div class="s2-result-success"><div class="s2-result-header">思维链</div>' +
      '<div class="s2-result-meta">文件：' + escapeHtml(sd.step4_cot_file) + '</div>' +
      '<div class="s2-result-actions">' +
      '<button class="btn btn--outline btn--sm" onclick="previewStep4File(\'' + escapeHtml(sd.step4_cot_file) + '\',\'思维链 COT\')">&#128065; 预览</button>' +
      '<a class="btn btn--outline btn--sm" href="' + API_BASE + sd.step4_cot_download_url + '" download>下载</a>' +
      '</div></div></div>';
  }
  if (qaPanel && sd.step4_qa_file) {
    qaPanel.style.display = 'block';
    qaPanel.innerHTML = '<div class="s4-artifact-panel"><div class="panel-header"><span>QA 对</span><span style="font-weight:400;font-size:11px;color:var(--text-muted);">一键编译生成</span></div>' +
      '<div class="s2-result-success"><div class="s2-result-header">QA 对</div>' +
      '<div class="s2-result-meta">文件：' + escapeHtml(sd.step4_qa_md_file || sd.step4_qa_file) + '</div>' +
      '<div class="s2-result-actions">' +
      '<button class="btn btn--outline btn--sm" onclick="previewStep4File(\'' + escapeHtml(sd.step4_qa_md_file || sd.step4_qa_file) + '\',\'QA 对\')">&#128065; 预览</button>' +
      '<a class="btn btn--outline btn--sm" href="' + API_BASE + sd.step4_qa_download_url + '" download>下载</a>' +
      '</div></div></div>';
  }
}

function restoreStep5Output() {
  if (!currentPipeline) return;
  const sd = currentPipeline.step_data || {};
  const out = document.getElementById('s5-output');
  if (!out || !sd.step5_run_id || sd.step5_hit_rate == null) return;

  const pct = Math.round(sd.step5_hit_rate * 100);
  const passed = sd.step5_hit_rate >= (sd.step5_hit_threshold || 0.8);
  const fillColor = passed ? '#16a34a' : (pct >= 60 ? '#f59e0b' : '#ef4444');
  let html = '<div class="validate-result">';
  html += '<h4>决策回放结果</h4>';
  html += '<div style="font-size:24px;font-weight:700;color:' + fillColor + '">' + pct + '% 命中率 ' + (passed ? '✅ 达标' : '⚠️ 未达门槛') + '</div>';
  if (sd.step5_replay_url) html += '<div style="margin-top:6px;"><a href="' + API_BASE + sd.step5_replay_url + '" target="_blank">查看完整回放报告</a></div>';
  if (sd.step5_suggestions_url) html += '<div><a href="' + API_BASE + sd.step5_suggestions_url + '" target="_blank">查看修订建议</a></div>';
  html += '</div>';
  renderOutput('s5-output', html);
}

function switchPanel(step) {
  if (step > MAX_STEP) step = MAX_STEP;
  if (step < 0) step = 0;
  currentStep = step;
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.getElementById('panel-' + step).classList.add('active');
  // 切换面板后重新初始化列宽拖动
  if (App.initResizableColumns) { setTimeout(App.initResizableColumns, 100); }

  renderPipelineProgressSummary(step);

  const navSteps = document.getElementById('nav-steps');
  const brandEl = document.getElementById('nav-brand');

  if (step === 0) {
    // Overview mode: hide step nav
    navSteps.classList.remove('visible');
    brandEl.textContent = '隐性知识显性化 · 五步法';
    loadPipelineOverview();
  } else {
    // Pipeline mode: show step nav with progress
    navSteps.classList.add('visible');
    if (currentPipeline) {
      brandEl.textContent = currentPipeline.name;
      updateStepProgress();
      // Restore form data for this step
      const stepDataKey = 'step' + step + '_form_data';
      const savedData = currentPipeline.step_data?.[stepDataKey];
      if (savedData) restoreStepFormData(step, savedData);
    }
  }

  // Refresh model selects when entering a step with AI
  if ([2, 3, 4, 5].includes(step)) {
    if (!allModels.length) loadModels();
    refreshModelSelects();
  }

  // Load skill selects for steps 2, 3
  if ([2, 3].includes(step)) loadStepSkillSelects(step);
  if (step === 1) {
    const fd = currentPipeline?.step_data?.step1_form_data || {};
    loadStep1SchemaAndTemplates(fd.legacy_template || fd.default_template || '', fd.knowledge_columns);
    restoreStep1Output();
  }

  // Auto-load previous step output（先刷新流水线再检测上一步产出）
  if (step === 2) {
    if (currentPipeline) {
      const s2Prev = document.getElementById('s2-prev-output-area');
      if (s2Prev) s2Prev.innerHTML = '<div class="loading" style="padding:12px;"><div class="spinner"></div>加载上一步产出...</div>';
      refreshCurrentPipeline().then(() => {
        loadStep2PrevOutput();
        updateStep2Readiness();
        loadStep2KbHint();
        if (currentPipeline?.step_status?.['2'] === 'done') restoreStep2Output();
      });
    }
  }
  if (step === 3 && currentPipeline) {
    var s3Draft = document.getElementById('s3-prev-draft');
    var s3Empty = document.getElementById('s3-prev-empty');
    if (s3Draft) { s3Draft.style.display = ''; }
    if (s3Empty) { s3Empty.style.display = 'none'; }
    loadStep3PrevOutput();
    loadStep3IRForAlignment();
    loadStep3RevisionContext();
    loadStep3SuggestionPool();
    updateStep3AlignModeHint();
    if (currentPipeline?.step_status?.['3'] === 'done') restoreStep3Output();
  }
  if (step === 4 && currentPipeline) {
    var s4Draft = document.getElementById('s4-prev-draft');
    var s4Empty = document.getElementById('s4-prev-empty');
    if (s4Draft) { s4Draft.style.display = 'block'; }
    if (s4Empty) { s4Empty.style.display = 'none'; }
    var s4Name = document.getElementById('s4-prev-name');
    if (s4Name) s4Name.textContent = '加载中...';
    loadStep4PrevOutput();
    if (currentPipeline?.step_status?.['4'] === 'done') restoreStep4Output();
  }
  if (step === 5 && currentPipeline) {
    refreshCurrentPipeline().then(function () {
      loadStep5Context();
      if (currentPipeline?.step_status?.['5'] === 'done') restoreStep5Output();
    });
  }
  refreshCachedUploadLabels(step);
}

/* ===== Back to Overview ===== */
function goBackToOverview() {
  currentPipeline = null;
  switchPanel(0);
}

async function rollbackToStep(step) {
  if (!currentPipeline) return;
  try {
    const resp = await fetch(API_BASE + '/api/pipelines/' + currentPipeline.id + '/rollback/' + step, { method: 'POST' });
    const data = await resp.json();
    if (data.status === 'ok') {
      currentPipeline = data.pipeline;
      currentPipeline.step_data = currentPipeline.step_data || {};
      switchPanel(step);
      showToast('已回退到第 ' + step + ' 步');
    } else {
      showToast(data.error || '回退失败', 'error');
    }
  } catch (e) {
    showToast('回退失败: ' + e.message, 'error');
  }
}

/* ===== Server Status（委托到 index.html 内联脚本，含 30s 自动重试） ===== */
checkServer = function() { /* no-op: 由 index.html 内联脚本处理 */ };
checkServer();

/* ===== Utility ===== */
function renderOutput(containerId, html) {
  document.getElementById(containerId).innerHTML = '<div class="output-result">' + html + '</div>';
}
function renderLoading(containerId) {
  document.getElementById(containerId).innerHTML = '<div class="loading"><div class="spinner"></div>处理中...</div>';
}
function escapeHtml(str) {
  if (str == null) return '';
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}
function escapeJsString(s) {
  return (s || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'");
}

async function copyTextToClipboard(text) {
  const value = text == null ? '' : String(text);
  if (!value) return false;
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(value);
      return true;
    }
  } catch (_) { /* fallback below */ }
  const ta = document.createElement('textarea');
  ta.value = value;
  ta.setAttribute('readonly', '');
  ta.style.position = 'fixed';
  ta.style.left = '-9999px';
  document.body.appendChild(ta);
  ta.select();
  let ok = false;
  try {
    ok = document.execCommand('copy');
  } catch (_) {
    ok = false;
  }
  document.body.removeChild(ta);
  return ok;
}
function qualityBar(pct) {
  const cls = pct >= 80 ? 'green' : pct >= 60 ? 'orange' : 'red';
  return '<div class="quality-bar"><div class="quality-fill ' + cls + '" style="width:' + pct + '%"></div></div>';
}
function statRow(label, value, cls) {
  return '<div class="stat-row"><span class="stat-label">' + label + '</span><span class="stat-value ' + (cls||'') + '">' + value + '</span></div>';
}

async function apiCall(endpoint, formData, timeoutMs = 120000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const resp = await fetch(API_BASE + endpoint, { method: 'POST', body: formData, signal: controller.signal });
    const text = await resp.text();
    try { return JSON.parse(text); } catch { return { raw: text }; }
  } catch (e) {
    if (e.name === 'AbortError') {
      return { status: 'error', error: '请求超时，请检查网络后重试' };
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

/** 包裹异步操作：自动禁用/恢复按钮，防止重复点击 */
async function withButtonLock(btnEl, fn) {
  if (!btnEl) return fn();
  if (btnEl._locked) return;
  btnEl._locked = true;
  btnEl.disabled = true;
  const origText = btnEl.innerHTML;
  try {
    return await fn();
  } finally {
    btnEl.disabled = false;
    btnEl.innerHTML = origText;
    btnEl._locked = false;
  }
}

async function apiCallJSON(endpoint, body, method = 'POST', timeoutMs = 0) {
  const controller = new AbortController();
  let timer = null;
  if (timeoutMs > 0) {
    timer = setTimeout(() => controller.abort(), timeoutMs);
  }
  try {
    const resp = await fetch(API_BASE + endpoint, {
      method: method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal
    });
    const text = await resp.text();
    try { return JSON.parse(text); } catch { return { raw: text }; }
  } catch (e) {
    if (e.name === 'AbortError') {
      return { status: 'error', error: '请求超时，请检查 API 地址与网络连通性' };
    }
    throw e;
  } finally {
    if (timer) clearTimeout(timer);
  }
}

async function markStepDone(step) {
  if (!currentPipeline) return;
  const allForm = collectAllStepsFormData();
  currentPipeline.step_data = mergeStepDataPreserveOutputs(currentPipeline.step_data, allForm);

  if (!currentPipeline.step_status) currentPipeline.step_status = {};
  currentPipeline.step_status[String(step)] = 'done';
  if (step < MAX_STEP) {
    currentPipeline.step_status[String(step + 1)] = currentPipeline.step_status[String(step + 1)] || 'active';
    currentPipeline.current_step = Math.max(currentPipeline.current_step || 1, step + 1);
  } else {
    currentPipeline.current_step = MAX_STEP;
  }
  try {
    await persistPipeline(currentPipeline.step_data, {
      current_step: currentPipeline.current_step,
      step_status: currentPipeline.step_status,
    });
  } catch (e) {
    console.error('Failed to update pipeline:', e);
  }
  updateStepProgress();
}

async function saveCurrentPipeline() {
  if (!currentPipeline) {
    showToast('请先创建或进入一条流水线', 'error');
    return;
  }
  try {
    const allForm = collectAllStepsFormData();
    currentPipeline.step_data = currentPipeline.step_data || {};
    Object.assign(currentPipeline.step_data, allForm);

    const resp = await fetch(API_BASE + '/api/pipelines/' + currentPipeline.id);
    const fresh = await resp.json();
    if (fresh.pipeline) {
      currentPipeline.current_step = Math.max(currentPipeline.current_step || 1, Math.min(MAX_STEP, Math.max(1, fresh.pipeline.current_step || 1)));
      currentPipeline.step_status = Object.assign({}, fresh.pipeline.step_status, currentPipeline.step_status);
      currentPipeline.step_data = mergeStepDataPreserveOutputs(
        fresh.pipeline.step_data,
        currentPipeline.step_data
      );
    }
    const persistResult = await persistPipeline(allForm, {
      current_step: currentPipeline.current_step,
      step_status: currentPipeline.step_status,
    });
    if (persistResult && persistResult.status === 'error') {
      showToast(persistResult.error || '保存失败', 'error');
    } else {
      showToast('流水线已保存（含各步骤填写内容）');
    }
  } catch (e) {
    console.error('Save failed:', e);
    showToast('保存失败: ' + (e.message || e), 'error');
  }
}

function clearCurrentPipeline() {
  if (!currentPipeline) return;
  if (!confirm('确定要清空当前流水线所有数据吗？此操作不可撤销。')) return;
  fetch(API_BASE + '/api/pipelines/' + currentPipeline.id + '/clear', {
    method: 'POST'
  }).then(r => r.json()).then(r => {
    if (r.status !== 'ok') throw new Error(r.error || '清空失败');
    const pipelineId = currentPipeline.id;
    clearTimeout(_formSaveTimer);

    currentPipeline.current_step = 1;
    currentPipeline.step_status = { '1': 'pending', '2': 'pending', '3': 'pending', '4': 'pending' };
    currentPipeline.step_data = {};

    // Remove per-pipeline browser cache to avoid stale UI restoration.
    sessionStorage.removeItem('step1_output:' + pipelineId);

    // Reset all step form inputs.
    const resetValue = (id, value = '') => {
      const el = document.getElementById(id);
      if (el) el.value = value;
    };
    const resetSelect = (id, preferred = '') => {
      const el = document.getElementById(id);
      if (!el) return;
      if (preferred && Array.from(el.options || []).some(o => o.value === preferred)) {
        el.value = preferred;
      } else {
        el.selectedIndex = 0;
      }
    };
    const resetText = (id, text = '') => {
      const el = document.getElementById(id);
      if (el) el.textContent = text;
    };

    resetValue('s1-scenario-name', '');
    resetValue('s1-scenario-content', '');
    resetValue('s3-expert-text', '');

    resetValue('s1-template-file', '');
    resetValue('s2-source-files', '');
    resetValue('s3-expert-file', '');

    resetSelect('s3-revision-style', '标准修订');
    resetSelect('s1-output-format', 'excel');
    resetSelect('s2-output-format', 'excel');
    resetSelect('s1-legacy-template', '');
    step1RenderKnowledgeColumns([]);
    resetSelect('s2-model', '');
    resetSelect('s3-model', '');
    resetSelect('s3-skill-select', '');

    resetText('s1-template-file-name', '未选择');
    resetText('s2-file-name', '');
    resetText('s3-file-name', '');

    updateStepProgress();

    // Clear output display areas
    document.querySelectorAll(
      '#s1-output, #s2-output, #s3-output, #s4-output-skill, #s4-output-cot, #s4-output-qa, #s4-output-freshness'
    ).forEach(el => {
      if (el) { el.innerHTML = ''; el.style.display = 'none'; }
    });
    const s2Prev = document.getElementById('s2-prev-output-area');
    if (s2Prev) s2Prev.innerHTML = '<div class="s2-prev-empty">尚未检测到上一步输出，请先完成场景锚定</div>';
    const s3Info = document.getElementById('s3-prev-info');
    const s3Tags = document.getElementById('s3-prev-tags');
    if (s3Info) s3Info.innerHTML = '';
    if (s3Tags) s3Tags.innerHTML = '';

    const s4Info = document.getElementById('s4-prev-info');
    if (s4Info) s4Info.innerHTML = '';
    const s5Prev = document.getElementById('s4-prev-draft');
    if (s5Prev) s5Prev.innerHTML = '';
    _lastStep2ExtractedText = '';
    closeExcelEditor();
    // Reset sub-scenarios
    const subList = document.getElementById('s1-sub-scenarios');
    if (subList) subList.innerHTML = '';
    _s1SubScenarioCount = 0;

    // Reset step3/step4 preview card visibility states.
    const s3Draft = document.getElementById('s3-prev-draft');
    const s3Empty = document.getElementById('s3-prev-empty');
    if (s3Draft) s3Draft.style.display = 'none';
    if (s3Empty) s3Empty.style.display = '';

    const s4Box = document.getElementById('s4-prev-draft');
    const s4Empty = document.getElementById('s4-prev-empty');
    if (s4Box) s4Box.style.display = 'none';
    if (s4Empty) s4Empty.style.display = 'flex';

    loadStep1SchemaAndTemplates();
    showToast('流水线已清空');
    goBackToOverview();
  }).catch(e => {
    console.error('Clear failed:', e);
    showToast('清空失败', 'error');
  });
}

function showToast(msg, type = 'ok') {
  const existing = document.querySelector('.s-toast');
  if (existing) existing.remove();
  const toast = document.createElement('div');
  toast.className = 's-toast' + (type === 'error' ? ' s-toast-error' : '');
  toast.textContent = msg;
  document.body.appendChild(toast);
  setTimeout(() => toast.classList.add('s-toast-show'), 10);
  setTimeout(() => {
    toast.classList.remove('s-toast-show');
    setTimeout(() => toast.remove(), 300);
  }, 2000);
}

// ═══════════════════════════════════════════════════════════════════
// LLM Model Management
// ═══════════════════════════════════════════════════════════════════

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

// ─── Verify Knowledge Base Panel ─────────────────────────────────

function openVerifyPanel() {
  closeModelPanel();
  closeSkillPanel();
  document.getElementById('verify-panel').classList.add('open');
  document.getElementById('model-overlay').classList.remove('hidden');
  document.getElementById('verify-nav-btn').classList.add('active');
  loadVerificationPanel();
}
function closeVerifyPanel() {
  document.getElementById('verify-panel').classList.remove('open');
  document.getElementById('model-overlay').classList.add('hidden');
  document.getElementById('verify-nav-btn').classList.remove('active');
}

let verificationCases = [];

async function loadVerificationPanel() {
  await Promise.all([loadVerificationCases(), loadModels(), loadPipelinesForVerify()]);
  refreshVerifyModelSelect();
  setDefaultVerifySelection();
}

async function loadVerificationCases() {
  try {
    const resp = await fetch(API_BASE + '/api/kb/verification_cases?limit=200');
    const data = await resp.json();
    if (data.status === 'ok') {
      verificationCases = data.cases || [];
      renderVerificationCases();
    } else {
      showToast(data.error || '加载用例失败', 'error');
    }
  } catch (e) {
    showToast('加载用例网络错误', 'error');
  }
}

function renderVerificationCases() {
  const container = document.getElementById('verification-case-list');
  if (!container) return;
  if (!verificationCases.length) {
    container.innerHTML = '<div class="verify-empty">暂无测试用例，请导入或新增</div>';
    return;
  }
  let html = '';
  verificationCases.forEach(function (c) {
    const inputSummary = (c.input && c.input.title) ? escapeHtml(c.input.title) : '';
    const inputJson = JSON.stringify(c.input || {}, null, 2);
    const expectedJson = JSON.stringify(c.expected_output || {}, null, 2);
    html += '<div class="verify-case-item" data-uid="' + escapeHtml(c.case_uid) + '">';
    html += '<div class="verify-case-header" onclick="toggleVerifyCaseDetail(\'' + escapeHtml(c.case_uid) + '\')">';
    html += '<div class="verify-case-title">' + escapeHtml(c.name) + '</div>';
    html += '<div class="verify-case-meta">' + escapeHtml(c.source || 'manual') + (inputSummary ? ' · ' + inputSummary : '') + '</div>';
    html += '</div>';
    html += '<div class="verify-case-actions">';
    html += '<button type="button" class="btn btn--outline btn--sm" onclick="event.stopPropagation(); runSingleVerificationCase(\'' + escapeHtml(c.case_uid) + '\')">';
    html += '<span class="btn__icon btn__icon--left" data-lucide="play"></span><span class="btn__text">运行</span></button>';
    html += '<button type="button" class="btn btn--ghost btn--sm" onclick="event.stopPropagation(); toggleVerifyCaseDetail(\'' + escapeHtml(c.case_uid) + '\')">';
    html += '<span class="btn__icon btn__icon--left" data-lucide="info"></span><span class="btn__text">详情</span></button>';
    html += '<button type="button" class="btn btn--ghost btn--sm" onclick="event.stopPropagation(); deleteVerificationCase(\'' + escapeHtml(c.case_uid) + '\')">';
    html += '<span class="btn__text">删除</span></button>';
    html += '</div>';
    html += '<div class="verify-case-detail hidden" id="verify-case-detail-' + escapeHtml(c.case_uid) + '">';
    if (c.description) {
      html += '<div class="verify-detail-section"><div class="verify-detail-label">用例说明</div><div class="verify-detail-desc">' + escapeHtml(c.description) + '</div></div>';
    }
    html += '<div class="verify-detail-section"><div class="verify-detail-label">输入 (input)</div><pre class="verify-detail-code">' + escapeHtml(inputJson) + '</pre></div>';
    html += '<div class="verify-detail-section"><div class="verify-detail-label">期望输出 (expected_output)</div><pre class="verify-detail-code">' + escapeHtml(expectedJson) + '</pre></div>';
    html += '</div>';
    html += '</div>';
  });
  container.innerHTML = html;
  if (typeof refreshIcons === 'function') refreshIcons(container);
}

function toggleVerifyCaseDetail(caseUid) {
  const detail = document.getElementById('verify-case-detail-' + caseUid);
  if (!detail) return;
  detail.classList.toggle('hidden');
  const item = detail.closest('.verify-case-item');
  if (item) item.classList.toggle('expanded', !detail.classList.contains('hidden'));
}

function refreshVerifyModelSelect() {
  const sel = document.getElementById('verify-model-select');
  if (!sel || !allModels.length) return;
  const cur = sel.value;
  sel.innerHTML = '<option value="">-- 选择模型 --</option>';
  allModels.forEach(function (m) {
    const opt = document.createElement('option');
    opt.value = m.name;
    opt.textContent = m.name;
    sel.appendChild(opt);
  });
  if (cur) sel.value = cur;
}

async function loadPipelinesForVerify() {
  const sel = document.getElementById('verify-pipeline-select');
  if (!sel) return;
  try {
    const resp = await fetch(API_BASE + '/api/pipelines');
    const data = await resp.json();
    if (data.status === 'ok') {
      const pipelines = data.pipelines || [];
      sel.innerHTML = '<option value="">-- 选择流水线 --</option>';
      pipelines.forEach(function (p) {
        const opt = document.createElement('option');
        opt.value = p.id;
        opt.textContent = (p.name || p.scenario || '未命名') + ' (' + p.id.slice(0, 6) + '...)';
        sel.appendChild(opt);
      });
    }
  } catch (e) {
    console.error('load pipelines for verify failed', e);
  }
}

function setDefaultVerifySelection() {
  const psel = document.getElementById('verify-pipeline-select');
  if (psel && psel.options.length > 1) {
    if (currentPipeline && Array.from(psel.options).some(function (o) { return o.value === currentPipeline.id; })) {
      psel.value = currentPipeline.id;
    } else {
      psel.value = psel.options[1].value;
    }
  }
  const msel = document.getElementById('verify-model-select');
  if (msel && msel.options.length > 1 && !msel.value) {
    msel.value = msel.options[1].value;
  }
}

function showAddVerificationCaseForm() {
  const name = prompt('用例名称：');
  if (!name) return;
  const inputRaw = prompt('输入 JSON（留空使用默认示例）：');
  let input = {};
  try { input = inputRaw ? JSON.parse(inputRaw) : {document_type: '示例', title: name, content: ''}; } catch (e) { input = {title: name}; }
  const expectedRaw = prompt('期望输出 JSON（如 {"prediction":"通过"}，可留空）：');
  let expected = {};
  try { expected = expectedRaw ? JSON.parse(expectedRaw) : {}; } catch (e) { expected = {}; }
  fetch(API_BASE + '/api/kb/verification_cases', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({name: name, input: input, expected_output: expected}),
  }).then(function (r) { return r.json(); }).then(function (data) {
    if (data.status === 'ok') {
      showToast('已新增用例', 'success');
      loadVerificationCases();
    } else {
      showToast(data.error || '新增失败', 'error');
    }
  }).catch(function (e) { showToast('新增失败', 'error'); });
}

async function deleteVerificationCase(caseUid) {
  if (!confirm('确定删除该用例？')) return;
  try {
    const resp = await fetch(API_BASE + '/api/kb/verification_cases/' + encodeURIComponent(caseUid), {method: 'DELETE'});
    const data = await resp.json();
    if (data.status === 'ok') {
      showToast('已删除', 'success');
      loadVerificationCases();
    } else {
      showToast(data.error || '删除失败', 'error');
    }
  } catch (e) { showToast('删除失败', 'error'); }
}

async function importVerificationData() {
  try {
    const resp = await fetch(API_BASE + '/api/verify/import_result_data', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({}),
    });
    const data = await resp.json();
    if (data.status === 'ok') {
      showToast('导入成功', 'success');
      loadVerificationCases();
    } else {
      showToast(data.error || '导入失败', 'error');
    }
  } catch (e) { showToast('导入失败', 'error'); }
}

function getVerifyModelName() {
  const sel = document.getElementById('verify-model-select');
  return sel ? sel.value : (allModels[0] ? allModels[0].name : '');
}

function getVerifyPipelineId() {
  const sel = document.getElementById('verify-pipeline-select');
  return sel ? sel.value : '';
}

async function runSingleVerificationCase(caseUid) {
  const model = getVerifyModelName();
  const pipelineId = getVerifyPipelineId();
  if (!pipelineId && !currentPipeline) { renderVerificationReport({error: '请先选择流水线或 SKILL 文件'}); return; }
  renderVerificationReport({loading: true, message: '正在运行用例 ' + escapeHtml(caseUid) + '，请稍候...'});
  try {
    const resp = await fetch(API_BASE + '/api/validate/run_case', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({case_uid: caseUid, pipeline_id: pipelineId || (currentPipeline && currentPipeline.id), model: model}),
    });
    const data = await resp.json();
    if (data.status === 'ok') {
      renderVerificationReport(data.result || {});
      showToast('运行完成', 'success');
    } else {
      renderVerificationReport({error: data.error || '运行失败'});
      showToast(data.error || '运行失败', 'error');
    }
  } catch (e) { renderVerificationReport({error: '运行失败：' + String(e.message || e)}); showToast('运行失败', 'error'); }
}

async function runVerificationSuite() {
  const model = getVerifyModelName();
  const pipelineId = getVerifyPipelineId();
  if (!pipelineId && !currentPipeline) { renderVerificationReport({error: '请先选择流水线或 SKILL 文件'}); return; }
  if (!verificationCases.length) { renderVerificationReport({error: '没有可运行的用例，请先导入或新增'}); return; }
  renderVerificationReport({loading: true, message: '正在批量运行 ' + verificationCases.length + ' 个用例，请稍候...'});
  try {
    const resp = await fetch(API_BASE + '/api/validate/run_suite', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        case_uids: verificationCases.map(function (c) { return c.case_uid; }),
        pipeline_id: pipelineId || (currentPipeline && currentPipeline.id),
        model: model,
      }),
    });
    const data = await resp.json();
    if (data.status === 'ok') {
      renderVerificationReport(data.report || {});
      showToast('批量运行完成', 'success');
    } else {
      renderVerificationReport({error: data.error || '运行失败'});
      showToast(data.error || '运行失败', 'error');
    }
  } catch (e) { renderVerificationReport({error: '运行失败：' + String(e.message || e)}); showToast('运行失败', 'error'); }
}

function _findVerificationCaseName(id) {
  if (!verificationCases || !verificationCases.length || !id) return '';
  const c = verificationCases.find(function (x) { return x.case_uid === id || String(x.id) === String(id); });
  return c ? (c.name || c.case_uid || '') : '';
}

function _scrollVerificationReportIntoView() {
  const container = document.getElementById('verification-report');
  const panelBody = document.getElementById('verify-panel-body');
  if (!container) return;
  if (container.scrollIntoView) {
    try { container.scrollIntoView({behavior: 'smooth', block: 'nearest'}); } catch (e) {}
  }
  if (panelBody) {
    panelBody.scrollTop = panelBody.scrollHeight;
  }
}

function renderVerificationReport(report) {
  const container = document.getElementById('verification-report');
  if (!container) return;
  if (report && report.error) {
    container.innerHTML = '<div class="verify-report-box" style="color:var(--error)"><h4>提示</h4><div>' + escapeHtml(report.error) + '</div></div>';
    _scrollVerificationReportIntoView();
    return;
  }
  if (report && report.loading) {
    container.innerHTML = '<div class="verify-report-box"><h4>验证结果</h4><div>' + escapeHtml(report.message || '运行中...') + '</div></div>';
    _scrollVerificationReportIntoView();
    return;
  }
  // 单用例结果（接口返回的是 result 对象，不是 report 对象）
  if (report && report.status && report.case_id !== undefined && report.total === undefined) {
    const diff = report.diff || {};
    let html = '<div class="verify-report-box">';
    html += '<h4>单用例验证结果</h4>';
    html += '<div>用例：' + escapeHtml(String(_findVerificationCaseName(report.case_id) || report.case_id)) + '</div>';
    html += '<div>状态：<span class="verify-case-status ' + escapeHtml(report.status) + '">' + escapeHtml(report.status) + '</span></div>';
    if (diff.expected_prediction !== undefined || diff.actual_prediction !== undefined) {
      html += '<div style="margin-top:8px"><strong>结论对比</strong></div>';
      html += '<div>期望：' + escapeHtml(String(diff.expected_prediction || '')) + '</div>';
      html += '<div>实际：' + escapeHtml(String(diff.actual_prediction || '')) + '</div>';
    }
    if (report.actual_output && report.actual_output.reasoning) {
      html += '<div style="margin-top:8px"><strong>推理过程</strong></div>';
      html += '<pre class="verify-detail-code">' + escapeHtml(String(report.actual_output.reasoning)) + '</pre>';
    }
    html += '</div>';
    container.innerHTML = html;
    _scrollVerificationReportIntoView();
    return;
  }
  const total = report.total || 0;
  const pass = report.pass || 0;
  const rate = total ? ((pass / total) * 100).toFixed(1) : 0;
  let html = '<div class="verify-report-box">';
  html += '<h4>验证结果</h4>';
  html += '<div>用例数：' + total + '，通过：' + pass + '，失败：' + (report.fail || 0) + '，通过率：' + rate + '%</div>';
  if (report.mismatches && report.mismatches.length) {
    html += '<div style="margin-top:8px;"><strong>不一致用例：</strong></div>';
    html += '<ul>';
    report.mismatches.forEach(function (m) {
      const diff = m.diff || {};
      const name = _findVerificationCaseName(m.case_id);
      html += '<li>' + escapeHtml(String(name || m.case_id || '?')) + ' — 期望：' +
              escapeHtml(String(diff.expected_prediction || '')) + '，实际：' +
              escapeHtml(String(diff.actual_prediction || '')) + '</li>';
    });
    html += '</ul>';
  }
  html += '</div>';
  container.innerHTML = html;
  _scrollVerificationReportIntoView();
}

let allSkills = [];

const SKILL_META = {
  'knowledge-extraction': { icon: '🔍', iconCls: 'icon-purple', step: 2 },
  'knowledge-revision': { icon: '📝', iconCls: 'icon-orange', step: 3 },
  'knowledge-pattern-mining': { icon: '🔬', iconCls: 'icon-teal', step: 2 },
  'knowledge-gap-analysis': { icon: '🎯', iconCls: 'icon-blue', step: 2 },
  'knowledge-freshness-audit': { icon: '🔄', iconCls: 'icon-green', step: 5 },
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
  const selects = ['s2-model', 's3-model', 's4-model', 's4-validate-model', 's5-model'];
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
  2: ['knowledge-extraction', 'knowledge-pattern-mining', 'knowledge-gap-analysis'],
  3: ['knowledge-revision'],
  5: ['knowledge-freshness-audit'],
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

// ═══════════════════════════════════════════════════════════════════
// Step 1: Scenario Anchoring
// ═══════════════════════════════════════════════════════════════════

let _s1SubScenarioCount = 0;

function step1AddSubScenario() {
  _s1SubScenarioCount++;
  const idx = _s1SubScenarioCount;
  const container = document.getElementById('s1-sub-scenarios');
  const div = document.createElement('div');
  div.className = 's1-sub-item';
  div.id = 's1-sub-' + idx;
  div.innerHTML = '<div class="s1-sub-row">' +
    '<input type="text" class="s1-sub-name" placeholder="子场景名称" data-idx="' + idx + '">' +
    '<button type="button" class="btn btn--ghost btn--sm s1-sub-remove" onclick="step1RemoveSubScenario(' + idx + ')"><span class="btn__icon" data-lucide="x"></span></button>' +
    '</div>' +
    '<textarea class="s1-sub-content" rows="2" placeholder="子场景内容描述" data-idx="' + idx + '"></textarea>';
  container.appendChild(div);
  refreshIcons();
}

function step1RemoveSubScenario(idx) {
  const el = document.getElementById('s1-sub-' + idx);
  if (el) el.remove();
}

function step1GetSubScenarios() {
  const subs = [];
  document.querySelectorAll('.s1-sub-item').forEach(el => {
    const name = el.querySelector('.s1-sub-name').value.trim();
    const content = el.querySelector('.s1-sub-content').value.trim();
    if (name || content) subs.push({ name, content });
  });
  return subs;
}

async function step1Generate() {
  const btn = document.getElementById('s1-generate');
  if (!btn || btn._locked) return;
  btn.disabled = true;
  btn._locked = true;
  try {
  const scenarioName = document.getElementById('s1-scenario-name').value.trim();
  const scenarioContent = document.getElementById('s1-scenario-content').value.trim();
  const templateFile = document.getElementById('s1-template-file').files[0];
  const outputFormat = document.getElementById('s1-output-format')?.value || 'excel';
  const legacyTemplate = document.getElementById('s1-legacy-template')?.value || '';
  const knowledgeColumns = step1GetKnowledgeColumns();
  const hasCustomColumns = knowledgeColumns.length > 0;

  if (!scenarioName) { alert('请填写场景名称'); return; }
  if (!currentPipeline) {
    alert('请先从总览页「新建流水线」或「继续」进入一条流水线，再生成场景骨架');
    return;
  }
  if (!templateFile && !legacyTemplate && knowledgeColumns.length === 0) {
    alert('请至少添加一列知识字段，或上传/选用 Excel 模板');
    return;
  }

  const subScenarios = step1GetSubScenarios();
  clearTimeout(_formSaveTimer);
  renderLoading('s1-output');

  const fd = new FormData();
  fd.append('scenario_name', scenarioName);
  fd.append('scenario_content', scenarioContent);
  fd.append('sub_scenarios', JSON.stringify(subScenarios));
  fd.append('knowledge_columns', JSON.stringify(knowledgeColumns));
  if (templateFile) {
    fd.append('template', templateFile);
    fd.append('output_format', outputFormat);
  } else {
    fd.append('output_format', outputFormat);
    // 有自定义知识列时，默认按自定义列生成；不再隐式落回 legacy 模板
    if (legacyTemplate && !hasCustomColumns) {
      fd.append('template_mode', 'legacy');
      fd.append('default_template', legacyTemplate);
    }
  }
  fd.append('pipeline_id', currentPipeline.id);

  try {
    const result = await apiCall('/api/step1/generate', fd);
    let html = '';
    if (result.status === 'ok') {
      applyStep1GenerateResult(result);
      syncPipelineFromStep1Response(result);
      const allForm = collectAllStepsFormData();
      currentPipeline.step_data = mergeStepDataPreserveOutputs(currentPipeline.step_data, allForm);
      const excelFile = result.excel_file || result.file_name;
      await persistPipeline({
        ...allForm,
        step1_output_file: excelFile,
        step1_download_url: result.excel_download_url || ('/downloads/' + excelFile),
        step1_knowledge_columns: result.knowledge_columns || knowledgeColumns,
        step1_output_format: result.output_format || outputFormat,
        ...(result.markdown_file ? {
          step1_md_file: result.markdown_file,
          step1_md_download_url: result.markdown_download_url,
        } : {}),
      });
      html += '<div class="s1-result-box">';
      html += '<div class="s1-result-title">场景骨架生成成功</div>';
      html += '<div class="s1-result-stats">';
      html += '<div class="s2-stat"><span class="s2-stat-num">' + (result.fields_info ? result.fields_info.length : 0) + '</span><span class="s2-stat-label">工作表</span></div>';
      html += '<div class="s2-stat"><span class="s2-stat-num">' + (result.sub_scenario_count || 0) + '</span><span class="s2-stat-label">子场景</span></div>';
      html += '</div>';
      const templateSourceMap = {
        schema: '自定义列 · Excel',
        schema_markdown: '自定义列 · Markdown+Excel',
        legacy: '部门 Excel 模板',
        legacy_markdown: '部门 Excel 模板 · Markdown+Excel',
        upload: '上传 Excel 模板',
        upload_markdown: '上传 Excel 模板 · Markdown+Excel',
      };
      const templateSourceLabel = templateSourceMap[result.template_source] || '模板';
      const templateName = result.template_name || '未命名';
      html += '<div class="s1-result-template">来源：' + escapeHtml(templateSourceLabel) + ' · ' + escapeHtml(templateName) + '</div>';
      if (result.knowledge_columns && result.knowledge_columns.length) {
        html += '<div class="s1-result-template">知识列：' + escapeHtml(result.knowledge_columns.join('、')) + '</div>';
      }
      if (result.columns_enriched) {
        html += '<div class="s1-result-template file-hint">已按 Markdown 模式自动补齐富语义列，Step2 将按完整字段深度萃取。</div>';
        step1RenderKnowledgeColumns(result.knowledge_columns);
      }
      if (result.fields_info && result.fields_info.length) {
        html += '<div class="s1-result-sheets">';
        result.fields_info.forEach(function(fi) {
          html += '<div class="s1-sheet-item"><span class="s1-sheet-name">' + escapeHtml(fi.sheet) + '</span><span class="s1-sheet-meta">' + fi.headers.length + ' 列 · ' + (fi.data_rows || 0) + ' 行</span></div>';
        });
        html += '</div>';
      }
      html += '<div class="s1-result-actions">';
      const mdFlow = (result.output_format === 'markdown') || prefersMarkdownFlow();
      const step1MdFile = result.markdown_file || '';
      // Markdown group
      if (mdFlow && step1MdFile) {
        html += `<button class="btn btn--primary btn--sm" onclick="previewStep4File('${escapeHtml(step1MdFile)}','Step1 骨架 Markdown 预览')">预览/编辑 Markdown</button>`;
      }
      if (result.download_url) {
        const dlLabel = mdFlow ? '下载 Markdown 骨架' : '下载 Excel 骨架';
        html += '<a class="btn btn--outline btn--sm" href="' + API_BASE + result.download_url + '" download>' + dlLabel + '</a>';
      }
      // Excel group
      if (!mdFlow && result.excel_download_url) {
        html += '<button class="btn btn--outline btn--sm" onclick="step1PreviewExcel(\'' + (result.excel_file || result.file_name) + '\')">预览 Excel</button>';
      }
      html += '</div>';
      html += '</div>';
      await markStepDone(1);
      if (currentStep === 2) loadStep2PrevOutput();
    } else {
      html = '<div class="error-list"><div class="error-item">' + escapeHtml(result.error || '未知错误') + '</div></div>';
    }
    renderOutput('s1-output', html);
  } catch (e) {
    renderOutput('s1-output', '<div class="error-list"><div class="error-item">' + escapeHtml(e.message) + '</div></div>');
  }
  } finally {
    btn.disabled = false;
    btn._locked = false;
  }
}

function restoreStep1Output() {
  if (!currentPipeline?.step_data) return;
  const sd = currentPipeline.step_data;
  const outputFile = sd.step1_output_file;
  if (!outputFile) return;
  const outputEl = document.getElementById('s1-output');
  if (!outputEl || outputEl.querySelector('.s1-result-box')) return;

  const mdFlow = (sd.step1_output_format === 'markdown') || prefersMarkdownFlow();
  const mdFile = sd.step1_md_file || '';
  let html = '<div class="s1-result-box">';
  html += '<div class="s1-result-title">场景骨架已生成</div>';
  if (sd.step1_template_name) {
    html += '<div class="s1-result-template">来源：' + escapeHtml(sd.step1_template_name) + '</div>';
  }
  if (sd.step1_knowledge_columns && sd.step1_knowledge_columns.length) {
    html += '<div class="s1-result-template">知识列：' + escapeHtml(sd.step1_knowledge_columns.join('、')) + '</div>';
  }
  html += '<div class="s1-result-actions">';
  // Markdown group
  if (mdFlow && mdFile) {
    html += '<button class="btn btn--primary btn--sm" onclick="previewStep4File(\'' + escapeHtml(mdFile) + '\',\'Step1 骨架 Markdown 预览\')">预览/编辑 Markdown</button>';
  }
  if (sd.step1_download_url) {
    const dlLabel = mdFlow ? '下载 Markdown 骨架' : '下载 Excel 骨架';
    html += '<a class="btn btn--outline btn--sm" href="' + API_BASE + sd.step1_download_url + '" download>' + dlLabel + '</a>';
  }
  // Excel group
  if (!mdFlow && sd.step1_download_url) {
    html += '<button class="btn btn--outline btn--sm" onclick="step1PreviewExcel(\'' + escapeHtml(outputFile) + '\')">预览 Excel</button>';
  }
  html += '</div></div>';
  renderOutput('s1-output', html);
}

async function step1PreviewExcel(fileName) {
  const modal = document.getElementById('excel-editor-modal');
  if (modal) modal.classList.add('active');
  renderExcelEditorLoading();
  if (typeof ExcelEditor !== 'undefined' && ExcelEditor.preloadLuckysheet) {
    ExcelEditor.preloadLuckysheet();
  }

  const fd = new FormData();
  fd.append('file_name', fileName);
  if (currentPipeline) fd.append('pipeline_id', currentPipeline.id);
  fd.append('step', '1');
  try {
    const result = await apiCall('/api/excel/read', fd);
    if (result.status === 'ok') {
      openExcelEditorWithSheets(result.sheets, fileName, result.file_path || fileName);
    } else {
      if (modal) modal.classList.remove('active');
      alert(result.error || '读取失败');
    }
  } catch (e) {
    if (modal) modal.classList.remove('active');
    alert('读取失败: ' + e.message);
  }
}

function openExcelEditorWithSheets(sheets, fileName, filePath) {
  const modal = document.getElementById('excel-editor-modal');
  const stepLabel = document.getElementById('excel-editor-step-label');
  if (stepLabel) stepLabel.textContent = '预览: ' + fileName;
  _excelEditorData.sheets = ExcelEditor.normalizeSheetsFromApi(
    typeof sheets === 'object' && !Array.isArray(sheets) ? sheets : { Sheet1: sheets }
  );
  _excelEditorData.file_path = filePath || fileName;
  _excelEditorData.active_sheet = Object.keys(_excelEditorData.sheets)[0] || '';
  _excelEditorData.modified = false;
  _excelEditorData.step = 1;
  if (modal) modal.classList.add('active');
  requestAnimationFrame(function () {
    requestAnimationFrame(function () {
      renderExcelEditorContent();
    });
  });
}

// ═══════════════════════════════════════════════════════════════════
// Step 2: Knowledge Extraction
// ═══════════════════════════════════════════════════════════════════

function renderStep2PrevOutputCard(data) {
  const area = document.getElementById('s2-prev-output-area');
  if (!area) return;
  let fieldsHtml = '';
  if (data.fields_info && data.fields_info.length) {
    const allHeaders = data.fields_info.flatMap(f => f.headers);
    fieldsHtml = '<div class="s2-prev-card-fields">' +
      allHeaders.slice(0, 12).map(h => '<span class="s2-prev-field-tag">' + escapeHtml(h) + '</span>').join('') +
      (allHeaders.length > 12 ? '<span class="s2-prev-field-tag">+' + (allHeaders.length - 12) + '</span>' : '') +
      '</div>';
  }
  area.innerHTML = `
    <div class="s2-prev-card">
      <div class="s2-prev-card-top">
        <div class="s2-prev-card-icon">📋</div>
        <div class="s2-prev-card-name">${escapeHtml(data.scenario || '场景模板')}</div>
        <span class="s2-prev-card-badge">已就绪</span>
      </div>
      <div class="s2-prev-card-info">
        领域：<span>${escapeHtml(data.domain || '-')}</span> · 文件：<span>${escapeHtml(data.file_name || '-')}</span>
      </div>
      ${fieldsHtml}
      <div class="s2-result-actions" style="margin-top:8px;">
        ${data.markdown_file ? `<button class="btn btn--outline btn--sm" onclick="previewStep4File('${escapeHtml(data.markdown_file)}','Step1 骨架 Markdown 预览')">预览/编辑 Markdown</button>` : ''}
        ${data.markdown_download_url ? `<a class="btn btn--outline btn--sm" href="${API_BASE + data.markdown_download_url}" download>下载 Markdown</a>` : ''}
        ${data.download_url ? `<button class="btn btn--outline btn--sm" onclick="step1PreviewExcel('${escapeHtml(data.file_name || '')}')">预览 Excel</button>` : ''}
        ${data.download_url ? `<a class="btn btn--outline btn--sm" href="${API_BASE + data.download_url}" download>下载 Excel</a>` : ''}
      </div>
    </div>
  `;
}

async function ensureStep1OutputLinked() {
  if (!currentPipeline?.step_data?.step1_output_file) {
    const recalled = recallStep1Output(currentPipeline.id);
    if (recalled?.file_name) {
      currentPipeline.step_data = currentPipeline.step_data || {};
      currentPipeline.step_data.step1_output_file = recalled.file_name;
      currentPipeline.step_data.step1_download_url = recalled.download_url;
      await persistPipeline({
        step1_output_file: recalled.file_name,
        step1_download_url: recalled.download_url,
      });
    }
  }
}

async function loadStep2PrevOutput() {
  const area = document.getElementById('s2-prev-output-area');
  if (!currentPipeline) {
    area.innerHTML = '<div class="s2-prev-empty">当前无流水线</div>';
    return;
  }

  area.innerHTML = '<div class="s2-prev-empty" style="color:var(--text-secondary)">检测中...</div>';

  try {
    await ensureStep1OutputLinked();

    const resp = await fetch(API_BASE + '/api/step2/prev_output?pipeline_id=' + currentPipeline.id);
    const data = await resp.json();

    if (data.status !== 'ok' || !data.has_output) {
      const hint = data.hint || '请先在「场景锚定」点击「生成场景骨架」（需已从总览进入当前流水线）';
      area.innerHTML = '<div class="s2-prev-empty">' + escapeHtml(hint) + '</div>';
      return;
    }

    renderStep2PrevOutputCard(data);
  } catch (e) {
    area.innerHTML = '<div class="s2-prev-empty">检测失败，可手动上传</div>';
  }
}


function isStep2PreextractFile(fileName) {
  const n = String(fileName || '').toLowerCase();
  if (!n.endsWith('.xlsx')) return false;
  return n.startsWith('preextract_') || n.startsWith('edited_step2_');
}

function resolveStep2DownloadInfo(result) {
  const apiName = result.download_name || '';
  const apiUrl = result.download_url || '';

  let dlName = '';
  let dlUrl = '';

  if (isStep2PreextractFile(apiName)) {
    dlName = apiName;
    dlUrl = apiUrl || ('/downloads/' + dlName);
  } else if (apiUrl) {
    const m = String(apiUrl).match(/\/([^/?#]+\.xlsx)(?:\?|$)/i);
    if (m && isStep2PreextractFile(m[1])) {
      dlName = m[1];
      dlUrl = apiUrl;
    }
  }

  if (dlName && !dlUrl) dlUrl = '/downloads/' + dlName;
  return { dlName, dlUrl };
}

// ═══════════════════════════════════════════════════════════════════
// Step 3: Interactive Knowledge Alignment
// ═══════════════════════════════════════════════════════════════════

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
        // Excel group
        if (data.download_url && !mdFlow) {
          actionBtns += `<button type="button" class="btn btn--outline btn--sm" onclick="step1PreviewExcel('${escapeHtml(data.file_name || '')}')">预览 Excel</button>`;
        }
        if (data.download_url) {
          actionBtns += `<a class="btn btn--outline btn--sm" href="${API_BASE + data.download_url}" download>下载 Excel</a>`;
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
  }
}

async function loadStep3IRForAlignment() {
  const pid = getCurrentPipelineId();
  if (!pid) return;
  try {
    const resp = await fetch(API_BASE + '/api/pipeline/detail?pipeline_id=' + pid);
    const data = await resp.json();
    if (data.status !== 'ok' || !data.pipeline) return;
    const sd = data.pipeline.step_data || {};
    const irName = sd.step3_aligned_file || sd.step2_draft_file;
    if (!irName) {
      document.getElementById('s3-ir-list').innerHTML = '<div class="output-placeholder">请先完成 Step2 萃取</div>';
      return;
    }
    const irResp = await fetch(API_BASE + '/downloads/' + irName);
    const ir = await irResp.json();
    renderStep3IRDualView(ir);
  } catch (e) {
    console.error('loadStep3IRForAlignment failed:', e);
    document.getElementById('s3-ir-list').innerHTML = '<div class="output-placeholder">加载 IR 失败: ' + escapeHtml(e.message) + '</div>';
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
  } catch (e) { panel.classList.add('hidden'); }
}

function _s3CheckedSuggestionIds() {
  var ids = [];
  document.querySelectorAll('.s3-suggestion-check:checked').forEach(function (c) { ids.push(c.value); });
  return ids;
}

async function step3ApplySuggestions() {
  var pid = currentPipeline ? currentPipeline.id : null;
  if (!pid) return;
  var ids = _s3CheckedSuggestionIds();
  if (!ids.length) { showToast('请先勾选要采纳的建议', 'error'); return; }
  var btn = document.getElementById('s3-suggestion-apply');
  if (btn) btn.disabled = true;
  try {
    var result = await apiCallJSON('/api/step3/apply_suggestions', { pipeline_id: pid, accepted_ids: ids });
    if (result.status !== 'ok') { showToast(result.error || '应用建议失败', 'error'); return; }
    if (currentPipeline) {
      currentPipeline.step_data = currentPipeline.step_data || {};
      if (result.aligned_file) {
        currentPipeline.step_data.step3_aligned_file = result.aligned_file;
        currentPipeline.step_data.step3_aligned_url = result.aligned_url || '';
        currentPipeline.step_data.step3_aligned_version = result.aligned_version || 0;
        if (result.aligned_md_file) {
          currentPipeline.step_data.step3_aligned_md_file = result.aligned_md_file;
          currentPipeline.step_data.step3_aligned_md_url = result.aligned_md_url || '';
        }
      }
    }
    showToast('已应用 ' + (result.applied_count || 0) + ' 条建议，生成对齐稿 v' + (result.aligned_version || '?'));
    loadStep3SuggestionPool();
    refreshCurrentPipeline();
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
  try {
    var result = await apiCallJSON('/api/step3/apply_suggestions', { pipeline_id: pid, rejected_ids: ids });
    if (result.status !== 'ok') { showToast(result.error || '驳回失败', 'error'); return; }
    showToast('已驳回 ' + ids.length + ' 条建议');
    loadStep3SuggestionPool();
  } catch (e) {
    showToast('驳回失败: ' + e.message, 'error');
  }
}

// Phase 1: Generate alignment preview (AI suggestions only)
async function step3GeneratePreview() {
  const pid = currentPipeline ? currentPipeline.id : null;
  if (!pid) { alert('请先进入流水线'); return; }
  const expertTextEl = document.getElementById('s3-expert-text');
  const expertText = expertTextEl.value.trim();
  const expertFileEl = document.getElementById('s3-expert-file');
  const cachedExpertFile = currentPipeline?.step_data?.step3_cached_file || '';
  let finalMessage = expertText;

  if (!finalMessage && expertFileEl.files.length > 0) {
    finalMessage = await expertFileEl.files[0].text();
  }
  const style = document.getElementById('s3-revision-style').value;
  const model = document.getElementById('s3-model').value;

  const btn = document.getElementById('s3-revise-btn');
  btn._locked = true;
  btn.disabled = true;
  btn.classList.add('loading');
  btn.innerHTML = '<span class="btn__text">处理中...</span>';
  clearTimeout(_formSaveTimer);
  renderLoading('s3-output');

  const fd = new FormData();
  fd.append('pipeline_id', pid);
  if (finalMessage) fd.append('message', finalMessage);
  fd.append('style', style);
  if (model) fd.append('model', model);
  if (expertFileEl && expertFileEl.files && expertFileEl.files.length > 0) {
    fd.append('expert_file', expertFileEl.files[0]);
  } else if (!finalMessage && cachedExpertFile) {
    fd.append('expert_cached_file', cachedExpertFile);
  }
  try {
    const resp = await fetch(API_BASE + '/api/step3/align_chat', { method: 'POST', body: fd });
    const result = await resp.json();

    if (result.status === 'ok') {
      if (Array.isArray(result.chat_history)) {
        _alignChatHistory = result.chat_history;
      } else {
        _alignChatHistory = _alignChatHistory || [];
        if (finalMessage) _alignChatHistory.push({ role: 'user', content: finalMessage });
        if (result.assistant_reply) _alignChatHistory.push({ role: 'assistant', content: result.assistant_reply });
      }
      renderStep3ChatHistory();
      if (expertTextEl) expertTextEl.value = '';
      _alignNotes = result.notes || [];
      if (!(_alignNotes.length > 0)) {
        const passThrough = result.auto_finalized || result.align_mode === 'pass_through' || result.no_opinion;
        if (passThrough) {
          await showStep3AlignComplete(result, { noRevision: true });
          renderOutput('s3-output', '<div class="s2-result-success"><div class="s2-result-header">' +
            escapeHtml(result.message || '已按预萃稿生成对齐稿（无修订）') + '</div></div>');
          return;
        }
        const msg = result.message || '未从专家意见/上传材料中解析出可执行的修订条目，请补充更明确的修改说明。';
        renderOutput('s3-output', '<div class="error-list"><div class="error-item">' + escapeHtml(msg) + '</div></div>');
        document.getElementById('s3-input-section').style.display = '';
        document.getElementById('s3-review-section').style.display = 'none';
        document.getElementById('s3-result-section').style.display = 'none';
        return;
      }

      _alignNoteStates = {};
      _alignEditedValues = {};
      _alignCurrentFilter = 'all';
      _alignNotes.forEach(n => { _alignNoteStates[n.id] = 'pending'; });

      const ruleHint = result.style_rule
        ? `风格 ${result.style_rule.mode} · 原始 ${result.style_rule.raw_count} 条 → 过滤后 ${result.style_rule.processed_count} 条`
        : '';
      renderOutput('s3-output', `<div class="s2-result-success"><div class="s2-result-header">AI 生成了 ${_alignNotes.length} 条对齐建议</div><div class="s2-result-meta">${escapeHtml(ruleHint)} · 请在下方逐条审核</div></div>`);

      document.getElementById('s3-input-section').style.display = 'none';
      document.getElementById('s3-review-section').style.display = '';
      document.getElementById('s3-result-section').style.display = 'none';

      renderAlignNotesList();
      updateAlignStats();
    } else {
      renderOutput('s3-output', '<div class="error-list"><div class="error-item">' + escapeHtml(result.error || '生成对齐建议失败') + '</div></div>');
    }
  } catch (e) {
    renderOutput('s3-output', '<div class="error-list"><div class="error-item">' + escapeHtml(e.message) + '</div></div>');
  } finally {
    btn.disabled = false;
    updateStep3AlignModeHint();
    refreshIcons();
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
  // Excel group
  if (!mdFlow && dlName) html += '<button class="btn btn--primary btn--sm" onclick="step1PreviewExcel(\'' + escapeHtml(dlName) + '\')">预览 Excel</button>';
  if (dlUrl) html += '<a href="' + escapeHtml(dlUrl) + '" class="btn btn--outline btn--sm" download>下载 Excel</a>';
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
      renderOutput('s3-output', '<div class="error-list"><div class="error-item">' + escapeHtml(result.error || '确认失败') + '</div></div>');
    }
  } catch (e) {
    console.error('step3ConfirmAsIs failed:', e);
    renderOutput('s3-output', '<div class="error-list"><div class="error-item">确认失败: ' + escapeHtml(e.message) + '</div></div>');
  }
}

// ═══════════════════════════════════════════════════════════════════
// Step 4: Compile & Quality & AI Refine
// ═══════════════════════════════════════════════════════════════════

async function loadStep4PrevOutput() {
  if (!currentPipeline) return;
  const el = document.getElementById('s4-prev-draft');
  const emptyEl = document.getElementById('s4-prev-empty');
  if (!el) return;
  try {
    const resp = await fetch(API_BASE + '/api/step3/align_output?pipeline_id=' + currentPipeline.id);
    const data = await resp.json();
    if (data.has_output) {
      el.style.display = 'block';
      if (emptyEl) emptyEl.style.display = 'none';
      const infoNameEl = document.getElementById('s4-prev-name');
      const infoMetaEl = document.getElementById('s4-prev-meta');
      const tagsEl = document.getElementById('s4-prev-tags');
      const mdFlow = prefersMarkdownFlow();
      if (infoNameEl) infoNameEl.textContent = (mdFlow && data.markdown_file) ? data.markdown_file : (data.file_name || '知识对齐稿');
      if (infoMetaEl) infoMetaEl.textContent = (data.scenario || '');
      if (tagsEl) {
        let tags = '';
        if (data.fields_info) {
          data.fields_info.forEach(s => {
            tags += '<span class="s2-prev-tag">' + escapeHtml(s.sheet) + ' (' + s.data_rows + '行)</span>';
          });
        }
        tagsEl.innerHTML = tags;
      }
      // Action buttons in a clean row below tags
      const actionsEl = document.getElementById('s4-prev-actions');
      if (actionsEl) {
        let btns = '';
        const mdName = data.markdown_file || '';
        const excelName = data.file_name || '';
        const mdUrl = mdName ? ('/downloads/' + mdName) : '';
        const excelUrl = data.download_url || '';
        // Markdown group
        if (mdFlow && mdName) btns += '<button class="btn btn--primary btn--sm" onclick="previewStep4File(\'' + escapeHtml(mdName) + '\',\'Step3 对齐 Markdown 预览\')">预览/编辑 Markdown</button>';
        if (!mdFlow && mdName) btns += '<button class="btn btn--outline btn--sm" onclick="previewStep4File(\'' + escapeHtml(mdName) + '\',\'Step3 对齐 Markdown 预览\')">预览/编辑 Markdown</button>';
        if (mdUrl) btns += '<a class="btn btn--outline btn--sm" href="' + API_BASE + mdUrl + '" download>下载 Markdown</a>';
        // Excel group
        if (!mdFlow && excelName) btns += '<button class="btn btn--primary btn--sm" onclick="step1PreviewExcel(\'' + escapeHtml(excelName) + '\')">预览 Excel</button>';
        if (mdFlow && excelName) btns += '<button class="btn btn--outline btn--sm" onclick="step1PreviewExcel(\'' + escapeHtml(excelName) + '\')">预览 Excel</button>';
        if (excelUrl) btns += '<a class="btn btn--outline btn--sm" href="' + API_BASE + excelUrl + '" download>下载 Excel</a>';
        actionsEl.innerHTML = btns;
      }
    } else {
      el.style.display = 'none';
      if (emptyEl) emptyEl.style.display = 'block';
    }
  } catch (e) { console.error('loadStep4PrevOutput error', e); }
}

function getSelectedStep4Formats() {
  const formats = [];
  if (document.getElementById('s4-fmt-cot')?.checked) formats.push('cot');
  if (document.getElementById('s4-fmt-qa')?.checked) formats.push('qa');
  if (document.getElementById('s4-fmt-skill')?.checked) formats.push('skill');
  return formats;
}

function renderStep4ArtifactCard(key, title, desc, countLabel, downloads, previewFn) {
  let html = '<div class="s4-artifact-card">';
  html += '<div class="s4-artifact-head"><div class="s4-artifact-title">' + escapeHtml(title) + '</div>';
  if (countLabel) html += '<span class="s4-artifact-badge">' + escapeHtml(countLabel) + '</span>';
  html += '</div>';
  html += '<div class="s4-artifact-desc">' + escapeHtml(desc) + '</div>';
  html += '<div class="s4-artifact-actions">';
  (downloads || []).forEach(d => {
    if (d.url) {
      html += '<a class="btn btn--outline btn--sm" href="' + escapeHtml(API_BASE + d.url) + '" download>' + escapeHtml(d.label) + '</a>';
    }
  });
  if (previewFn) {
    html += '<button type="button" class="btn btn--outline btn--sm" onclick="' + previewFn + '">&#128065; 预览</button>';
  }
  html += '</div></div>';
  return html;
}

async function step4FreshnessAudit() {
  var btn = document.getElementById('s4-freshness-btn');
  if (!btn || btn._locked || !currentPipeline) return;
  var origBtnHtml = btn.innerHTML;
  btn._locked = true;
  btn.disabled = true;
  btn.classList.add('loading');
  btn.innerHTML = '<span class="btn__icon btn__icon--left" data-lucide="refresh-cw"></span><span class="btn__text">审计中...</span>';
  var fd = new FormData();
  fd.append('skill_id', 'knowledge-freshness-audit');
  fd.append('pipeline_id', currentPipeline.id);
  fd.append('model', resolveModelName('s4-model') || (allModels.length ? allModels[0].name : ''));
  try {
    var resp = await fetch(API_BASE + '/api/skills/execute', { method: 'POST', body: fd });
    var result = await resp.json();
    var s5out = document.getElementById('s4-output-freshness');
    s5out.style.display = 'block';
    if (result.status === 'ok') {
      var dl = result.download_url || '';
      s5out.innerHTML =
        '<div class="s2-result-success"><div class="s2-result-header">保鲜度审计完成</div>' +
        '<div class="s2-result-meta">共 ' + (result.total_items || 0) + ' 条知识 · 高置信度占比 ' + (result.high_confidence_pct || 0) + '%' +
        (result.completeness_score ? ' · 完整性得分 ' + result.completeness_score + '%' : '') + '</div>' +
        (result.stale_indicators && result.stale_indicators.length ?
          '<div style="margin-top:8px">' + result.stale_indicators.map(function(s){return '<div style="font-size:12px;color:#8b6914;margin:2px 0">⚠️ '+escapeHtml(s)+'</div>';}).join('') + '</div>' : '') +
        '<div class="s2-result-actions" style="margin-top:12px">' +
        '<button class="btn btn--primary btn--sm" onclick="previewStep4File(\'' + escapeHtml(result.report_name || '') + '\',\'保鲜度审计报告\')">&#128065; 预览报告</button>' +
        (dl ? '<a class="btn btn--outline btn--sm" href="'+API_BASE+dl+'" download>下载报告</a>' : '') +
        '</div>' +
        '</div>';
    } else {
      s5out.innerHTML = '<div class="error-list"><div class="error-item">' + escapeHtml(result.error || '审计失败') + '</div></div>';
    }
  } catch (e) {
    document.getElementById('s4-output-freshness').innerHTML = '<div class="error-list"><div class="error-item">' + escapeHtml(e.message) + '</div></div>';
  } finally {
    btn._locked = false;
    btn.disabled = false;
    btn.classList.remove('loading');
    btn.innerHTML = origBtnHtml;
    refreshIcons();
  }
}


async function step4GenerateCOT() {
  if (!currentPipeline) { showToast('请先进入流水线', 'error'); return; }
  const btn = document.getElementById('s4-cot-btn');
  if (!btn || btn._locked) return;
  btn._locked = true; btn.disabled = true;
  const origHtml = btn.innerHTML;
  btn.classList.add('loading');
  btn.innerHTML = 'LLM 生成中<span class="btn-estimate">· 约 15-30s</span>';

  try {
    const fd = new FormData();
    fd.append('pipeline_id', currentPipeline.id);
    const model = resolveModelName('s4-model') || '';
    if (model) fd.append('model', model);

    const resp = await fetch(API_BASE + '/api/step4/generate-cot', { method: 'POST', body: fd });
    const result = await resp.json();
    if (result.status !== 'ok') { showToast(result.error || '生成失败', 'error'); return; }

    var html = '<div class="s2-result-success"><div class="s2-result-header">思维链 (COT) 已生成</div>';
    html += '<div class="s2-result-content"><pre style="font-size:11px;">' + escapeHtml(result.preview || '') + '</pre></div>';
    html += '<div class="s2-result-actions">';
    html += '<button class="btn btn--outline btn--sm" onclick="previewStep4File(\'' + escapeHtml(result.filename) + '\',\'COT\')">预览/编辑 Markdown</button>';
    html += '<a class="btn btn--outline btn--sm" href="' + API_BASE + result.download_url + '" download>下载 Markdown</a>';
    html += '</div></div>';
    document.getElementById('s4-output-cot').style.display = 'block';
    document.getElementById('s4-output-cot').innerHTML = '<div class="s4-artifact-panel"><div class="panel-header"><span>思维链 (COT)</span><span style="font-weight:400;font-size:11px;color:var(--text-muted);">LLM 生成</span></div>' + html + '</div>';
    await markStepDone(4);
  } catch (e) {
    showToast('生成失败: ' + e.message, 'error');
  } finally {
    btn._locked = false; btn.disabled = false; btn.innerHTML = origHtml;
    btn.classList.remove('loading');
    refreshIcons();
  }
}

async function step4GenerateQA() {
  if (!currentPipeline) { showToast('请先进入流水线', 'error'); return; }
  const btn = document.getElementById('s4-qa-btn');
  if (!btn || btn._locked) return;
  btn._locked = true; btn.disabled = true;
  const origHtml = btn.innerHTML;
  btn.classList.add('loading');
  btn.innerHTML = 'LLM 生成中<span class="btn-estimate">· 约 20-40s</span>';

  try {
    const fd = new FormData();
    fd.append('pipeline_id', currentPipeline.id);
    const model = resolveModelName('s4-model') || '';
    if (model) fd.append('model', model);

    const resp = await fetch(API_BASE + '/api/step4/generate-qa', { method: 'POST', body: fd });
    const result = await resp.json();
    if (result.status !== 'ok') { showToast(result.error || '生成失败', 'error'); return; }

    var html = '<div class="s2-result-success"><div class="s2-result-header">QA 对已生成</div>';
    html += '<div class="s2-result-meta">共 <strong>' + (result.qa_count || 0) + '</strong> 个问答对</div>';
    html += '<div class="s2-result-content"><pre style="font-size:11px;">' + escapeHtml(result.preview || '') + '</pre></div>';
    html += '<div class="s2-result-actions">';
    html += '<button class="btn btn--outline btn--sm" onclick="previewStep4File(\'' + escapeHtml(result.md_filename || '') + '\',\'QA\')">预览/编辑 Markdown</button>';
    html += '<a class="btn btn--outline btn--sm" href="' + API_BASE + result.md_download_url + '" download>下载 Markdown</a>';
    html += '<a class="btn btn--outline btn--sm" href="' + API_BASE + result.download_url + '" download>下载 JSON</a>';
    html += '</div></div>';
    document.getElementById('s4-output-qa').style.display = 'block';
    document.getElementById('s4-output-qa').innerHTML = '<div class="s4-artifact-panel"><div class="panel-header"><span>QA 对</span><span style="font-weight:400;font-size:11px;color:var(--text-muted);">LLM 生成</span></div>' + html + '</div>';
    await markStepDone(4);
  } catch (e) {
    showToast('生成失败: ' + e.message, 'error');
  } finally {
    btn._locked = false; btn.disabled = false; btn.innerHTML = origHtml;
    btn.classList.remove('loading');
    refreshIcons();
  }
}

async function step4GenerateExecSkill() {
  if (!currentPipeline) { showToast('请先进入流水线', 'error'); return; }
  const btn = document.getElementById('s4-exec-skill-btn');
  if (!btn || btn._locked) return;
  btn._locked = true; btn.disabled = true;
  const origHtml = btn.innerHTML;
  btn.classList.add('loading');
  btn.innerHTML = 'LLM 生成中<span class="btn-estimate">· 约 30-60s</span>';

  try {
    const fd = new FormData();
    fd.append('pipeline_id', currentPipeline.id);
    const model = resolveModelName('s4-model') || '';
    if (model) fd.append('model', model);

    const resp = await fetch(API_BASE + '/api/step4/generate-executable-skill', { method: 'POST', body: fd });
    const result = await resp.json();
    if (result.status !== 'ok') { showToast(result.error || '生成失败', 'error'); return; }

    var html = '<div class="s2-result-success"><div class="s2-result-header">可执行 Agent Skill 已生成</div>';
    html += '<div class="s2-result-meta">章节数: <strong>' + (result.section_count || 0) + '</strong>';
    if (result.has_sql) html += ' · 含 SQL 查询';
    if (result.golden_stats && result.golden_stats.available) {
      html += ' · golden 库: ' + Object.keys(result.golden_stats.tables).length + ' 表可用';
    }
    html += '</div>';
    html += '<div class="s2-result-content"><pre style="font-size:11px;">' + escapeHtml(result.preview || '') + '</pre></div>';
    html += '<div class="s2-result-actions">';
    html += '<button class="btn btn--outline btn--sm" onclick="previewStep4File(\'' + escapeHtml(result.skill_filename) + '\',\'Agent Skill\')">预览/编辑 Markdown</button>';
    html += '<a class="btn btn--outline btn--sm" href="' + API_BASE + result.download_url + '" download>下载 SKILL.md</a>';
    html += '</div></div>';
    document.getElementById('s4-output-skill').style.display = 'block';
    document.getElementById('s4-output-skill').innerHTML = '<div class="s4-artifact-panel"><div class="panel-header"><span>可执行 Agent Skill</span><span style="font-weight:400;font-size:11px;color:var(--text-muted);">LLM 生成</span></div>' + html + '</div>';
    await markStepDone(4);
  } catch (e) {
    showToast('生成失败: ' + e.message, 'error');
  } finally {
    btn._locked = false; btn.disabled = false; btn.innerHTML = origHtml;
    btn.classList.remove('loading');
    refreshIcons();
  }
}



	async function previewStep4File(fileName, title) {
  if (!fileName) { alert('暂无可预览文件'); return; }
  try {
    let url = API_BASE + '/api/files/read?file_name=' + encodeURIComponent(fileName);
    if (currentPipeline?.id) url += '&pipeline_id=' + encodeURIComponent(currentPipeline.id);
    const resp = await fetch(url);
    const data = await resp.json();
    if (data.status === 'ok') {
      openMarkdownEditor(fileName, data.content);
      document.getElementById('markdown-editor-title').textContent = title || fileName;
    } else {
      alert('加载失败: ' + (data.error || '未知错误'));
    }
  } catch (e) {
    alert('加载失败: ' + e.message);
  }
}

function previewStep4Cot() {
  previewStep4File(currentPipeline?.step_data?.step4_cot_file, '思维链预览');
}
function previewStep4Qa() {
  const sd = currentPipeline?.step_data || {};
  previewStep4File(sd.step4_qa_md_file || sd.step4_qa_file, 'QA 对预览');
}
function previewStep4Skill() {
  previewStep4File(currentPipeline?.step_data?.step4_skill_file, 'Skill 预览');
}

async function step4Quality() {
  if (!currentPipeline) { alert('请先进入流水线'); return; }
  renderLoading('s4-output-freshness');
  document.getElementById('s4-output-freshness').style.display = 'block';
  try {
    const fd = new FormData();
    fd.append('pipeline_id', currentPipeline.id);
    const result = await apiCall('/api/step4/quality', fd);
    let html = '';
    if (result.overall_score !== undefined) {
      const grade = result.grade || '-';
      const gradeCls = grade === 'A' ? 'grade-a' : grade === 'B' ? 'grade-b' : grade === 'C' ? 'grade-c' : 'grade-d';

      html += '<div class="s4-compile-result">';
      html += '<div class="s4-compile-header">';
      html += '<div class="s4-compile-icon">&#11088;</div>';
      html += '<div class="s4-compile-title">质量报告</div>';
      html += '<div class="s4-compile-subtitle">五维度质量评估</div>';
      html += '</div>';

      html += '<div class="s4-stats-grid">';
      html += '<div class="s4-stat-card"><div class="s4-stat-value">' + result.overall_score + '</div><div class="s4-stat-label">综合评分</div></div>';
      html += '<div class="s4-stat-card"><div class="s4-stat-value"><span class="grade-badge ' + gradeCls + '">' + grade + '</span></div><div class="s4-stat-label">质量等级</div></div>';
      html += '</div>';

      if (result.dimensions) {
        html += '<div class="s4-section"><div class="s4-section-title">维度详情</div>';
        html += '<div class="s4-coverage-grid">';
        Object.entries(result.dimensions).forEach(([k, v]) => {
          const label = { completeness: '完整性', accuracy: '准确性', actionability: '可操作性', antipattern: '反模式覆盖', traceability: '来源可溯' }[k] || k;
          const pct = typeof v === 'object' ? (v.score || v.value || 0) : v;
          const cls = pct >= 80 ? 'green' : pct >= 60 ? 'orange' : 'red';
          html += '<div class="s4-coverage-item"><div class="s4-coverage-info"><div class="s4-coverage-label">' + label + '</div>';
          html += '<div class="s4-coverage-bar"><div class="s4-coverage-fill ' + cls + '" style="width:' + pct + '%"></div></div></div>';
          html += '<div class="s4-coverage-value">' + pct + '%</div></div>';
        });
        html += '</div></div>';
      }

      if (result.download_url) {
        html += '<div class="s4-actions">';
        html += '<a class="btn btn--primary btn--sm" href="' + API_BASE + result.download_url + '" download>&#11015; 下载质量报告</a>';
        html += '</div>';
      }
      html += '</div>';
    } else {
      html += '<pre style="font-size:12px;overflow:auto;max-height:300px">' + escapeHtml(JSON.stringify(result, null, 2)) + '</pre>';
    }
    document.getElementById('s4-output-freshness').innerHTML = '<div class="output-result">' + html + '</div>';
  } catch (e) {
    document.getElementById('s4-output-freshness').innerHTML = '<div class="error-list"><div class="error-item">' + escapeHtml(e.message) + '</div></div>';
  }
}

// Markdown Editor for SKILL.md
function openMarkdownEditor(fileName, content) {
  const modal = document.getElementById('markdown-editor-modal');
  if (!modal) return;
  modal.dataset.fileName = fileName;
  document.getElementById('markdown-editor-title').textContent = fileName;
  document.getElementById('markdown-editor-content').value = content;
  renderMarkdownPreview(content);
  modal.classList.add('active');
}

function closeMarkdownEditor() {
  const modal = document.getElementById('markdown-editor-modal');
  if (modal) modal.classList.remove('active');
}

function renderMarkdownPreview(content) {
  const preview = document.getElementById('markdown-preview');
  if (!preview) return;
  // Simple markdown rendering
  let html = escapeHtml(content);
  // Headers
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');
  // Bold
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  // Italic
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
  // Code blocks
  html = html.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
  // Inline code
  html = html.replace(/`(.+?)`/g, '<code>$1</code>');
  // Lists
  html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
  html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');
  // Line breaks
  html = html.replace(/\n\n/g, '</p><p>');
  html = html.replace(/\n/g, '<br>');
  html = '<p>' + html + '</p>';
  preview.innerHTML = html;
}

function onMarkdownEditorInput() {
  const content = document.getElementById('markdown-editor-content').value;
  renderMarkdownPreview(content);
}

function copyMarkdownContent() {
  const content = document.getElementById('markdown-editor-content').value;
  navigator.clipboard.writeText(content).then(() => {
    const btn = document.querySelector('.md-btn-copy');
    if (btn) {
      const orig = btn.innerHTML;
      btn.innerHTML = renderBtnChildren({ icon: 'check', text: '已复制' });
      refreshIcons();
      setTimeout(() => { btn.innerHTML = orig; refreshIcons(); }, 1500);
    }
  });
}

async function saveMarkdownContent() {
  const modal = document.getElementById('markdown-editor-modal');
  const fileName = modal?.dataset.fileName || document.getElementById('markdown-editor-title').textContent;
  const content = document.getElementById('markdown-editor-content').value;
  const saveBtn = document.getElementById('md-editor-save-btn');

  if (saveBtn) { saveBtn.disabled = true; saveBtn.innerHTML = renderBtnChildren({ icon: 'save', text: '保存中...' }); refreshIcons(); }

  try {
    const resp = await fetch(API_BASE + '/api/files/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_name: fileName, content: content })
    });
    const data = await resp.json();
    if (data.status === 'ok') {
      if (saveBtn) { saveBtn.innerHTML = renderBtnChildren({ icon: 'check', text: '已保存' }); refreshIcons(); }
      showToast('文件已保存');
      setTimeout(() => { if (saveBtn) { saveBtn.innerHTML = renderBtnChildren({ icon: 'save', text: '保存' }); refreshIcons(); } }, 2000);
    } else {
      alert('保存失败: ' + (data.error || '未知错误'));
      if (saveBtn) { saveBtn.innerHTML = renderBtnChildren({ icon: 'save', text: '保存' }); refreshIcons(); }
    }
  } catch (e) {
    alert('保存失败: ' + e.message);
    if (saveBtn) { saveBtn.innerHTML = renderBtnChildren({ icon: 'save', text: '保存' }); refreshIcons(); }
  } finally {
    if (saveBtn) saveBtn.disabled = false;
  }
}

function downloadMarkdownContent() {
  const fileName = document.getElementById('markdown-editor-title').textContent;
  const content = document.getElementById('markdown-editor-content').value;
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ═══════════════════════════════════════════════════════════════════
// Shared Validation Renderer
// ═══════════════════════════════════════════════════════════════════

// ═══════════════════════════════════════════════════════════════════
// Pipeline Management
// ═══════════════════════════════════════════════════════════════════

async function loadPipelineOverview() {
  const container = document.getElementById('pipeline-list-container');
  if (!container) return;

  container.innerHTML = '<div class="pipeline-overview"><div style="text-align:center;padding:40px"><div class="spinner"></div>加载中...</div></div>';

  try {
    const resp = await fetch(API_BASE + '/api/pipelines');
    const data = await resp.json();
    if (data.status !== 'ok') throw new Error(data.error || '加载失败');

    const pipelines = data.pipelines || [];

    let html = '<div class="pipeline-overview">';

    // Banner
    html += '<div class="overview-banner">';
    html += '<div class="overview-banner-inner">';
    html += '<div class="overview-banner-text">';
    html += '<div class="overview-banner-title">隐性知识显性化 · 五步法萃取流水线</div>';
    html += '<div class="overview-banner-desc">将领域专家的隐性经验系统性显性化为 AI 可加载的结构化知识，通过五步法流水线，从场景定义到智能转化，层层递进、步步可追溯。</div>';
    html += '</div>';
    html += '<button type="button" class="btn btn--light btn--lg" onclick="showNewPipelineForm()">';
    html += '<span class="btn__icon btn__icon--left" data-lucide="plus"></span>';
    html += '<span class="btn__text">新建流水线</span>';
    html += '</button>';
    html += '</div>';
    html += '</div>';

    // Steps Roadmap - vertical layout with timeline
    const stepCards = [
      { num: '01', title: '场景锚定', desc: '定义知识模板骨架，确定领域边界与字段规范，生成场景配置文件', icon: '&#9776;' },
      { num: '02', title: '知识萃取', desc: '从已有文档中提取知识条目，AI 辅助生成待审稿', icon: '&#9997;' },
      { num: '03', title: '知识对齐', desc: '融合修订与确认，完成专家意见对齐并生成最终可发布稿', icon: '&#10003;' },
      { num: '04', title: '智能转化', desc: '生成思维链、QA 对、OpenClaw Skill 三类交付物', icon: '&#9881;' },
      { num: '05', title: '验证回放', desc: '用 SKILL 终版判历史案例，分歧回流第3步形成闭环', icon: '&#9851;' },
    ];
    html += '<div class="overview-roadmap">';
    html += '<div class="roadmap-header"><span class="roadmap-header-line"></span><span class="roadmap-header-text">五步法流程概览</span><span class="roadmap-header-line"></span></div>';
    html += '<div class="roadmap-cards">';
    stepCards.forEach((s, i) => {
      html += '<div class="roadmap-step" data-step="' + s.num + '">';
      html += '<div class="roadmap-step-track">';
      html += '<div class="roadmap-step-node">' + s.icon + '</div>';
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
    html += '<div class="overview-history-count">共 ' + pipelines.length + ' 条</div>';
    html += '</div>';

    if (pipelines.length > 0) {
      html += '<div class="pipeline-list">';
      pipelines.forEach(p => {
        html += renderPipelineItem(p);
      });
      html += '</div>';
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
    html += '<div class="pipeline-progress-step ' + status + '" title="' + STEP_NAMES[i] + '"></div>';
  }
  html += '</div>';

  // Step mini labels
  html += '<div class="pipeline-step-badges">';
  for (let i = 1; i <= MAX_STEP; i++) {
    const status = ss[String(i)] || 'pending';
    const label = String(i).padStart(2, '0') + ' ' + STEP_NAMES[i];
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

// ═══════════════════════════════════════════════════════════════════
// Excel Online Editor
// ═══════════════════════════════════════════════════════════════════

let _excelEditorData = {
  sheets: {},
  file_path: '',
  active_sheet: '',
  step: 3,
  isRevision: false,
  modified: false
};

function openExcelEditor(step) {
  _excelEditorData.step = step;
  const modal = document.getElementById('excel-editor-modal');
  if (modal) modal.classList.add('active');
}

function closeExcelEditor() {
  if (typeof ExcelEditor !== 'undefined') ExcelEditor.destroy();
  const modal = document.getElementById('excel-editor-modal');
  if (modal) modal.classList.remove('active');
}

async function editStep2Preextract() {
  if (!currentPipeline) { alert('请先进入流水线'); return; }

  const fileName = currentPipeline.step_data?.step2_output_file;
  if (!fileName || !isStep2PreextractFile(fileName)) {
    alert('未找到有效的萃取 Excel（preextract_*.xlsx），请先执行知识萃取');
    return;
  }

  _excelEditorData.step = 2;
  renderExcelEditorLoading();

  try {
    const resp = await fetch(API_BASE + '/api/excel/read', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        file_name: fileName,
        pipeline_id: currentPipeline.id,
        step: 2,
      }),
    });
    const data = await resp.json();
    if (data.status === 'ok') {
      _excelEditorData.sheets = ExcelEditor.normalizeSheetsFromApi(data.sheets);
      _excelEditorData.file_path = data.file_path || fileName;
      _excelEditorData.active_sheet = Object.keys(_excelEditorData.sheets)[0] || '';
      _excelEditorData.modified = false;
      openExcelEditor(2);
      requestAnimationFrame(function () {
        requestAnimationFrame(function () { renderExcelEditorContent(); });
      });
    } else {
      alert('读取萃取 Excel 失败: ' + (data.error || '未知错误'));
    }
  } catch (e) {
    alert('加载萃取 Excel 出错: ' + e.message);
  }
}


function resolveStep3ExcelFile(stepData) {
  const sd = stepData || {};
  if (isStep4FinalFile(sd.step3_final_file)) {
    return {
      fileName: sd.step3_final_file,
      downloadUrl: sd.step3_final_download_url || ('/downloads/' + sd.step3_final_file),
      isRevision: true,
      editorStep: 4,
    };
  }
  if (isStep2PreextractFile(sd.step2_output_file)) {
    return {
      fileName: sd.step2_output_file,
      downloadUrl: sd.step2_download_url || ('/downloads/' + sd.step2_output_file),
      isRevision: false,
      editorStep: 2,
    };
  }
  return null;
}

async function editStep3Revision() {
  if (!currentPipeline) { alert('请先进入流水线'); return; }

  await refreshCurrentPipeline();
  const resolved = resolveStep3ExcelFile(currentPipeline.step_data);
  if (!resolved || !resolved.fileName) {
    alert('未找到可编辑的 Excel，请先完成知识萃取（Step2）');
    return;
  }

  // 直接打开已有文件（优先 final，fallback 到 preextract）
  _excelEditorData.step = resolved.editorStep || (resolved.isRevision ? 3 : 2);
  _excelEditorData.isRevision = !!resolved.isRevision;
  renderExcelEditorLoading();

  try {
    const resp = await fetch(API_BASE + '/api/excel/read', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        file_name: resolved.fileName,
        pipeline_id: currentPipeline.id,
        step: String(_excelEditorData.step),
      }),
    });
    const data = await resp.json();
    if (data.status === 'ok') {
      _excelEditorData.sheets = ExcelEditor.normalizeSheetsFromApi(data.sheets);
      _excelEditorData.file_path = data.file_path || resolved.fileName;
      _excelEditorData.active_sheet = Object.keys(_excelEditorData.sheets)[0] || '';
      _excelEditorData.modified = false;
      const stepLabel = document.getElementById('excel-editor-step-label');
      if (stepLabel) {
        stepLabel.textContent = resolved.isRevision ? '在线编辑：知识对齐稿' : '在线编辑：萃取底稿（执行后生成知识对齐稿）';
      }
      openExcelEditor(_excelEditorData.step);
      requestAnimationFrame(function () {
        requestAnimationFrame(function () { renderExcelEditorContent(); });
      });
    } else {
      alert('读取 Excel 失败: ' + (data.error || '未知错误'));
    }
  } catch (e) {
    alert('加载 Excel 出错: ' + e.message);
  }
}

async function loadExcelToEditor(fileInputId, step) {
  const fileInput = document.getElementById(fileInputId);
  if (!fileInput || !fileInput.files[0]) {
    alert('请先上传 Excel 文件');
    return;
  }

  _excelEditorData.step = step;
  renderExcelEditorLoading();

  const fd = new FormData();
  fd.append('excel', fileInput.files[0]);
  if (currentPipeline) fd.append('pipeline_id', currentPipeline.id);
  fd.append('step', String(step));

  try {
    const resp = await fetch(API_BASE + '/api/excel/read', { method: 'POST', body: fd });
    const data = await resp.json();
    if (data.status === 'ok') {
      _excelEditorData.sheets = ExcelEditor.normalizeSheetsFromApi(data.sheets);
      _excelEditorData.file_path = data.file_path;
      _excelEditorData.active_sheet = Object.keys(_excelEditorData.sheets)[0] || '';
      _excelEditorData.modified = false;
      openExcelEditor(step);
      requestAnimationFrame(function () {
        requestAnimationFrame(function () { renderExcelEditorContent(); });
      });
    } else {
      alert(data.error || '读取 Excel 失败');
    }
  } catch (e) {
    alert('读取失败: ' + e.message);
  }
}

function renderExcelEditorLoading() {
  const modal = document.getElementById('excel-editor-modal');
  if (!modal) return;
  modal.classList.add('active');
  const content = document.getElementById('excel-editor-content');
  if (content) content.innerHTML = '<div class="excel-editor-loading">正在加载 Excel 数据...</div>';
}

function renderExcelEditorContent() {
  const content = document.getElementById('excel-editor-content');
  if (!content) return;

  content.innerHTML =
    '<div class="excel-luckysheet-wrap">' +
    '<div id="excel-luckysheet-mount" class="excel-luckysheet-mount"></div>' +
    '<div class="excel-status-bar">' +
    '<span id="excel-modified-indicator" style="display:none" class="modified-dot"></span>' +
    '<span id="excel-modified-text">未修改</span>' +
    '</div></div>';

  const mountEl = document.getElementById('excel-luckysheet-mount');
  if (mountEl && typeof ExcelEditor !== 'undefined') {
    ExcelEditor.mount(mountEl, _excelEditorData.sheets, _excelEditorData.active_sheet).catch(function (e) {
      console.error('ExcelEditor.mount failed:', e);
      mountEl.innerHTML = '<div class="excel-editor-loading">表格编辑器加载异常：' + escapeHtml(e.message || String(e)) + '</div>';
    });
  }
}

function syncExcelDataFromDOM() {
  if (typeof ExcelEditor === 'undefined') return;
  const synced = ExcelEditor.syncBeforeSave(_excelEditorData.sheets);
  if (synced) _excelEditorData.sheets = synced;
}

function markExcelModified() {
  _excelEditorData.modified = true;
  const indicator = document.getElementById('excel-modified-indicator');
  const text = document.getElementById('excel-modified-text');
  if (indicator) indicator.style.display = 'inline-block';
  if (text) text.textContent = '已修改（未保存）';
}

async function saveExcelEditor() {
  syncExcelDataFromDOM();

  if (!_excelEditorData.file_path) {
    alert('无源文件路径，请重新上传');
    return;
  }

  const saveBtn = document.getElementById('excel-editor-save-btn');
  const saveBtnText = saveBtn ? saveBtn.querySelector('.btn__text') : null;
  if (saveBtn) { saveBtn.disabled = true; }
  if (saveBtnText) { saveBtnText.textContent = '保存中...'; }

  try {
    const resp = await fetch(API_BASE + '/api/excel/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        file_path: _excelEditorData.file_path,
        sheets: _excelEditorData.sheets,
        pipeline_id: currentPipeline ? currentPipeline.id : '',
        step: String(_excelEditorData.step)
      })
    });
    const data = await resp.json();

    if (data.status === 'ok') {
      _excelEditorData.modified = false;
      _excelEditorData.file_path = data.file_path;

      const indicator = document.getElementById('excel-modified-indicator');
      const text = document.getElementById('excel-modified-text');
      if (indicator) indicator.style.display = 'none';
      if (text) text.textContent = '已保存';

      const step = _excelEditorData.step;
      if (String(step) === '1' && currentPipeline && data.file_path) {
        const base = data.file_path.replace(/^.*[\\/]/, '');
        applyStep1GenerateResult({
          file_name: base,
          download_url: data.download_url || ('/downloads/' + base),
        });
        persistPipeline({
          step1_output_file: base,
          step1_download_url: data.download_url || ('/downloads/' + base),
        }).catch(e => { console.error('Link step1 output failed:', e); showToast('Excel 已保存，但流水线同步失败', 'error'); });
        if (currentStep === 2) loadStep2PrevOutput();
      }

      if (String(step) === '2' && currentPipeline && data.file_path) {
        const base = data.file_path.replace(/^.*[\\/]/, '');
        if (isStep2PreextractFile(base)) {
          currentPipeline.step_data.step2_output_file = base;
          currentPipeline.step_data.step2_download_url = data.download_url || ('/downloads/' + base);
          persistPipeline({
            step2_output_file: base,
            step2_download_url: currentPipeline.step_data.step2_download_url,
          }).catch(function (e) { console.error('Link step2 output failed:', e); });
        }
      }

      if (String(step) === '3' && currentPipeline && data.file_path && _excelEditorData.isRevision) {
        const base = data.file_path.replace(/^.*[\\/]/, '');
        if (isStep3RevisionFile(base)) {
          currentPipeline.step_data.step3_revision_file = base;
          currentPipeline.step_data.step3_download_url = data.download_url || ('/downloads/' + base);
          persistPipeline({
            step3_revision_file: base,
            step3_download_url: currentPipeline.step_data.step3_download_url,
          }).catch(function (e) { console.error('Link step3 output failed:', e); });
        }
      }
      if (String(step) === '4' && currentPipeline && data.file_path) {
        const base = data.file_path.replace(/^.*[\\/]/, '');
        const snapUrl = data.download_url || '';
        if (isStep4FinalFile(base)) {
          currentPipeline.step_data.step3_final_file = base;
          currentPipeline.step_data.step3_final_download_url = snapUrl || ('/downloads/' + base);
          persistPipeline({
            step3_final_file: base,
            step3_final_download_url: currentPipeline.step_data.step3_final_download_url,
          }).catch(function (e) { console.error('Link step3 final output failed:', e); });
        } else if (isStep3RevisionFile(base) || _excelEditorData.isRevision) {
          currentPipeline.step_data.step3_revision_file = base;
          currentPipeline.step_data.step3_download_url = snapUrl || ('/downloads/' + base);
          persistPipeline({
            step3_revision_file: base,
            step3_download_url: currentPipeline.step_data.step3_download_url,
          }).catch(function (e) { console.error('Link step3 revision from step3 editor failed:', e); });
        }
      }


      const outputId = 's' + step + '-output';
      const outputEl = document.getElementById(outputId);
      if (outputEl && data.download_url) {
        let existing = outputEl.querySelector('.excel-download-link');
        if (!existing) {
          const label = step === 3 ? '修订稿' : step === 4 ? '最终稿' : step === 1 ? '场景骨架' : 'Excel';
          const div = document.createElement('div');
          div.className = 'excel-download-link';
          div.innerHTML = '<span class="download-icon">📥</span> <a href="' + escapeHtml(API_BASE + data.download_url) + '" download>下载' + label + ' Excel</a>';
          outputEl.appendChild(div);
        }
      }
    } else {
      alert(data.error || '保存失败');
    }
  } catch (e) {
    alert('保存失败: ' + e.message);
  } finally {
    if (saveBtn) { saveBtn.disabled = false; }
    if (saveBtnText) { saveBtnText.textContent = '保存'; }
  }
}

// ── 委托公共函数到 utils.js / state.js 模块 ──
;(function() {
  var A = window.App;
  if (!A) return;
  // 工具函数委托（utils.js 在 app.js 之前加载）
  if (A.escapeHtml)    { escapeHtml = A.escapeHtml; showToast = A.showToast; copyTextToClipboard = A.copyTextToClipboard; }
  if (A.qualityBar)    { qualityBar = A.qualityBar; statRow = A.statRow; }
  if (A.apiCall)       { apiCall = A.apiCall; apiCallJSON = A.apiCallJSON; withButtonLock = A.withButtonLock; }
  if (A.renderOutput)  { renderOutput = A.renderOutput; renderLoading = A.renderLoading; }
  // 状态管理器委托
  if (A.PipelineState) {
    // scheduleFormSave 委托到 PipelineState（防抖已改为 2 秒）
    var _origScheduleFormSave = scheduleFormSave;
    scheduleFormSave = function(step) { A.PipelineState.scheduleFormSave(step, collectAllStepsFormData); };
    // persistPipeline 委托
    persistPipeline = function(extraStepData, extraFields) { return A.PipelineState.persist(extraStepData, extraFields); };
  }
})();

// ═══════════════════════════════════════════════════════════════════
// 方案四: 显性化校验回放
// ═══════════════════════════════════════════════════════════════════

function openValidatePanel() {
  var panel = document.getElementById('s4-validate-panel');
  panel.classList.toggle('hidden');
  if (!panel.classList.contains('hidden')) {
    if (allModels.length) refreshModelSelects();
  }
}

async function runValidateReplay() {
  var btn = document.getElementById('s4-validate-run-btn');
  var resultEl = document.getElementById('s4-validate-result');
  var text = document.getElementById('s4-validate-cases').value.trim();
  if (!text) { showToast('请输入历史案例', 'error'); return; }
  if (!currentPipeline) { showToast('请先进入一条流水线', 'error'); return; }

  // 解析案例文本
  var lines = text.split('\n').filter(function (l) { return l.trim(); });
  var cases = [];
  lines.forEach(function (line) {
    var parts = line.split(/[,，]/);
    if (parts.length >= 3) {
      cases.push({
        case_id: parts[0].trim(),
        description: parts[1].trim(),
        conclusion: parts[2].trim(),
      });
    }
  });
  if (cases.length === 0) { showToast('案例格式错误，每行为: 案例ID,场景描述,专家结论', 'error'); return; }

  var model = document.getElementById('s4-validate-model')?.value || resolveModelName('s4-model');
  if (!model) { showToast('请选择模型', 'error'); return; }

  btn.disabled = true;
  btn.innerHTML = '<span class="btn__icon btn__icon--left" data-lucide="loader-2"></span><span class="btn__text">校验中...</span>';
  resultEl.innerHTML = '<div class="loading"><div class="spinner"></div>正在用知识库判断 ' + cases.length + ' 个案例...</div>';

  try {
    var fd = new FormData();
    fd.append('pipeline_id', currentPipeline.id);
    fd.append('model', model);
    fd.append('cases', JSON.stringify(cases));
    var resp = await fetch(API_BASE + '/api/validate/replay', { method: 'POST', body: fd });
    var data = await resp.json();
    if (data.status === 'ok') {
      var pct = Math.round(data.hit_rate * 100);
      var fillColor = pct >= 80 ? '#16a34a' : pct >= 60 ? '#f59e0b' : '#ef4444';
      var html = '<div class="validate-result">';
      html += '<h4>校验结果</h4>';
      html += '<div style="font-size:24px;font-weight:700;color:' + fillColor + '">' + pct + '% 命中率</div>';
      html += '<div style="font-size:12px;color:var(--text-muted)">' + data.hits + '/' + data.total + ' 一致 · ' + data.mismatch_count + ' 分歧</div>';
      html += '<div class="validate-hit-bar"><div class="validate-hit-fill" style="width:' + pct + '%;background:' + fillColor + '"></div></div>';
      if (data.mismatches && data.mismatches.length) {
        html += '<h4 style="margin-top:12px;">分歧案例</h4>';
        data.mismatches.forEach(function (m) {
          html += '<div class="validate-mismatch"><strong>' + escapeHtml(m.case_id) + '</strong>: LLM判「' + escapeHtml(m.prediction) + '」→ 专家判「' + escapeHtml(m.expert_conclusion) + '」<br><span style="color:var(--text-muted);font-size:11px">推理: ' + escapeHtml((m.reasoning || '').substring(0, 120)) + '</span></div>';
        });
        html += '<div class="file-hint" style="margin-top:8px">💡 这些分歧条目可反推为 Step3 修订建议来源</div>';
      }
      html += '</div>';
      resultEl.innerHTML = html;
    } else {
      resultEl.innerHTML = '<div style="color:var(--error);font-size:12px;margin-top:8px">' + escapeHtml(data.error || '校验失败') + '</div>';
    }
  } catch (e) {
    resultEl.innerHTML = '<div style="color:var(--error);font-size:12px;margin-top:8px">网络错误: ' + escapeHtml(e.message) + '</div>';
  }
  btn.disabled = false;
  btn.innerHTML = '<span class="btn__icon btn__icon--left" data-lucide="zap"></span><span class="btn__text">执行校验</span>';
  refreshIcons();
}

/* ===== Step4: 一键编译交付包（确定性主路径）===== */
async function step4Compile() {
  if (!currentPipeline) { showToast('请先进入一条流水线', 'error'); return; }
  var btn = document.getElementById('s4-compile-btn');
  var panel = document.getElementById('s4-output-compile');
  if (btn) { btn.disabled = true; btn.classList.add('loading'); }
  if (panel) { panel.style.display = 'block'; panel.innerHTML = '<div class="loading"><div class="spinner"></div>正在确定性编译交付包...</div>'; }
  try {
    var fd = new FormData();
    fd.append('pipeline_id', currentPipeline.id);
    fd.append('formats', 'skill,cot,qa');
    var resp = await fetch(API_BASE + '/api/step4/compile', { method: 'POST', body: fd });
    var data = await resp.json();
    if (data.status !== 'ok') {
      if (panel) panel.innerHTML = '<div class="error-list"><div class="error-item">' + escapeHtml(data.error || '编译失败') + '</div></div>';
      showToast(data.error || '编译失败', 'error');
      return;
    }
    if (currentPipeline) {
      currentPipeline.step_data = currentPipeline.step_data || {};
      if (data.download_name) { currentPipeline.step_data.step4_skill_file = data.download_name; currentPipeline.step_data.step4_download_url = data.download_url; }
      if (data.cot_download_name) { currentPipeline.step_data.step4_cot_file = data.cot_download_name; currentPipeline.step_data.step4_cot_download_url = data.cot_download_url; }
      if (data.qa_download_name) { currentPipeline.step_data.step4_qa_file = data.qa_download_name; currentPipeline.step_data.step4_qa_download_url = data.qa_download_url; }
    }
    var html = '<div class="s4-compile-result">';
    html += '<div class="s4-compile-header"><div class="s4-compile-icon">&#127919;</div><div class="s4-compile-title">交付包编译完成</div>';
    html += '<div class="s4-compile-subtitle">' + (data.input_kind === 'ir' ? ('输入：Skill 草稿 v' + (data.ir_version || '?') + '（IR）') : '输入：Excel 对齐稿（过渡兼容）') + ' · 共 ' + (data.knowledge_count || 0) + ' 条知识</div></div>';
    if (typeof data.quality_score === 'number') {
      var qColor = data.can_publish ? '#16a34a' : '#f59e0b';
      html += '<div style="margin:8px 0;font-size:13px;">质量分 <strong style="color:' + qColor + '">' + data.quality_score + '</strong> / 100（' + escapeHtml(data.quality_grade || '') + '级，发布门槛 ' + (data.publish_threshold || 75) + '）';
      html += data.can_publish ? ' · <span style="color:#16a34a">可发布到知识库</span>' : ' · <span style="color:#f59e0b">未达发布门槛</span>';
      html += '</div>';
    }
    html += '<div class="s2-result-actions" style="margin-top:8px;">';
    if (data.download_url) html += '<a class="btn btn--primary btn--sm" href="' + API_BASE + data.download_url + '" download>下载 SKILL.md 终版</a>';
    if (data.cot_download_url) html += '<a class="btn btn--outline btn--sm" href="' + API_BASE + data.cot_download_url + '" download>下载思维链</a>';
    if (data.qa_download_url) html += '<a class="btn btn--outline btn--sm" href="' + API_BASE + data.qa_download_url + '" download>下载 QA 对</a>';
    if (data.openclaw_manifest_url) html += '<a class="btn btn--outline btn--sm" href="' + API_BASE + data.openclaw_manifest_url + '" download>下载 manifest</a>';
    if (data.can_publish) html += '<button class="btn btn--primary btn--sm" onclick="step4PublishToKb()">发布到知识库</button>';
    html += '</div></div>';
    if (panel) panel.innerHTML = html;
    // 同步点亮右侧 Skill/COT/QA 面板，与后端产物一一对应
    restoreStep4Output();
    showToast('交付包编译完成');
    try { await markStepDone(4); } catch (e) { /* ignore */ }
  } catch (e) {
    if (panel) panel.innerHTML = '<div class="error-list"><div class="error-item">' + escapeHtml(e.message) + '</div></div>';
    showToast('编译失败: ' + e.message, 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.classList.remove('loading'); }
  }
}

async function step4PublishToKb() {
  if (!currentPipeline) return;
  try {
    var result = await apiCallJSON('/api/kb/publish', { pipeline_id: currentPipeline.id });
    if (result.status !== 'ok') { showToast(result.error || '发布失败', 'error'); return; }
    showToast('已发布到知识库：新增 ' + (result.created || 0) + ' 条 · 更新 ' + (result.superseded || 0) + ' 条');
  } catch (e) {
    showToast('发布失败: ' + e.message, 'error');
  }
}

/* ===== Step5: 验证回放与回流 ===== */
var _s5LastSuggestions = [];

function step5OnCaseSourceChange() {
  var src = document.getElementById('s5-case-source')?.value || 'upload';
  var up = document.getElementById('s5-upload-area');
  var kb = document.getElementById('s5-kb-area');
  if (up) up.style.display = src === 'upload' ? '' : 'none';
  if (kb) kb.style.display = src === 'kb' ? '' : 'none';
}

function loadStep5Context() {
  var infoEl = document.getElementById('s5-target-info');
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

async function step5RunReplay() {
  if (!currentPipeline) { showToast('请先进入一条流水线', 'error'); return; }
  var btn = document.getElementById('s5-replay-btn');
  var outEl = document.getElementById('s5-output');
  var model = resolveModelName('s5-model');
  if (!model) { showToast('请先配置并选择判官模型', 'error'); return; }
  var caseSource = document.getElementById('s5-case-source')?.value || 'upload';

  var fd = new FormData();
  fd.append('pipeline_id', currentPipeline.id);
  fd.append('judge_model', model);
  fd.append('case_source', caseSource);

  if (caseSource === 'kb') {
    fd.append('kb_domain', currentPipeline.domain || '');
    fd.append('kb_scenario', currentPipeline.scenario || '');
    fd.append('kb_difficulty', document.getElementById('s5-kb-difficulty')?.value || '');
  } else {
    var casesText = document.getElementById('s5-cases-text')?.value.trim() || '';
    var casesFile = document.getElementById('s5-cases-file');
    if (casesText) {
      try { JSON.parse(casesText); } catch (e) { showToast('案例 JSON 格式错误: ' + e.message, 'error'); return; }
      fd.append('cases', casesText);
    } else if (casesFile && casesFile.files.length > 0) {
      fd.append('cases_file', casesFile.files[0]);
    } else {
      showToast('请输入案例 JSON 或上传案例文件', 'error');
      return;
    }
  }

  if (btn) { btn.disabled = true; btn.classList.add('loading'); }
  renderLoading('s5-output');
  try {
    var resp = await fetch(API_BASE + '/api/step5/replay', { method: 'POST', body: fd });
    var data = await resp.json();
    if (data.status !== 'ok') {
      renderOutput('s5-output', '<div class="error-list"><div class="error-item">' + escapeHtml(data.error || '回放失败') + '</div></div>');
      showToast(data.error || '回放失败', 'error');
      return;
    }
    _s5LastSuggestions = data.suggestions || [];
    if (currentPipeline) {
      currentPipeline.step_data = currentPipeline.step_data || {};
      currentPipeline.step_data.step5_hit_rate = data.hit_rate;
      currentPipeline.step_data.step5_run_id = data.run_id;
      currentPipeline.step_data.step5_replay_file = data.report_name || '';
      currentPipeline.step_data.step5_replay_url = data.download_url || '';
      if (data.suggestions_url) currentPipeline.step_data.step5_suggestions_url = data.suggestions_url;
    }
    var pct = Math.round(data.hit_rate * 100);
    var fillColor = data.passed ? '#16a34a' : (pct >= 60 ? '#f59e0b' : '#ef4444');
    var srcNames = { skill_final: 'SKILL 终版', step3_aligned_file: '对齐稿 IR 渲染', step2_draft_file: '萃取稿 IR 渲染', excel: 'Excel 知识文本（过渡）' };
    var html = '<div class="validate-result">';
    html += '<h4>决策回放结果 <span style="font-weight:400;font-size:11px;color:var(--text-muted)">（验证对象：' + escapeHtml(srcNames[data.knowledge_source] || data.knowledge_source) + ' · 判官：' + escapeHtml(data.judge_model || '') + '）</span></h4>';
    html += '<div style="font-size:24px;font-weight:700;color:' + fillColor + '">' + pct + '% 命中率 ' + (data.passed ? '✅ 达标' : '⚠️ 未达门槛 ' + Math.round((data.hit_threshold || 0.8) * 100) + '%') + '</div>';
    html += '<div style="font-size:12px;color:var(--text-muted)">' + data.hits + '/' + data.total + ' 一致 · ' + data.mismatch_count + ' 分歧</div>';
    html += '<div class="validate-hit-bar"><div class="validate-hit-fill" style="width:' + pct + '%;background:' + fillColor + '"></div></div>';
    if (data.download_url) html += '<div style="margin-top:6px;"><a href="' + API_BASE + data.download_url + '" target="_blank">查看完整回放报告</a></div>';
    if (data.mismatches && data.mismatches.length) {
      html += '<h4 style="margin-top:12px;">分歧案例</h4>';
      data.mismatches.slice(0, 8).forEach(function (m) {
        html += '<div class="validate-mismatch"><strong>' + escapeHtml(m.case_id) + '</strong>: Skill判「' + escapeHtml(m.prediction) + '」→ 专家判「' + escapeHtml(m.expert_conclusion) + '」';
        if (m.referenced_rules && m.referenced_rules.length) html += '<br><span style="color:var(--text-muted);font-size:11px">引用规则: ' + escapeHtml(m.referenced_rules.join(', ')) + '</span>';
        html += '</div>';
      });
    }
    if (_s5LastSuggestions.length) {
      html += '<h4 style="margin-top:12px;">回流建议（' + _s5LastSuggestions.length + ' 条）</h4>';
      _s5LastSuggestions.forEach(function (s) {
        html += '<div class="validate-mismatch" style="border-left:3px solid #6366f1;">';
        html += '<strong>' + escapeHtml(s.entry_id || '新增条目') + '</strong>' + (s.field ? ' / ' + escapeHtml(s.field) : '') + ' · ' + escapeHtml(s.action || '');
        if (s.new_value) html += '<br><span style="font-size:11px;">' + escapeHtml(String(s.new_value).slice(0, 160)) + '</span>';
        html += '</div>';
      });
      html += '<button type="button" class="btn btn--outline btn--md" style="margin-top:10px;" onclick="step5PushFeedback()">'
        + '<span class="btn__icon btn__icon--left" data-lucide="refresh-cw"></span>'
        + '<span class="btn__text">回流到知识对齐（建议池）</span></button>';
      html += '<div class="file-hint" style="margin-top:4px;">建议不会自动应用——回流后请到第 3 步建议池逐条裁决</div>';
    } else if (data.mismatch_count === 0) {
      html += '<div style="margin-top:10px;color:#16a34a;">所有案例判断与专家结论一致，无需回流。</div>';
    }
    html += '</div>';
    renderOutput('s5-output', html);
    refreshIcons();
    loadStep5Context();
    try { await markStepDone(5); } catch (e) { /* ignore */ }
  } catch (e) {
    renderOutput('s5-output', '<div class="error-list"><div class="error-item">' + escapeHtml(e.message) + '</div></div>');
    showToast('回放失败: ' + e.message, 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.classList.remove('loading'); }
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

async function step5GoldenVerify() {
  if (!currentPipeline) { showToast('请先进入一条流水线', 'error'); return; }
  var btn = document.getElementById('s5-golden-btn');
  if (btn) btn.disabled = true;
  renderLoading('s5-output');
  try {
    var result = await apiCallJSON('/api/step5/golden_verify', { pipeline_id: currentPipeline.id });
    if (result.status === 'error') {
      renderOutput('s5-output', '<div class="error-list"><div class="error-item">' + escapeHtml(result.error || result.message || 'Golden 验证失败') + '</div></div>');
      return;
    }
    var html = '<div class="validate-result"><h4>Golden 基准验证</h4>';
    var metrics = result.metrics || result;
    ['precision', 'recall', 'f1'].forEach(function (k) {
      if (metrics[k] != null) html += '<div style="font-size:13px;">' + k.toUpperCase() + '：<strong>' + (Math.round(metrics[k] * 1000) / 10) + '%</strong></div>';
    });
    if (result.matched_count != null) html += '<div style="font-size:12px;color:var(--text-muted);margin-top:4px;">匹配 ' + result.matched_count + ' / 黄金 ' + (result.golden_total || '?') + ' · 流水线 ' + (result.pipeline_total || '?') + ' 条</div>';
    if (result.download_url) html += '<div style="margin-top:8px;"><a href="' + API_BASE + result.download_url + '" target="_blank">查看完整报告</a></div>';
    html += '</div>';
    renderOutput('s5-output', html);
  } catch (e) {
    renderOutput('s5-output', '<div class="error-list"><div class="error-item">' + escapeHtml(e.message) + '</div></div>');
  } finally {
    if (btn) btn.disabled = false;
  }
}

/* ===== Step2 IR v2 rendering helpers ===== */
function getCurrentPipelineId() {
  if (!currentPipeline || !currentPipeline.id) {
    console.error('No current pipeline available');
    return null;
  }
  return currentPipeline.id;
}

function getSelectedModel() {
  return resolveModelName('s2-model');
}

function switchStep2Tab(tab) {
  document.querySelectorAll('#s2-output .s2-tab').forEach(function (el) { el.classList.remove('active'); });
  document.querySelectorAll('#s2-output .s2-tab-panel').forEach(function (el) { el.style.display = 'none'; });
  var tabBtn = document.querySelector('#s2-output .s2-tab[data-tab="' + tab + '"]');
  if (tabBtn) tabBtn.classList.add('active');
  var panel = document.getElementById('s2-ir-' + tab);
  if (panel) panel.style.display = 'block';
}

function renderStep2IR(ir) {
  window.currentStep2IR = ir;
  document.getElementById('s2-ir-tree').innerHTML = renderIRTree(ir);
  var mdHtml;
  if (typeof marked !== 'undefined' && typeof marked.parse === 'function') {
    mdHtml = marked.parse(renderIRMarkdown(ir));
  } else {
    mdHtml = renderIRMarkdown(ir).replace(/\n/g, '<br>');
  }
  document.getElementById('s2-ir-markdown').innerHTML = mdHtml;
  document.getElementById('s2-ir-table').innerHTML = renderIRTable(ir);
  document.getElementById('s2-generate-sql').disabled = ir && ir.skill_meta && ir.skill_meta.draft_version >= 2;
}

function renderIRTree(ir) {
  var entries = ir.entries || [];
  var html = '<ul class="ir-tree">';
  entries.forEach(function (e) {
    html += '<li><strong>' + escapeHtml(e.entry_id) + '</strong> [' + escapeHtml(e.step_phase) + '] ' + escapeHtml(e.fields.knowledge_desc) + '</li>';
  });
  html += '</ul>';
  return html;
}

function renderIRMarkdown(ir) {
  var md = '# ' + (ir.anchors && ir.anchors.scenario ? ir.anchors.scenario : 'Skill IR') + '\n\n';
  (ir.entries || []).forEach(function (e) {
    md += '## ' + e.entry_id + ' | ' + e.sub_scenario + ' | ' + e.step_phase + '\n';
    md += '- 业务描述：' + (e.fields.knowledge_desc || '') + '\n';
    md += '- 规则：' + (e.fields.rule_ref || '') + '\n';
    md += '- SQL：```sql\n' + ((e.fields.data_logic || {}).sql || '待生成') + '\n```\n\n';
  });
  return md;
}

function renderIRTable(ir) {
  var html = '<table class="ir-table"><thead><tr><th>编号</th><th>子场景</th><th>阶段</th><th>业务描述</th><th>规则</th><th>SQL</th></tr></thead><tbody>';
  (ir.entries || []).forEach(function (e) {
    var sql = (e.fields.data_logic || {}).sql || '待生成';
    html += '<tr><td>' + escapeHtml(e.entry_id) + '</td><td>' + escapeHtml(e.sub_scenario) + '</td><td>' + escapeHtml(e.step_phase) + '</td><td>' + escapeHtml(e.fields.knowledge_desc) + '</td><td>' + escapeHtml(e.fields.rule_ref) + '</td><td><code>' + escapeHtml(sql) + '</code></td></tr>';
  });
  html += '</tbody></table>';
  return html;
}

function step2ExtractRules() {
  var pipelineId = getCurrentPipelineId();
  if (!pipelineId) { showToast('请先进入一条流水线', 'error'); return; }
  var model = getSelectedModel();
  if (!model) { showToast('请先选择模型', 'error'); return; }

  var formData = new FormData();
  formData.append('pipeline_id', pipelineId);
  formData.append('model', model);
  var files = document.getElementById('s2-source-files').files;
  for (var i = 0; i < files.length; i++) formData.append('files', files[i]);

  fetch(API_BASE + '/api/step2/extract_rules', { method: 'POST', body: formData })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (data.status === 'ok') {
        renderStep2IR(data.ir);
        document.getElementById('s2-generate-sql').disabled = false;
      } else {
        alert(data.error || '生成规则失败');
      }
    })
    .catch(function (e) {
      console.error('step2ExtractRules failed:', e);
      alert('网络错误: ' + e.message);
    });
}

function step2GenerateSQL() {
  var pipelineId = getCurrentPipelineId();
  if (!pipelineId) { showToast('请先进入一条流水线', 'error'); return; }
  var model = getSelectedModel();
  if (!model) { showToast('请先选择模型', 'error'); return; }

  var formData = new FormData();
  formData.append('pipeline_id', pipelineId);
  formData.append('model', model);

  fetch(API_BASE + '/api/step2/extract_sql', { method: 'POST', body: formData })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (data.status === 'ok') {
        renderStep2IR(data.ir);
      } else {
        alert(data.error || '生成取数逻辑失败');
      }
    })
    .catch(function (e) {
      console.error('step2GenerateSQL failed:', e);
      alert('网络错误: ' + e.message);
    });
}

function downloadCurrentIR() {
  var ir = window.currentStep2IR;
  if (!ir) {
    alert('没有可下载的 IR');
    return;
  }
  var blob = new Blob([JSON.stringify(ir, null, 2)], { type: 'application/json' });
  var url = URL.createObjectURL(blob);
  var a = document.createElement('a');
  a.href = url;
  a.download = 'skill_ir_v2.json';
  a.click();
  URL.revokeObjectURL(url);
}

// Load pipeline overview on startup
loadPipelineOverview();

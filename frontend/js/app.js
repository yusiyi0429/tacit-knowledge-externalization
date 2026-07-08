/* ===== State ===== */
let currentStep = 0;
const API_BASE = window.location.origin;
let allModels = [];
let currentPipeline = null; // { id, name, scenario, domain, current_step, step_status, step_data }
const MAX_STEP = 5;
const MAX_FORM_STEP = 3;
const STEP_NAME_KEYS = { 1: 'step1_name', 2: 'step2_name', 3: 'step3_name', 4: 'step4_name', 5: 'step5_name' };
function getStepName(i) { return App.I18n.t(STEP_NAME_KEYS[i] || ''); }
let _formSaveTimer = null;
let _lastStep2ExtractedText = '';
let _step2ActiveSkill = 'knowledge-extraction'; // 当前选中的 Skill
let _alignTacitAnnotations = {}; // { noteId: { question, answer } } — Step3 修订经验批注缓存
var _s1SubScenarioCount = 0; // Step1 子场景计数器（需在 step1.js 之前声明为全局）

/* ===== i18n shortcut ===== */
const t = function (key, fallback) { return App.I18n.t(key, fallback); };

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
  'step5_suggestions_file', 'step5_suggestions_url', 'step5_report_file', 'step5_report_url',
  'step5_precision', 'step5_recall', 'step5_f1',
  'step5_hit_rate', 'step5_case_source', 'step5_run_id',
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
  'step5_suggestions_file', 'step5_suggestions_url', 'step5_report_file', 'step5_report_url',
  'step5_precision', 'step5_recall', 'step5_f1',
  'step5_hit_rate', 'step5_case_source', 'step5_run_id',
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

const DEFAULT_KNOWLEDGE_COLUMN_MAP = {
  "环节": "Stage",
  "访谈方向": "Interview Direction",
  "具体方法": "Specific Method",
  "知识类型": "Knowledge Type",
  "知识引用": "Knowledge Reference",
  "适用条件": "Applicable Conditions",
  "判断逻辑": "Decision Logic",
  "反模式/踩坑提示": "Anti-pattern / Pitfall Tips",
  "经验判断": "Experiential Judgment",
  "适用边界": "Applicable Boundary",
  "例外情形": "Exceptions",
  "来源文档": "Source Document",
  "来源位置": "Source Location",
  "置信度": "Confidence",
  "贡献专家": "Contributing Expert",
  "证据数": "Evidence Count",
  "突破数": "Exception Count",
  "知识描述": "Knowledge Description"
};
const REVERSE_KNOWLEDGE_COLUMN_MAP = Object.fromEntries(
  Object.entries(DEFAULT_KNOWLEDGE_COLUMN_MAP).map(([k, v]) => [v, k])
);

function localizeKnowledgeColumn(name, lang) {
  if (!name) return name;
  lang = lang || (typeof App !== 'undefined' && App.I18n ? App.I18n.getLang() : 'zh-CN');
  if (lang === 'en') return DEFAULT_KNOWLEDGE_COLUMN_MAP[name] || name;
  return REVERSE_KNOWLEDGE_COLUMN_MAP[name] || name;
}

function localizeKnowledgeColumns(columns, lang) {
  return (columns || []).map(c => localizeKnowledgeColumn(c, lang));
}

function step1SyncKnowledgeColumnLanguage(lang) {
  document.querySelectorAll('.s1-k-col-input').forEach(function (el) {
    const v = el.value.trim();
    if (!v) return;
    const localized = localizeKnowledgeColumn(v, lang);
    if (localized !== v) el.value = localized;
  });
}

function step1IsAbstractColumn(name) {
  const s = String(name || '').trim();
  if (!s) return true;
  return /^(列[a-zA-Z0-9]{1,3}|(column|field|字段)\s*\d+|[a-zA-Z]\d?)$/i.test(s);
}

function step1MergeRichColumnsForMarkdown() {
  const rich = localizeKnowledgeColumns(_s1RichMarkdownColumns.length ? _s1RichMarkdownColumns : _s1DefaultKnowledgeColumns);
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
    '<input type="text" class="s1-k-col-input" placeholder="' + t('placeholder_knowledge_column', '如：具体方法、判断逻辑') + '" value="' + escapeHtml(name || '') + '">' +
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
    if (!v) return;
    // 默认列名在英文界面显示为英文，但保存时仍按中文原名存储，保证后端兼容
    cols.push(localizeKnowledgeColumn(v, 'zh-CN'));
  });
  return cols;
}

function step1RenderKnowledgeColumns(columns) {
  const container = document.getElementById('s1-knowledge-columns');
  if (!container) return;
  container.innerHTML = '';
  _s1KnowledgeColumnSeq = 0;
  const list = (columns && columns.length)
    ? localizeKnowledgeColumns(columns)
    : localizeKnowledgeColumns(_s1DefaultKnowledgeColumns);
  if (!list.length) {
    step1AddKnowledgeColumn(localizeKnowledgeColumn('具体方法'), 1);
    return;
  }
  list.forEach((name, i) => step1AddKnowledgeColumn(name, i + 1));
  _s1KnowledgeColumnSeq = list.length;
}

function step1ResetKnowledgeColumns() {
  const fmt = document.getElementById('s1-output-format')?.value || 'excel';
  if (fmt === 'markdown' && _s1RichMarkdownColumns.length) {
    step1RenderKnowledgeColumns(localizeKnowledgeColumns(_s1RichMarkdownColumns));
  } else {
    step1RenderKnowledgeColumns(localizeKnowledgeColumns(_s1DefaultKnowledgeColumns));
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
    if (docEl) docEl.value = data.doc_text || '';
    if (styleEl) styleEl.value = data.extract_style || '';
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
  if (state === 'saving') { txt.textContent = t('autosave_saving', '保存中...'); }
  else if (state === 'saved') {
    var now = new Date();
    var time = now.getHours().toString().padStart(2,'0') + ':' + now.getMinutes().toString().padStart(2,'0');
    txt.textContent = t('autosave_saved', '已保存 {time}').replace('{time}', time);
    _autoSaveTimer = setTimeout(function () { el.classList.remove('visible'); }, 3000);
  }
  else if (state === 'failed') {
    txt.textContent = t('autosave_failed', '保存失败，点击重试');
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
  ['s2-doc-text', 's2-extract-style'].forEach(id => bind(id, 2));
  ['s3-expert-text', 's3-revision-style'].forEach(id => bind(id, 3));
  const s2Model = document.getElementById('s2-model');
  const s2SourceFiles = document.getElementById('s2-source-files');
  const s2TextInputs = document.getElementById('s2-text-inputs');
  const s3Expert = document.getElementById('s3-expert-text');
  const s3File = document.getElementById('s3-expert-file');
  if (s2Model) s2Model.addEventListener('change', App.Step2.updateStep2Readiness);
  if (s2SourceFiles) s2SourceFiles.addEventListener('change', App.Step2.updateStep2Readiness);
  if (s2TextInputs) s2TextInputs.addEventListener('input', App.Step2.updateStep2Readiness);
  if (s3Expert) s3Expert.addEventListener('input', App.Step3.updateStep3AlignModeHint);
  if (s3File) s3File.addEventListener('change', App.Step3.updateStep3AlignModeHint);
}
/* ===== File upload name display ===== */
document.addEventListener('DOMContentLoaded', () => {
  [['s1-template-file', 's1-template-file-name'], ['s2-source-files', 's2-file-name'], ['s3-expert-file', 's3-file-name']].forEach(([inputId, nameId]) => {
    const input = document.getElementById(inputId);
    const nameEl = document.getElementById(nameId);
    if (input && nameEl) {
      input.addEventListener('change', async () => {
        nameEl.textContent = input.files.length
          ? (input.files.length + ' ' + App.I18n.t('files_count', '个文件'))
          : App.I18n.t('no_file_chosen', '未选择');
        if (!input.files.length) return;
        if (inputId === 's2-source-files') App.Step2.updateStep2Readiness();
        if (inputId === 's3-expert-file') await cacheUploadedFile(3, input, nameEl);
        if (inputId === 's3-expert-file') App.Step3.updateStep3AlignModeHint();
      });
    }
  });
  loadStep1SchemaAndTemplates();
  setupFormAutoSave();
  App.Panels.loadModels();
  refreshIcons();
  // 初始化列宽拖动调节
  if (App.initResizableColumns) { setTimeout(App.initResizableColumns, 300); }
});

window.onAppLangChange = function(lang) {
  step1SyncKnowledgeColumnLanguage(lang);
  // 语言切换后即时重渲当前视图，避免用户手动刷新
  if (currentStep === 0) {
    App.Overview.loadPipelineOverview();
  } else if (currentPipeline) {
    switchPanel(currentStep);
  }
  // 重渲配置面板（动态内容不走 data-i18n，需要重新生成才能同步语言）
  if (App.Panels.loadSkills) App.Panels.loadSkills();
  if (App.Panels.loadModels) App.Panels.loadModels();
};

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
  const brandTextEl = document.getElementById('nav-brand-text');

  if (step === 0) {
    // Overview mode: hide step nav
    navSteps.classList.remove('visible');
    if (brandTextEl) brandTextEl.textContent = App.I18n.t('nav_brand', '隐性知识显性化 · 五步法');
    App.Overview.loadPipelineOverview();
  } else {
    // Pipeline mode: show step nav with progress
    navSteps.classList.add('visible');
    if (currentPipeline) {
      if (brandTextEl) brandTextEl.textContent = currentPipeline.name;
      updateStepProgress();
      // Restore form data for this step
      const stepDataKey = 'step' + step + '_form_data';
      const savedData = currentPipeline.step_data?.[stepDataKey];
      if (savedData) restoreStepFormData(step, savedData);
    }
  }

  // Refresh model selects when entering a step with AI
  if ([2, 3, 4, 5].includes(step)) {
    if (!allModels.length) App.Panels.loadModels();
    App.Panels.refreshModelSelects();
  }

  // Load skill selects for steps 2, 3
  if ([2, 3].includes(step)) App.Panels.loadStepSkillSelects(step);
  if (step === 1) {
    const fd = currentPipeline?.step_data?.step1_form_data || {};
    loadStep1SchemaAndTemplates(fd.legacy_template || fd.default_template || '', fd.knowledge_columns);
    App.Step1.restoreStep1Output();
    // 进入 Step1 时重置生成按钮状态，防止上次请求中断导致按钮被永久锁定
    const s1GenerateBtn = document.getElementById('s1-generate');
    if (s1GenerateBtn) {
      s1GenerateBtn.disabled = false;
      s1GenerateBtn._locked = false;
    }
  }

  // Auto-load previous step output（先刷新流水线再检测上一步产出）
  if (step === 2) {
    if (currentPipeline) {
      const s2Prev = document.getElementById('s2-prev-output-area');
      if (s2Prev) s2Prev.innerHTML = '<div class="loading" style="padding:12px;"><div class="spinner"></div>加载上一步产出...</div>';
      refreshCurrentPipeline().then(() => {
        App.Step2.loadStep2PrevOutput();
        App.Step2.updateStep2Readiness();
        App.Step2.loadStep2KbHint();
        if (currentPipeline?.step_status?.['2'] === 'done') App.Step2.restoreStep2Output();
      });
    }
  }
  if (step === 3 && currentPipeline) {
    var s3Draft = document.getElementById('s3-prev-draft');
    var s3Empty = document.getElementById('s3-prev-empty');
    if (s3Draft) { s3Draft.style.display = ''; }
    if (s3Empty) { s3Empty.style.display = 'none'; }
    App.Step3.loadStep3PrevOutput();
    App.Step3.loadStep3IRForAlignment();
    App.Step3.loadStep3SkillMd();
    App.Step3.loadStep3RevisionContext();
    App.Step3.loadStep3SuggestionPool();
    App.Step3.updateStep3AlignModeHint();
    if (currentPipeline?.step_status?.['3'] === 'done') App.Step3.restoreStep3Output();
  }
  if (step === 4 && currentPipeline) {
    var s4Draft = document.getElementById('s4-prev-draft');
    var s4Empty = document.getElementById('s4-prev-empty');
    if (s4Draft) { s4Draft.style.display = 'block'; }
    if (s4Empty) { s4Empty.style.display = 'none'; }
    var s4Name = document.getElementById('s4-prev-name');
    if (s4Name) s4Name.textContent = '加载中...';
    App.Step4.loadStep4PrevOutput();
    if (currentPipeline?.step_status?.['4'] === 'done') App.Step4.restoreStep4Output();
  }
  if (step === 5 && currentPipeline) {
    refreshCurrentPipeline().then(function () {
      App.Step5.loadStep5Context();
      App.Step5.loadStep5PrevOutput();
      if (currentPipeline?.step_status?.['5'] === 'done') App.Step5.restoreStep5Output();
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

function renderOutput(containerId, html) {
  var el = document.getElementById(containerId);
  if (!el) return;
  el.style.display = '';
  el.innerHTML = '<div class="output-result">' + html + '</div>';
  console.log('[renderOutput]', containerId, 'set innerHTML length:', el.innerHTML.length);
  // 保险：部分浏览器/环境下 innerHTML 写入后会被异常清空，50ms 后检查并重绘
  var expectedHtml = html;
  setTimeout(function() {
    if (!el.querySelector('.output-result') || el.innerHTML.length < 50) {
      console.warn('[renderOutput] output was cleared, re-render', containerId);
      el.style.display = '';
      el.innerHTML = '<div class="output-result">' + expectedHtml + '</div>';
    }
  }, 50);
}
function renderLoading(containerId) {
  var el = document.getElementById(containerId);
  if (el) { el.style.display = ''; el.innerHTML = '<div class="loading"><div class="spinner"></div>' + t('loading') + '</div>'; }
}
function renderError(containerId, msg) {
  renderOutput(containerId, '<div class="error-list"><div class="error-item">' + escapeHtml(msg || '未知错误') + '</div></div>');
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

function resetAllStepFormInputs() {
  // 清空所有步骤表单输入，避免新建/切换流水线时旧内容污染。
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

  // 清空子场景
  const subList = document.getElementById('s1-sub-scenarios');
  if (subList) subList.innerHTML = '';
  if (typeof _s1SubScenarioCount !== 'undefined') _s1SubScenarioCount = 0;

  resetValue('s3-expert-text', '');

  resetValue('s1-template-file', '');
  resetValue('s2-source-files', '');
  resetValue('s3-expert-file', '');

  resetSelect('s3-revision-style', '标准修订');
  resetSelect('s1-output-format', 'excel');
  resetSelect('s1-legacy-template', '');
  step1RenderKnowledgeColumns([]);
  resetSelect('s2-model', '');
  resetSelect('s3-model', '');
  resetSelect('s3-skill-select', '');

  resetText('s1-template-file-name', '未选择');
  resetText('s2-file-name', '');
  resetText('s3-file-name', '');
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
      '#s1-output, #s2-output, #s3-output, #s4-output, #s5-output'
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
    const resp = await fetch(API_BASE + '/api/files/excel/read', {
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
    const resp = await fetch(API_BASE + '/api/files/excel/read', {
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
    const resp = await fetch(API_BASE + '/api/files/excel/read', { method: 'POST', body: fd });
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
    '<span id="excel-modified-text">' + t('excel_unmodified', '未修改') + '</span>' +
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
  if (text) text.textContent = t('modified_unsaved', '已修改（未保存）');
}

async function saveExcelEditor() {
  syncExcelDataFromDOM();

  if (!_excelEditorData.file_path) {
    alert(t('excel_save_no_path', '无源文件路径，请重新上传'));
    return;
  }

  const saveBtn = document.getElementById('excel-editor-save-btn');
  const saveBtnText = saveBtn ? saveBtn.querySelector('.btn__text') : null;
  if (saveBtn) { saveBtn.disabled = true; }
  if (saveBtnText) { saveBtnText.textContent = t('excel_saving', '保存中...'); }

  try {
    const resp = await fetch(API_BASE + '/api/files/excel/save', {
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
      if (text) text.textContent = t('excel_saved', '已保存');

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
        }).catch(e => { console.error('Link step1 output failed:', e); showToast(t('excel_save_sync_failed', 'Excel 已保存，但流水线同步失败'), 'error'); });
        if (currentStep === 2) App.Step2.loadStep2PrevOutput();
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
      alert(data.error || t('excel_save_failed', '保存失败'));
    }
  } catch (e) {
    alert(t('excel_save_failed', '保存失败') + ': ' + e.message);
  } finally {
    if (saveBtn) { saveBtn.disabled = false; }
    if (saveBtnText) { saveBtnText.textContent = t('save', '保存'); }
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
/* ===== Global aliases for inline onclick handlers ===== */
window.goBackToOverview = goBackToOverview;
window.enterPipeline = function (id) { App.Overview.enterPipeline(id); };
window.deletePipeline = function (id, btn) { App.Overview.deletePipeline(id, btn); };
window.showNewPipelineForm = function () { App.Overview.showNewPipelineForm(); };
window.hideNewPipelineForm = function () { App.Overview.hideNewPipelineForm(); };
window.createPipeline = function () { App.Overview.createPipeline(); };
window.filterPipelineList = function (q) { App.Overview.filterPipelineList(q); };
window.changePage = function (p) { App.Overview.changePage(p); };

window.openSkillPanel = function () { App.Panels.openSkillPanel(); };
window.closeSkillPanel = function () { App.Panels.closeSkillPanel(); };
window.toggleSkillDetail = function (skillId) { App.Panels.toggleSkillDetail(skillId); };
window.toggleSkill = function (skillId, enable) { App.Panels.toggleSkill(skillId, enable); };
window.resolveModelName = function (selectId) { return App.Panels.resolveModelName(selectId); };
window.openModelPanel = function () { App.Panels.openModelPanel(); };
window.closeModelPanel = function () { App.Panels.closeModelPanel(); };
window.showAddModelForm = function () { App.Panels.showAddModelForm(); };
window.hideAddModelForm = function () { App.Panels.hideAddModelForm(); };
window.saveModel = function () { App.Panels.saveModel(); };
window.toggleCcbModelFields = function () { App.Panels.toggleCcbModelFields(); };

window.step1AddSubScenario = function () { App.Step1.step1AddSubScenario(); };
window.step1RemoveSubScenario = function (idx) { App.Step1.step1RemoveSubScenario(idx); };
window.step1GetSubScenarios = function () { return App.Step1.step1GetSubScenarios(); };
window.step1AddKnowledgeColumn = step1AddKnowledgeColumn;
window.step1RemoveKnowledgeColumn = step1RemoveKnowledgeColumn;
window.step1ResetKnowledgeColumns = step1ResetKnowledgeColumns;
window.step1Generate = function () { App.Step1.step1Generate(); };
window.step1PreviewExcel = function (fileName) { App.Step1.step1PreviewExcel(fileName); };

window.selectStep2Skill = function (skillId) { App.Step2.selectStep2Skill(skillId); };
window.addStep2TextRow = function () { App.Step2.addStep2TextRow(); };
window.step2Execute = function () { App.Step2.step2Execute(); };
window.step2ExtractSkillMd = function () { App.Step2.step2ExtractSkillMd(); };
window.downloadCurrentIR = function () { App.Step2.downloadCurrentIR(); };
window.isStep2PreextractFile = function (fileName) { return App.Step2.isStep2PreextractFile(fileName); };

window.toggleSignalPanel = function () { App.Step3.toggleSignalPanel(); };
window.step3GeneratePreview = function () { App.Step3.step3GeneratePreview(); };
window.step3ToggleSelectAll = function () { App.Step3.step3ToggleSelectAll(); };
window.loadStep3SuggestionPool = function () { App.Step3.loadStep3SuggestionPool(); };
window.step3ApplySuggestions = function () { App.Step3.step3ApplySuggestions(); };
window.step3RejectSuggestions = function () { App.Step3.step3RejectSuggestions(); };
window.step3BackToInput = function () { App.Step3.step3BackToInput(); };
window.alignFilterNotes = function (filter) { App.Step3.alignFilterNotes(filter); };
window.alignSetState = function (id, state) { App.Step3.alignSetState(id, state); };
window.alignToggleEdit = function (id) { App.Step3.alignToggleEdit(id); };
window.alignSaveEdit = function (id) { App.Step3.alignSaveEdit(id); };
window.alignBatchAcceptAll = function () { App.Step3.alignBatchAcceptAll(); };
window.alignBatchRejectAll = function () { App.Step3.alignBatchRejectAll(); };
window.step3ApplyNotes = function () { App.Step3.step3ApplyNotes(); };
window.step3ConfirmAsIs = function () { App.Step3.step3ConfirmAsIs(); };
window.step3SaveEntryRevision = function (entryId) { App.Step3.step3SaveEntryRevision(entryId); };
window.step3RegenerateEntrySQL = function (entryId) { App.Step3.step3RegenerateEntrySQL(entryId); };
window.dismissTacitFollowup = function (btn) { App.Step3.dismissTacitFollowup(btn); };

window.step4Compile = function () { App.Step4.step4Compile(); };
window.step4Quality = function () { App.Step4.step4Quality(); };
window.step4PublishToKb = function () { App.Step4.step4PublishToKb(); };
window.previewStep4File = function (fileName, title) { App.Step4.previewStep4File(fileName, title); };
window.previewStep4Cot = function () { App.Step4.previewStep4Cot(); };
window.previewStep4Qa = function () { App.Step4.previewStep4Qa(); };
window.previewStep4Skill = function () { App.Step4.previewStep4Skill(); };
window.closeMarkdownEditor = function () { App.Step4.closeMarkdownEditor(); };
window.saveMarkdownContent = function () { App.Step4.saveMarkdownContent(); };
window.downloadMarkdownContent = function () { App.Step4.downloadMarkdownContent(); };
window.copyMarkdownContent = function () { App.Step4.copyMarkdownContent(); };

window.getCurrentPipelineId = function () {
  if (!currentPipeline || !currentPipeline.id) {
    console.error('No current pipeline available');
    return null;
  }
  return currentPipeline.id;
};
window.step5RunReplay = function () { App.Step5.step5RunReplay(); };
window.step5RunFeedback = function () { App.Step5.step5RunFeedback(); };
window.step5GoldenVerify = function () { App.Step5.step5GoldenVerify(); };
window.step5Finalize = function () { App.Step5.step5Finalize(); };
window.previewStep5InputJSON = function (url) { App.Step5.previewStep5InputJSON(url); };
window.closeModal = function () { App.Step5.closeModal(); };

/* ===== Initialization ===== */
App.Overview.loadPipelineOverview();

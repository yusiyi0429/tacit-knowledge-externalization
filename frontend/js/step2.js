(function (global) {
  'use strict';

  // Depends on globals: currentPipeline
  // Depends on globals: API_BASE
  // Depends on globals: escapeHtml
  // Depends on globals: renderOutput
  // Depends on globals: renderLoading
  // Depends on globals: renderError
  // Depends on globals: showToast
  // Depends on globals: clearDownstreamOutputs
  // Depends on globals: markStepDone
  // Depends on globals: updateStep2Readiness
  // Depends on globals: refreshCurrentPipeline
  // Depends on globals: resolveModelName
  // Depends on globals: isStep2PreextractFile
  // Depends on globals: step1PreviewExcel
  const API_BASE = global.location.origin;
  const t = function (key, fallback) { return App.I18n.t(key, fallback); };

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

async function step2ExtractSkillMd() {
  var pipelineId = getCurrentPipelineId();
  if (!pipelineId) { showToast('请先进入一条流水线', 'error'); return; }
  var model = resolveModelName('s2-model');
  if (!model) { showToast('请先选择模型', 'error'); return; }

  var formData = new FormData();
  formData.append('pipeline_id', pipelineId);
  formData.append('model', model);
  var files = document.getElementById('s2-source-files').files;
  for (var i = 0; i < files.length; i++) formData.append('files', files[i]);

  // 收集文本输入行
  var textRows = document.querySelectorAll('#s2-text-inputs .s2-text-input-row');
  var textInputs = [];
  textRows.forEach(function (row) {
    var label = (row.querySelector('.s2-text-input-label') || {}).value || '';
    var content = (row.querySelector('.s2-text-input-content') || {}).value || '';
    if (content.trim()) textInputs.push({ source_label: label, content: content.trim() });
  });
  if (textInputs.length > 0) {
    formData.append('text_inputs', JSON.stringify(textInputs));
  }

  // 知识库继承
  if (document.getElementById('s2-kb-inherit')?.checked) {
    formData.append('kb_inherit', '1');
  }

  renderLoading('s2-output');
  try {
    var resp = await fetch(API_BASE + '/api/step2/extract_skill_md', { method: 'POST', body: formData });
    var data = await resp.json();
    if (data.status === 'ok') {
      var html = '';
      if (typeof marked !== 'undefined') {
        html = marked.parse(data.skill_md);
      } else {
        html = '<pre style="white-space:pre-wrap;">' + escapeHtml(data.skill_md) + '</pre>';
      }
      // Recreate the output structure (renderLoading destroyed it)
      var s2out = document.getElementById('s2-output');
      s2out.innerHTML = '<div id="s2-md-preview" class="md-preview" style="max-height:500px;overflow:auto;">' + html + '</div>';
      s2out.innerHTML += '<div id="s2-actions" style="margin-top:12px;"><a class="btn btn--primary btn--sm" href="' + API_BASE + data.download_url + '" download>下载 SKILL.md</a></div>';
      await refreshCurrentPipeline();
    } else {
      renderError('s2-output', data.error);
    }
  } catch (e) {
    renderError('s2-output', e.message);
  }
}


  global.App = global.App || {};

function restoreStep2Output() {
  if (!currentPipeline) return;
  const sd = currentPipeline.step_data || {};
  const mdFile = sd.step2_skill_md_file || sd.step2_draft_md_file || sd.step2_md_file || '';
  const mdUrl = sd.step2_skill_md_url || sd.step2_draft_md_url || sd.step2_md_download_url || '';
  if (!mdFile && !mdUrl) {
    document.getElementById('s2-md-preview').innerHTML = '';
    document.getElementById('s2-actions').innerHTML = '';
    return;
  }
  // Try to load the md content
  if (mdFile) {
    fetch(API_BASE + '/downloads/' + mdFile)
      .then(function (r) { if (r.ok) return r.text(); throw new Error('not found'); })
      .then(function (md) {
        var html = '';
        if (typeof marked !== 'undefined') {
          html = marked.parse(md);
        } else {
          html = '<pre style="white-space:pre-wrap;">' + escapeHtml(md) + '</pre>';
        }
        document.getElementById('s2-md-preview').innerHTML = html;
        if (mdUrl) {
          document.getElementById('s2-actions').innerHTML = '<a class="btn btn--primary btn--sm" href="' + API_BASE + mdUrl + '" download>下载 SKILL.md</a>';
        }
      })
      .catch(function () {
        document.getElementById('s2-md-preview').innerHTML = '<div class="s2-result-success"><div class="s2-result-header">SKILL.md 已生成</div></div>';
        if (mdUrl) {
          document.getElementById('s2-actions').innerHTML = '<a class="btn btn--primary btn--sm" href="' + API_BASE + mdUrl + '" download>下载 SKILL.md</a>';
        }
      });
  }
}

  const Step2 = {
    renderStep2PrevOutputCard,
    ensureStep1OutputLinked,
    loadStep2PrevOutput,
    isStep2PreextractFile,
    resolveStep2DownloadInfo,
    getCurrentPipelineId,
    getSelectedModel,
    switchStep2Tab,
    renderStep2IR,
    renderIRTree,
    renderIRMarkdown,
    renderIRTable,
    step2ExtractSkillMd,
    restoreStep2Output,
  };
  global.App.Step2 = Step2;
})(window);

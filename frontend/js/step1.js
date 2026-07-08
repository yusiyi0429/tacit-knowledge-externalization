(function (global) {
  'use strict';

  // Depends on globals: currentPipeline
  // Depends on globals: currentStep
  // Depends on globals: API_BASE
  // Depends on globals: escapeHtml
  // Depends on globals: refreshIcons
  // Depends on globals: renderOutput
  // Depends on globals: renderLoading
  // Depends on globals: showToast
  // Depends on globals: persistPipeline
  // Depends on globals: markStepDone
  // Depends on globals: clearDownstreamOutputs
  // Depends on globals: collectAllStepsFormData
  // Depends on globals: mergeStepDataPreserveOutputs
  // Depends on globals: loadStep1SchemaAndTemplates
  // Depends on globals: step1RenderKnowledgeColumns
  // Depends on globals: step1GetKnowledgeColumns
  // Depends on globals: step1GetSubScenarios
  // Depends on globals: applyStep1GenerateResult
  // Depends on globals: syncPipelineFromStep1Response
  // Depends on globals: rememberStep1Output
  // Depends on globals: prefersMarkdownFlow
  // Depends on globals: openExcelEditorWithSheets
  const API_BASE = global.location.origin;
  const t = function (key, fallback) { return App.I18n.t(key, fallback); };

function step1AddSubScenario() {
  _s1SubScenarioCount++;
  const idx = _s1SubScenarioCount;
  const container = document.getElementById('s1-sub-scenarios');
  const div = document.createElement('div');
  div.className = 's1-sub-item';
  div.id = 's1-sub-' + idx;
  div.innerHTML = '<div class="s1-sub-row">' +
    '<input type="text" class="s1-sub-name" placeholder="' + t('sub_scenario_name', '子场景名称') + '" data-idx="' + idx + '">' +
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
  if (!btn) return;
  // 防御：若之前请求因页面刷新/异常中断导致锁标记残留，但按钮已恢复可用，则强制清除
  if (btn._locked && !btn.disabled) {
    console.warn('[step1Generate] clear stale _locked flag on enabled button');
    btn._locked = false;
  }
  if (btn._locked) return;
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

  if (!scenarioName) { alert(t('step1_scenario_name_required', '请填写场景名称')); return; }
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
      // 先构建并渲染结果，让用户立刻看到输出，不受后续 persistPipeline 网络延迟影响
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
      console.log('[step1Generate] render output, html length:', html.length);
      renderOutput('s1-output', html);

      // 保险：强制浏览器重排，确保输出区立即渲染
      const s1OutputEl = document.getElementById('s1-output');
      if (s1OutputEl) { void s1OutputEl.offsetHeight; }

      // 更新列输入框（如果有富语义列补齐）
      if (result.columns_enriched) {
        step1RenderKnowledgeColumns(result.knowledge_columns);
      }

      // 再保存状态到服务器
      console.log('[step1Generate] start persistence');
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
      await markStepDone(1);
      // 保险：如果用户仍在 Step1，确保输出区显示最新结果
      if (currentStep === 1) {
        restoreStep1Output();
      }
      if (currentStep === 2) loadStep2PrevOutput();
    } else {
      html = '<div class="error-list"><div class="error-item">' + escapeHtml(result.error || '未知错误') + '</div></div>';
      renderOutput('s1-output', html);
    }
  } catch (e) {
    console.error('[step1Generate] error during generation:', e);
    renderOutput('s1-output', '<div class="error-list"><div class="error-item">' + escapeHtml(e.message) + '</div></div>');
  }
  } finally {
    // 即使请求很快完成，也保持按钮锁定至少 500ms，防止用户连续快速点击造成视觉抖动
    setTimeout(function() {
      btn.disabled = false;
      btn._locked = false;
    }, 500);
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
    const result = await apiCall('/api/files/excel/read', fd);
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
  if (stepLabel) stepLabel.textContent = t('preview_prefix', '预览：') + fileName;
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


  global.App = global.App || {};
  const Step1 = {
    step1AddSubScenario,
    step1RemoveSubScenario,
    step1GetSubScenarios,
    step1Generate,
    restoreStep1Output,
    step1PreviewExcel,
    openExcelEditorWithSheets,
  };
  global.App.Step1 = Step1;
})(window);

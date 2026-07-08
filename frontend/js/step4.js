(function (global) {
  'use strict';

  // Depends on globals: currentPipeline
  // Depends on globals: API_BASE
  // Depends on globals: escapeHtml
  // Depends on globals: renderOutput
  // Depends on globals: renderLoading
  // Depends on globals: showToast
  // Depends on globals: refreshCurrentPipeline
  // Depends on globals: prefersMarkdownFlow
  // Depends on globals: apiCall
  // Depends on globals: apiCallJSON
  // Depends on globals: renderBtnChildren
  // Depends on globals: refreshIcons
  // Depends on globals: openMarkdownEditor
  // Depends on globals: closeMarkdownEditor
  // Depends on globals: renderMarkdownPreview
  const API_BASE = global.location.origin;
  const t = function (key, fallback) { return App.I18n.t(key, fallback); };

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
        actionsEl.innerHTML = btns;
      }
    } else {
      el.style.display = 'none';
      if (emptyEl) emptyEl.style.display = 'block';
    }
  } catch (e) { console.error('loadStep4PrevOutput error', e); }
}

function getSelectedStep4Formats() {
  const hasFmtCot = document.getElementById('s4-fmt-cot');
  const hasFmtQa = document.getElementById('s4-fmt-qa');
  const hasFmtSkill = document.getElementById('s4-fmt-skill');
  // 如果页面未配置格式复选框，默认生成全部三种交付物
  if (!hasFmtCot && !hasFmtQa && !hasFmtSkill) {
    return ['cot', 'qa', 'skill'];
  }
  const formats = [];
  if (hasFmtCot?.checked) formats.push('cot');
  if (hasFmtQa?.checked) formats.push('qa');
  if (hasFmtSkill?.checked) formats.push('skill');
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


async function step4Compile() {
  if (!currentPipeline) { showToast('请先进入流水线', 'error'); return; }

  const formats = getSelectedStep4Formats();
  if (!formats.length) { showToast('请至少选择一种交付物格式', 'error'); return; }

  renderLoading('s4-output');
  const output = document.getElementById('s4-output');
  if (output) output.style.display = 'block';

  try {
    const fd = new FormData();
    fd.append('pipeline_id', currentPipeline.id);
    fd.append('formats', formats.join(','));

    const resp = await fetch(API_BASE + '/api/step4/compile', { method: 'POST', body: fd });
    const data = await resp.json();

    if (data.status === 'ok') {
      await refreshCurrentPipeline();
      renderStep4CompileResult(data);
    } else {
      if (output) {
        output.innerHTML = '<div class="error-list"><div class="error-item">' + escapeHtml(data.error || '编译失败') + '</div></div>';
      }
    }
  } catch (e) {
    if (output) {
      output.innerHTML = '<div class="error-list"><div class="error-item">' + escapeHtml(e.message) + '</div></div>';
    }
  }
}

function renderStep4CompileResult(data) {
  const output = document.getElementById('s4-output');
  if (!output) return;

  let html = '<div class="s4-compile-result">';
  html += '<div class="s4-compile-header">';
  html += '<div class="s4-compile-icon">&#9989;</div>';
  html += '<div class="s4-compile-title">' + escapeHtml(t('compile_success', '编译完成')) + '</div>';
  html += '<div class="s4-compile-subtitle">' + escapeHtml(data.knowledge_count || 0) + ' 条知识 · ' + (data.category_count || 0) + ' 个分类 · 质量分 ' + (data.quality_score || 0) + '</div>';
  html += '</div>';

  html += '<div class="s4-stats-grid">';
  html += '<div class="s4-stat-card"><div class="s4-stat-value">' + (data.knowledge_count || 0) + '</div><div class="s4-stat-label">知识条目</div></div>';
  html += '<div class="s4-stat-card"><div class="s4-stat-value">' + (data.quality_score || 0) + '</div><div class="s4-stat-label">质量评分</div></div>';
  html += '</div>';

  html += '<div class="s4-section"><div class="s4-section-title">交付物下载</div>';
  html += '<div class="s4-downloads">';
  const downloads = data.downloads || {};
  if (downloads.skill_zip) {
    html += '<a class="s4-download-link" href="' + API_BASE + downloads.skill_zip + '" download>' + escapeHtml(t('download_skill_zip', 'Agent-Skill 可执行包 (.zip)')) + '</a>';
  }
  if (downloads.skill) {
    html += '<a class="s4-download-link" href="' + API_BASE + downloads.skill + '" download>' + escapeHtml(t('download_skill_md', 'SKILL.md')) + '</a>';
  }
  if (downloads.cot) {
    html += '<a class="s4-download-link" href="' + API_BASE + downloads.cot + '" download>' + escapeHtml(t('download_cot', '思维链 (CoT)')) + '</a>';
  }
  if (downloads.qa) {
    html += '<a class="s4-download-link" href="' + API_BASE + downloads.qa + '" download>' + escapeHtml(t('download_qa', 'QA 对')) + '</a>';
  }
  html += '</div></div>';

  html += '</div>';
  output.innerHTML = '<div class="output-result">' + html + '</div>';
}

async function step4GenerateCOT() {
  // Deprecated: functionality merged into step4Compile
}

async function step4GenerateQA() {
  // Deprecated: functionality merged into step4Compile
}

async function step4GenerateExecSkill() {
  // Deprecated: functionality merged into step4Compile
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
  var output = document.getElementById('s4-output');
  if (!output) return; // safety guard
  if (!currentPipeline) { alert('请先进入流水线'); return; }
  renderLoading('s4-output');
  output.style.display = 'block';
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
    output.innerHTML = '<div class="output-result">' + html + '</div>';
  } catch (e) {
    output.innerHTML = '<div class="error-list"><div class="error-item">' + escapeHtml(e.message) + '</div></div>';
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


  global.App = global.App || {};

function restoreStep4Output() {
  if (!currentPipeline || !currentPipeline.id) return;
  var sd = currentPipeline.step_data || {};

  // New contract: step4_skill_dir_zip_file + step4_step5_input_file
  if (sd.step4_skill_dir_zip_file) {
    var html = '<div class="s2-result-success"><div class="s2-result-header">编译完成</div><div class="s2-result-meta">版本 ' + (sd.step4_published_version || '') + '</div></div>';
    html += '<div class="s4-downloads">';
    if (sd.step4_skill_dir_zip_file) {
      html += '<a class="s4-download-link" href="' + API_BASE + (sd.step4_skill_dir_zip_url || '/downloads/' + sd.step4_skill_dir_zip_file) + '" download>Agent-Skill 可执行包 (.zip)</a>';
    }
    if (sd.step4_step5_input_file) {
      html += '<a class="s4-download-link" href="' + API_BASE + (sd.step4_step5_input_url || '/downloads/' + sd.step4_step5_input_file) + '" download>Step5 验证输入 (.json)</a>';
    }
    html += '</div>';
    document.getElementById('s4-output').innerHTML = html;
    return;
  }

  // Fallback: check old contract
  if (sd.step4_download_url || sd.step4_compile_result) {
    document.getElementById('s4-output').innerHTML = '<div class="s2-result-success"><div class="s2-result-header">交付包已生成</div></div>';
    return;
  }
}

  const Step4 = {
    loadStep4PrevOutput,
    getSelectedStep4Formats,
    renderStep4ArtifactCard,
    step4Compile,
    renderStep4CompileResult,
    step4GenerateCOT,
    step4GenerateQA,
    step4GenerateExecSkill,
    previewStep4File,
    previewStep4Cot,
    previewStep4Qa,
    previewStep4Skill,
    step4Quality,
    openMarkdownEditor,
    closeMarkdownEditor,
    renderMarkdownPreview,
    onMarkdownEditorInput,
    copyMarkdownContent,
    saveMarkdownContent,
    downloadMarkdownContent,
    restoreStep4Output,
  };
  global.App.Step4 = Step4;
})(window);

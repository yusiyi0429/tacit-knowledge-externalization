(function (global) {
  'use strict';

  const API_BASE = global.location.origin;

  const API = {
    // Pipelines
    listPipelines() { return fetch(API_BASE + '/api/pipelines').then(r => r.json()); },
    getPipeline(id) { return fetch(API_BASE + '/api/pipelines/' + id).then(r => r.json()); },
    createPipeline(payload) { return App.apiCallJSON('/api/pipelines', payload, 'POST'); },
    updatePipeline(id, payload) { return App.apiCallJSON('/api/pipelines/' + id, payload, 'PUT'); },
    deletePipeline(id) { return fetch(API_BASE + '/api/pipelines/' + id, { method: 'DELETE' }).then(r => r.json()); },
    rollbackPipeline(id, step) { return fetch(API_BASE + '/api/pipelines/' + id + '/rollback/' + step, { method: 'POST' }).then(r => r.json()); },
    clearPipeline(id) { return fetch(API_BASE + '/api/pipelines/' + id + '/clear', { method: 'POST' }).then(r => r.json()); },

    // Step1
    getStep1Templates() { return fetch(API_BASE + '/api/step1/templates').then(r => r.json()); },
    generateStep1Skeleton(formData) { return App.apiCall('/api/step1/generate', formData); },

    // Step2
    extractStep2(formData) { return fetch(API_BASE + '/api/step2/extract', { method: 'POST', body: formData }).then(r => r.text()); },
    getStep2PrevOutput(pipelineId) { return fetch(API_BASE + '/api/step2/prev_output?pipeline_id=' + pipelineId).then(r => r.json()); },
    extractStep2SkillMd(formData) { return fetch(API_BASE + '/api/step2/extract_skill_md', { method: 'POST', body: formData }).then(r => r.json()); },

    // Step3
    reviseStep3WithExpert(formData) { return fetch(API_BASE + '/api/step3/revision_with_expert', { method: 'POST', body: formData }).then(r => r.json()); },
    saveStep3SkillMd(payload) { return fetch(API_BASE + '/api/step3/save_skill_md', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }).then(r => r.json()); },
    confirmStep3SkillMd(payload) { return fetch(API_BASE + '/api/step3/confirm_skill_md', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }).then(r => r.json()); },
    getStep3PrevOutput(pipelineId) { return fetch(API_BASE + '/api/step3/prev_output?pipeline_id=' + pipelineId).then(r => r.json()); },
    getStep3AlignOutput(pipelineId) { return fetch(API_BASE + '/api/step3/align_output?pipeline_id=' + pipelineId).then(r => r.json()); },
    getStep3RevisionContext(pipelineId) { return fetch(API_BASE + '/api/step3/revision_context?pipeline_id=' + pipelineId).then(r => r.json()); },
    getStep3Suggestions(pipelineId) { return fetch(API_BASE + '/api/step3/suggestions?pipeline_id=' + pipelineId).then(r => r.json()); },
    applyStep3Suggestions(payload) { return App.apiCallJSON('/api/step3/apply_suggestions', payload, 'POST'); },
    applyStep3Notes(payload) { return fetch(API_BASE + '/api/step3/apply_notes', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }).then(r => r.json()); },
    confirmStep3AsIs(payload) { return App.apiCallJSON('/api/step3/confirm_as_is', payload, 'POST'); },
    alignStep3Ir(payload) { return App.apiCallJSON('/api/step3/align_ir', payload, 'POST'); },

    // Step4
    buildSkill(formData) { return fetch(API_BASE + '/api/step4/build_skill', { method: 'POST', body: formData }).then(r => r.json()); },
    qualityStep4(formData) { return App.apiCall('/api/step4/quality', formData); },
    publishToKb(payload) { return App.apiCallJSON('/api/kb/publish', payload, 'POST'); },

    // Step5
    replayStep5(formData) { return fetch(API_BASE + '/api/step5/replay', { method: 'POST', body: formData }).then(r => r.json()); },
    feedbackStep5(payload) { return fetch(API_BASE + '/api/step5/feedback', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }).then(r => r.json()); },
    finalizeStep5(pipelineId) { return fetch(API_BASE + '/api/step5/finalize', { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: 'pipeline_id=' + encodeURIComponent(pipelineId) }).then(r => r.json()); },
    getStep5PrevOutput(pipelineId) { return fetch(API_BASE + '/api/step5/prev_output?pipeline_id=' + pipelineId).then(r => r.json()); },

    // KB
    listKbEntries(params) { return fetch(API_BASE + '/api/kb/entries?' + params.toString()).then(r => r.json()); },

    // Skills
    listSkills() { return fetch(API_BASE + '/api/skills').then(r => r.json()); },
    getSkill(skillId) { return fetch(API_BASE + '/api/skills/' + skillId).then(r => r.json()); },
    updateSkill(skillId, payload) { return fetch(API_BASE + '/api/skills/' + skillId, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }).then(r => r.json()); },

    // Models
    listModels() { return fetch(API_BASE + '/api/llm/models').then(r => r.json()); },
    getModel(name) { return fetch(API_BASE + '/api/llm/models/' + encodeURIComponent(name)).then(r => r.json()); },
    createModel(payload) { return App.apiCallJSON('/api/llm/models', payload, 'POST'); },
    updateModel(name, payload) { return App.apiCallJSON('/api/llm/models/' + encodeURIComponent(name), payload, 'PUT'); },
    deleteModel(name) { return fetch(API_BASE + '/api/llm/models/' + encodeURIComponent(name), { method: 'DELETE' }).then(r => r.json()); },
    testModel(payload) { return App.apiCallJSON('/api/llm/test', payload, 'POST', 25000); },
    streamTestModel(payload) { return fetch(API_BASE + '/api/llm/stream-test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }); },

    // Files
    cacheUpload(formData) { return fetch(API_BASE + '/api/files/cache_upload', { method: 'POST', body: formData }).then(r => r.json()); },
    readFile(urlParams) { return fetch(API_BASE + '/api/files/read?' + urlParams.toString()).then(r => r.json()); },
    saveFile(payload) { return fetch(API_BASE + '/api/files/save', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }).then(r => r.json()); },

    // Excel
    readExcel(payload) { return fetch(API_BASE + '/api/excel/read', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }).then(r => r.json()); },
    readExcelFormData(formData) { return fetch(API_BASE + '/api/excel/read', { method: 'POST', body: formData }).then(r => r.json()); },
    saveExcel(payload) { return fetch(API_BASE + '/api/excel/save', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }).then(r => r.json()); },
  };

  global.App = global.App || {};
  global.App.API = API;
})(window);

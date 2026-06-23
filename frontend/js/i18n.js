/**
 * Lightweight page-level i18n for the tacit-knowledge frontend.
 * Default language: Simplified Chinese (zh-CN). Toggle to English (en).
 * Persistence: localStorage key "app-lang".
 *
 * Usage in HTML:
 *   <span data-i18n="key">fallback text</span>
 *   <input data-i18n-placeholder="placeholder_key" placeholder="fallback">
 *   <button data-i18n-title="title_key" title="fallback">
 *
 * Usage in JS:
 *   App.I18n.t('key', 'fallback');
 *   App.I18n.setLang('en');
 */
(function (global) {
  'use strict';

  const DEFAULT_LANG = 'zh-CN';
  const STORAGE_KEY = 'app-lang';

  const translations = {
    'zh-CN': {
      page_title: '隐性知识显性化 · 五步法萃取流水线',
      nav_brand: '隐性知识显性化 · 五步法',
      nav_back: '返回',
      nav_save: '保存',
      nav_clear: '清空',
      nav_skill_config: 'Skill配置',
      nav_model_config: '模型配置',
      nav_lang_config: '语言配置',
      lang_panel_title: '语言配置',
      lang_toggle: '中 / EN',
      lang_toggle_title: '切换语言 / Switch language',
      server_checking: '检测中...',
      server_online: '服务就绪',
      server_offline: '离线模式',

      step1_name: '场景锚定',
      step2_name: '知识萃取',
      step3_name: '知识对齐',
      step4_name: '智能转化',
      step5_name: '验证回放',

      input: '输入',
      input_en: 'Input',
      action: '操作',
      action_en: 'Action',
      config: '配置',
      config_en: 'Config',
      output: '输出',
      output_en: 'Output',
      core_points: '核心要点',

      skill_panel_title: 'Skill 配置',
      close: '关闭',
      model_panel_title: 'LLM 模型配置',
      configured_models: '已配置模型',
      add_model: '添加模型',
      add_model_title: '添加自定义模型',
      model_name: '模型名称',
      api_type: '接口类型',
      api_type_openai: 'OpenAI 兼容',
      api_type_ccb: '建行 ainlplm',
      model_id: '模型标识 (model)',
      api_url: 'API 地址',
      api_key: 'API Key / Access_Key_Id',
      tx_code: 'Tx-Code',
      sec_node: 'Sec-Node-No',
      max_tokens: 'Max Tokens',
      temperature: 'Temperature',
      desc_optional: '描述（可选）',
      cancel: '取消',
      add: '添加',
      placeholder_model_name: '如: GPT-4o',
      placeholder_model_id: '如: gpt-4o 或 F-G-98-...',
      placeholder_api_url: 'OpenAI: .../v1/chat/completions 或建行: .../ainlplm/chat',
      placeholder_api_key: '输入 API Key 或 Access_Key_Id',
      placeholder_tx_code: '如: A4011LM01',
      placeholder_sec_node: '如: 400136',
      placeholder_desc: '模型能力简述',

      step1_title: '场景确认与骨架定制',
      step1_subtitle: '骨架错则全盘错——本步定义"这个领域的知识应该长什么样"',
      scenario_name: '场景名称',
      scenario_content: '场景内容',
      sub_scenarios: '子场景',
      add_sub_scenario: '添加子场景',
      knowledge_columns: '知识列（可自定义）',
      add_column: '添加列',
      reset_columns: '恢复默认列',
      hint_fixed_columns: '锚定四列（场景/场景说明/子场景/子场景说明）固定，此处仅配置知识列',
      output_format: '骨架输出方式',
      output_format_excel: '系统生成 Excel',
      output_format_markdown: '系统生成 Markdown',
      hint_markdown_columns: '选择 Markdown 时，将自动补齐环节、判断逻辑、反模式等富语义列，便于 Step2 深度萃取',
      advanced_template: '高级：上传或选用部门 Excel 模板',
      upload_template: '上传 .xlsx 模板（优先级最高）',
      choose_file: '选择文件',
      no_file_chosen: '未选择',
      samples_template: '或选用 samples 中的 Excel 模板',
      no_template: '不使用（按上方自定义列生成）',
      hint_upload_template: '上传/选用 Excel 后，将按文件表头为准，自定义知识列仅作记录',
      generate_skeleton: '生成场景骨架',
      step1_action_note: '自由定义知识列与输出格式；后续步骤仍使用配套 Excel 继续流水线',
      step1_output_placeholder: '填写场景信息后点击"生成场景骨架"查看结果',
      placeholder_scenario_name: '如：信贷审批',
      placeholder_scenario_content: '描述该场景的核心业务流程、关键判断点和知识特征',
      placeholder_knowledge_column: '如：具体方法、判断逻辑',

      step2_title: '多源知识萃取',
      step2_subtitle: '把已显性化的10%先固化下来——让专家面对的不是空白Excel，而是一份"待审稿"',
      prev_output_label: '上一步输出件（场景锚定模板）',
      prev_output_empty: '尚未检测到上一步输出，请先完成场景锚定',
      source_files: '知识来源文件（可多选）',
      source_files_hint: '上传待萃取的制度文件、操作手册、案例库（TXT/MD/DOCX/PDF），支持多选',
      paste_source: '或粘贴文本来源',
      source_label_placeholder: '来源标注（如：制度文件A）',
      paste_content_placeholder: '粘贴文档内容...',
      remove_title: '移除',
      add_more_source: '添加更多文本来源',
      inherit_kb: '继承知识库已沉淀知识（作为融合源参与去重）',
      inherit_kb_hint_prefix: '已匹配知识库条目：',
      choose_ability: '选择能力',
      skill_knowledge_extraction: '知识萃取',
      skill_knowledge_extraction_desc: 'Excel模板 → Skill预萃稿',
      skill_knowledge_extraction_hint: '上传标准萃取模板，生成 IR 预萃稿（Markdown）',
      select_skill: '-- 选择 Skill --',
      extraction_style: '萃取风格',
      style_standard: '标准萃取（8-22条）',
      style_deep: '深度萃取（12-40条）',
      style_compact: '精简萃取（5-10条）',
      select_model: '选择模型',
      generate_skill_md: '生成 SKILL.md',
      execute_extraction: '执行知识萃取',
      step2_readiness_default: '请补全模型与文档后点击生成规则',
      step2_no_pipeline: '请先从总览进入一条流水线后再执行',
      step2_no_model: '请先配置并选择模型',
      step2_no_source: '请至少上传一个文件或填入文本来源',
      step2_ready: '已就绪：可执行知识萃取',
      kb_hint_has_entries: '知识库已有 {count} 条相关知识，勾选后将与新萃取结果融合去重',
      kb_hint_no_entries: '知识库暂无相关沉淀（首条流水线发布后可供后续继承）',
      step2_action_note: '上传知识文档后点击生成规则，IR 生成后可点击生成 SQL',

      step3_title: '知识对齐',
      step3_subtitle: '对 Step2 生成的 Skill 预萃稿逐条审核与修订',
      s3_draft_title: '知识萃取稿',
      s3_draft_linked: '已关联',
      s3_no_draft: '暂无 Step2 萃取稿输出',
      s3_no_draft_hint: '请先完成知识萃取节点',
      revision_context: '修订上下文',
      chat_history: '对话记录（专家与模型）',
      chat_empty: '暂无对话。请先输入一条修订意见并发送。',
      expert_input: '专家输入（本轮意见）',
      expert_placeholder: '可填写具体修订意见；若无修改可留空或填写「暂无意见」，系统将自动确认当前萃取稿为对齐稿',
      upload_minutes: '或上传专家纪要文件',
      align_style: '对齐风格',
      align_style_standard: '标准修订',
      align_style_strict: '严格修订',
      align_style_loose: '宽松修订',
      select_skill_default: '-- 选择 Skill --',
      select_skill_default_label: '引用 Skill',
      send_revise: '发送并智能修订',
      s3_align_hint: '若无意见可直接点击按钮，系统将按预萃稿直通生成对齐稿',
      s3_action_note: '专家可多轮输入修订意见，模型会结合历史对话持续更新对齐建议。',
      signal_review: '信号审核',
      signal_blur: '边界模糊',
      signal_island: '知识孤岛',
      signal_lowconf: '共识度低',
      signal_conflict: '冲突',
      suggestion_pool: '建议池（验证回流 / 访谈转化）',
      select_all: '全选 / 取消全选',
      stat_accepted: '已采纳 ',
      stat_rejected: '已驳回 ',
      stat_pending: '待审 ',
      stat_edited: '已编辑 ',

      apply_suggestions: '采纳勾选建议 → 生成新对齐稿',
      reject_suggestions: '驳回勾选建议',
      refresh: '刷新',
      review_title: '对齐建议审核',
      filter_all: '全部',
      filter_modify: '修改',
      filter_add: '新增',
      filter_delete: '删除',
      filter_supplement: '补充',
      accept_all: '全部采纳',
      reject_all: '全部驳回',
      back_to_edit: '返回修改',
      online_edit_draft: '在线编辑底稿',
      confirm_aligned: '确认并生成对齐稿',
      revise_skill_md: '修订 SKILL.md（可直接编辑代码块中的 SQL）：',

      step4_title: '三类交付物生成',
      step4_subtitle: '一次生成思维链、QA 对、OpenClaw 兼容 Skill，覆盖推理、问答与 Agent 技能三类消费场景',
      s4_input_draft: '知识对齐稿',
      s4_no_aligned: '暂无知识对齐稿，请先完成知识对齐节点',
      skill_generator: 'Skill生成器（内置）',
      select_skill_label: '选择 Skill',
      generate_deliverables: '生成待验证 Skill + 思维链 + QA 对',
      step4_action_note: 'LLM 解析 Step3 对齐稿，生成 QA对/思维链/待验证 Agent-Skill 三个交付物',
      step4_output_placeholder: '点击「生成」创建三个交付物',

      step5_title: '决策回放与回流',
      step5_subtitle: '用 SKILL 终版判断历史案例并与专家结论比对；分歧自动生成修订建议，回流知识对齐形成闭环',
      s5_validation_target: '验证对象',
      s5_deliverable_title: 'Step4 交付物',
      s5_deliverable_linked: '已验证',
      s5_no_deliverables: '暂无 Step4 交付物',
      s5_no_deliverables_hint: '请先完成智能转化节点',
      test_data_source: '测试数据来源',
      all_test_customers: '全部 test_customers',
      run_replay: '执行 P/R/F1 验证',
      step5_action_note: '在 test_customers 表上执行 agent-skill，对照期望结果计算精度/召回/F1',
      feedback_divergence: '反馈分歧到 Step3',
      feedback_hint: '将验证分歧推入 Step3 建议池，专家可重新审核',
      step5_output_placeholder: '执行 P/R/F1 验证后查看度量结果',

      excel_editor_title: '在线编辑',
      save: '保存',
      md_editor_title: 'SKILL.md 预览编辑',
      download: '下载',
      copy: '复制',
      edit_area: '编辑区',
      preview_area: '预览区',
      md_placeholder: 'SKILL.md 内容...',
      excel_placeholder: '请上传 Excel 文件后点击"在线编辑"按钮',

      loading: '处理中...',
    },
    en: {
      page_title: 'Tacit Knowledge Externalization · 5-Step Pipeline',
      nav_brand: 'Tacit Knowledge · 5 Steps',
      nav_back: 'Back',
      nav_save: 'Save',
      nav_clear: 'Clear',
      nav_skill_config: 'Skill Config',
      nav_model_config: 'Model Config',
      nav_lang_config: 'Language',
      lang_panel_title: 'Language',
      lang_toggle: '中 / EN',
      lang_toggle_title: '切换语言 / Switch language',
      server_checking: 'Checking...',
      server_online: 'Ready',
      server_offline: 'Offline',

      step1_name: 'Scenario Anchoring',
      step2_name: 'Knowledge Extraction',
      step3_name: 'Knowledge Alignment',
      step4_name: 'Knowledge Delivery',
      step5_name: 'Validation Replay',

      input: 'Input',
      input_en: 'Input',
      action: 'Action',
      action_en: 'Action',
      config: 'Config',
      config_en: 'Config',
      output: 'Output',
      output_en: 'Output',
      core_points: 'Key Points',

      skill_panel_title: 'Skill Config',
      close: 'Close',
      model_panel_title: 'LLM Model Config',
      configured_models: 'Configured Models',
      add_model: 'Add Model',
      add_model_title: 'Add Custom Model',
      model_name: 'Model Name',
      api_type: 'API Type',
      api_type_openai: 'OpenAI Compatible',
      api_type_ccb: 'CCB ainlplm',
      model_id: 'Model ID',
      api_url: 'API URL',
      api_key: 'API Key / Access_Key_Id',
      tx_code: 'Tx-Code',
      sec_node: 'Sec-Node-No',
      max_tokens: 'Max Tokens',
      temperature: 'Temperature',
      desc_optional: 'Description (optional)',
      cancel: 'Cancel',
      add: 'Add',
      placeholder_model_name: 'e.g. GPT-4o',
      placeholder_model_id: 'e.g. gpt-4o or F-G-98-...',
      placeholder_api_url: 'OpenAI: .../v1/chat/completions or CCB: .../ainlplm/chat',
      placeholder_api_key: 'Enter API Key or Access_Key_Id',
      placeholder_tx_code: 'e.g. A4011LM01',
      placeholder_sec_node: 'e.g. 400136',
      placeholder_desc: 'Brief model capability description',

      step1_title: 'Scenario Confirmation & Skeleton Customization',
      step1_subtitle: 'If the skeleton is wrong, everything is wrong — this step defines what knowledge in this domain should look like.',
      scenario_name: 'Scenario Name',
      scenario_content: 'Scenario Content',
      sub_scenarios: 'Sub-scenarios',
      add_sub_scenario: 'Add Sub-scenario',
      knowledge_columns: 'Knowledge Columns (customizable)',
      add_column: 'Add Column',
      reset_columns: 'Reset Defaults',
      hint_fixed_columns: 'The first four columns (scenario / scenario description / sub-scenario / sub-scenario description) are fixed; only knowledge columns are configured here.',
      output_format: 'Skeleton Output Format',
      output_format_excel: 'Generate Excel',
      output_format_markdown: 'Generate Markdown',
      hint_markdown_columns: 'When Markdown is selected, rich semantic columns such as stage, decision logic, and anti-patterns are automatically added to facilitate deep extraction in Step 2.',
      advanced_template: 'Advanced: Upload or select department Excel template',
      upload_template: 'Upload .xlsx template (highest priority)',
      choose_file: 'Choose File',
      no_file_chosen: 'No file chosen',
      samples_template: 'Or select an Excel template from samples',
      no_template: 'None (generate from columns above)',
      hint_upload_template: 'After uploading/selecting Excel, the file headers take precedence; custom knowledge columns are only recorded.',
      generate_skeleton: 'Generate Scenario Skeleton',
      step1_action_note: 'Customize knowledge columns and output format; subsequent steps still use the matching Excel to continue the pipeline.',
      step1_output_placeholder: 'Fill in scenario information and click "Generate Scenario Skeleton" to view results',
      placeholder_scenario_name: 'e.g. Credit Approval',
      placeholder_scenario_content: 'Describe the core business process, key decision points and knowledge characteristics of this scenario',
      placeholder_knowledge_column: 'e.g. specific method, decision logic',

      step2_title: 'Multi-source Knowledge Extraction',
      step2_subtitle: 'Solidify the 10% already explicit first — let experts face a draft to review rather than a blank Excel.',
      prev_output_label: 'Previous output (scenario anchoring template)',
      prev_output_empty: 'No previous output detected; please complete scenario anchoring first.',
      source_files: 'Knowledge Source Files (multi-select)',
      source_files_hint: 'Upload policies, manuals, case libraries (TXT/MD/DOCX/PDF); multi-select supported.',
      paste_source: 'Or paste text source',
      source_label_placeholder: 'Source label (e.g. Policy A)',
      paste_content_placeholder: 'Paste document content...',
      remove_title: 'Remove',
      add_more_source: 'Add More Text Sources',
      inherit_kb: 'Inherit existing knowledge base entries (participate in deduplication)',
      inherit_kb_hint_prefix: 'Matched knowledge base entries: ',
      choose_ability: 'Select Capability',
      skill_knowledge_extraction: 'Knowledge Extraction',
      skill_knowledge_extraction_desc: 'Excel template → Skill draft',
      skill_knowledge_extraction_hint: 'Upload a standard extraction template to generate an IR pre-draft (Markdown).',
      select_skill: '-- Select Skill --',
      extraction_style: 'Extraction Style',
      style_standard: 'Standard (8-22 items)',
      style_deep: 'Deep (12-40 items)',
      style_compact: 'Compact (5-10 items)',
      select_model: 'Select Model',
      generate_skill_md: 'Generate SKILL.md',
      execute_extraction: 'Run Extraction',
      step2_readiness_default: 'Please complete model and document selection before generating rules.',
      step2_no_pipeline: 'Please enter a pipeline from the overview first.',
      step2_no_model: 'Please configure and select a model first.',
      step2_no_source: 'Please upload at least one file or enter a text source.',
      step2_ready: 'Ready: knowledge extraction can be executed.',
      kb_hint_has_entries: 'Knowledge base has {count} related entries; after checking, they will participate in fusion and deduplication.',
      kb_hint_no_entries: 'No related knowledge base沉淀 yet (available for inheritance after the first pipeline is published).',
      step2_action_note: 'Upload knowledge documents and click generate rules; SQL generation becomes available after IR is generated.',

      step3_title: 'Knowledge Alignment',
      step3_subtitle: 'Review and revise the Skill pre-draft generated in Step 2 item by item.',
      s3_draft_title: 'Knowledge Extraction Draft',
      s3_draft_linked: 'Linked',
      s3_no_draft: 'No Step 2 extraction draft output',
      s3_no_draft_hint: 'Please complete the knowledge extraction step first.',
      revision_context: 'Revision Context',
      chat_history: 'Conversation History (Expert & Model)',
      chat_empty: 'No conversation yet. Enter a revision comment and send.',
      expert_input: 'Expert Input (this round)',
      expert_placeholder: 'Enter specific revision comments; leave blank or enter "no comment" and the system will automatically confirm the current draft as the aligned version.',
      upload_minutes: 'Or upload expert minutes file',
      align_style: 'Alignment Style',
      align_style_standard: 'Standard Revision',
      align_style_strict: 'Strict Revision',
      align_style_loose: 'Loose Revision',
      select_skill_default: '-- Select Skill --',
      select_skill_default_label: 'Reference Skill',
      send_revise: 'Send & Smart Revise',
      s3_align_hint: 'If there are no comments, you can click the button and the system will pass through the current draft as the aligned version.',
      s3_action_note: 'Experts can enter revision comments in multiple rounds; the model continuously updates alignment suggestions based on the conversation history.',
      signal_review: 'Signal Review',
      signal_blur: 'Boundary Blur',
      signal_island: 'Knowledge Island',
      signal_lowconf: 'Low Consensus',
      signal_conflict: 'Conflict',
      suggestion_pool: 'Suggestion Pool (Validation Feedback / Interview Conversion)',
      select_all: 'Select All / Deselect All',
      stat_accepted: 'Accepted ',
      stat_rejected: 'Rejected ',
      stat_pending: 'Pending ',
      stat_edited: 'Edited ',
      apply_suggestions: 'Adopt Selected → Generate New Aligned Draft',
      reject_suggestions: 'Reject Selected',
      refresh: 'Refresh',
      review_title: 'Alignment Suggestion Review',
      filter_all: 'All',
      filter_modify: 'Modify',
      filter_add: 'Add',
      filter_delete: 'Delete',
      filter_supplement: 'Supplement',
      accept_all: 'Accept All',
      reject_all: 'Reject All',
      back_to_edit: 'Back to Edit',
      online_edit_draft: 'Edit Draft Online',
      confirm_aligned: 'Confirm & Generate Aligned Draft',
      revise_skill_md: 'Revise SKILL.md (SQL in code blocks can be edited directly):',

      step4_title: 'Generate Three Deliverables',
      step4_subtitle: 'Generate chain-of-thought, QA pairs and OpenClaw-compatible Skill in one pass, covering reasoning, Q&A and Agent-skill consumption scenarios.',
      s4_input_draft: 'Knowledge Aligned Draft',
      s4_no_aligned: 'No aligned draft; please complete knowledge alignment first.',
      skill_generator: 'Skill Generator (built-in)',
      select_skill_label: 'Select Skill',
      generate_deliverables: 'Generate Skill + CoT + QA Pairs',
      step4_action_note: 'LLM parses the Step 3 aligned draft and generates three deliverables: QA pairs, chain-of-thought, and an Agent-Skill pending validation.',
      step4_output_placeholder: 'Click "Generate" to create the three deliverables',

      step5_title: 'Decision Replay & Feedback',
      step5_subtitle: 'Use the final SKILL to judge historical cases and compare with expert conclusions; disagreements automatically generate revision suggestions and flow back to knowledge alignment.',
      s5_validation_target: 'Validation Target',
      s5_deliverable_title: 'Step 4 Deliverables',
      s5_deliverable_linked: 'Validated',
      s5_no_deliverables: 'No Step 4 deliverables',
      s5_no_deliverables_hint: 'Please complete the knowledge delivery step first.',
      test_data_source: 'Test Data Source',
      all_test_customers: 'All test_customers',
      run_replay: 'Run P/R/F1 Validation',
      step5_action_note: 'Run the agent-skill on the test_customers table and calculate precision/recall/F1 against expected results.',
      feedback_divergence: 'Feedback Divergence to Step 3',
      feedback_hint: 'Push validation disagreements into the Step 3 suggestion pool for expert review.',
      step5_output_placeholder: 'Run P/R/F1 validation to view metrics',

      excel_editor_title: 'Online Editor',
      save: 'Save',
      md_editor_title: 'SKILL.md Preview & Edit',
      download: 'Download',
      copy: 'Copy',
      edit_area: 'Edit',
      preview_area: 'Preview',
      md_placeholder: 'SKILL.md content...',
      excel_placeholder: 'Please upload an Excel file and click the "Online Edit" button',

      loading: 'Processing...',
    },
  };


  const DYNAMIC_PHRASES = {
  "隐性知识显性化 · 五步法": "Tacit Knowledge Externalization · 5 Steps",
  "隐性知识显性化 · 五步法萃取流水线": "Tacit Knowledge Externalization · 5-Step Pipeline",
  "新建流水线": "New Pipeline",
  "历史流水线": "Pipeline History",
  "五步法流程概览": "5-Step Process Overview",
  "将领域专家的隐性经验系统性显性化为 AI 可加载的结构化知识，通过五步法流水线，从场景定义到智能转化，层层递进、步步可追溯。": "Systematically externalize domain experts' tacit experience into AI-loadable structured knowledge through a 5-step pipeline, progressively traceable.",
  "场景锚定": "Scenario Anchoring",
  "知识萃取": "Knowledge Extraction",
  "知识对齐": "Knowledge Alignment",
  "智能转化": "Knowledge Delivery",
  "验证回放": "Validation Replay",
  "定义知识模板骨架，确定领域边界与字段规范，生成场景配置文件": "Define the knowledge template skeleton, domain boundaries and field standards, and generate the scenario config.",
  "从已有文档中提取知识条目，AI 辅助生成待审稿": "Extract knowledge entries from existing documents with AI-assisted draft generation.",
  "融合修订与确认，完成专家意见对齐并生成最终可发布稿": "Merge revisions and confirmations, align expert opinions, and generate the final publishable draft.",
  "生成思维链、QA 对、OpenClaw Skill 三类交付物": "Generate chain-of-thought, QA pairs and OpenClaw-compatible Skill deliverables.",
  "用 SKILL 终版判历史案例，分歧回流第3步形成闭环": "Judge historical cases with the final SKILL and feed disagreements back to Step 3 to close the loop.",
  "已完成": "Completed",
  "进行中": "In Progress",
  "继续": "Continue",
  "删除": "Delete",
  "进度": "Progress",
  "共": "Total",
  "搜索流水线名称、场景...": "Search pipeline name, scenario...",
  "暂无历史流水线，点击上方\"新建流水线\"开始": "No pipeline history; click \"New Pipeline\" above to start.",
  "流水线名称": "Pipeline Name",
  "业务领域": "Business Domain",
  "选择预设场景": "Select Preset Scenario",
  "信贷审批": "Credit Approval",
  "风控": "Risk Control",
  "营销": "Marketing",
  "自定义": "Custom",
  "输入自定义场景名称": "Enter custom scenario name",
  "创建并开始": "Create & Start",
  "取消": "Cancel",
  "请输入流水线名称": "Please enter pipeline name",
  "请选择或输入场景名称": "Please select or enter scenario name",
  "创建失败": "Create failed",
  "加载流水线失败": "Load pipeline failed",
  "确定删除该流水线？删除后不可恢复。": "Confirm delete this pipeline? It cannot be recovered.",
  "保存中...": "Saving...",
  "已保存": "Saved",
  "保存失败，点击重试": "Save failed, click to retry",
  "保存失败": "Save failed",
  "流水线已保存（含各步骤填写内容）": "Pipeline saved (including step inputs)",
  "请先创建或进入一条流水线": "Please create or enter a pipeline",
  "确定要清空当前流水线所有数据吗？此操作不可撤销。": "Clear all pipeline data? This cannot be undone.",
  "流水线已清空": "Pipeline cleared",
  "清空失败": "Clear failed",
  "已回退到第": "Rolled back to step",
  "回退失败": "Rollback failed",
  "请先完成第": "Please complete step",
  "未知错误": "Unknown error",
  "请求超时，请检查网络后重试": "Request timeout; please check network and retry",
  "请求超时，请检查 API 地址与网络连通性": "Request timeout; please check API URL and network connectivity",
  "已复制": "Copied",
  "复制": "Copy",
  "文件已保存": "File saved",
  "暂无可预览文件": "No file to preview",
  "加载失败": "Load failed",
  "网络错误": "Network error",
  "场景骨架生成成功": "Scenario skeleton generated successfully",
  "场景骨架已生成": "Scenario skeleton generated",
  "生成场景骨架": "Generate Scenario Skeleton",
  "请填写场景名称": "Please enter scenario name",
  "请先从总览页「新建流水线」或「继续」进入一条流水线，再生成场景骨架": "Please enter a pipeline from the overview via \"New Pipeline\" or \"Continue\" before generating the skeleton.",
  "请至少添加一列知识字段，或上传/选用 Excel 模板": "Please add at least one knowledge column or upload/select an Excel template.",
  "工作表": "Worksheets",
  "子场景": "Sub-scenarios",
  "列": "columns",
  "行": "rows",
  "来源：": "Source:",
  "模板": "Template",
  "未命名": "Unnamed",
  "知识列：": "Knowledge columns:",
  "已按 Markdown 模式自动补齐富语义列，Step2 将按完整字段深度萃取。": "Markdown mode has auto-completed rich semantic columns; Step 2 will deeply extract by full fields.",
  "预览/编辑 Markdown": "Preview/Edit Markdown",
  "下载 Markdown 骨架": "Download Markdown Skeleton",
  "下载 Excel 骨架": "Download Excel Skeleton",
  "预览 Excel": "Preview Excel",
  "子场景名称": "Sub-scenario name",
  "子场景内容描述": "Sub-scenario description",
  "如：具体方法、判断逻辑": "e.g. specific method, decision logic",
  "添加子场景": "Add Sub-scenario",
  "添加列": "Add Column",
  "恢复默认列": "Reset Defaults",
  "知识列（可自定义）": "Knowledge Columns (customizable)",
  "高级：上传或选用部门 Excel 模板": "Advanced: upload or select department Excel template",
  "上传 .xlsx 模板（优先级最高）": "Upload .xlsx template (highest priority)",
  "未选择": "No file chosen",
  "或选用 samples 中的 Excel 模板": "Or select an Excel template from samples",
  "不使用（按上方自定义列生成）": "None (generate from columns above)",
  "上传/选用 Excel 后，将按文件表头为准，自定义知识列仅作记录": "After uploading/selecting Excel, file headers take precedence; custom columns are for reference only.",
  "场景内容": "Scenario Content",
  "输出格式": "Output Format",
  "系统生成 Excel": "Generate Excel",
  "系统生成 Markdown": "Generate Markdown",
  "选择 Markdown 时，将自动补齐环节、判断逻辑、反模式等富语义列，便于 Step2 深度萃取": "Markdown automatically adds rich semantic columns such as stage, decision logic and anti-patterns for deep Step 2 extraction.",
  "填写场景信息后点击\"生成场景骨架\"查看结果": "Fill scenario info and click \"Generate Scenario Skeleton\" to view results.",
  "如：信贷审批": "e.g. Credit Approval",
  "描述该场景的核心业务流程、关键判断点和知识特征": "Describe the core process, key decision points and knowledge characteristics.",
  "如：信贷、风控、营销（默认同场景名称）": "e.g. credit, risk, marketing (defaults to scenario name)",
  "在线编辑": "Online Editor",
  "编辑区": "Edit Area",
  "预览区": "Preview Area",
  "SKILL.md 内容...": "SKILL.md content...",
  "请上传 Excel 文件后点击\"在线编辑\"按钮": "Please upload an Excel file and click the \"Online Edit\" button",
  "未修改": "Not modified",
  "已修改（未保存）": "Modified (unsaved)",
  "正在加载 Excel 数据...": "Loading Excel data...",
  "读取 Excel 失败": "Read Excel failed",
  "读取失败": "Read failed",
  "请先上传 Excel 文件": "Please upload Excel file first",
  "无源文件路径，请重新上传": "No source file path; please re-upload",
  "场景骨架": "Scenario Skeleton",
  "修订稿": "Revision Draft",
  "最终稿": "Final Draft",
  "下载 Excel": "Download Excel",
  "表格编辑器加载异常": "Spreadsheet editor load error",
  "没有可下载的 IR": "No IR available for download",
  "在线编辑：知识对齐稿": "Online Edit: Knowledge Aligned Draft",
  "在线编辑：萃取底稿（执行后生成知识对齐稿）": "Online Edit: Extraction Draft (aligned draft generated after execution)",
  "Excel 已保存，但流水线同步失败": "Excel saved, but pipeline sync failed",
  "执行知识萃取": "Run Knowledge Extraction",
  "选择模型": "-- Select Model --",
  "选择 Skill": "-- Select Skill --",
  "选择能力": "Select Capability",
  "Excel模板 → Skill预萃稿": "Excel template → Skill pre-draft",
  "上传标准萃取模板，生成 IR 预萃稿（Markdown）": "Upload standard extraction template to generate IR pre-draft (Markdown).",
  "萃取风格": "Extraction Style",
  "标准萃取（8-22条）": "Standard Extraction (8-22)",
  "深度萃取（12-40条）": "Deep Extraction (12-40)",
  "精简萃取（5-10条）": "Compact Extraction (5-10)",
  "生成 SKILL.md": "Generate SKILL.md",
  "执行中": "Executing",
  "· 通常 10-60s": "· usually 10-60s",
  "知识萃取完成": "Knowledge Extraction Complete",
  "共提取": "Extracted",
  "条知识": "knowledge items",
  "源": "sources",
  "去重": "dedup",
  "已生成": "Generated",
  "Skill 草稿 v": "Skill draft v",
  "（初版，待专家对齐）": "(initial draft, pending expert alignment)",
  "预览 Skill 草稿": "Preview Skill Draft",
  "下载草稿 Markdown": "Download Draft Markdown",
  "下载草稿 JSON (IR)": "Download Draft JSON (IR)",
  "信号报告": "Signal Report",
  "边界模糊": "Boundary Blur",
  "知识孤岛": "Knowledge Island",
  "共识度低": "Low Consensus",
  "冲突": "Conflict",
  "请先补全执行条件": "Please complete execution conditions",
  "萃取失败": "Extraction failed",
  "请至少上传一个文件或填入文本来源": "Please upload at least one file or enter a text source",
  "个文件": "files",
  "（已缓存）": "(cached)",
  "检测中...": "Detecting...",
  "当前无流水线": "No current pipeline",
  "检测失败，可手动上传": "Detection failed; upload manually",
  "请先在「场景锚定」点击「生成场景骨架」（需已从总览进入当前流水线）": "Please first click \"Generate Scenario Skeleton\" in Scenario Anchoring (enter the current pipeline from overview).",
  "场景模板": "Scenario Template",
  "领域：": "Domain:",
  "文件：": "File:",
  "已就绪": "Ready",
  "上一步输出件（场景锚定模板）": "Previous output (scenario anchoring template)",
  "尚未检测到上一步输出，请先完成场景锚定": "No previous output detected; please complete scenario anchoring first.",
  "知识来源文件（可多选）": "Knowledge Source Files (multi-select)",
  "上传待萃取的制度文件、操作手册、案例库（TXT/MD/DOCX/PDF），支持多选": "Upload policies, manuals and case libraries (TXT/MD/DOCX/PDF); multi-select supported.",
  "或粘贴文本来源": "Or paste text source",
  "来源标注（如：制度文件A）": "Source label (e.g. Policy A)",
  "粘贴文档内容...": "Paste document content...",
  "移除": "Remove",
  "添加更多文本来源": "Add more text sources",
  "继承知识库已沉淀知识（作为融合源参与去重）": "Inherit existing knowledge base entries (participate in deduplication)",
  "知识库已有": "Knowledge base has",
  "条相关知识，勾选后将与新萃取结果融合去重": "related entries; checked entries will be fused and deduplicated with new results.",
  "知识库暂无相关沉淀（首条流水线发布后可供后续继承）": "No related deposits in knowledge base (available for inheritance after first pipeline is published).",
  "请补全模型与文档后点击生成规则": "Please complete model and documents before generating rules.",
  "上传知识文档后点击生成规则，IR 生成后可点击生成 SQL": "Upload knowledge documents and click generate rules; SQL generation available after IR is generated.",
  "处理中...": "Processing...",
  "加载中...": "Loading...",
  "下载 SKILL.md": "Download SKILL.md",
  "SKILL.md 已生成": "SKILL.md generated",
  "加载上一步产出...": "Loading previous output...",
  "已配置模型": "Configured Models",
  "暂无模型配置": "No model configured",
  "添加自定义模型": "Add Custom Model",
  "编辑预设模型": "Edit Preset Model",
  "编辑自定义模型": "Edit Custom Model",
  "模型名称": "Model Name",
  "接口类型": "API Type",
  "OpenAI 兼容": "OpenAI Compatible",
  "建行 ainlplm": "CCB ainlplm",
  "模型标识 (model)": "Model ID",
  "API 地址": "API URL",
  "API Key / Access_Key_Id": "API Key / Access_Key_Id",
  "Tx-Code": "Tx-Code",
  "Sec-Node-No": "Sec-Node-No",
  "Max Tokens": "Max Tokens",
  "Temperature": "Temperature",
  "描述（可选）": "Description (optional)",
  "添加": "Add",
  "保存": "Save",
  "如: GPT-4o": "e.g. GPT-4o",
  "如: gpt-4o 或 F-G-98-...": "e.g. gpt-4o or F-G-98-...",
  "OpenAI: .../v1/chat/completions 或建行: .../ainlplm/chat": "OpenAI: .../v1/chat/completions or CCB: .../ainlplm/chat",
  "输入 API Key 或 Access_Key_Id": "Enter API Key or Access_Key_Id",
  "如: A4011LM01": "e.g. A4011LM01",
  "如: 400136": "e.g. 400136",
  "模型能力简述": "Brief model capability description",
  "编辑": "Edit",
  "测试连接": "Test Connection",
  "流式测试": "Stream Test",
  "流式中...": "Streaming...",
  "流式完成": "Stream complete",
  "流式失败": "Stream failed",
  "流式连接": "Streaming connection",
  "测试中...": "Testing...",
  "连接成功": "Connection successful",
  "连接失败": "Connection failed",
  "名称、模型标识、API 地址均为必填": "Name, model ID and API URL are required",
  "添加模型时 API Key 为必填": "API Key is required when adding a model",
  "建行接口需填写 Tx-Code 与 Sec-Node-No": "CCB interface requires Tx-Code and Sec-Node-No",
  "加载模型失败": "Load model failed",
  "确定删除模型": "Confirm delete model",
  "预设": "Preset",
  "建行": "CCB",
  "OpenAI": "OpenAI",
  "模型": "Model",
  "已注册技能": "Registered Skills",
  "暂无已注册的 Skill": "No registered Skills",
  "已启用": "Enabled",
  "已禁用": "Disabled",
  "加载详情...": "Loading details...",
  "详细说明": "Description",
  "业务价值": "Business Value",
  "使用步骤": "Usage Steps",
  "输入示例": "Input Example",
  "输出示例": "Output Example",
  "输入 / 输出": "Input / Output",
  "适用场景": "Applicable Scenarios",
  "核心能力": "Core Capabilities",
  "支持格式": "Supported Formats",
  "输出风格": "Output Styles",
  "触发条件": "Triggers",
  "局限性": "Limitations",
  "最大文件：": "Max file:",
  "版本：": "Version:",
  "关联步骤：": "Related step:",
  "知识对齐完成": "Knowledge Alignment Complete",
  "已生成对齐稿（共处理": "Aligned draft generated (processed",
  "处修订）": "revisions)",
  "已确认（无修订）": "Confirmed (no revisions)",
  "当前稿已作为对齐稿": "Current draft has been used as the aligned draft",
  "重新对齐": "Re-align",
  "在线编辑底稿": "Edit draft online",
  "确认并生成对齐稿": "Confirm & Generate Aligned Draft",
  "采纳": "Accept",
  "驳回": "Reject",
  "保存修改": "Save Edit",
  "无匹配的对齐建议": "No matching alignment suggestions",
  "审核进度": "Review progress",
  "修改": "Modify",
  "新增": "Add",
  "补充": "Supplement",
  "全部采纳": "Accept All",
  "全部驳回": "Reject All",
  "返回修改": "Back to Edit",
  "信号审核": "Signal Review",
  "建议池（验证回流 / 访谈转化）": "Suggestion Pool (Validation Feedback / Interview Conversion)",
  "全选 / 取消全选": "Select All / Deselect All",
  "已采纳": "Accepted",
  "已驳回": "Rejected",
  "待审": "Pending",
  "已编辑": "Edited",
  "采纳勾选建议 → 生成新对齐稿": "Adopt Selected → Generate New Aligned Draft",
  "驳回勾选建议": "Reject Selected Suggestions",
  "对齐建议审核": "Alignment Suggestion Review",
  "请先完成 Step2 萃取": "Please complete Step 2 extraction",
  "加载 IR 失败": "Load IR failed",
  "暂无 IR 条目": "No IR entries",
  "业务描述": "Business Description",
  "数据来源": "Data Source",
  "规则引用": "Rule Reference",
  "保存修订": "Save Revision",
  "重新生成 SQL": "Regenerate SQL",
  "修订已保存": "Revision saved",
  "部分字段保存失败": "Some fields failed to save",
  "流水线未加载": "Pipeline not loaded",
  "请先进入流水线": "Please enter a pipeline",
  "生成对齐稿失败": "Generate aligned draft failed",
  "请至少采纳一条对齐建议": "Please accept at least one alignment suggestion",
  "生成中...": "Generating...",
  "若无意见可直接点击按钮，系统将按预萃稿直通生成对齐稿": "If no comments, click the button and the system will pass through the pre-draft as the aligned draft.",
  "专家可多轮输入修订意见，模型会结合历史对话持续更新对齐建议。": "Experts can enter revision comments in multiple rounds; the model continuously updates alignment suggestions based on conversation history.",
  "无意见直通生成对齐稿": "No-comment pass-through to aligned draft",
  "未填写意见：将直接按预萃稿生成对齐稿（无修订）": "No comment entered: generate aligned draft from pre-draft (no revision).",
  "检测到“无修订”表达：将自动确认当前稿为对齐稿": "No-revision expression detected: current draft will be auto-confirmed as aligned draft.",
  "已检测到专家意见/材料：将按意见生成修订建议": "Expert comment/material detected: revision suggestions will be generated based on the comment.",
  "发送并智能修订": "Send & Smart Revise",
  "按当前稿生成对齐稿": "Generate aligned draft from current",
  "修订 SKILL.md（可直接编辑代码块中的 SQL）：": "Revise SKILL.md (SQL in code blocks can be edited directly):",
  "知识萃取稿": "Knowledge Extraction Draft",
  "已关联": "Linked",
  "暂无 Step2 萃取稿输出": "No Step 2 extraction draft output",
  "请先完成知识萃取节点": "Please complete the knowledge extraction step",
  "修订上下文": "Revision Context",
  "对话记录（专家与模型）": "Conversation History (Expert & Model)",
  "暂无对话。请先输入一条修订意见并发送。": "No conversation yet. Enter a revision comment and send.",
  "专家输入（本轮意见）": "Expert Input (this round)",
  "可填写具体修订意见；若无修改可留空或填写「暂无意见」，系统将自动确认当前萃取稿为对齐稿": "Enter specific revision comments; leave blank or enter \"no comment\" and the system will auto-confirm the current draft as the aligned draft.",
  "或上传专家纪要文件": "Or upload expert minutes file",
  "对齐风格": "Alignment Style",
  "标准修订": "Standard Revision",
  "严格修订": "Strict Revision",
  "宽松修订": "Loose Revision",
  "引用 Skill": "Reference Skill",
  "验证回流": "Validation Feedback",
  "访谈转化": "Interview Conversion",
  "新值：": "New value:",
  "含深挖补充": "Includes deep-dive supplements",
  "经验批注已记录 — 将在生成定稿时一并保存": "Tacit annotation recorded — will be saved when finalizing the draft.",
  "经验批注已保存": "Tacit annotation saved",
  "能分享一下这次修订背后的经验吗？": "Could you share the experience behind this revision?",
  "请补充您对本条的经验批注，以完善最终校验": "Please add your tacit annotation for this item to improve final validation.",
  "请说明本条在什么情况下可能产生误导，便于后续核查": "Please explain when this item could mislead, for later verification.",
  "请补充新增内容背后的判断经验，帮助其他人理解": "Please add the judgment experience behind the new content to help others understand.",
  "请补充您的经验批注，说明补充内容的依据": "Please add your annotation explaining the basis for the supplement.",
  "跳过": "Skip",
  "保存经验批注": "Save Tacit Annotation",
  "简要记录您的修订经验与判断依据...": "Briefly record your revision experience and rationale...",
  "建议 #": "Suggestion #",
  "清空字段": "Clear field",
  "删除条目": "Delete entry",
  "新增条目": "Add entry",
  "修改为：": "Change to:",
  " 条": " items",
  "原值": "Original value",
  "编号": "ID",
  "阶段": "Phase",
  "规则": "Rule",
  "业务描述：": "Business description:",
  "规则：": "Rule:",
  "SQL：": "SQL:",
  "待生成": "Pending generation",
  "编译完成": "Compile Complete",
  "交付包已生成": "Deliverable package generated",
  "版本": "Version",
  "Agent-Skill 可执行包 (.zip)": "Agent-Skill Executable Package (.zip)",
  "Step5 验证输入 (.json)": "Step5 Validation Input (.json)",
  "质量报告": "Quality Report",
  "五维度质量评估": "Five-dimension Quality Evaluation",
  "综合评分": "Overall Score",
  "质量等级": "Quality Grade",
  "维度详情": "Dimension Details",
  "完整性": "Completeness",
  "准确性": "Accuracy",
  "可操作性": "Actionability",
  "反模式覆盖": "Anti-pattern Coverage",
  "来源可溯": "Traceability",
  "下载质量报告": "Download Quality Report",
  "生成完成（": "Generation complete (",
  "条知识）": "knowledge items)",
  "QA 对": "QA Pairs",
  "用于 RAG 检索和 Step5 验证的问答对": "QA pairs for RAG retrieval and Step5 validation",
  "思维链": "Chain of Thought",
  "分步推理链条，供 Agent 决策参考": "Step-by-step reasoning chain for Agent decision reference",
  "待验证 Agent-Skill": "Agent-Skill Pending Validation",
  "可执行 Skill 包，供 Step5 验证回放": "Executable Skill package for Step5 validation replay",
  "生成失败": "Generation failed",
  "暂无知识对齐稿，请先完成知识对齐节点": "No aligned draft; please complete the knowledge alignment step.",
  "知识对齐稿": "Knowledge Aligned Draft",
  "Skill生成器（内置）": "Skill Generator (built-in)",
  "生成待验证 Skill + 思维链 + QA 对": "Generate pending Skill + CoT + QA pairs",
  "点击「生成」创建三个交付物": "Click \"Generate\" to create the three deliverables",
  "预览": "Preview",
  "下载": "Download",
  "QA 对预览（": "QA Pairs Preview (",
  "条）": "items)",
  "思维链预览": "Chain-of-Thought Preview",
  "已发布到知识库：新增": "Published to knowledge base: created",
  "条 · 更新": "items · updated",
  "发布失败": "Publish failed",
  "Step2 萃取 Markdown 预览": "Step2 Extraction Markdown Preview",
  "Step3 对齐 Markdown 预览": "Step3 Alignment Markdown Preview",
  "Step1 骨架 Markdown 预览": "Step1 Skeleton Markdown Preview",
  "Skill 草稿预览 (v": "Skill Draft Preview (v",
  "验证报告 (.json)": "Validation Report (.json)",
  "已执行验证回放（旧版）": "Validation replay executed (legacy)",
  "已就绪：可执行决策回放": "Ready: decision replay can be executed",
  "可执行（建议先在第 4 步编译 SKILL 终版）": "Executable (recommend compiling the final SKILL in Step 4 first)",
  "可冒烟验证（建议先完成知识对齐与转化）": "Smoke-test executable (recommend completing alignment and delivery first)",
  "请先完成知识萃取": "Please complete knowledge extraction first",
  "上次回放命中率：": "Last replay hit rate:",
  "查看报告": "View report",
  "Agent-Skill 交付包 v": "Agent-Skill Deliverable Package v",
  "编译完成，可供验证回放": "Compiled, ready for validation replay",
  "验证输入 (.json)": "Validation Input (.json)",
  "预览验证输入": "Preview Validation Input",
  "验证中...": "Validating...",
  "验证失败": "Validation failed",
  "分歧详情": "Mismatch Details",
  "期望:": "Expected:",
  "预测:": "Predicted:",
  "生成最终版 Agent-Skill": "Generate Final Agent-Skill",
  "最终版已生成": "Final version generated",
  "已反馈": "Feedback sent",
  "条建议到 Step3": "suggestions to Step3",
  "反馈失败": "Feedback failed",
  "回流失败": "Feedback failed",
  "请先完成前序步骤": "Please complete previous steps first",
  "测试数据来源": "Test Data Source",
  "全部 test_customers": "All test_customers",
  "执行 P/R/F1 验证": "Run P/R/F1 Validation",
  "SKILL 终版：": "Final SKILL:",
  "验证对象 = Step4 编译的最终交付物": "Validation target = final deliverable compiled in Step4",
  "尚未编译 SKILL 终版，将以 IR 渲染结果作为验证对象": "Final SKILL not yet compiled; IR rendered result will be used as validation target.",
  "尚未对齐，仅可做冒烟验证": "Not yet aligned; smoke test only.",
  "暂无可验证的 SKILL/草稿，请先完成前序步骤": "No SKILL/draft available for validation; please complete previous steps.",
  "验证输入 JSON（": "Validation Input JSON (",
  "专家": "Expert",

  "知识列": "Knowledge Columns",
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
  "知识描述": "Knowledge Description",

  "判断规则": "Judgment Rule",
  "操作流程": "Operation Process",
  "反模式": "Anti-pattern",

  "场景骨架": "Scenario Skeleton",
  "当前 SKILL.md": "Current SKILL.md",
  "专家反馈意见": "Expert Feedback",
  "修订要求": "Revision Requirements",
  "知识来源文档": "Knowledge Source Documents",
  "输出要求": "Output Requirements",
  "示例": "Example",
  "执行说明": "Execution Instructions",
  "知识规则": "Knowledge Rules",
  "附录：术语表": "Appendix: Glossary",
  "重要要求": "Important Requirements",
  "阶段一：客户筛选": "Stage 1: Customer Screening",
  "阶段二：客户数据匹配": "Stage 2: Customer Data Matching",
  "阶段三：原因归因": "Stage 3: Root Cause Analysis",
  "阶段四：决策建议": "Stage 4: Decision Recommendation",
  "交付物 1：QA 对（JSON 数组）": "Deliverable 1: QA Pairs (JSON array)",
  "交付物 2：思维链（Markdown）": "Deliverable 2: Chain-of-Thought (Markdown)",
  "交付物 3：Agent-Skill 可执行结构（JSON）": "Deliverable 3: Agent-Skill Executable Structure (JSON)"
};

  let _dynamicObserver = null;
  let _dynamicPhraseRegex = null;

  function _escapeRegExp(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  function _initDynamicPhraseRegex() {
    var keys = Object.keys(DYNAMIC_PHRASES).sort(function (a, b) { return b.length - a.length; });
    if (!keys.length) {
      _dynamicPhraseRegex = null;
      return;
    }
    var pattern = keys.map(_escapeRegExp).join('|');
    try {
      _dynamicPhraseRegex = new RegExp(pattern, 'g');
    } catch (e) {
      _dynamicPhraseRegex = null;
    }
  }

  function _translateDynamicText(text) {
    if (!_dynamicPhraseRegex) _initDynamicPhraseRegex();
    if (!_dynamicPhraseRegex) return text;
    return text.replace(_dynamicPhraseRegex, function (match) {
      return DYNAMIC_PHRASES[match] || match;
    });
  }

  function translateDynamic(root) {
    if (!root || currentLang === 'zh-CN') return;
    if (root.nodeType !== Node.ELEMENT_NODE && root.nodeType !== Node.TEXT_NODE) return;

    if (root.nodeType === Node.TEXT_NODE) {
      if (root.nodeValue && /[\u4e00-\u9fa5]/.test(root.nodeValue)) {
        var translated = _translateDynamicText(root.nodeValue);
        if (translated !== root.nodeValue) root.nodeValue = translated;
      }
      return;
    }

    var doc = root.ownerDocument || (typeof document !== 'undefined' ? document : null);
    if (!doc || !doc.createTreeWalker) return;
    var nodeFilter = function (n) {
      var parent = n.parentNode;
      if (parent && /^(script|style|textarea|noscript)$/i.test(parent.tagName)) return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    };
    var walker = doc.createTreeWalker(root, NodeFilter.SHOW_TEXT, nodeFilter, false);
    var n = walker.nextNode();
    while (n) {
      if (n.nodeValue && /[\u4e00-\u9fa5]/.test(n.nodeValue)) {
        var t = _translateDynamicText(n.nodeValue);
        if (t !== n.nodeValue) n.nodeValue = t;
      }
      n = walker.nextNode();
    }

    var elements = [root].concat(Array.prototype.slice.call(root.querySelectorAll('*')));
    for (var j = 0; j < elements.length; j++) {
      var el = elements[j];
      if (el.title && /[\u4e00-\u9fa5]/.test(el.title)) {
        el.title = _translateDynamicText(el.title);
      }
      if (el.placeholder && /[\u4e00-\u9fa5]/.test(el.placeholder)) {
        el.placeholder = _translateDynamicText(el.placeholder);
      }
    }
  }

  function _getObserveRoot() {
    var doc = window.document;
    return doc.querySelector('.app') || doc.body;
  }

  function startDynamicObserver() {
    var root = _getObserveRoot();
    if (!window.MutationObserver || _dynamicObserver || !root) return;
    var pending = [];
    var scheduled = false;
    var config = { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ['title', 'placeholder'] };

    _dynamicObserver = new MutationObserver(function (mutations) {
      if (currentLang === 'zh-CN') return;
      mutations.forEach(function (m) {
        if (m.type === 'characterData') {
          if (m.target && m.target.nodeType === Node.TEXT_NODE) pending.push(m.target);
        } else if (m.type === 'attributes') {
          pending.push(m.target);
        } else {
          Array.prototype.forEach.call(m.addedNodes, function (node) {
            pending.push(node);
          });
        }
      });
      if (pending.length && !scheduled) {
        scheduled = true;
        window.requestAnimationFrame(function () {
          if (!_dynamicObserver) return;
          _dynamicObserver.disconnect();
          var nodes = pending;
          pending = [];
          scheduled = false;
          nodes.forEach(function (node) { translateDynamic(node); });
          _dynamicObserver.observe(root, config);
        });
      }
    });
    _dynamicObserver.observe(root, config);
  }

  let currentLang = DEFAULT_LANG;

  function getLang() {
    return currentLang;
  }

  function setLang(lang) {
    if (!translations[lang]) lang = DEFAULT_LANG;
    currentLang = lang;
    try {
      localStorage.setItem(STORAGE_KEY, lang);
    } catch (_) { /* ignore */ }
    document.documentElement.lang = lang === 'zh-CN' ? 'zh-CN' : 'en';
    translateDocument();
    var app = document.querySelector('.app');
    if (app) translateDynamic(app);
    // Also translate modals/overlays that live outside .app
    ['#excel-editor-modal', '#markdown-editor-modal', '#model-overlay'].forEach(function (sel) {
      var el = document.querySelector(sel);
      if (el) translateDynamic(el);
    });
    startDynamicObserver();
    if (typeof window.onAppLangChange === 'function') {
      try { window.onAppLangChange(lang); } catch (_) { /* ignore */ }
    }
  }

  function t(key, fallback) {
    const val = translations[currentLang] && translations[currentLang][key];
    if (val != null) return val;
    if (fallback != null) return fallback;
    const def = translations[DEFAULT_LANG] && translations[DEFAULT_LANG][key];
    return def != null ? def : key;
  }

  function translateDocument() {
    document.querySelectorAll('[data-i18n]').forEach(function (el) {
      const val = t(el.getAttribute('data-i18n'), null);
      if (val != null) el.innerHTML = val;
    });
    document.querySelectorAll('[data-i18n-text]').forEach(function (el) {
      const val = t(el.getAttribute('data-i18n-text'), null);
      if (val != null) el.textContent = val;
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(function (el) {
      const val = t(el.getAttribute('data-i18n-placeholder'), null);
      if (val != null) el.placeholder = val;
    });
    document.querySelectorAll('[data-i18n-title]').forEach(function (el) {
      const val = t(el.getAttribute('data-i18n-title'), null);
      if (val != null) el.title = val;
    });
  }

  function cycleLanguage() {
    setLang(currentLang === 'zh-CN' ? 'en' : 'zh-CN');
  }

  function openLangPanel() {
    const panel = document.getElementById('lang-panel');
    const overlay = document.getElementById('model-overlay');
    if (panel) panel.classList.add('open');
    if (overlay) overlay.classList.remove('hidden');
    updateLangPanelSelection();
  }

  function closeLangPanel() {
    const panel = document.getElementById('lang-panel');
    const overlay = document.getElementById('model-overlay');
    if (panel) panel.classList.remove('open');
    if (overlay && !document.getElementById('skill-panel')?.classList.contains('open') && !document.getElementById('model-panel')?.classList.contains('open')) {
      overlay.classList.add('hidden');
    }
  }

  function updateLangPanelSelection() {
    document.querySelectorAll('.lang-option').forEach(function (opt) {
      opt.classList.toggle('active', opt.getAttribute('data-lang') === currentLang);
    });
  }

  function selectLang(lang) {
    if (translations[lang]) {
      setLang(lang);
      closeLangPanel();
    }
  }

  function init() {
    let saved = DEFAULT_LANG;
    try {
      saved = localStorage.getItem(STORAGE_KEY) || DEFAULT_LANG;
    } catch (_) { /* ignore */ }
    if (!translations[saved]) saved = DEFAULT_LANG;
    currentLang = saved;

    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', function () {
        setLang(saved);
      });
    } else {
      setLang(saved);
    }
  }

  const I18n = {
    getLang: getLang,
    setLang: setLang,
    t: t,
    translateDocument: translateDocument,
    translateDynamic: translateDynamic,
    cycleLanguage: cycleLanguage,
    openLangPanel: openLangPanel,
    closeLangPanel: closeLangPanel,
    selectLang: selectLang,
  };

  global.App = global.App || {};
  global.App.I18n = I18n;

  init();
})(window);

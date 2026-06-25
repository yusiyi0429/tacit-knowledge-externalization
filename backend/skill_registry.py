"""Skill registry — extracted from app_server.py."""

from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

SKILL_REGISTRY = {
    "knowledge-extraction": {
        "id": "knowledge-extraction",
        "name": "知识萃取",
        "version": "3.0.0",
        "description": "基于场景骨架和知识文档，通过LLM生成 Agent SKILL.md 初稿。",
        "prompt_template": "step2_generate_skill_md.txt",
        "related_step": 2,
        "enabled": True,
        "detailed_description": "知识萃取是隐性知识显性化流水线的核心入口。该 Skill 接收 Step1 生成的场景骨架（含业务领域、客户画像、营销目标）以及专家提供的知识文档（制度文件、案例复盘、培训材料等），调用大语言模型从中提炼出结构化的 Agent SKILL.md。\n\nSKILL.md 包含角色定位、核心流程、判断规则、数据取数逻辑等要素，是后续步骤的输入基础。",
        "business_value": "将散落在文档、制度、案例中的专家经验转化为机器可执行的 Agent Skill，大幅降低知识沉淀的人力成本。一次萃取可覆盖一个完整业务场景，后续通过流水线持续迭代。",
        "usage_guide": "1. 确保 Step1 场景锚定已完成，场景骨架已生成\n2. 准备知识文档（支持 .txt / .docx / .pdf，也可直接粘贴文本）\n3. 在界面中选择「Markdown 流水线」模式\n4. 选择模型后点击「执行知识萃取」\n5. 等待 LLM 生成 SKILL.md 初稿，预览并确认",
        "input_example": "场景：对公普惠客户潜力营销\n知识文档：科技型企业普惠贷款营销知识文档.txt（含客户筛选规则、数据标签、决策建议）",
        "output_example": "SKILL.md 文件，包含：角色定义（你是一名对公客户经理）、核心流程（客户筛选→需求分析→产品匹配→营销执行）、数据表引用（对公客户信息表、存款信息表等）、判断规则（准入条件、资质标签等）",
        "applicable_scenarios": ["对公客户潜力挖掘与营销", "普惠贷款产品推荐", "客户分层与精准营销", "新客户准入评估"],
        "capabilities": ["场景骨架解析", "知识文档理解", "规则与逻辑提炼", "Agent SKILL.md 生成"],
        "supported_formats": [".txt", ".docx", ".pdf", "纯文本粘贴"],
        "output_styles": ["结构化 SKILL.md", "含角色/流程/规则/数据"],
        "triggers": ["用户完成 Step1 场景锚定后", "用户上传知识文档并选择【知识萃取】"],
        "limitations": ["依赖输入的文档质量，文档信息不足时产出可能不完整", "LLM 生成的初稿需要专家在 Step3 对齐确认", "暂不支持图片/表格结构文档的深度解析"],
        "i18n": {
            "en": {
                "name": "Knowledge Extraction",
                "description": "Generate an Agent SKILL.md draft from scenario skeleton and knowledge documents via LLM.",
                "detailed_description": "Knowledge Extraction is the core entry point of the tacit-knowledge externalization pipeline. The Skill receives the scenario skeleton produced in Step 1 and expert-provided knowledge documents, then invokes a large language model to distill a structured Agent SKILL.md containing role definition, core processes, decision rules, and data access logic.\n\nSKILL.md is the foundational input for all downstream steps.",
                "business_value": "Convert expert experience scattered across documents, policies, and cases into machine-executable Agent Skills, significantly reducing the manual cost of knowledge沉淀. One extraction can cover a complete business scenario; the pipeline continuously iterates afterwards.",
                "usage_guide": "1. Ensure Step 1 Scenario Anchoring is completed and the skeleton is generated.\n2. Prepare knowledge documents (.txt / .docx / .pdf) or paste text directly.\n3. Select Markdown Pipeline mode in the UI.\n4. Select a model and click Run Knowledge Extraction.\n5. Wait for the LLM to generate the SKILL.md draft, preview and confirm.",
                "input_example": "Scenario: SME inclusive-loan potential-customer marketing. Knowledge document: english-loan-marketing-guide.txt (contains customer filtering rules, data tags, decision recommendations).",
                "output_example": "SKILL.md file containing role definition, core process (customer filter → demand analysis → product matching → marketing execution), data table references, and decision rules.",
                "applicable_scenarios": ["SME potential-customer mining and marketing", "Inclusive-loan product recommendation", "Customer segmentation and precision marketing", "New-customer admission assessment"],
                "capabilities": ["Scenario skeleton parsing", "Knowledge-document understanding", "Rule and logic extraction", "Agent SKILL.md generation"],
                "supported_formats": [".txt", ".docx", ".pdf", "plain text paste"],
                "output_styles": ["Structured SKILL.md", "Includes role/process/rules/data"],
                "triggers": ["User completes Step 1 Scenario Anchoring", "User uploads knowledge documents and selects Knowledge Extraction"],
                "limitations": ["Output quality depends on input document quality", "LLM-generated draft requires expert alignment in Step 3", "Does not yet support deep parsing of image/table-structured documents"],
            }
        },
    },
    "knowledge-revision": {
        "id": "knowledge-revision",
        "name": "知识对齐",
        "version": "3.0.0",
        "description": "基于专家自然语言反馈，通过LLM对 SKILL.md 进行修订对齐。",
        "prompt_template": "step3_align_with_expert.txt",
        "related_step": 3,
        "enabled": True,
        "detailed_description": "知识对齐是专家介入修订的核心环节。该 Skill 接收 Step2 生成的 SKILL.md 初稿，结合专家的自然语言反馈意见（如「客户筛选条件需要增加成立年限判断」「额度测算逻辑不对，参照 XX 制度」），调用 LLM 进行语义级修订并生成新版 SKILL.md。\n\n支持多轮修订：每轮反馈独立生成一个修订版本，不覆盖历史，专家可在界面中预览差异。",
        "business_value": "解决 LLM 初稿与专家实际经验之间的偏差。通过自然语言交互而非手动编辑，将专家的隐性判断（「正常情况怎么处理」「边界条件是什么」）快速融入知识体系，确保产出符合业务实际。",
        "usage_guide": "1. 查看 Step2 生成的 SKILL.md 初稿内容\n2. 在「专家反馈」输入框中用自然语言描述需要修改的内容\n3. 选择模型后点击「发送并智能修订」\n4. 预览修订后的 SKILL.md，如不满意可继续反馈\n5. 确认无误后进入 Step4",
        "input_example": "专家反馈：「客户筛选部分，科技型企业还要区分是否有有效专利，没有专利的即使有资质标签也不应该优先营销。在额度测算部分，补充一条规则：如果客户有他行信用贷款且正常还款，可以适度上浮额度。」",
        "output_example": "修订版 SKILL.md，在原文基础上：1) 客户筛选规则新增「有效专利判断」条件分支；2) 额度测算部分新增「他行信用贷款正常还款」上浮规则；3) 逻辑前后保持一致性",
        "applicable_scenarios": ["LLM 初稿需要领域专家审核修订", "业务规则或制度发生变更需要更新逻辑", "多轮迭代优化的知识条目"],
        "capabilities": ["自然语言反馈理解", "SKILL.md 语义级修订", "多轮修订版本管理", "修订日志与差异追踪"],
        "supported_formats": ["SKILL.md 全文修订"],
        "output_styles": ["修订版 SKILL.md", "含修订记录元信息"],
        "triggers": ["Step2 知识萃取完成", "专家在 Step3 界面提交反馈"],
        "limitations": ["单次反馈建议聚焦于一个方面，避免多主题混杂降低修订质量", "修改幅度受 LLM 上下文窗口限制（max_tokens=100000）", "无法保证自动验证修订逻辑的正确性，需专家人工确认"],
        "i18n": {
            "en": {
                "name": "Knowledge Alignment",
                "description": "Revise and align SKILL.md based on expert natural-language feedback via LLM.",
                "detailed_description": "Knowledge Alignment is the core step where experts participate in revision. The Skill receives the SKILL.md draft generated in Step 2, combines it with expert natural-language feedback (e.g., 'customer screening conditions need to add establishment-year judgment', 'the credit-limit calculation logic is wrong, refer to XX policy'), and invokes LLM to perform semantic-level revision to generate a new version of SKILL.md.\n\nSupports multi-round revision: each round of feedback independently generates a revision version without overwriting history, so experts can preview differences in the UI.",
                "business_value": "Resolves the deviation between LLM drafts and actual expert experience. Through natural-language interaction rather than manual editing, experts' tacit judgments ('how to handle normal cases', 'what are boundary conditions') are quickly integrated into the knowledge system, ensuring the output matches business reality.",
                "usage_guide": "1. Review the SKILL.md draft generated in Step 2.\n2. Describe the content that needs modification in natural language in the Expert Feedback input box.\n3. Select a model and click Send and Smart Revise.\n4. Preview the revised SKILL.md; continue giving feedback if not satisfied.\n5. After confirmation, proceed to Step 4.",
                "input_example": "Expert feedback: 'In the customer screening section, technology enterprises should also be distinguished by whether they have valid patents; those without patents should not be prioritized for marketing even if they have qualification tags. In the credit-limit calculation section, add a rule: if the customer has credit loans from other banks and is repaying normally, the limit can be moderately increased.'",
                "output_example": "Revised SKILL.md, based on the original text: 1) Customer screening rules add a new 'valid patent judgment' condition branch; 2) Credit-limit calculation section adds a new 'normal repayment of credit loans from other banks' increase rule; 3) Logic remains consistent throughout.",
                "applicable_scenarios": ["LLM drafts require domain expert review and revision", "Business rules or policies change and logic needs updating", "Knowledge entries for multi-round iterative optimization"],
                "capabilities": ["Natural-language feedback understanding", "SKILL.md semantic-level revision", "Multi-round revision version management", "Revision log and difference tracking"],
                "supported_formats": ["Full-text SKILL.md revision"],
                "output_styles": ["Revised SKILL.md", "Contains revision record metadata"],
                "triggers": ["Step 2 Knowledge Extraction completed", "Expert submits feedback in Step 3 UI"],
                "limitations": ["Single feedback should focus on one aspect; mixing multiple topics may reduce revision quality", "Revision amplitude is limited by LLM context window (max_tokens=100000)", "Cannot automatically verify correctness of revised logic; requires expert manual confirmation"],
            }
        },
    },
    "skill-generator": {
        "id": "skill-generator",
        "name": "Skill生成器",
        "version": "1.0.0",
        "description": "基于修订后的 SKILL.md，通过LLM生成 QA对、思维链和待验证 Agent-Skill。",
        "prompt_template": "step4_build_deliverables.txt",
        "related_step": 4,
        "enabled": True,
        "detailed_description": "Skill生成器是流水线的交付环节，将经过专家确认的 SKILL.md 转化为可直接分发的 Agent Skill 包。\n\n输出包含三部分：1) QA 对（Question-Answer 验证用例，用于评估 Skill 准确率）；2) 思维链（Chain-of-Thought，对核心判断逻辑的分步推演）；3) Agent-Skill 可执行包（含 SKILL.md、manifest.json、执行脚本等的 zip 压缩包，符合 agentskills.io 标准）。\n\n生成的 Agent-Skill 可在 Step5 中进行 P/R/F1 验证，通过后产生最终发布的 Skill zip。",
        "business_value": "从人工知识到可分发、可执行的 Agent Skill 的一键打包。生成的 QA 对可直接用于后续回归测试，思维链帮助新用户理解模型判断逻辑，zip 包可通过内网或平台分发给一线客户经理使用。",
        "usage_guide": "1. 确保 Step3 知识对齐已完成，SKILL.md 已确认\n2. 在 Step4 界面选择「构建 Skill」\n3. 等待 LLM 生成三份交付物：QA 对、CoT、Agent-Skill zip\n4. 预览 QA 对和思维链内容\n5. 进入 Step5 进行验证回放",
        "input_example": "输入：经 Step3 专家确认的对公普惠客户潜力营销 SKILL.md（含客户筛选规则、额度测算逻辑、产品推荐策略等完整内容）",
        "output_example": "输出三份文件：1) qa_*.json — 约 10-20 组 QA 对，覆盖准入判断、产品推荐、拒贷理由等场景；2) cot_*.md — 分步思维链，展示从客户信息到营销建议的完整推理路径；3) SKILL_VERIFY_*.zip — 可部署的 Agent Skill 包",
        "applicable_scenarios": ["SKILL.md 定稿后生成可交付 Skill", "需要 QA 验证数据集", "需要 Chain-of-Thought 解释逻辑"],
        "capabilities": ["SKILL.md 解析与重构", "QA 验证集自动生成", "Chain-of-Thought 推理链生成", "Agent-Skill zip 打包"],
        "supported_formats": ["SKILL.md → QA JSON + CoT Markdown + Skill zip"],
        "output_styles": ["结构化 QA 对", "Markdown 思维链", "agentskills.io 标准 zip"],
        "triggers": ["Step3 知识对齐完成并确认"],
        "limitations": ["QA 对的覆盖面和准确性受 SKILL.md 完整度影响", "思维链为 LLM 推导，可能存在推理盲区", "zip 包生成后需在 Step5 通过 P/R/F1 验证才能发布"],
        "i18n": {
            "en": {
                "name": "Skill Generator",
                "description": "Generate QA pairs, Chain-of-Thought, and an agent-ready Skill package from the revised SKILL.md via LLM.",
                "detailed_description": "Skill Generator is the delivery step of the pipeline, transforming the expert-confirmed SKILL.md into a directly distributable Agent Skill package.\n\nOutput contains three parts: 1) QA pairs (Question-Answer validation cases for evaluating Skill accuracy); 2) Chain-of-Thought (step-by-step deduction of core judgment logic); 3) Agent-Skill executable package (zip containing SKILL.md, manifest.json, execution scripts, etc., conforming to the agentskills.io standard).\n\nThe generated Agent-Skill can be validated in Step 5 with P/R/F1 metrics; after passing, the final released Skill zip is produced.",
                "business_value": "One-click packaging from human knowledge to distributable, executable Agent Skill. Generated QA pairs can be directly used for subsequent regression testing, Chain-of-Thought helps new users understand model judgment logic, and the zip package can be distributed to frontline account managers via intranet or platform.",
                "usage_guide": "1. Ensure Step 3 Knowledge Alignment is completed and SKILL.md is confirmed.\n2. Select Build Skill in the Step 4 UI.\n3. Wait for LLM to generate three deliverables: QA pairs, CoT, Agent-Skill zip.\n4. Preview QA pairs and Chain-of-Thought content.\n5. Proceed to Step 5 for validation replay.",
                "input_example": "Input: SME inclusive-loan potential-customer marketing SKILL.md confirmed by Step 3 expert (containing complete content such as customer screening rules, credit-limit calculation logic, product recommendation strategy).",
                "output_example": "Output three files: 1) qa_*.json — about 10-20 QA pairs covering admission judgment, product recommendation, rejection reasons, etc.; 2) cot_*.md — step-by-step Chain-of-Thought showing the complete reasoning path from customer information to marketing recommendations; 3) SKILL_VERIFY_*.zip — deployable Agent Skill package.",
                "applicable_scenarios": ["Generate deliverable Skill after SKILL.md finalization", "Need QA validation dataset", "Need Chain-of-Thought to explain logic"],
                "capabilities": ["SKILL.md parsing and reconstruction", "QA validation set auto-generation", "Chain-of-Thought reasoning chain generation", "Agent-Skill zip packaging"],
                "supported_formats": ["SKILL.md → QA JSON + CoT Markdown + Skill zip"],
                "output_styles": ["Structured QA pairs", "Markdown Chain-of-Thought", "agentskills.io standard zip"],
                "triggers": ["Step 3 Knowledge Alignment completed and confirmed"],
                "limitations": ["Coverage and accuracy of QA pairs depend on completeness of SKILL.md", "Chain-of-Thought is LLM-derived and may have reasoning blind spots", "After zip package generation, must pass P/R/F1 validation in Step 5 before release"],
            }
        },
    },
}


def get_skill_registry(lang: str = "zh-CN") -> dict:
    """Return a copy of SKILL_REGISTRY with metadata localized to ``lang``.

    Supported languages: ``zh-CN`` and ``en``. Unknown languages fall back to
    ``zh-CN``. Translations listed under ``skill["i18n"][lang]`` override the
    default Chinese top-level fields; fields without a translation keep their
    Chinese value. The ``i18n`` block itself is removed from the returned
    entries so callers receive a flat skill dict.
    """
    if lang not in {"zh-CN", "en"}:
        lang = "zh-CN"
    result = {}
    for sid, skill in SKILL_REGISTRY.items():
        entry = dict(skill)
        i18n = entry.pop("i18n", {})
        translations = i18n.get(lang, {})
        for key, value in translations.items():
            if key in entry:
                entry[key] = value
        result[sid] = entry
    return result


def get_prompt_template_path(template_name: str, locale: str = "zh-CN") -> Path:
    """Resolve a locale-aware prompt template path.

    For ``zh-CN`` (default) the original ``template_name`` is used unchanged.
    For other locales the function first tries ``{stem}.{locale}.txt`` and
    falls back to the original file when the localized version does not exist.
    """
    base = Path(template_name).stem
    suffix = "" if locale == "zh-CN" else f".{locale}"
    path = SCRIPT_DIR / "prompts" / f"{base}{suffix}.txt"
    if path.exists():
        return path
    return SCRIPT_DIR / "prompts" / template_name

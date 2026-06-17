"""Skill registry — extracted from app_server.py."""

SKILL_REGISTRY = {
    "knowledge-extraction": {
        "id": "knowledge-extraction",
        "name": "知识萃取",
        "version": "2.0.0",
        "description": "基于场景骨架和知识文档，通过LLM生成 Agent SKILL.md 初稿。",
        "prompt_template": "step2_generate_skill_md.txt",
        "related_step": 2,
        "enabled": True,
    },
    "knowledge-revision": {
        "id": "knowledge-revision",
        "name": "知识对齐",
        "version": "2.0.0",
        "description": "基于专家自然语言反馈，通过LLM对 SKILL.md 进行修订对齐。",
        "prompt_template": "step3_align_with_expert.txt",
        "related_step": 3,
        "enabled": True,
    },
    "skill-generator": {
        "id": "skill-generator",
        "name": "Skill生成器",
        "version": "1.0.0",
        "description": "基于修订后的 SKILL.md，通过LLM生成 QA对、思维链和待验证 Agent-Skill。",
        "prompt_template": "step4_build_deliverables.txt",
        "related_step": 4,
        "enabled": True,
    },
    "skill-creator": {
        "id": "skill-creator",
        "name": "Skill 生成器 (meta-skill)",
        "version": "1.0.0",
        "description": "将 pipeline 对齐定稿结合 golden 知识库，通过 LLM 生成可部署到 Hermes/OpenClaw 平台的 Agent SKILL.md。生成的 Skill 包含 SQL 知识匹配引擎、决策链和评估输出模板。",
        "detailed_description": (
            "这是一个「生成 Skill 的 Skill」——它的输入不是原始文档，而是流水线前三个步骤的产物（场景骨架、"
            "知识萃取稿、知识对齐定稿），以及预设的 golden 知识库（SQLite 数据库）。\n\n"
            "**核心能力**：\n"
            "- 自动读取 golden DB schema，生成引用真实表名/列名的 SQL 查询\n"
            "- 为每个「环节」构建决策链步骤（输入条件→匹配知识→输出建议→下一跳）\n"
            "- 生成标准化的 Agent 评估输出模板（匹配知识/置信度/建议动作/缺失信息）\n"
            "- 输出兼容 Hermes/OpenClaw SKILL.md 格式，可直接部署\n\n"
            "**工作原理**：\n"
            "1. 读取 Step3 对齐定稿中的知识条目（含环节/判断逻辑/反模式/适用条件等字段）\n"
            "2. 读取 golden_items 表的 Schema 和样例数据\n"
            "3. 调用 LLM 按照预设的 six-section 模板生成完整 SKILL.md（元数据→触发规则→SQL匹配引擎→决策链→输出模板→示例）\n"
            "4. 保存为 SKILL_*.md 文件，可下载部署"
        ),
        "usage_guide": (
            "1. 确保已完成「知识对齐」节点，生成了 final_*.xlsx 定稿\n"
            "2. 确保 golden 知识库存在（data/golden/golden_test.db）\n"
            "3. 在 Step4 点击「生成可执行 Agent Skill」\n"
            "4. 等待 LLM 生成（约 30-60s）\n"
            "5. 下载生成的 SKILL.md，部署到 Hermes/OpenClaw\n\n"
            "生成的 Skill 可直接加载到 Agent 平台——当用户提交贷款申请或案例复盘文档时，"
            "Agent 会自动触发此 Skill，执行 SQL 知识匹配并输出结构化评估报告。"
        ),
        "triggers": [
            "生成Agent Skill",
            "skill生成",
            "创建可执行skill",
            "skill creator",
            "meta skill",
            "可执行skill",
        ],
        "capabilities": [
            "从知识条目自动生成可执行 Agent SKILL.md",
            "整合 golden DB Schema 生成真实 SQL 知识匹配查询",
            "构建按环节组织的决策链（输入→匹配→输出→下一跳）",
            "生成标准化 Agent 评估输出模板（匹配知识/置信度/建议动作）",
            "输出兼容 Hermes / OpenClaw 平台格式",
        ],
        "requires": ["step3_alignment", "golden_database"],
        "produces": ["executable_skill_md"],
        "related_step": 4,
        "enabled": True,
    },
}

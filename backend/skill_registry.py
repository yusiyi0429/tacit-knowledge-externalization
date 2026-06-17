"""Skill registry — extracted from app_server.py."""

SKILL_REGISTRY = {
    "knowledge-extraction": {
        "id": "knowledge-extraction",
        "name": "知识萃取",
        "version": "1.0.0",
        "description": "从标准萃取模板（Excel）中自动提取结构化知识，生成 Skill 预萃稿（Markdown）。",
        "detailed_description": (
            "上传标准萃取模板 Excel 文件，系统通过大语言模型自动将模板中的场景锚定信息和知识文档"
            "抽取为结构化的 Skill 预萃稿。预萃稿为 Markdown 格式，包含场景说明和各条知识规则的业务描述、"
            "规则引用、数据来源和期望输出。\n\n"
            "**输出格式**：Skill 预萃稿（Markdown），不再生成 Excel 或 Markdown 交付包。\n\n"
            "**三种萃取风格**：\n"
            "标准（8-22条，平衡覆盖）、深度（12-40条，完整覆盖所有字段）、精简（5-10条，仅保留高价值高置信条目）"
        ),
        "usage_guide": (
            "1. 先在「场景锚定」完成场景定义\n"
            "2. 上传标准萃取模板 Excel 文件\n"
            "3. 选择萃取风格（不确定时用「标准萃取」）\n"
            "4. 选择模型，点击「执行知识萃取」\n"
            "5. 等待 LLM 生成，在下方面板查看 Markdown 预萃稿"
        ),
        "input_example": "上传《对公普惠场景标准萃取模板.xlsx》",
        "output_example": "生成 Skill IR，在前端以 Markdown / 表格视图展示，可下载为 skill_ir.json",
        "business_value": (
            "将散落在文档和个人经验中的知识，转化为团队可共享、可检索、可执行的结构化知识资产。"
            "案例复盘模式特别适合把老信贷员的「踩坑故事」转化为团队的「避坑指南」。"
        ),
        "applicable_scenarios": [
            "新业务制度发布后的知识入库",
            "老员工离职前的经验抢救",
            "案例复盘会后的结构化沉淀",
            "部门操作手册的知识化改造",
        ],
        "limitations": [
            "无法自动判断知识的正确性——萃取的可信度取决于输入文档的质量",
            "对极度专业的领域术语可能需要人工校验",
            "案例复盘模式需要专家愿意花时间填写结构化表单",
        ],
        "triggers": ["上传文档", "上传制度文件", "知识萃取", "知识预萃", "提取知识条目", "案例复盘"],
        "supported_formats": ["TXT", "MD", "DOCX", "PDF"],
        "max_file_size_mb": 50,
        "output_styles": ["标准萃取（8-22条）", "深度萃取（12-40条）", "精简萃取（5-10条）"],
        "capabilities": [
            "文档智能解析与分段",
            "知识条目结构化提取",
            "字段自动填充（知识分类/判断逻辑/适用条件）",
            "反模式与踩坑提示识别",
            "置信度自动评估",
            "案例复盘中的隐性信号检测（反模式/破例/直觉/关系依赖）",
        ],
        "related_step": 2,
        "enabled": True,
    },
    "knowledge-revision": {
        "id": "knowledge-revision",
        "name": "知识对齐",
        "version": "1.1.0",
        "description": "对 Step2 生成的 Skill 预萃稿逐条审核、修订，确认后生成对齐稿。",
        "detailed_description": (
            "Step2 生成的 Skill 预萃稿（Markdown格式）需要专家逐条审核。本Skill支持对预萃稿中的"
            "每条知识规则进行修改（修改规则引用/业务描述/数据来源），也可以重新生成对应的 SQL。\n\n"
            "**双视图对齐**：左侧为规则视图（业务描述、规则引用、数据来源），右侧为 SQL 视图（可手动编辑或重新生成）。"
            "修改后点击「保存修订」即写入版本历史。\n\n"
            "**无意见直通**：如果专家对预萃稿满意，点击「确认对齐」即可将预萃稿提升为对齐稿。"
        ),
        "usage_guide": (
            "1. 在下方面板查看 Step2 生成的 Skill 预萃稿（自动加载）\n"
            "2. 逐条审核每条知识的规则引用和 SQL\n"
            "3. 如需修改：直接在卡片中编辑字段后点击「保存修订」\n"
            "4. 如需重新生成 SQL：点击「重新生成 SQL」\n"
            "5. 确认无误后点击「确认对齐」，预萃稿提升为对齐稿"
        ),
        "input_example": "预萃稿中某条知识规则引用为「近2年无逾期记录」，专家改为「近1年无逾期且流水覆盖月均10万」",
        "output_example": "生成对齐 IR，版本号从 draft 变为 aligned，可进入 Step4 编译为 agent-skill 可执行包。",
        "business_value": (
            "传统方式下，专家的修订意见散落在微信、邮件、会议纪要中，修订理由往往丢失。"
            "本Skill把修订过程结构化，并将修订背后的隐性判断以版本历史形式保存——这是知识库中最珍贵的一层信息。"
        ),
        "applicable_scenarios": [
            "专家审核预萃稿并提出修改意见",
            "多人会议纪要需要合并为统一修订",
            "合规/风控部门对知识条目进行合规审查",
        ],
        "limitations": [
            "修订建议的质量依赖于专家输入的明确程度——模糊的意见会产生模糊的修订",
            "不适用于大量增删的场景",
        ],
        "triggers": ["知识对齐", "专家对齐", "最终确认", "生成对齐稿"],
        "supported_formats": ["IR v2 (JSON)"],
        "max_file_size_mb": 50,
        "output_styles": [],
        "capabilities": [
            "IR 结构解析与比对",
            "规则引用字段逐条编辑",
            "SQL 手动编辑与重新生成",
            "版本历史追踪",
            "无意见直通（不强制提交专家意见）",
        ],
        "related_step": 3,
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

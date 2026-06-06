-- ============================================================
-- MySQL 建表脚本 (从 SQLite golden_test.db 迁移)
-- 数据库: golden_knowledge
-- 用途:  银行信贷专家隐性知识库，支撑 Agent Skill 生成与验证
-- ============================================================

CREATE DATABASE IF NOT EXISTS golden_knowledge
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE golden_knowledge;

-- -----------------------------------------------------------
-- 1. golden_scenarios — 知识场景定义
-- -----------------------------------------------------------
CREATE TABLE golden_scenarios (
    id          INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(200) NOT NULL UNIQUE COMMENT '场景名称',
    description TEXT         NULL     COMMENT '场景说明',
    domain      VARCHAR(100) NOT NULL DEFAULT '通用' COMMENT '领域',
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='知识场景定义 (如：科技型企业普惠贷款全流程管理)';


-- -----------------------------------------------------------
-- 2. golden_documents — 源文档
-- -----------------------------------------------------------
CREATE TABLE golden_documents (
    id           INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    scenario_id  INT UNSIGNED NOT NULL COMMENT '所属场景',
    filename     VARCHAR(500) NOT NULL COMMENT '源文件名',
    content      LONGTEXT     NOT NULL COMMENT '文档全文',
    source_type  ENUM('制度','纪要','案例','访谈','培训','其他')
                              NOT NULL DEFAULT '其他' COMMENT '来源类型',
    created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_doc_scenario FOREIGN KEY (scenario_id)
        REFERENCES golden_scenarios(id) ON DELETE CASCADE,

    INDEX idx_doc_scenario (scenario_id),
    INDEX idx_doc_source_type (source_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='源文档 (制度手册/案例复盘/专家纪要等)';


-- -----------------------------------------------------------
-- 3. golden_items — 结构化知识条目
-- -----------------------------------------------------------
CREATE TABLE golden_items (
    id             INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    scenario_id    INT UNSIGNED NOT NULL COMMENT '所属场景',
    document_id    INT UNSIGNED NULL     COMMENT '来源文档',
    知识编号       VARCHAR(20)  NULL     COMMENT 'KN-001',
    环节           VARCHAR(50)  NULL     COMMENT '客户筛选/贷前尽调/审批决策/贷后监控...',
    具体方法       TEXT         NOT NULL COMMENT '可操作的具体做法',
    知识类型       ENUM('判断规则','操作流程','反模式')
                                 NULL     COMMENT '知识分类',
    适用条件       TEXT         NULL     COMMENT '什么情况下使用',
    判断逻辑       TEXT         NULL     COMMENT 'IF-THEN 结构化逻辑',
    反模式踩坑提示 TEXT         NULL     COMMENT '踩过的坑/不要做的事',
    经验判断       TEXT         NULL     COMMENT '专家的直觉/潜规则',
    适用边界       TEXT         NULL     COMMENT '此知识不适用的场景',
    例外情形       TEXT         NULL     COMMENT '规则何时可以破例',
    来源文档       VARCHAR(500) NULL     COMMENT '出处文件名',
    来源位置       VARCHAR(200) NULL     COMMENT '章节/段落',
    置信度         ENUM('高','中','低')
                                 NULL     COMMENT '知识可信度',
    贡献专家       VARCHAR(100) NULL     COMMENT '提供此知识的专家姓名',
    证据数         INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '支撑案例数',
    突破数         INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '被案例突破/质疑次数',
    created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_item_scenario FOREIGN KEY (scenario_id)
        REFERENCES golden_scenarios(id) ON DELETE CASCADE,
    CONSTRAINT fk_item_document FOREIGN KEY (document_id)
        REFERENCES golden_documents(id) ON DELETE SET NULL,

    INDEX idx_item_scenario (scenario_id),
    INDEX idx_item_document (document_id),
    INDEX idx_item_知识编号 (知识编号),
    INDEX idx_item_环节 (环节),
    INDEX idx_item_知识类型 (知识类型),
    INDEX idx_item_置信度 (置信度),
    INDEX idx_item_突破数 (突破数)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='结构化知识条目 (金色标准 · Agent Skill 的实际数据源)';


-- -----------------------------------------------------------
-- 4. verification_runs — Skill 验证运行记录
-- -----------------------------------------------------------
CREATE TABLE verification_runs (
    id                  INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    scenario_id         INT UNSIGNED NOT NULL COMMENT '所属场景',
    run_at              DATETIME     NULL     DEFAULT CURRENT_TIMESTAMP,
    pipeline_id         VARCHAR(50)  NULL     COMMENT '流水线 ID',
    step                TINYINT      NULL     COMMENT '验证步骤 (2/3/4)',
    total_golden_items  INT UNSIGNED NULL     COMMENT 'golden_items 总数',
    matched_items       INT UNSIGNED NULL     COMMENT 'pipeline 命中的条目数',
    pipeline_total      INT UNSIGNED NULL     COMMENT 'pipeline 输出的总条数',
    precision           DECIMAL(5,2) NULL     COMMENT '精确率',
    recall              DECIMAL(5,2) NULL     COMMENT '召回率',
    f1_score            DECIMAL(5,2) NULL     COMMENT 'F1 得分',
    field_match_rate    DECIMAL(5,2) NULL     COMMENT '字段级匹配率',
    extra_items_json    JSON         NULL     COMMENT 'pipeline 多出的条目',
    missing_items_json  JSON         NULL     COMMENT 'pipeline 遗漏的条目',
    mismatch_details_json JSON       NULL     COMMENT '不匹配详情',
    report_json         JSON         NULL     COMMENT '完整报告 (JSON)',

    CONSTRAINT fk_verify_scenario FOREIGN KEY (scenario_id)
        REFERENCES golden_scenarios(id) ON DELETE CASCADE,

    INDEX idx_verify_scenario (scenario_id),
    INDEX idx_verify_pipeline (pipeline_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Agent Skill 验证运行记录 (golden vs pipeline 对比)';

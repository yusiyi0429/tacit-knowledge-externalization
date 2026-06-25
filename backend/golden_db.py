#!/usr/bin/env python3
"""
Golden Test Database — 测试基准知识库
========================================
管理用于流水线回归验证的「期望输出」数据，支持：
  - 场景 / 输入文档 / 黄金条目 的 CRUD
  - 种子数据初始化（从 sample 数据提取）
  - 流水线输出 vs 黄金条目的自动对比（precision / recall / F1）

用法:
  python golden_db.py --init              # 初始化 DB + 种子数据
  python golden_db.py --list-scenarios     # 列出所有场景
  python golden_db.py --scenario <id> --items  # 列出场景下所有黄金条目
  python golden_db.py --verify <json_file> --scenario <id>  # 对比流水线输出
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from field_aliases import resolve_header
except Exception:  # pragma: no cover - field_aliases may not be importable in some contexts
    resolve_header = None

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_DIR = PROJECT_ROOT / "data" / "golden"
DB_PATH = DB_DIR / "golden_test.db"
SAMPLES_DIR = PROJECT_ROOT / "data" / "samples"

# 种子文档：filename → 实际 sample 文件路径（用于读取全文）
SEED_DOC_MAP = {
    "科技型企业普惠贷款营销知识文档.txt": (
        SAMPLES_DIR / "step2-文档萃取" / "科技型企业普惠贷款营销知识文档.txt"
    ),
    "案例复盘_01_芯片企业流水异常.txt": (
        SAMPLES_DIR / "step2-案例复盘" / "案例复盘_01_芯片企业流水异常.txt"
    ),
    "案例复盘_02_生物医药破例审批.txt": (
        SAMPLES_DIR / "step2-案例复盘" / "案例复盘_02_生物医药破例审批.txt"
    ),
    "Step3_专家会议纪要.txt": (
        SAMPLES_DIR / "step3-知识对齐" / "Step3_专家会议纪要.txt"
    ),
}

SEED_DOC_TYPES = {
    "科技型企业普惠贷款营销知识文档.txt": "制度",
    "案例复盘_01_芯片企业流水异常.txt": "案例",
    "案例复盘_02_生物医药破例审批.txt": "案例",
    "Step3_专家会议纪要.txt": "纪要",
}

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS golden_scenarios (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL UNIQUE,
    description   TEXT,
    domain        TEXT    DEFAULT '通用',
    created_at    TEXT    DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS golden_documents (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    scenario_id   INTEGER NOT NULL REFERENCES golden_scenarios(id) ON DELETE CASCADE,
    filename      TEXT    NOT NULL,
    content       TEXT    NOT NULL,
    source_type   TEXT    CHECK(source_type IN ('制度','纪要','案例','访谈','培训','其他')),
    created_at    TEXT    DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS golden_items (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    scenario_id   INTEGER NOT NULL REFERENCES golden_scenarios(id) ON DELETE CASCADE,
    document_id   INTEGER REFERENCES golden_documents(id) ON DELETE SET NULL,
    知识编号       TEXT,
    环节           TEXT,
    具体方法       TEXT    NOT NULL,
    知识类型       TEXT    CHECK(知识类型 IN ('判断规则','操作流程','反模式')),
    适用条件       TEXT,
    判断逻辑       TEXT,
    反模式踩坑提示  TEXT,
    经验判断       TEXT,
    适用边界       TEXT,
    例外情形       TEXT,
    来源文档       TEXT,
    来源位置       TEXT,
    置信度         TEXT    CHECK(置信度 IN ('高','中','低')),
    贡献专家       TEXT,
    证据数         INTEGER DEFAULT 0,
    突破数         INTEGER DEFAULT 0,
    created_at    TEXT    DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS verification_runs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    scenario_id         INTEGER NOT NULL REFERENCES golden_scenarios(id) ON DELETE CASCADE,
    run_at              TEXT    DEFAULT (datetime('now','localtime')),
    pipeline_id         TEXT,
    step                INTEGER CHECK(step IN (2,3,4)),
    total_golden_items  INTEGER,
    matched_items       INTEGER,
    pipeline_total      INTEGER,
    precision           REAL,
    recall              REAL,
    f1_score            REAL,
    field_match_rate    REAL,
    extra_items_json    TEXT,
    missing_items_json  TEXT,
    mismatch_details_json TEXT,
    report_json         TEXT
);

CREATE INDEX IF NOT EXISTS idx_items_scenario   ON golden_items(scenario_id);
CREATE INDEX IF NOT EXISTS idx_items_document   ON golden_items(document_id);
CREATE INDEX IF NOT EXISTS idx_documents_scenario ON golden_documents(scenario_id);
CREATE INDEX IF NOT EXISTS idx_runs_scenario    ON verification_runs(scenario_id);
CREATE INDEX IF NOT EXISTS idx_runs_run_at      ON verification_runs(run_at);
"""

# ---------------------------------------------------------------------------
# 种子数据 — 科技型企业普惠贷款
# ---------------------------------------------------------------------------

SEED_SCENARIO = {
    "name": "科技型企业普惠贷款全流程管理",
    "description": "面向高新技术企业、专精特新企业等科创属性企业的普惠贷款营销、贷后管理与不良分析全流程知识萃取",
    "domain": "银行信贷",
}

SEED_ITEMS = [
    # ===== 来自营销知识文档 =====
    {
        "知识编号": "KN-001",
        "环节": "客户筛选",
        "具体方法": "筛选归属当前网点、账户状态正常、具备科技标签（高新技术企业/专精特新/科技型中小企业/瞪羚/科技小巨人/创新型企业）且未办理普惠信用快贷的无贷户，输出本网点科技型无贷户清单",
        "知识类型": "操作流程",
        "适用条件": "对公营销拓客阶段，目标客群为科技型企业",
        "判断逻辑": "同时满足：归属当前网点 AND 账户正常 AND 具备至少一个科技标签 AND 未办理普惠信用快贷 → 纳入营销清单",
        "来源文档": "科技型企业普惠贷款营销知识文档",
        "来源位置": "第4.1节",
        "置信度": "高",
    },
    {
        "知识编号": "KN-002",
        "环节": "客户数据匹配",
        "具体方法": "校验企业准入条件：成立年限满X年、实控人年龄符合要求、征信良好无不良、纳税/流水/经营稳定、无多头借贷异常负债，输出符合信用快贷准入客户清单",
        "知识类型": "操作流程",
        "适用条件": "客户筛选完成后，对初步清单进行准入校验",
        "判断逻辑": "成立年限达标 AND 实控人年龄合规 AND 征信无不良 AND 经营数据稳定 AND 无多头借贷 → 准入通过",
        "来源文档": "科技型企业普惠贷款营销知识文档",
        "来源位置": "第4.2节",
        "置信度": "高",
    },
    {
        "知识编号": "KN-003",
        "环节": "原因归因",
        "具体方法": "将客户按三类核心原因分组：无融资需求（现金流充足/存款高/无资金缺口）、有意但不符合条件（曾申请被拒/年限不足/征信瑕疵）、产品不匹配/未触达（额度不够/利率偏高/不了解产品），分别制定营销策略",
        "知识类型": "判断规则",
        "适用条件": "客户数据匹配后，对不符合准入或未办理的客户进行归因分析",
        "判断逻辑": "IF 客户现金流充足且金融总量高 → 无融资需求; ELIF 客户有贷款意愿但被拒或条件不达标 → 有意不符合; ELSE → 产品不匹配/未触达",
        "来源文档": "科技型企业普惠贷款营销知识文档",
        "来源位置": "第4.3节",
        "置信度": "高",
    },
    {
        "知识编号": "KN-004",
        "环节": "营销策略",
        "具体方法": "无融资需求客户转向结算/现金池/票据池/资金归集和资产配置（大额存单/结构性存款/基金/黄金），长期跟踪定期回访等待需求窗口期",
        "知识类型": "操作流程",
        "适用条件": "客户归因为「无融资需求」类别",
        "来源文档": "科技型企业普惠贷款营销知识文档",
        "来源位置": "第4.4节(1)",
        "置信度": "高",
    },
    {
        "知识编号": "KN-005",
        "环节": "营销策略",
        "具体方法": "不符合准入条件客户：资料不全的指导补全财报/纳税/流水/知识产权；经营时间短的提升结算沉淀培育后再申报；征信瑕疵的持续跟踪修复后再申报。策略：培育、跟踪、等待达标",
        "知识类型": "操作流程",
        "适用条件": "客户归因为「有意但不符合条件」类别",
        "来源文档": "科技型企业普惠贷款营销知识文档",
        "来源位置": "第4.4节(2)",
        "置信度": "高",
    },
    {
        "知识编号": "KN-006",
        "环节": "营销策略",
        "具体方法": "产品不匹配/未触达客户：深度访谈了解真实需求，推荐善新贷/知识产权质押贷/抵押快贷/税贷，强调贴息/担保/线上审批/无抵押优势，快速触达/政策讲解/产品对比/上门服务",
        "知识类型": "操作流程",
        "适用条件": "客户归因为「产品不匹配/未触达」类别",
        "来源文档": "科技型企业普惠贷款营销知识文档",
        "来源位置": "第4.4节(3)",
        "置信度": "高",
    },
    {
        "知识编号": "KN-007",
        "环节": "营销风控",
        "具体方法": "不夸大额度、不承诺审批、不保证利率；严禁向空壳企业、无经营企业、异常征信企业、多头借贷客户营销",
        "知识类型": "反模式",
        "适用条件": "所有营销环节",
        "反模式踩坑提示": "夸大额度可能导致客户预期过高而投诉；承诺审批违反合规要求；向空壳或多头借贷客户营销会引入信用风险和监管处罚",
        "来源文档": "科技型企业普惠贷款营销知识文档",
        "来源位置": "第8章",
        "置信度": "高",
    },
    # ===== 来自营销知识文档（补充：客群画像/产品匹配/话术/流程/渠道） =====
    {
        "知识编号": "KN-015",
        "环节": "客群准入",
        "具体方法": "科技型企业认定依据七类标签：国家高新技术企业、国家级/省级/市级专精特新企业、科技型中小企业（入库）、瞪羚企业、科技小巨人企业、创新型企业、技术先进型服务企业。拥有发明专利/实用新型/软件著作权、研发投入稳定、纳税正常、经营满1年以上的企业优先纳入营销范围",
        "知识类型": "判断规则",
        "适用条件": "对公客户池初筛阶段，判断客户是否属于科技型客群",
        "判断逻辑": "企业持有至少一个科技标签（高新/专精特新/科小/瞪羚/小巨人/创新型/技术先进型）AND 研发投入稳定 AND 经营满1年 → 纳入科技型客群",
        "来源文档": "科技型企业普惠贷款营销知识文档",
        "来源位置": "第2.1节、第2.2节",
        "置信度": "高",
    },
    {
        "知识编号": "KN-016",
        "环节": "客户营销",
        "具体方法": "识别科技企业五大核心痛点并匹配产品：无抵押物→知识产权质押贷（盘活专利/软著）；研发投入大现金流紧→信用快贷（纯信用全线上）；审批周期长赶不上项目节点→线上秒批产品；不了解贴息担保政策→政策讲解+组合推荐；标准化产品不匹配→善新贷/善营贷定制方案",
        "知识类型": "判断规则",
        "适用条件": "与科技企业首次接触诊断阶段",
        "判断逻辑": "诊断痛点类型 → 匹配对应产品优势 → 强调痛点解决而非产品推销（需求诊断式营销）",
        "来源文档": "科技型企业普惠贷款营销知识文档",
        "来源位置": "第2.3节、第3章、第5.2节",
        "置信度": "高",
    },
    {
        "知识编号": "KN-017",
        "环节": "产品匹配",
        "具体方法": "根据企业资质特征推荐最优产品：有科创资质+纳税流水→信用快贷科创版（10万-500万纯信用全线上）；有专利/软著→知识产权质押贷（10万-300万盘活无形资产）；专精特新资质→善新贷（政府担保利率更低）；纳税开票数据好→善营贷/税贷（线上审批资料极简）；有少量房产厂房→抵押快贷（额度更高期限更长作为补充）",
        "知识类型": "判断规则",
        "适用条件": "客户准入通过后，根据企业具体资质选择最适配产品",
        "判断逻辑": "IF 专精特新 AND 有政府担保需求 → 善新贷; ELIF 有发明专利/软著→ 知识产权质押贷; ELIF 有纳税开票数据 → 善营贷/税贷; ELIF 有少量房产 → 抵押快贷; DEFAULT → 信用快贷科创版",
        "来源文档": "科技型企业普惠贷款营销知识文档",
        "来源位置": "第3章",
        "置信度": "高",
    },
    {
        "知识编号": "KN-018",
        "环节": "营销触达",
        "具体方法": "营销话术采用三段式结构：（1）开场：直接说明针对科技企业的科创普惠信用贷款，不需抵押，凭高新技术/专精特新/专利就能办，利率低、线上审批、当天出额度；（2）痛点破解：科技企业大多轻资产传统贷款不好批——不看厂房土地只看科创资质和经营情况，帮企业把专利软著变成可贷款的资产；（3）收尾：纯信用+利率低+审批快+可循环+政策贴息，资料简单线上办理不耽误经营",
        "知识类型": "操作流程",
        "适用条件": "首次触达科技型企业客户的营销通话或拜访场景",
        "来源文档": "科技型企业普惠贷款营销知识文档",
        "来源位置": "第5章",
        "置信度": "高",
    },
    {
        "知识编号": "KN-019",
        "环节": "业务办理",
        "具体方法": "科技型企业普惠贷款办理流程七步：客户筛选→资质初审→线上申请→数据核验→审批出额→签约放款→贷后管理。必备资料五件套：营业执照+法人身份证、科创资质证书（高企/专精特新/科小入库）、知识产权证书（专利/软著）、近两年纳税开票流水、财报经营合同（如需）",
        "知识类型": "操作流程",
        "适用条件": "客户确认意向后启动办理流程",
        "来源文档": "科技型企业普惠贷款营销知识文档",
        "来源位置": "第6章",
        "置信度": "高",
    },
    {
        "知识编号": "KN-020",
        "环节": "渠道拓客",
        "具体方法": "科技企业拓客五类最高效渠道按优先级排序：（1）科技园区/孵化器/产业园——直接触达聚集区；（2）科技局/工信局/中小企业服务中心——政府背书批量获客；（3）知识产权代理公司/专利所/科技服务机构——精准触达有专利企业；（4）会计师事务所/财税公司——通过财务数据发现优质客户；（5）存量对公客户挖掘+老客户转介绍——最低成本最高转化",
        "知识类型": "操作流程",
        "适用条件": "制定科技企业获客策略或分配营销资源时",
        "来源文档": "科技型企业普惠贷款营销知识文档",
        "来源位置": "第7章",
        "置信度": "高",
    },
    {
        "知识编号": "KN-021",
        "环节": "营销风控",
        "具体方法": "营销环节四条红线不可逾越：（1）不夸大额度——避免客户预期过高导致投诉；（2）不承诺审批——审批结果由系统+人工综合判定；（3）不保证利率——利率根据企业资质和当期政策浮动；（4）严禁向空壳企业、无经营企业、异常征信企业、多头借贷客户营销——优先营销真实经营、有研发、有资质的科技实体企业",
        "知识类型": "反模式",
        "适用条件": "所有营销环节的合规底线",
        "反模式踩坑提示": "夸大额度→客户投诉+监管处罚；承诺审批→审批不通过则失信于客户且违反合规要求；向空壳/多头借贷客户营销→信用风险敞口+不良率上升",
        "来源文档": "科技型企业普惠贷款营销知识文档",
        "来源位置": "第8章",
        "置信度": "高",
    },
    # ===== 来自案例复盘 =====
    {
        "知识编号": "KN-008",
        "环节": "贷前尽调",
        "具体方法": "核查流水时重点关注季度末规律性大额资金进出：若每个季度末最后一周有固定金额大额转入且3-5天内转出，须追查资金往来方的股权结构和关联关系，判断是否为流水过桥美化",
        "知识类型": "判断规则",
        "适用条件": "企业流水核查阶段，特别是报表数据漂亮但流水存在规律性异常的企业",
        "判断逻辑": "季度末规律性大额转入 AND 短期内等额转出 AND 往来方非正常客户/供应商 → 流水真实性存疑 → 查股权关联 + 现场核实 + 纳税申报与流水交叉比对",
        "反模式踩坑提示": "仅看审计报告和财务报表而不核查流水细节；被漂亮的资质和财务数据误导而忽略交易模式的异常规律",
        "经验判断": "审计报告数据太整齐的（各项指标刚好符合银行偏好），更要警惕——真实经营数据不可能这么工整",
        "来源文档": "案例复盘_01_芯片企业流水异常",
        "置信度": "高",
        "贡献专家": "信贷审批专家（匿名）",
    },
    {
        "知识编号": "KN-009",
        "环节": "贷前尽调",
        "具体方法": "放款前必须做二次征信核查，即使首次查询在1个月以内——小微企业实际控制人的信用状况变化非常快。同时应在贷前尽调时查询企业在其他银行的授信变化情况",
        "知识类型": "操作流程",
        "适用条件": "审批通过后、放款前的最后核查环节",
        "经验判断": "同事说这个案子太完美的时候，反而要更仔细地挑毛病",
        "反模式踩坑提示": "仅依赖首次征信结果放款，错过放款前实际控制人信用恶化的关键信号",
        "来源文档": "案例复盘_01_芯片企业流水异常",
        "置信度": "高",
        "贡献专家": "信贷审批专家（匿名）",
    },
    {
        "知识编号": "KN-010",
        "环节": "审批决策",
        "具体方法": "科技型企业不能仅用传统财务指标（净利润、营收、成立年限）衡量——净利润为负要看钱花到哪里去（研发 vs 挥霍）；轻资产但技术壁垒极高的企业可以考虑破例审批，前提是充分论证破例理由并设置安全垫（追加保证、限定用途、阶段报告）",
        "知识类型": "判断规则",
        "适用条件": "科技型企业的审批决策，特别是传统指标不达标但技术壁垒高、VC背书强的企业",
        "判断逻辑": "传统指标不达标 BUT 技术壁垒高 AND VC背书强 AND 现金安全垫充足 → 可考虑破例审批（降额+个保+用途限定+阶段监控）",
        "经验判断": "在我不熟悉的行业做决策前，找一个懂行的朋友聊一聊——他的一句话可能比我查三天的公开资料更有价值。创始人面谈时最有效的不是问你公司怎么样，而是问「你最担心什么」——坦率承认风险的创始人比满嘴稳赢的更值得信任",
        "适用边界": "谨慎用于市场天花板过低的领域（如患者数少于5万人的罕见病），即使技术成功市场规模也有限",
        "例外情形": "2024年某生物医药企业案例：成立不满3年+净利为负，但因创始人配置顶尖+VC1.2亿+18个月现金安全垫，破例批贷200万且按期收回",
        "反模式踩坑提示": "仅因企业技术概念好就放宽条件而不设安全垫；在不熟悉的行业用传统框架硬套而错过优质客户",
        "来源文档": "案例复盘_02_生物医药破例审批",
        "置信度": "高",
        "贡献专家": "信贷审批专家（匿名）",
    },
    # ===== 来自专家会议纪要（修订意见） =====
    {
        "知识编号": "KN-011",
        "环节": "营销触达",
        "具体方法": "采用「需求诊断式」营销而非产品推销式：先了解企业资金需求痛点（回款周期长/研发投入大/轻资产无抵押/对利率时效敏感），再根据痛点匹配推荐产品（信用快贷/知识产权质押贷/善新贷/税贷）",
        "知识类型": "操作流程",
        "适用条件": "首次接触科技型企业的营销场景",
        "判断逻辑": "先诊断痛点 → 再匹配产品 → 强调对应优势（如轻资产→知识产权质押贷→盘活无形资产）",
        "来源文档": "Step3_专家会议纪要",
        "置信度": "高",
        "贡献专家": "张主任（普惠金融部）",
    },
    {
        "知识编号": "KN-012",
        "环节": "贷后监控",
        "具体方法": "贷后风险预警指标必须包含「研发投入骤降」和「核心技术人员变动」两个非传统维度——研发投入骤降可能意味着企业资金链紧张或核心项目停滞；核心技术人员离职可能预示着技术路线调整或团队不稳定",
        "知识类型": "判断规则",
        "适用条件": "科技型企业贷后管理阶段",
        "判断逻辑": "研发投入环比骤降>30% OR 核心技术人员离职 → 触发风险预警 → 下户核查 + 阶段性监控强化",
        "经验判断": "科技企业的最核心资产是人——核心技术人员变动比财务指标恶化更早发出风险信号",
        "来源文档": "Step3_专家会议纪要",
        "置信度": "高",
        "贡献专家": "李经理（风险管理部）",
    },
    {
        "知识编号": "KN-013",
        "环节": "不良分析",
        "具体方法": "引入「科创属性衰减指数」作为风险预判参考：综合评估企业专利维持情况、研发投入占比变化、技术迭代速度，判断企业科创能力是否在衰减。科创属性持续衰减的企业应提前纳入关注名单",
        "知识类型": "判断规则",
        "适用条件": "不良贷款分析及风险预判阶段",
        "来源文档": "Step3_专家会议纪要",
        "置信度": "中",
        "贡献专家": "王研究员（科技金融研究中心）",
    },
    {
        "知识编号": "KN-014",
        "环节": "知识萃取",
        "具体方法": "知识萃取应重点提取「判断类知识」（在什么条件下做什么决策）和「规则类知识」（具体如何执行），而非仅停留在「信息类知识」（定义和概念是什么）。每条知识必须包含可行动的判断逻辑或操作步骤",
        "知识类型": "操作流程",
        "适用条件": "所有知识萃取场景",
        "来源文档": "Step3_专家会议纪要",
        "置信度": "高",
        "贡献专家": "张主任, 李经理, 王研究员",
    },
]

# ---------------------------------------------------------------------------
# Golden case field aliases (bilingual — supports English golden DB files)
# ---------------------------------------------------------------------------

_GOLDEN_CASE_FIELD_ALIASES = {
    "case_id": ["case_id", "案例编号", "id"],
    "customer_id": ["customer_id", "客户编号", "customer"],
    "step_phase": ["step_phase", "步骤阶段", "环节", "stage", "phase"],
    "customer_features": ["customer_features", "客户特征", "features", "input"],
    "expected_action": [
        "expected_action", "action", "结论", "期望动作", "预期动作", "decision",
    ],
    "knowledge_desc": [
        "knowledge_desc", "知识描述", "具体方法", "知识内容", "描述",
        "description", "method",
    ],
    "logic": ["logic", "判断逻辑", "判断规则", "逻辑", "judgment_logic"],
    "confidence": ["confidence", "置信度", "可信度"],
}


def _resolve_case_field(raw_field: str) -> str:
    """Map a raw case field name to a canonical English field name."""
    if not raw_field:
        return raw_field
    raw = str(raw_field).strip()

    # Leverage the project-wide alias resolver for overlapping knowledge fields.
    if resolve_header is not None:
        resolved = resolve_header(raw)
        if resolved and resolved != raw:
            if resolved == "knowledge_desc":
                return "knowledge_desc"
            if resolved == "judgment_logic":
                return "logic"
            if resolved == "confidence":
                return "confidence"
            if resolved == "stage":
                return "step_phase"

    for canonical, aliases in _GOLDEN_CASE_FIELD_ALIASES.items():
        if raw in aliases:
            return canonical
        if raw.lower() in [a.lower() for a in aliases]:
            return canonical
    return raw


def _normalize_case(case: dict) -> dict:
    """Normalize field names of a single golden case to canonical English keys."""
    normalized: dict[str, Any] = {}
    for key, value in case.items():
        canonical = _resolve_case_field(key)
        normalized[canonical] = value
    return normalized


def load_golden_cases(json_path: str | Path) -> list[dict]:
    """Load golden cases from a JSON file.

    Supports the following top-level shapes:
      - {"cases": [...]}
      - {"items": [...]}
      - {"records": [...]}
      - {"data": [...]}
      - [...]

    Field names are normalized to canonical English keys while unknown fields
    are preserved as-is.
    """
    path = Path(json_path)
    if not path.is_file():
        raise FileNotFoundError(f"Golden cases file not found: {path}")

    data = json.loads(path.read_text(encoding="utf-8"))

    if isinstance(data, dict):
        cases: list[dict] = []
        for key in ("cases", "items", "records", "data", "knowledge_items"):
            if key in data and isinstance(data[key], list):
                cases = data[key]
                break
        else:
            cases = [data]
    elif isinstance(data, list):
        cases = data
    else:
        cases = []

    return [_normalize_case(c) for c in cases if isinstance(c, dict)]


# ---------------------------------------------------------------------------
# 数据库核心操作
# ---------------------------------------------------------------------------


def get_db() -> sqlite3.Connection:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def reinit_db() -> int:
    """删除并重建所有表和数据。"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS verification_runs")
    cur.execute("DROP TABLE IF EXISTS golden_items")
    cur.execute("DROP TABLE IF EXISTS golden_documents")
    cur.execute("DROP TABLE IF EXISTS golden_scenarios")
    cur.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()
    return _seed_db()


def init_db() -> int:
    """创建表结构并写入种子数据（幂等）。返回种子条目数。"""
    conn = get_db()
    cur = conn.cursor()
    cur.executescript(SCHEMA_SQL)

    existing = cur.execute("SELECT id FROM golden_scenarios WHERE name = ?",
                           (SEED_SCENARIO["name"],)).fetchone()
    if existing:
        print(f"[SKIP] 种子数据已存在 (scenario_id={existing['id']})，使用 --reinit 重建")
        conn.close()
        return 0

    conn.close()
    return _seed_db()


def _seed_db() -> int:
    """写入种子数据（场景 + 文档 + 黄金条目）。"""
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO golden_scenarios (name, description, domain) VALUES (?,?,?)",
        (SEED_SCENARIO["name"], SEED_SCENARIO["description"], SEED_SCENARIO["domain"]),
    )
    scenario_id = cur.lastrowid

    # 从实际 sample 文件读取文档全文
    doc_ids = {}
    doc_count = 0
    for filename, filepath in SEED_DOC_MAP.items():
        if filepath.is_file():
            content = filepath.read_text(encoding="utf-8")
        else:
            print(f"[WARN] 源文件不存在，跳过文档: {filepath}")
            continue
        source_type = SEED_DOC_TYPES.get(filename, "其他")
        cur.execute(
            "INSERT INTO golden_documents (scenario_id, filename, content, source_type) VALUES (?,?,?,?)",
            (scenario_id, filename, content, source_type),
        )
        doc_ids[filename] = cur.lastrowid
        doc_count += 1

    # 写入黄金条目
    count = 0
    for item in SEED_ITEMS:
        doc_id = doc_ids.get(item.get("来源文档", ""))
        cur.execute(
            """INSERT INTO golden_items (
                scenario_id, document_id, 知识编号, 环节, 具体方法, 知识类型,
                适用条件, 判断逻辑, 反模式踩坑提示, 经验判断, 适用边界, 例外情形,
                来源文档, 来源位置, 置信度, 贡献专家, 证据数, 突破数
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                scenario_id, doc_id,
                item.get("知识编号"), item.get("环节"), item["具体方法"], item.get("知识类型"),
                item.get("适用条件"), item.get("判断逻辑"), item.get("反模式踩坑提示"),
                item.get("经验判断"), item.get("适用边界"), item.get("例外情形"),
                item.get("来源文档"), item.get("来源位置"), item.get("置信度"),
                item.get("贡献专家"), item.get("证据数", 0), item.get("突破数", 0),
            ),
        )
        count += 1

    conn.commit()
    conn.close()

    # 显示文档大小
    sizes = ", ".join(
        f"{f}={len(SEED_DOC_MAP[f].read_text(encoding='utf-8'))}字"
        for f in doc_ids if SEED_DOC_MAP.get(f, Path()).is_file()
    )
    print(f"[OK] 初始化完成: scenario_id={scenario_id}, {doc_count} 文档({sizes}), {count} 黄金条目")
    return count


# ---------------------------------------------------------------------------
# 查询
# ---------------------------------------------------------------------------

def list_scenarios() -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT s.*, COUNT(gi.id) AS item_count FROM golden_scenarios s "
        "LEFT JOIN golden_items gi ON gi.scenario_id = s.id "
        "GROUP BY s.id ORDER BY s.id"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_items(scenario_id: int) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM golden_items WHERE scenario_id = ? ORDER BY 知识编号", (scenario_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_documents(scenario_id: int) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT id, filename, source_type, length(content) AS content_len "
        "FROM golden_documents WHERE scenario_id = ? ORDER BY id",
        (scenario_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# 匹配与验证
# ---------------------------------------------------------------------------

# 用于匹配的关键字段权重
_MATCH_FIELDS = {
    "具体方法": 0.30,
    "知识类型": 0.10,
    "环节": 0.15,
    "适用条件": 0.15,
    "判断逻辑": 0.20,
    "反模式踩坑提示": 0.10,
}

# 用于对比的所有字段
_COMPARE_FIELDS = [
    "环节", "具体方法", "知识类型", "适用条件", "判断逻辑",
    "反模式踩坑提示", "经验判断", "适用边界", "例外情形",
    "来源文档", "置信度", "贡献专家",
]


def _normalize(text: str | None) -> str:
    """去空白/标点，全转小写，用于模糊匹配。"""
    if not text:
        return ""
    return re.sub(r"\s+", "", str(text)).lower()


def _token_overlap(a: str, b: str) -> float:
    """基于 2-gram 字符集的重叠率。"""
    na, nb = _normalize(a), _normalize(b)
    if not na or not nb:
        return 0.0
    set_a = {na[i : i + 2] for i in range(len(na) - 1)}
    set_b = {nb[i : i + 2] for i in range(len(nb) - 1)}
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def _field_similarity(field: str, golden_val: str, pipeline_val: str) -> float:
    """计算单个字段的相似度。短字段用精确匹配，长字段用 2-gram 重叠率。"""
    gv, pv = str(golden_val or "").strip(), str(pipeline_val or "").strip()
    if not gv and not pv:
        return 1.0
    if not gv or not pv:
        return 0.0
    if len(gv) < 30 and len(pv) < 30:
        return 1.0 if _normalize(gv) == _normalize(pv) else 0.0
    return _token_overlap(gv, pv)


def _item_similarity(golden: dict, pipeline: dict) -> float:
    """计算两个知识条目的加权相似度。"""
    score = 0.0
    for field, weight in _MATCH_FIELDS.items():
        gv = golden.get(field, "")
        pv = _pipeline_value(pipeline, field)
        score += weight * _field_similarity(field, gv, pv)
    return score


def _field_aliases(field: str) -> list[str]:
    """Return possible aliases used in pipeline output for a golden DB field.

    Supports both legacy Chinese keys and canonical English keys so that
    English pipeline output can be verified against the Chinese-schema DB.
    """
    aliases = {
        "具体方法": ["知识描述", "knowledge_desc", "description", "method", "具体方案"],
        "知识类型": ["knowledge_type", "type", "Knowledge Type"],
        "环节": ["stage", "step_phase", "步骤阶段", "Stage"],
        "适用条件": ["applicable_condition", "condition", "trigger", "Condition"],
        "判断逻辑": ["logic", "judgment_logic", "rule", "rules", "Logic"],
        "反模式踩坑提示": ["反模式", "踩坑提示", "anti_pattern", "pitfall", "caveat", "Anti-pattern"],
        "经验判断": ["expert_judgment", "expert_opinion", "experience_judgment", "Experience Judgment"],
        "适用边界": ["applicable_boundary", "boundary", "Boundary"],
        "例外情形": ["exception_case", "exception", "Exception"],
        "来源文档": ["来源", "source_doc", "source", "source_document", "Source Doc"],
        "置信度": ["confidence", "credibility", "Confidence"],
        "贡献专家": ["contributor", "contributing_expert", "Contributor"],
    }
    return aliases.get(field, [field])


def _pipeline_value(item: dict, field: str) -> Any:
    """Fetch a value from a pipeline item, trying field and its known aliases."""
    if field in item:
        return item[field]
    for alias in _field_aliases(field):
        if alias in item:
            return item[alias]
    return ""


def _best_match(golden: dict, pipeline_items: list[dict], used_indices: set[int],
                threshold: float = 0.35) -> tuple[int, float]:
    """找到 pipeline 输出中与 golden 条目最匹配的，跳过已使用的。返回 (index, score)。"""
    best_idx, best_score = -1, 0.0
    for i, pi in enumerate(pipeline_items):
        if i in used_indices:
            continue
        s = _item_similarity(golden, pi)
        if s > best_score:
            best_score = s
            best_idx = i
    return (best_idx, best_score) if best_score >= threshold else (-1, 0.0)


def verify(pipeline_output: list[dict],
           scenario_id: int | None = None,
           scenario_name: str | None = None,
           step: int = 2,
           pipeline_id: str = "",
           threshold: float = 0.35) -> dict:
    """对比流水线输出与黄金条目，返回完整验证报告。

    流水线输出的每条记录应包含：具体方法（或知识描述）、知识类型、环节、适用条件、判断逻辑 等字段。
    """
    conn = get_db()
    if scenario_id:
        golden_items = [dict(r) for r in conn.execute(
            "SELECT * FROM golden_items WHERE scenario_id = ?", (scenario_id,)
        ).fetchall()]
    elif scenario_name:
        row = conn.execute(
            "SELECT id FROM golden_scenarios WHERE name = ?", (scenario_name,)
        ).fetchone()
        if not row:
            conn.close()
            return {"status": "error", "message": f"场景不存在: {scenario_name}"}
        golden_items = [dict(r) for r in conn.execute(
            "SELECT * FROM golden_items WHERE scenario_id = ?", (row["id"],)
        ).fetchall()]
        scenario_id = row["id"]
    else:
        conn.close()
        return {"status": "error", "message": "必须指定 scenario_id 或 scenario_name"}

    total_golden = len(golden_items)
    pipeline_items = list(pipeline_output)
    pipeline_total = len(pipeline_items)

    if total_golden == 0:
        conn.close()
        return {"status": "error", "message": "该场景下无黄金条目"}

    # 全局贪心匹配：每次取相似度最高的 (golden, pipeline) 对
    import heapq
    pairs: list[tuple[float, int, int]] = []  # (-score, gi_idx, pi_idx) for max-heap
    for gi_idx, gi in enumerate(golden_items):
        for pi_idx, pi in enumerate(pipeline_items):
            s = _item_similarity(gi, pi)
            if s >= threshold:
                pairs.append((-s, gi_idx, pi_idx))
    heapq.heapify(pairs)

    used_golden: set[int] = set()
    used_pipeline: set[int] = set()
    matched_count = 0
    match_details = []
    field_scores = []

    while pairs:
        neg_s, gi_idx, pi_idx = heapq.heappop(pairs)
        if gi_idx in used_golden or pi_idx in used_pipeline:
            continue
        score = -neg_s
        used_golden.add(gi_idx)
        used_pipeline.add(pi_idx)
        matched_count += 1

        gi = golden_items[gi_idx]
        pi = pipeline_items[pi_idx]

        # 逐字段对比
        field_diffs = {}
        item_field_scores = {}
        for field in _COMPARE_FIELDS:
            gv_raw = gi.get(field, "")
            pv_raw = _pipeline_value(pi, field)
            gv = str(gv_raw or "").strip()
            pv = str(pv_raw or "").strip()
            fs = _field_similarity(field, gv_raw, pv_raw)
            item_field_scores[field] = round(fs, 2)
            if fs < 1.0 and (gv or pv):
                field_diffs[field] = {"golden": gv[:200], "pipeline": pv[:200], "similarity": round(fs, 2)}
        field_scores.append(item_field_scores)

        match_details.append({
            "golden_id": gi["知识编号"],
            "golden_method": gi["具体方法"][:80],
            "pipeline_index": pi_idx,
            "similarity": round(score, 3),
            "field_diffs": field_diffs if field_diffs else None,
        })

    missing_items = [
        {"golden_id": golden_items[i]["知识编号"],
         "golden_method": golden_items[i]["具体方法"][:80]}
        for i in range(total_golden) if i not in used_golden
    ]
    extra_items = [
        {"pipeline_index": i,
         "method": str(_pipeline_value(pipeline_items[i], "具体方法"))[:80]}
        for i in range(pipeline_total) if i not in used_pipeline
    ]

    # 指标
    precision = matched_count / pipeline_total if pipeline_total > 0 else 0.0
    recall = matched_count / total_golden if total_golden > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    # 字段级匹配率
    if field_scores:
        avg_field = {}
        for field in _COMPARE_FIELDS:
            vals = [fs[field] for fs in field_scores]
            avg_field[field] = round(sum(vals) / len(vals), 2)
        field_match_rate = round(
            sum(v for v in avg_field.values()) / len(avg_field), 2
        )
    else:
        avg_field = {}
        field_match_rate = 0.0

    report = {
        "status": "ok",
        "run_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "scenario_id": scenario_id,
        "step": step,
        "pipeline_id": pipeline_id,
        "threshold": threshold,
        "metrics": {
            "total_golden_items": total_golden,
            "pipeline_total": pipeline_total,
            "matched_items": matched_count,
            "missing_items": total_golden - matched_count,
            "extra_items": pipeline_total - matched_count,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1, 4),
            "field_match_rate": field_match_rate,
        },
        "field_scores": avg_field,
        "match_details": match_details,
        "missing_items": missing_items,
        "extra_items": extra_items,
    }

    # 持久化
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO verification_runs (
            scenario_id, run_at, pipeline_id, step,
            total_golden_items, matched_items, pipeline_total,
            precision, recall, f1_score, field_match_rate,
            extra_items_json, missing_items_json, mismatch_details_json, report_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            scenario_id,
            report["run_at"],
            pipeline_id,
            step,
            total_golden,
            matched_count,
            pipeline_total,
            round(precision, 4),
            round(recall, 4),
            round(f1, 4),
            field_match_rate,
            json.dumps(extra_items, ensure_ascii=False),
            json.dumps(missing_items, ensure_ascii=False),
            json.dumps([m for m in match_details if m.get("field_diffs")], ensure_ascii=False),
            json.dumps(report, ensure_ascii=False),
        ),
    )
    conn.commit()
    run_id = cur.lastrowid
    report["run_id"] = run_id
    conn.close()

    return report


def get_run_history(scenario_id: int | None = None, limit: int = 10) -> list[dict]:
    conn = get_db()
    query = (
        "SELECT vr.*, gs.name AS scenario_name FROM verification_runs vr "
        "JOIN golden_scenarios gs ON gs.id = vr.scenario_id "
    )
    params = ()
    if scenario_id:
        query += " WHERE vr.scenario_id = ?"
        params = (scenario_id,)
    query += " ORDER BY vr.run_at DESC LIMIT ?"
    params += (limit,)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# 报告格式化
# ---------------------------------------------------------------------------

def format_report(report: dict) -> str:
    if report.get("status") == "error":
        return f"[ERROR] {report.get('message')}"

    m = report["metrics"]
    lines = [
        "=" * 60,
        f"  验证报告 — 场景 #{report['scenario_id']}  Step {report['step']}",
        f"  时间: {report['run_at']}  |  阈值: {report['threshold']}",
        "=" * 60,
        "",
        "## 核心指标",
        f"  黄金条目: {m['total_golden_items']}  |  流水线产出: {m['pipeline_total']}",
        f"  匹配成功: {m['matched_items']}  |  遗漏: {m['missing_items']}  |  多余: {m['extra_items']}",
        "",
        f"  Precision (精确率): {m['precision']:.1%}",
        f"  Recall    (召回率): {m['recall']:.1%}",
        f"  F1 Score           : {m['f1_score']:.1%}",
        f"  字段级匹配率       : {m['field_match_rate']:.1%}",
        "",
    ]

    if report.get("field_scores"):
        lines.append("## 各字段匹配率")
        for field, score in report["field_scores"].items():
            bar = "#" * int(score * 20) + "-" * (20 - int(score * 20))
            lines.append(f"  {field:　<12s} {bar} {score:.0%}")
        lines.append("")

    if report.get("missing_items"):
        lines.append(f"## 遗漏条目 ({len(report['missing_items'])})")
        for item in report["missing_items"]:
            lines.append(f"  ✗ [{item['golden_id']}] {item['golden_method']}")
        lines.append("")

    if report.get("extra_items"):
        lines.append(f"## 多余条目 ({len(report['extra_items'])})")
        for item in report["extra_items"]:
            lines.append(f"  + [{item['pipeline_index']}] {item['method']}")
        lines.append("")

    # 字段差异（仅展示前5个）
    diffs = [m for m in report.get("match_details", []) if m.get("field_diffs")]
    if diffs:
        lines.append(f"## 字段差异 ({len(diffs)} 条匹配但有差异)")
        for d in diffs[:5]:
            lines.append(f"  [{d['golden_id']}] ↔ pipeline[{d['pipeline_index']}] similarity={d['similarity']}")
            for field, diff in d["field_diffs"].items():
                lines.append(f"    {field}: similarity={diff['similarity']}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_table(rows: list[dict], columns: list[str]):
    if not rows:
        print("  (无数据)")
        return
    widths = {c: max(len(c), max((len(str(r.get(c, ""))) for r in rows), default=0)) for c in columns}
    header = " | ".join(c.ljust(widths[c]) for c in columns)
    print(f"  {header}")
    print(f"  {'-' * len(header)}")
    for r in rows:
        print("  " + " | ".join(str(r.get(c, "")).ljust(widths[c]) for c in columns))


def main():
    # Windows GBK 终端兼容
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Golden Test Database")
    parser.add_argument("--init", action="store_true", help="初始化数据库与种子数据")
    parser.add_argument("--reinit", action="store_true", help="删除并重建数据库（保留验证历史）")
    parser.add_argument("--list-scenarios", action="store_true", help="列出所有场景")
    parser.add_argument("--scenario", type=int, help="指定场景 ID")
    parser.add_argument("--items", action="store_true", help="列出黄金条目")
    parser.add_argument("--docs", action="store_true", help="列出关联文档")
    parser.add_argument("--verify", type=str, metavar="JSON_FILE", help="对比流水线输出 JSON 文件")
    parser.add_argument("--step", type=int, default=2, help="验证步骤编号 (2/3/4, 默认 2)")
    parser.add_argument("--pipeline-id", type=str, default="", help="流水线 ID（用于记录）")
    parser.add_argument("--threshold", type=float, default=0.35, help="匹配相似度阈值 (默认 0.35)")
    parser.add_argument("--history", action="store_true", help="查看验证历史")
    parser.add_argument("--limit", type=int, default=10, help="历史记录条数")

    args = parser.parse_args()

    if args.reinit:
        reinit_db()
    elif args.init:
        init_db()
    elif args.list_scenarios:
        _print_table(list_scenarios(), ["id", "name", "domain", "item_count", "created_at"])
    elif args.history:
        _print_table(
            get_run_history(args.scenario, args.limit),
            ["id", "scenario_name", "step", "precision", "recall", "f1_score", "field_match_rate", "run_at"],
        )
    elif args.items and args.scenario:
        items = get_items(args.scenario)
        print(f"场景 #{args.scenario} 共 {len(items)} 条黄金条目:\n")
        for i in items:
            fields = []
            for f in ["知识编号", "环节", "知识类型", "具体方法"]:
                v = i.get(f, "")
                if v:
                    fields.append(f"{f}: {v}")
            print("  " + " | ".join(fields))
            if i.get("判断逻辑"):
                print(f"    判断逻辑: {i['判断逻辑'][:120]}")
            if i.get("反模式踩坑提示"):
                print(f"    反模式: {i['反模式踩坑提示'][:120]}")
            print()
    elif args.docs and args.scenario:
        _print_table(get_documents(args.scenario), ["id", "filename", "source_type", "content_len"])
    elif args.verify:
        with open(args.verify, "r", encoding="utf-8") as f:
            pipeline_output = json.load(f)
        if isinstance(pipeline_output, dict):
            # 尝试从常见格式中提取列表
            for key in ("items", "knowledge_items", "data", "records", "qa_pairs"):
                if key in pipeline_output and isinstance(pipeline_output[key], list):
                    pipeline_output = pipeline_output[key]
                    break
            else:
                pipeline_output = [pipeline_output] if not isinstance(pipeline_output, list) else list(pipeline_output.values())
        if not isinstance(pipeline_output, list):
            print("[ERROR] JSON 文件格式不支持：需要数组或包含 items/data/records 字段的对象")
            sys.exit(1)
        report = verify(
            pipeline_output,
            scenario_id=args.scenario,
            step=args.step,
            pipeline_id=args.pipeline_id,
            threshold=args.threshold,
        )
        print(format_report(report))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

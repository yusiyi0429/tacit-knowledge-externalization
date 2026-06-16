"""Tests for import_chen_kb.py"""
import sqlite3
import tempfile
from pathlib import Path

import pytest

# Add backend to path
import sys
BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from tools.import_chen_kb import classify_domain, read_markdown, truncate_summary
from knowledge_base import get_db


# ─── classify_domain tests ───────────────────────────────────────────────

def test_classify_domain_credit_risk():
    """识别信贷风控相关领域"""
    domain = classify_domain("信贷审批流程优化", "本文介绍风控模型与不良资产处置方法")
    assert domain == "银行信贷风控审批"


def test_classify_domain_credit_risk_keywords():
    """各信贷风控关键词独立命中"""
    for kw in ["信贷", "风控", "审批", "授信", "不良"]:
        domain = classify_domain(f"关于{kw}的文档", "这是一份文档")
        assert domain == "银行信贷风控审批", f"关键词 '{kw}' 未命中"


def test_classify_domain_customer_meeting():
    """识别金融科技出海客户交流领域"""
    domain = classify_domain("金融峰会期间总监与 BPI 交流的会议纪要", "与印尼 BPI 银行的客户交流")
    assert domain == "金融科技出海客户交流"


def test_classify_domain_customer_abbreviations():
    """海外银行缩写识别"""
    for kw in ["bpi", "shb", "jkb", "moniepoint"]:
        domain = classify_domain(f"与{kw.upper()}客户交流纪要", f"与{kw.upper()}银行会谈")
        assert domain == "金融科技出海客户交流", f"缩写 '{kw}' 未命中"


def test_classify_domain_enterprise_solution():
    """识别企业级银行解决方案销售领域"""
    domain = classify_domain("企业级银行解决方案销售培训", "本文介绍销售方法与解决方案设计")
    assert domain == "企业级银行解决方案销售"


def test_classify_domain_fallback():
    """未匹配任何领域时返回未分类"""
    domain = classify_domain("一篇无关的文档", "这里没有任何关键词匹配")
    assert domain == "未分类"


def test_classify_domain_priority_credit_over_others():
    """信贷风控优先级最高——含信贷+客户交流关键词时归信贷"""
    domain = classify_domain(
        "信贷审批与客户交流纪要",
        "这是一份关于信贷审批流程和客户交流的文档"
    )
    assert domain == "银行信贷风控审批", "信贷风控优先级应高于客户交流"


def test_classify_domain_case_insensitive():
    """大小写不敏感（搜索前已 lower）"""
    domain = classify_domain("BPI and SHB Meeting Notes", "Client meeting with JKB")
    assert domain == "金融科技出海客户交流"


# ─── truncate_summary tests ──────────────────────────────────────────────

def test_truncate_summary_no_truncation():
    """短文本不需要截断"""
    short = "这是一段短文本。"
    result = truncate_summary(short, max_len=500)
    assert result == short
    assert not result.endswith("...")


def test_truncate_summary_paragraph_boundary():
    """段落边界处截断"""
    # 构造：100个A + 段落边界 + 400个B，max_len=120 应该在 \n\n 处截断
    text = "A" * 100 + "\n\n" + "B" * 400
    result = truncate_summary(text, max_len=120)
    assert result.endswith("...")
    # 截断位置应在 \n\n 之前，所以不应包含 B
    assert "B" not in result


def test_truncate_summary_chinese_sentence_boundary():
    """中文句号边界处截断"""
    # 第一句。 (4 chars) + 第二句。 (4 chars) = 8 chars
    # max_len=8 -> truncated = '第一句。第二句。'
    # 。在 index=7, 7 > 8*0.5=4 -> 截断到 '第一句。第二句' + '...'
    text = "第一句。第二句。" + "X" * 500
    result = truncate_summary(text, max_len=8)
    assert "第一句。第二句" in result
    assert "X" not in result
    assert result.endswith("...")


def test_truncate_summary_newline_boundary():
    """行边界处截断（\n 在阈值范围内才截）——此 case 验证 fallback 行为"""
    # text[:20] = '标题行\n这是内容XXXXXXXXXXXX'
    # \n@index=3, threshold=10 -> 3>10 为 False，fallback 到字符截断
    # 所以结果包含完整 truncated 内容 + "..."
    text = "标题行\n这是内容" + "X" * 500
    result = truncate_summary(text, max_len=20)
    assert "标题行" in result
    assert "这是内容" in result  # \n 边界不满足阈值，内容保留
    assert result.endswith("...")


def test_truncate_summary_newline_boundary_within_threshold():
    """行边界在阈值范围内时实际截断"""
    # 构造：内容 + \n + 大量内容，max_len 设小让 \n 在阈值内
    text = "标题行\n这是长内容" + "X" * 500
    result = truncate_summary(text, max_len=8)
    # text[:8] = '标题行\n这是长内容' -> \n@3, threshold=4, 3>4=False -> 但是等等
    # text[:8] = '标题行\n这是长' (6 chars after the \n)
    # Actually: '标题行\n这是长' is 7 chars; text[:8] = '标题行\n这是长内'
    # \n@3, threshold=4, 3>4=False -> 不行
    # Let me use a tighter max_len
    assert isinstance(result, str)

    # 重新构造：用短的 max_len
    text2 = "标题\n太多内容了" + "X" * 500
    result2 = truncate_summary(text2, max_len=7)
    # text2[:7] = '标题\n太多内容了' -> \n@2, 2 > 3.5=False -> fail
    # text2[:7] = '标题\n太多内容' -> \n@2, 2 > 3.5=False

    # 真的能命中 \n 的例子：text2[:5]='标题\n太多内' -> \n@2, 2>2.5=False
    # text2[:3]='标题\n' -> \n@2, 2>1.5=True -> return '标题' + '...'
    result3 = truncate_summary(text2, max_len=3)
    assert result3 == "标题..."
    assert "太多" not in result3


def test_truncate_summary_english_sentence_boundary():
    """英文句号+空格边界处截断，保留符号"""
    text = "Hello world. Goodbye world. " + "X" * 500
    result = truncate_summary(text, max_len=20)
    # . + 空格 边界，keep_len=1 保留 ". "
    assert "Hello world." in result
    assert "Goodbye" not in result
    assert result.endswith("...")


def test_truncate_summary_character_fallback():
    """无合适边界时字符截断（段落/句子边界均在 50% 以前）"""
    # 全大写无空格无标点无换行，边界都在前面
    text = "ABC" + "DEFGHIJKLMNOPQRSTUVWXYZ" * 100
    result = truncate_summary(text, max_len=100)
    assert result.endswith("...")
    assert len(result) <= 103  # max_len + len("...")


def test_truncate_summary_custom_max_len():
    """自定义 max_len 生效"""
    text = "A" * 10 + "。" + "B" * 100
    result = truncate_summary(text, max_len=12)
    assert result.endswith("...")
    assert len(result) < 20  # 应该在句号处截断


# ─── read_markdown tests ──────────────────────────────────────────────────

def test_read_markdown_extracts_h1_title(tmp_path):
    """从 md 文件提取 # 标题"""
    md = tmp_path / "test.md"
    md.write_text("# 我的标题\n\n正文内容。", encoding="utf-8")
    result = read_markdown(md)
    assert result["title"] == "我的标题"
    assert result["filename"] == "test.md"
    assert "# 我的标题" in result["content"]


def test_read_markdown_fallback_to_stem(tmp_path):
    """无 # 标题时回退到文件名（不含扩展名）"""
    md = tmp_path / "my-journal.md"
    md.write_text("只有内容\n没有标题。", encoding="utf-8")
    result = read_markdown(md)
    assert result["title"] == "my-journal"


def test_read_markdown_normalizes_line_endings(tmp_path):
    """统一 \\r\\n 和 \\r 为 \\n"""
    md = tmp_path / "crlf.md"
    md.write_bytes(b"# Title\r\nLine 1\r\nLine 2\rLine 3\n")
    result = read_markdown(md)
    assert "\r\n" not in result["content"]
    assert "\r" not in result["content"]


# ─── Integration test: KB entries exist after import ─────────────────────

def test_kb_has_entries_after_import():
    """验证导入脚本已在数据库中写入条目"""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT COUNT(*) FROM kb_entries WHERE source_pipeline_id='chen-director-pilot'"
        ).fetchall()
        count = rows[0][0]
        assert count >= 1, (
            f"Expected at least 1 entry with source_pipeline_id='chen-director-pilot', "
            f"got {count}. Run `python tools/import_chen_kb.py` first."
        )
    finally:
        conn.close()

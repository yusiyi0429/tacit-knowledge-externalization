#!/usr/bin/env python3
"""导入陈总监会议纪要 .md 文档到知识库 (kb_entries)。"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

# 把 backend 加入路径
BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from knowledge_base import get_db, init_db, publish_entries


def read_markdown(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # 提取第一行 # 标题作为 title
    title = path.stem
    m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if m:
        title = m.group(1).strip()
    return {
        "title": title,
        "content": text,
        "filename": path.name,
    }


def classify_domain(title: str, content: str) -> str:
    text = (title + " " + content).lower()
    if any(k in text for k in ["信贷", "风控", "审批", "授信", "不良"]):
        return "银行信贷风控审批"
    # 客户交流关键词（含海外银行缩写）
    # BPI = Bank of the Philippine Islands / 印尼 BPI 银行
    # SHB = Saigon-Hanoi Commercial Joint Stock Bank / 越南西贡河内银行
    # JKB = Jordan Kuwait Bank / 约旦科威特银行
    # Moniepoint = 尼日利亚金融科技公司
    if any(k in text for k in ["客户交流", "会议纪要", "会议总结", "bpi", "shb", "jkb", "moniepoint", "格鲁吉亚", "约旦", "峰会"]):
        return "金融科技出海客户交流"
    if any(k in text for k in ["销售", "解决方案", "培训", "企业级"]):
        return "企业级银行解决方案销售"
    return "未分类"


def truncate_summary(text: str, max_len: int = 500) -> str:
    """智能截断摘要，优先段落边界，其次句子边界，最后字符边界。"""
    if len(text) <= max_len:
        return text
    truncated = text[:max_len]
    # 1. 尝试段落边界
    para_boundary = truncated.rfind("\n\n")
    if para_boundary != -1 and para_boundary > max_len * 0.5:
        return truncated[:para_boundary] + "..."
    # 2. 尝试句子边界
    for delim, keep_len in (("\n", 0), ("。", 0), (". ", 1)):
        idx = truncated.rfind(delim)
        if idx != -1 and idx > max_len * 0.5:
            return truncated[:idx + keep_len] + "..."
    # 3. 字符边界
    return truncated + "..."


def main() -> None:
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="导入陈总监会议纪要 .md 文档到知识库")
    parser.add_argument("--source-dir", type=str, help="Markdown 文件来源目录")
    args = parser.parse_args()

    # SOURCE_DIR 优先级：环境变量 > 命令行参数 > 默认路径
    env_dir = os.environ.get("CHEN_KB_SOURCE_DIR")
    if env_dir:
        source_dir = Path(env_dir)
    elif args.source_dir:
        source_dir = Path(args.source_dir)
    else:
        source_dir = Path("/mnt/c/Users/yusiyi/Desktop/我的工作空间/samples/陈总监知识汇集")

    if not source_dir.exists():
        print(f"错误：来源目录不存在: {source_dir}", file=sys.stderr)
        sys.exit(1)

    init_db()
    md_files = sorted(source_dir.glob("*.md"))
    if not md_files:
        print("未找到 .md 文件", file=sys.stderr)
        sys.exit(1)

    # 试点：先处理第一个 .md，但收集所有 entries 后一次性 publish
    # TODO: 未来批量处理多文件时，应聚合各文件的 domain（如取众数），而非仅用最后一个文件的 domain
    entries = []
    # 从第一个文件确定 domain（试点仅处理单个文件，批量扩展时需改为聚合逻辑）
    first_doc = read_markdown(md_files[0])
    domain = classify_domain(first_doc["title"], first_doc["content"])
    for path in md_files[:1]:
        doc = read_markdown(path)
        summary = truncate_summary(doc["content"])

        entries.append(
            {
                "sub_scenario": "",
                "category": "会议纪要",
                "fields": {
                    "知识描述": doc["title"],
                    "具体方法": summary,
                    "适用条件": "",
                    "判断逻辑": "",
                    "贡献专家": "陈总监",
                    "来源文件": doc["filename"],
                    "原文内容": doc["content"],
                },
            }
        )
        print(f"处理 [{domain}] {path.name}")

    ir = {
        "skill_meta": {
            "domain": domain,
            "scenario_name": "总监知识汇集",
        },
        "anchors": {
            "scenario": "总监知识汇集",
        },
        "entries": entries,
    }

    try:
        result = publish_entries(
            ir=ir,
            pipeline_id="chen-director-pilot",
            by="import-script",
        )
    except Exception as exc:
        print(f"错误：publish_entries 失败: {exc}", file=sys.stderr)
        sys.exit(1)

    entry_uid = result["entry_uids"][0] if result.get("entry_uids") else "N/A"
    print(f"导入完成 -> {entry_uid}")


if __name__ == "__main__":
    main()

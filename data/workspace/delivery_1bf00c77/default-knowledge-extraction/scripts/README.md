# scripts/

本目录可放置调用该 Skill 的可执行脚本，例如：

- `run_skill.py`：读取输入客户数据，调用 LLM 按 SKILL.md 指令执行客户筛选/数据匹配/原因归因/决策建议。
- `batch_evaluate.py`：批量跑验证用例并输出命中率。
- `sync_knowledge.py`：将修订后的知识条目同步回 golden DB。

当前为占位，需根据实际部署环境补充实现。

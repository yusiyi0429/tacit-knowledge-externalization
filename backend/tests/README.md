# Backend tests

本目录存放 pytest 可发现的测试与端到端脚本。

| Script | Purpose |
|--------|---------|
| `test_*.py` | 单元/集成测试，通过 `pytest backend/tests/` 运行 |
| `e2e_pipeline_test.py` | 端到端 API 测试（Step1→Step4），需后端运行在 `http://127.0.0.1:5000` |
| `e2e_ir_pipeline_test.py` | IR 路径端到端测试 |

一次性工具/导入脚本已迁移到 `backend/tools/`。

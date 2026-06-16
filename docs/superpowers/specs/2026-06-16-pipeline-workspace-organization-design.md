# Pipeline 工作区文件分类整理设计文档

## 背景

`tacit-knowledge-platform` 的 `data/workspace/` 目录目前把所有产物平铺在根目录：

- `template_*.xlsx`
- `preextract_*.xlsx`
- `final_*.xlsx`、`revision_*.xlsx`
- `skill_draft_*.json`
- `SKILL_*.md`、`COT_*.md`、`QA_*.{json,md}`
- `delivery_*`、`SKILL_DIR_*.zip`
- `validation_*`、`signal_report_*`、`fusion_*` 等

随着流水线运行，文件数量快速增长，用户很难按流水线定位和管理产物。

## 目标

将 `data/workspace/` 按 **pipeline + step** 组织成两级目录结构，同时保证：

1. 向后兼容：现有 API 的 `download_url`、`step_data` 中的文件引用仍可正常工作。
2. 下载路由 `/downloads/<filename>` 保持不变。
3. 服务启动时自动完成一次性历史文件迁移。
4. 无法识别归属的文件直接删除。

## 目录结构

```
data/workspace/
├── pipelines.json
├── custom_models.json
├── preset_overrides.json
├── .workspace_organized          # 迁移标记文件
├── <pipeline_id>/
│   ├── step1/
│   │   ├── template_<hash>.xlsx
│   │   └── template_<hash>.md
│   ├── step2/
│   │   ├── preextract_<hash>.xlsx
│   │   ├── preextract_<hash>.md
│   │   ├── skill_draft_<pid>_v1_<hash>.json
│   │   ├── skill_draft_<pid>_v1_<hash>.md
│   │   ├── fusion_<hash>.json
│   │   └── signal_report_<hash>.json
│   ├── step3/
│   │   ├── final_<pid>_<time>.xlsx
│   │   ├── final_<pid>_<time>.md
│   │   ├── revision_<pid>_<time>.xlsx
│   │   ├── skill_draft_<pid>_v2_<hash>.json   # aligned IR
│   │   └── skill_draft_<pid>_v2_<hash>.md
│   ├── step4/
│   │   ├── SKILL_<hash>.md
│   │   ├── SKILL_DIR_<hash>.zip
│   │   ├── COT_<hash>.md
│   │   ├── QA_<hash>.json
│   │   ├── QA_<hash>.md
│   │   ├── openclaw_<hash>.json
│   │   └── delivery_<hash>/                  # 保留完整目录
│   │       ├── SKILL.md
│   │       ├── manifest.json
│   │       ├── <skill-slug>/
│   │       │   ├── SKILL.md
│   │       │   ├── manifest.json
│   │       │   ├── references/
│   │       │   ├── scripts/
│   │       │   └── assets/
│   │       └── <skill-slug>.zip
│   ├── step5/
│   │   ├── validation_replay_<hash>.md
│   │   ├── validation_result_<hash>.json
│   │   ├── validation_suggestions_<hash>.json
│   │   └── quality_report_<hash>.md
│   └── uploads/          # 该 pipeline 的上传缓存
│       └── cache_s2_<hash>.txt
```

受保护文件（`pipelines.json`、`custom_models.json`、`preset_overrides.json`）仍保留在根目录。

## 文件名 → step 映射规则

| 前缀/模式 | step |
|---|---|
| `template_`、`edited_step1_` | step1 |
| `preextract_`、`edited_step2_`、`skill_draft_*_v1_`、`fusion_`、`signal_report_`、`interview_` | step2 |
| `final_`、`revision_`、`edited_step3_`、`skill_draft_*_vN_` (v>=2) | step3 |
| `SKILL_`、`COT_`、`QA_`、`openclaw_`、`delivery_`、`SKILL_DIR_`、`pattern_mining_`、`gap_analysis_`、`freshness_audit_` | step4 |
| `validation_`、`quality_report_` | step5 |
| `cache_s2_`、`cache_s3_`、`upload_`、`edit_read_`、`upload_tpl_` | uploads |

## 核心改动点

### 1. 新增工具函数

在 `backend/pipeline_artifacts.py` 中新增：

- `infer_file_step(name: str) -> str | None`：根据文件名推断所属 step。
- `workspace_path_for(pipeline_id: str, step: str, filename: str) -> Path`：返回产物应写入的完整路径。
- `locate_workspace_file(filename: str, workspace: Path, pipeline_id: str | None = None) -> Path | None`：按 basename 定位文件，优先在对应 pipeline/step 子目录中查找，fallback 根目录。

### 2. 统一写文件入口

所有生成产物的地方从 `WORKSPACE / filename` 改为 `workspace_path_for(pipeline_id, step, filename)`，主要包括：

- `backend/app_server.py`：Step1/2/3/4/5 产物生成、`_publish_artifact`。
- `backend/skill_ir.py`：`save_ir()`。
- `backend/knowledge_delivery.py`：`records_to_delivery_bundle()` 的 `output_dir`。
- `backend/shared.py` 或 `app_server.py`：`save_upload()`。

### 3. 下载路由兼容

`/downloads/<filename>` 保持原 URL，内部使用 `locate_workspace_file()` 查找：

1. 如果请求带 `pipeline_id` query（可选），优先到对应目录查。
2. 否则按 basename 全局搜索子目录。
3. Fallback 根目录（兼容旧文件）。

### 4. 启动迁移

新增 `_maybe_organize_workspace()`，在 `_maybe_migrate_from_old_default()` 之后调用：

1. 检查根目录是否存在 `.workspace_organized` 标记文件，存在则跳过。
2. 读取 `pipelines.json`，建立每个 `pipeline_id` 引用过的 basename 集合。
3. 遍历根目录下所有文件：
   - 跳过受保护文件和 `.workspace_organized`。
   - 根据文件名推断 step。
   - 如果能匹配到某个 pipeline 的引用集合，移动到 `data/workspace/<pipeline_id>/<step>/`。
   - 如果不能匹配任何 pipeline，直接删除。
4. 创建 `.workspace_organized` 标记文件。

## 向后兼容保证

- 所有 `download_url` 保持 `/downloads/<filename>` 不变。
- `pipelines.json` 里的 `*_file` 字段只存 basename。
- `safe_workspace_path()` 增强为支持在子目录中定位文件。
- 旧文件在迁移前仍可从根目录下载。

## 测试计划

1. 新增 `backend/tests/test_workspace_organization.py`：
   - 验证新产物写入正确子目录。
   - 验证下载路由能从子目录找到文件。
   - 验证迁移脚本正确移动/删除文件。
2. 更新 `backend/tests/e2e_ir_pipeline_test.py`：
   - Step4 断言产物在 `<pid>/step4/` 下。
3. 运行现有测试套件确保无回归。

## 未纳入范围

- 修改前端展示逻辑（前端仍通过 `download_url` 下载，无需感知目录结构）。
- 改变 `pipelines.json` schema。
- 改变 Skill 目录内部结构（已完成的 agentskills.io 目录导出保持不变）。

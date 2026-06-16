# Pipeline Workspace 文件分类整理实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `data/workspace/` 从平铺结构改造成按 `pipeline_id/stepN/` 组织的两级目录，同时保持 `/downloads/<filename>` 和 `step_data` 中 basename 引用的向后兼容。

**Architecture:** 在 `backend/pipeline_artifacts.py` 中新增文件名推断、路径生成、文件定位三个工具函数；所有产物写入点改用新路径函数；`/downloads/<filename>` 路由通过新定位函数支持子目录查找；服务启动时做一次性迁移。

**Tech Stack:** Python 3.11, Flask, pytest, pathlib

---

## 文件结构

| 文件 | 责任 |
|---|---|
| `backend/pipeline_artifacts.py` | 新增 `infer_file_step`、`workspace_path_for`、`locate_workspace_file`、`organize_workspace`；维护文件名→step 映射和白名单 |
| `backend/app_server.py` | 替换所有产物写入为 `workspace_path_for`；增强 `/downloads/<filename>`；在启动迁移后调用 organize |
| `backend/skill_ir.py` | `save_ir()` 使用 `workspace_path_for` |
| `backend/knowledge_delivery.py` | `records_to_delivery_bundle()` 的 `output_dir` 使用 `workspace_path_for` |
| `backend/shared.py` | `save_upload()` 支持传入 `pipeline_id` 并路由到对应目录 |
| `backend/tests/test_workspace_organization.py` | 新增单元测试 |
| `backend/tests/e2e_ir_pipeline_test.py` | 更新断言，验证产物在子目录 |

---

## Task 1: 新增 pipeline_artifacts.py 工具函数

**Files:**
- Modify: `backend/pipeline_artifacts.py`
- Test: `backend/tests/test_workspace_organization.py`

- [ ] **Step 1: 写失败测试**

```python
def test_infer_file_step():
    from pipeline_artifacts import infer_file_step
    assert infer_file_step("template_abc.xlsx") == "step1"
    assert infer_file_step("preextract_abc.xlsx") == "step2"
    assert infer_file_step("skill_draft_pid_v1_abc.json") == "step2"
    assert infer_file_step("final_pid_123456.xlsx") == "step3"
    assert infer_file_step("skill_draft_pid_v2_abc.json") == "step3"
    assert infer_file_step("SKILL_abc.md") == "step4"
    assert infer_file_step("validation_result_abc.json") == "step5"
    assert infer_file_step("cache_s2_abc.txt") == "uploads"
    assert infer_file_step("unknown.bin") is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /mnt/d/my-workspace/tacit-knowledge-platform && .venv/bin/python -m pytest backend/tests/test_workspace_organization.py::test_infer_file_step -v`
Expected: FAIL with `ImportError` or `NameError`

- [ ] **Step 3: 实现 infer_file_step**

在 `backend/pipeline_artifacts.py` 中添加：

```python
import re

_STEP_PREFIX_RULES = [
    (re.compile(r"^(?:edited_step1_|template_)"), "step1"),
    (re.compile(r"^(?:edited_step2_|preextract_|fusion_|signal_report_|interview_|skill_draft_.*_v1_)"), "step2"),
    (re.compile(r"^(?:edited_step3_|final_|revision_|skill_draft_.*_v(?!1\b)\d+_)"), "step3"),
    (re.compile(r"^(?:SKILL_|SKILL_DIR_|COT_|QA_|openclaw_|delivery_|pattern_mining_|gap_analysis_|freshness_audit_)"), "step4"),
    (re.compile(r"^(?:validation_|quality_report_)"), "step5"),
    (re.compile(r"^(?:cache_s\d+|upload|edit_read|upload_tpl)_"), "uploads"),
]


def infer_file_step(name: str) -> str | None:
    """根据文件名推断所属 step/目录。"""
    base = os.path.basename(str(name))
    for pattern, step in _STEP_PREFIX_RULES:
        if pattern.search(base):
            return step
    return None
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /mnt/d/my-workspace/tacit-knowledge-platform && .venv/bin/python -m pytest backend/tests/test_workspace_organization.py::test_infer_file_step -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
cd /mnt/d/my-workspace/tacit-knowledge-platform
git add backend/pipeline_artifacts.py backend/tests/test_workspace_organization.py
git commit -m "feat: add infer_file_step for workspace organization"
```

---

## Task 2: 实现 workspace_path_for 和 locate_workspace_file

**Files:**
- Modify: `backend/pipeline_artifacts.py`
- Test: `backend/tests/test_workspace_organization.py`

- [ ] **Step 1: 写失败测试**

```python
def test_workspace_path_for_and_locate(tmp_path):
    from pipeline_artifacts import workspace_path_for, locate_workspace_file
    workspace = tmp_path / "ws"
    workspace.mkdir()
    path = workspace_path_for(workspace, "pid123", "step2", "preextract_abc.xlsx")
    assert path == workspace / "pid123" / "step2" / "preextract_abc.xlsx"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x")
    assert locate_workspace_file(workspace, "preextract_abc.xlsx") == path
    assert locate_workspace_file(workspace, "preextract_abc.xlsx", pipeline_id="pid123") == path
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /mnt/d/my-workspace/tacit-knowledge-platform && .venv/bin/python -m pytest backend/tests/test_workspace_organization.py::test_workspace_path_for_and_locate -v`
Expected: FAIL

- [ ] **Step 3: 实现函数**

在 `backend/pipeline_artifacts.py` 中添加：

```python
def workspace_path_for(workspace: Path, pipeline_id: str, step: str, filename: str) -> Path:
    """返回产物应写入的完整路径。"""
    if not pipeline_id or not step:
        return Path(workspace) / os.path.basename(filename)
    return Path(workspace) / str(pipeline_id) / str(step) / os.path.basename(filename)


def locate_workspace_file(workspace: Path, filename: str, *, pipeline_id: str | None = None) -> Path | None:
    """按 basename 定位文件，优先子目录，fallback 根目录。"""
    base = os.path.basename(str(filename))
    workspace = Path(workspace)

    # 1. 如果给了 pipeline_id，优先在对应目录按推断 step 查找
    if pipeline_id:
        step = infer_file_step(base)
        if step:
            candidate = workspace / str(pipeline_id) / step / base
            if candidate.is_file():
                return candidate
        # 兜底：在该 pipeline 所有子目录里找
        pipeline_dir = workspace / str(pipeline_id)
        if pipeline_dir.is_dir():
            for subdir in pipeline_dir.iterdir():
                if subdir.is_dir():
                    candidate = subdir / base
                    if candidate.is_file():
                        return candidate

    # 2. 全局子目录搜索
    for root, _dirs, files in os.walk(workspace):
        if base in files:
            return Path(root) / base

    # 3. fallback 根目录
    root_candidate = workspace / base
    return root_candidate if root_candidate.is_file() else None
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /mnt/d/my-workspace/tacit-knowledge-platform && .venv/bin/python -m pytest backend/tests/test_workspace_organization.py::test_workspace_path_for_and_locate -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
cd /mnt/d/my-workspace/tacit-knowledge-platform
git add backend/pipeline_artifacts.py backend/tests/test_workspace_organization.py
git commit -m "feat: add workspace_path_for and locate_workspace_file"
```

---

## Task 3: 实现启动迁移 organize_workspace

**Files:**
- Modify: `backend/pipeline_artifacts.py`
- Test: `backend/tests/test_workspace_organization.py`

- [ ] **Step 1: 写失败测试**

```python
def test_organize_workspace(tmp_path):
    from pipeline_artifacts import organize_workspace
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "pipelines.json").write_text("[]")
    (workspace / "custom_models.json").write_text("{}")
    (workspace / "preextract_abc.xlsx").write_text("x")
    (workspace / "SKILL_unknown.md").write_text("x")
    (workspace / "random.txt").write_text("x")

    organize_workspace(workspace)

    assert (workspace / "preextract_abc.xlsx").exists() is False
    assert (workspace / "SKILL_unknown.md").exists() is False
    assert (workspace / "random.txt").exists() is False
    assert (workspace / ".workspace_organized").exists() is True
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /mnt/d/my-workspace/tacit-knowledge-platform && .venv/bin/python -m pytest backend/tests/test_workspace_organization.py::test_organize_workspace -v`
Expected: FAIL

- [ ] **Step 3: 实现 organize_workspace**

在 `backend/pipeline_artifacts.py` 中添加：

```python
def organize_workspace(workspace: Path) -> dict:
    """一次性迁移：把根目录下能识别归属的文件按 pipeline/step 分类，无归属的删除。"""
    workspace = Path(workspace)
    marker = workspace / ".workspace_organized"
    if marker.exists():
        return {"status": "already_organized"}

    protected = {"pipelines.json", "custom_models.json", "preset_overrides.json"}
    result = {"moved": 0, "deleted": 0, "skipped": 0}

    # 建立 pipeline 引用集合
    pipeline_refs: dict[str, set[str]] = {}
    pipelines_file = workspace / "pipelines.json"
    if pipelines_file.is_file():
        try:
            import json
            pipelines = json.loads(pipelines_file.read_text(encoding="utf-8"))
            for p in pipelines or []:
                pid = str(p.get("id", ""))
                if not pid:
                    continue
                refs = set()
                sd = p.get("step_data", {})
                for val in sd.values():
                    if isinstance(val, str) and val.startswith("/downloads/"):
                        refs.add(os.path.basename(val))
                    elif isinstance(val, str) and "/" not in val and "." in val:
                        refs.add(os.path.basename(val))
                pipeline_refs[pid] = refs
        except Exception:
            pass

    for item in list(workspace.iterdir()):
        if not item.is_file():
            continue
        if item.name in protected or item.name == ".workspace_organized":
            result["skipped"] += 1
            continue

        step = infer_file_step(item.name)
        if not step:
            try:
                item.unlink()
                result["deleted"] += 1
            except Exception:
                pass
            continue

        # 尝试匹配 pipeline
        target_pid = None
        for pid, refs in pipeline_refs.items():
            if item.name in refs:
                target_pid = pid
                break

        if target_pid:
            dest_dir = workspace / target_pid / step
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / item.name
            try:
                item.rename(dest)
                result["moved"] += 1
            except Exception:
                pass
        else:
            try:
                item.unlink()
                result["deleted"] += 1
            except Exception:
                pass

    marker.write_text("", encoding="utf-8")
    return result
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /mnt/d/my-workspace/tacit-knowledge-platform && .venv/bin/python -m pytest backend/tests/test_workspace_organization.py::test_organize_workspace -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
cd /mnt/d/my-workspace/tacit-knowledge-platform
git add backend/pipeline_artifacts.py backend/tests/test_workspace_organization.py
git commit -m "feat: add organize_workspace migration"
```

---

## Task 4: 更新 app_server.py 启动迁移和下载路由

**Files:**
- Modify: `backend/app_server.py`
- Test: `backend/tests/e2e_ir_pipeline_test.py`

- [ ] **Step 1: 在 app_server.py 启动时调用 organize**

找到 `_maybe_migrate_from_old_default()` 调用处（约 line 130），在其后添加：

```python
try:
    from pipeline_artifacts import organize_workspace
    organize_workspace(WORKSPACE)
except Exception:
    pass
```

- [ ] **Step 2: 更新 /downloads 路由使用 locate_workspace_file**

将 `downloads()` 函数改为：

```python
@app.route("/downloads/<path:filename>")
def downloads(filename):
    base = basename_only(filename)
    if not is_download_allowed(base):
        return jsonify({"status": "error", "error": "不允许下载该文件"}), 403

    pipeline_id = request.args.get("pipeline_id", "") or request.form.get("pipeline_id", "")
    from pipeline_artifacts import locate_workspace_file
    path = locate_workspace_file(WORKSPACE, base, pipeline_id=pipeline_id or None)
    if not path:
        return jsonify({"status": "error", "error": "文件不存在"}), 404
    return send_from_directory(str(path.parent), path.name, as_attachment=True)
```

- [ ] **Step 3: 运行 e2e 测试确认下载仍正常**

Run: `cd /mnt/d/my-workspace/tacit-knowledge-platform && .venv/bin/python backend/tests/e2e_ir_pipeline_test.py`
Expected: All IR pipeline e2e tests passed.

- [ ] **Step 4: 提交**

```bash
cd /mnt/d/my-workspace/tacit-knowledge-platform
git add backend/app_server.py
git commit -m "feat: integrate workspace organization into startup and downloads"
```

---

## Task 5: 替换产物写入路径（Step1-5 + publish）

**Files:**
- Modify: `backend/app_server.py`
- Test: `backend/tests/e2e_ir_pipeline_test.py`

- [ ] **Step 1: 修改 _publish_artifact 使用 workspace_path_for**

```python
def _publish_artifact(key: str, src_path: str, prefix: str, ext: str):
    if not src_path or not os.path.isfile(src_path):
        return None
    name = f"{prefix}_{uuid.uuid4().hex[:8]}{ext}"
    from pipeline_artifacts import workspace_path_for
    dest = workspace_path_for(WORKSPACE, pipeline_id, infer_file_step(name) or "step4", name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_path, str(dest))
    info = {
        "file_name": name,
        "download_url": "/downloads/" + name,
    }
    ...
```

注意：`_publish_artifact` 是 `api_step4_compile` 内部函数，可访问 `pipeline_id`。

- [ ] **Step 2: 修改 Step1 产物写入路径**

在 `api_step1_generate` 中，找到 `output_path = str(WORKSPACE / output_name)` 等位置，改为：

```python
from pipeline_artifacts import workspace_path_for
output_path = str(workspace_path_for(WORKSPACE, pipeline_id, "step1", output_name))
md_path = workspace_path_for(WORKSPACE, pipeline_id, "step1", md_name)
```

- [ ] **Step 3: 修改 Step2 产物写入路径**

在 `_execute_knowledge_extraction` 和 `step2_extract_unified` 中：

```python
output_path = workspace_path_for(WORKSPACE, pipeline_id, "step2", output_name)
md_path = workspace_path_for(WORKSPACE, pipeline_id, "step2", md_name)
```

- [ ] **Step 4: 修改 Step3 产物写入路径**

在 `_publish_final_from_source`、`_publish_alignment_draft` 等函数中：

```python
output_path = workspace_path_for(WORKSPACE, pipeline_id, "step3", output_name)
md_path = workspace_path_for(WORKSPACE, pipeline_id, "step3", md_name)
```

- [ ] **Step 5: 修改 Step4 产物写入路径**

在 `api_step4_compile` 中：

```python
output_dir = str(workspace_path_for(WORKSPACE, pipeline_id, "step4", f"delivery_{uuid.uuid4().hex[:8]}"))
```

- [ ] **Step 6: 修改 Step5 产物写入路径**

在 `api_step5_validate` 等函数中：

```python
report_path = workspace_path_for(WORKSPACE, pipeline_id, "step5", report_name)
```

- [ ] **Step 7: 运行 e2e 测试**

Run: `cd /mnt/d/my-workspace/tacit-knowledge-platform && .venv/bin/python backend/tests/e2e_ir_pipeline_test.py`
Expected: All IR pipeline e2e tests passed.

- [ ] **Step 8: 提交**

```bash
cd /mnt/d/my-workspace/tacit-knowledge-platform
git add backend/app_server.py
git commit -m "feat: route all step artifacts into pipeline/step subdirectories"
```

---

## Task 6: 更新 skill_ir.py 的 save_ir

**Files:**
- Modify: `backend/skill_ir.py`
- Test: `backend/tests/test_skill_ir.py`

- [ ] **Step 1: 修改 save_ir**

```python
def save_ir(workspace, ir: dict, pipeline_id: str = "") -> str:
    errors = validate_ir(ir)
    if errors:
        raise ValueError("IR 校验失败: " + "; ".join(errors[:5]))
    meta = ir.get("skill_meta") or {}
    pid = pipeline_id or _norm(meta.get("pipeline_id"))
    version = int(meta.get("draft_version", 1) or 1)
    name = draft_filename(pid, version)

    from pipeline_artifacts import workspace_path_for, infer_file_step
    step = "step2" if version == 1 else "step3"
    path = workspace_path_for(Path(workspace), pid, step, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ir, ensure_ascii=False, indent=2), encoding="utf-8")
    return name
```

- [ ] **Step 2: 运行测试**

Run: `cd /mnt/d/my-workspace/tacit-knowledge-platform && .venv/bin/python -m pytest backend/tests/test_skill_ir.py -v`
Expected: PASS

- [ ] **Step 3: 提交**

```bash
cd /mnt/d/my-workspace/tacit-knowledge-platform
git add backend/skill_ir.py
git commit -m "feat: save skill IR drafts into pipeline/step subdirectories"
```

---

## Task 7: 更新 knowledge_delivery.py 的 output_dir

**Files:**
- Modify: `backend/knowledge_delivery.py`
- Test: `backend/tests/e2e_ir_pipeline_test.py`

- [ ] **Step 1: 修改 records_to_delivery_bundle 入口**

在 `records_to_delivery_bundle` 中，当 `pipeline_context` 包含 `pipeline_id` 时：

```python
if pipeline_context and pipeline_context.get("pipeline_id"):
    from pipeline_artifacts import workspace_path_for
    output_dir = str(workspace_path_for(
        Path(output_dir).parent,
        pipeline_context["pipeline_id"],
        "step4",
        Path(output_dir).name,
    ))
```

或者更干净地在 `app_server.py` 里构造 `output_dir` 时直接传入。

- [ ] **Step 2: 运行 e2e 测试**

Run: `cd /mnt/d/my-workspace/tacit-knowledge-platform && .venv/bin/python backend/tests/e2e_ir_pipeline_test.py`
Expected: All IR pipeline e2e tests passed.

- [ ] **Step 3: 提交**

```bash
cd /mnt/d/my-workspace/tacit-knowledge-platform
git add backend/knowledge_delivery.py
git commit -m "feat: route delivery bundle output into pipeline/step4 subdirectory"
```

---

## Task 8: 更新 save_upload 支持 pipeline_id

**Files:**
- Modify: `backend/shared.py` 或 `backend/app_server.py`
- Test: `backend/tests/test_workspace_organization.py`

- [ ] **Step 1: 修改 save_upload**

```python
def save_upload(file_obj, prefix="upload", pipeline_id: str = ""):
    ext = Path(file_obj.filename).suffix if file_obj.filename else ".xlsx"
    fname = f"{prefix}_{uuid.uuid4().hex[:8]}{ext}"
    from pipeline_artifacts import workspace_path_for, infer_file_step
    step = infer_file_step(fname) or "uploads"
    fpath = workspace_path_for(WORKSPACE, pipeline_id or "", step, fname)
    fpath.parent.mkdir(parents=True, exist_ok=True)
    file_obj.save(str(fpath))
    return str(fpath)
```

- [ ] **Step 2: 更新所有 save_upload 调用点传入 pipeline_id**

搜索 `save_upload(` 调用点，在已知 `pipeline_id` 的地方传入。例如：

- `api_step4_compile` 中的 `input_path = save_upload(excel_file, prefix="compile", pipeline_id=pipeline_id)`
- `api_file_cache_upload` 中的 `saved_path = save_upload(file_obj, prefix=f"cache_s{step or 'x'}", pipeline_id=pipeline_id)`
- 其他调用点如未知 pipeline_id 可不传。

- [ ] **Step 3: 运行测试**

Run: `cd /mnt/d/my-workspace/tacit-knowledge-platform && .venv/bin/python -m pytest backend/tests/test_workspace_organization.py -v`
Expected: PASS

- [ ] **Step 4: 提交**

```bash
cd /mnt/d/my-workspace/tacit-knowledge-platform
git add backend/shared.py backend/app_server.py
git commit -m "feat: route uploads into pipeline/uploads subdirectory"
```

---

## Task 9: 更新 e2e 断言验证子目录结构

**Files:**
- Modify: `backend/tests/e2e_ir_pipeline_test.py`

- [ ] **Step 1: 在 Step4 compile 后断言产物位置**

```python
# 在 Step4 compile 测试块中
sd = requests.get(f"{BASE}/api/pipelines/{pid}", timeout=30).json()["pipeline"]["step_data"]
skill_file = sd.get("step4_skill_file", "")
assert skill_file, "缺少 step4_skill_file"
assert (workspace / pid / "step4" / skill_file).is_file(), "SKILL 文件应在 pipeline/step4 子目录"
zip_file = sd.get("step4_skill_dir_zip_file", "")
if zip_file:
    assert (workspace / pid / "step4" / zip_file).is_file(), "zip 文件应在 pipeline/step4 子目录"
```

- [ ] **Step 2: 运行 e2e 测试**

Run: `cd /mnt/d/my-workspace/tacit-knowledge-platform && .venv/bin/python backend/tests/e2e_ir_pipeline_test.py`
Expected: All IR pipeline e2e tests passed.

- [ ] **Step 3: 提交**

```bash
cd /mnt/d/my-workspace/tacit-knowledge-platform
git add backend/tests/e2e_ir_pipeline_test.py
git commit -m "test: assert e2e artifacts land in pipeline/step subdirectories"
```

---

## Task 10: 全量回归测试

**Files:**
- All above

- [ ] **Step 1: 运行 artifact + IR + e2e 测试**

Run: `cd /mnt/d/my-workspace/tacit-knowledge-platform && .venv/bin/python -m pytest backend/tests/test_artifact_invariants.py backend/tests/test_artifacts.py backend/tests/test_skill_ir.py backend/tests/e2e_ir_pipeline_test.py -q`
Expected: all passed

- [ ] **Step 2: 手动验证迁移脚本（可选）**

```bash
cd /mnt/d/my-workspace/tacit-knowledge-platform
.venv/bin/python -c "
from pathlib import Path
from backend.pipeline_artifacts import organize_workspace
organize_workspace(Path('data/workspace'))
"
```

Expected: 无异常，根目录仅剩受保护文件和 pipeline 子目录。

- [ ] **Step 3: 提交/收尾**

```bash
cd /mnt/d/my-workspace/tacit-knowledge-platform
git add docs/superpowers/plans/2026-06-16-pipeline-workspace-organization-plan.md
git commit -m "docs: add workspace organization implementation plan"
```

---

## Spec 覆盖检查

| Spec 要求 | 对应 Task |
|---|---|
| 按 `pipeline_id/stepN` 两级目录 | Task 2, 5, 6, 7, 8 |
| 文件名 → step 映射 | Task 1 |
| 下载路由 `/downloads/<filename>` 保持不变 | Task 4 |
| 启动时一次性迁移 | Task 3, 4 |
| 无归属文件删除 | Task 3 |
| 受保护文件保留根目录 | Task 3 |
| 向后兼容 basename 引用 | Task 4, 5, 6, 7, 8 |
| 测试覆盖 | Task 1-3, 9, 10 |

无 gap，无 placeholder。

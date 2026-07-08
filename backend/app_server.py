#!/usr/bin/env python3
"""Flask backend server compatibility shim for the Tacit Knowledge Extraction app.

All routes have been moved to backend/api/ Blueprints and business logic to
backend/services/.  This module only creates the Flask app, re-exports symbols
that existing tests import, and provides the CLI entry point.
"""

from __future__ import annotations

import argparse
import datetime
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Add backend to path for legacy imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Shared module is the single source of truth for workspace paths.
import shared  # noqa: E402

# Resolve workspace before creating the app so blueprints can import it.
PROJECT_DIR = Path(__file__).resolve().parent.parent
PROJECT_WORKSPACE = PROJECT_DIR / "data" / "workspace"
OLD_DEFAULT_WORKSPACE = Path(tempfile.gettempdir()) / "tacit_knowledge_app"


def _resolve_workspace(cli_workspace: str | None = None) -> Path:
    if cli_workspace:
        return Path(cli_workspace).expanduser().resolve()
    env = os.environ.get("WORKSPACE_DIR", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return PROJECT_WORKSPACE.resolve()


def _maybe_migrate_from_old_default():
    """一次性迁移：如果新的持久化工作空间为空，而旧 /tmp 默认目录有数据，则自动复制。"""
    if not OLD_DEFAULT_WORKSPACE.exists():
        return
    old_pipelines = OLD_DEFAULT_WORKSPACE / "pipelines.json"
    if not old_pipelines.exists():
        return
    if shared.PIPELINES_PATH.exists():
        return
    try:
        for item in OLD_DEFAULT_WORKSPACE.iterdir():
            dest = shared.WORKSPACE / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)
        print(f"[MIGRATE] 已从旧临时工作空间迁移数据: {OLD_DEFAULT_WORKSPACE} -> {shared.WORKSPACE}")
    except Exception as e:
        print(f"[MIGRATE WARNING] 迁移旧数据失败: {e}")


# Re-export shared helpers and services for tests that import from app_server.
from shared import (  # noqa: E402
    load_pipelines,
    save_pipelines,
    load_llm_config,
    save_custom_models,
    load_preset_overrides,
    save_preset_overrides,
    get_model_by_name,
    _sanitize_model_for_client,
    _mask_api_key,
    extract_text_from_file,
    extract_text_from_path,
    _parse_extracted_items,
    _normalize_extracted_items,
    _extract_json_from_text,
    _safe_workbook,
    _pipelines_lock,
    _models_lock,
    EXTRACT_STYLE_RULES,
    REVISION_STYLE_RULES,
)
from pipeline_artifacts import (  # noqa: E402
    basename_only,
    locate_workspace_file,
    safe_workspace_path,
    workspace_path_for,
    workspace_dir_for,
    resolve_knowledge_ir_path,
    resolve_knowledge_workbook_path,
    validate_step_data_patch,
    is_download_allowed,
    is_step1_filename,
    is_step2_preextract_filename,
    is_step3_revision_filename,
    is_step3_final_filename,
    is_skill_draft_filename,
    infer_file_step,
    keys_to_clear_from_step,
    downstream_output_keys,
    auxiliary_step_data_keys,
    PROTECTED_WORKSPACE_FILES,
)
from services.pipeline_service import get_pipeline as _get_pipeline  # noqa: E402

# Legacy aliases
_get_pipeline = _get_pipeline

# Create the Flask application via the Blueprint factory.
from api import create_app  # noqa: E402

app = create_app()


def main():
    parser = argparse.ArgumentParser(description="Tacit Knowledge Extraction Web App")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind")
    parser.add_argument("--port", type=int, default=5000, help="Port to bind")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument(
        "--workspace",
        default="",
        help="持久化工作空间目录（默认：项目内 data/workspace/；可用 WORKSPACE_DIR 环境变量覆盖）",
    )
    args = parser.parse_args()

    shared.WORKSPACE = _resolve_workspace(args.workspace or None)
    shared.WORKSPACE.mkdir(parents=True, exist_ok=True)
    shared.CUSTOM_MODELS_PATH = shared.WORKSPACE / "custom_models.json"
    shared.PRESET_OVERRIDES_PATH = shared.WORKSPACE / "preset_overrides.json"
    shared.PIPELINES_PATH = shared.WORKSPACE / "pipelines.json"
    _maybe_migrate_from_old_default()
    try:
        from pipeline_artifacts import organize_workspace
        organize_workspace(shared.WORKSPACE)
    except Exception:
        pass

    print(f"Starting server at http://{args.host}:{args.port}")
    print(f"Workspace: {shared.WORKSPACE}")
    from shared import FRONTEND_DIR
    print(f"Frontend dir: {FRONTEND_DIR}")
    _vendor_checks = [
        FRONTEND_DIR / "vendor" / "luckysheet" / "plugins" / "js" / "plugin.js",
        FRONTEND_DIR / "vendor" / "luckysheet" / "luckysheet.umd.js",
    ]
    for p in _vendor_checks:
        if p.exists():
            print(f"  [OK] Excel editor asset: {p.relative_to(FRONTEND_DIR)}")
        else:
            print(f"  [WARN] Missing {p} — run: cd frontend && npm install luckysheet@2.1.13 jquery@3.6.4 --no-save && node ../scripts/copy-frontend-vendor.js")
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()

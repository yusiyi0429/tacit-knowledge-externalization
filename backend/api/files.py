"""File read/write and Excel editor Blueprint."""

from __future__ import annotations

from flask import Blueprint, request, jsonify

import shared
from pipeline_artifacts import (
    basename_only,
    is_download_allowed,
    locate_workspace_file,
    PROTECTED_WORKSPACE_FILES,
    safe_workspace_path,
)
from services.file_service import (
    cache_upload,
    read_excel_for_editor,
    save_excel_from_editor,
    save_upload_service,
)
from shared import _pipelines_lock, load_pipelines, save_pipelines

bp = Blueprint("files", __name__)


@bp.route("/read", methods=["GET"])
def api_file_read():
    """Read a file from workspace and return its content as text."""
    file_name = request.args.get("file_name", "")
    pipeline_id = request.args.get("pipeline_id", "").strip()
    if not file_name:
        return jsonify({"status": "error", "error": "缺少 file_name 参数"})
    file_name = basename_only(file_name)
    if file_name in PROTECTED_WORKSPACE_FILES or not is_download_allowed(file_name):
        return jsonify({"status": "error", "error": "不允许读取该文件"})
    resolved = locate_workspace_file(shared.WORKSPACE, file_name, pipeline_id=pipeline_id or None)
    if not resolved:
        return jsonify({"status": "error", "error": f"文件不存在: {file_name}"})
    try:
        with open(str(resolved), "r", encoding="utf-8") as f:
            content = f.read()
        return jsonify({"status": "ok", "content": content, "file_name": file_name})
    except Exception as e:
        return jsonify({"status": "error", "error": f"读取失败: {str(e)}"})


@bp.route("/save", methods=["POST"])
def api_file_save():
    """Save text content to a file in workspace."""
    data = request.get_json(force=True)
    file_name = (data.get("file_name") or "").strip()
    content = data.get("content", "")
    if not file_name:
        return jsonify({"status": "error", "error": "缺少 file_name 参数"})
    file_name = basename_only(file_name)
    if file_name in PROTECTED_WORKSPACE_FILES or not is_download_allowed(file_name):
        return jsonify({"status": "error", "error": "不允许写入该文件"})
    file_path = safe_workspace_path(shared.WORKSPACE, file_name, must_exist=False)
    if not file_path:
        return jsonify({"status": "error", "error": "非法文件路径"})
    try:
        with open(str(file_path), "w", encoding="utf-8") as f:
            f.write(content)
        return jsonify({"status": "ok", "file_name": file_name, "size": len(content)})
    except Exception as e:
        return jsonify({"status": "error", "error": f"保存失败: {str(e)}"})


@bp.route("/cache_upload", methods=["POST"])
def api_file_cache_upload():
    """Cache uploaded source file in workspace, return cached filename."""
    file_obj = request.files.get("file")
    pipeline_id = request.form.get("pipeline_id", "").strip()
    step = request.form.get("step", "").strip()
    if not file_obj or not file_obj.filename:
        return jsonify({"status": "error", "error": "缺少上传文件"})

    try:
        return jsonify(cache_upload(
            shared.WORKSPACE,
            file_obj,
            pipeline_id,
            step,
            _pipelines_lock,
            load_pipelines,
            save_pipelines,
        ))
    except Exception as e:
        return jsonify({"status": "error", "error": f"缓存上传失败: {str(e)}"})


@bp.route("/excel/read", methods=["POST"])
def api_excel_read():
    """Read Excel file and return structured data for online editing."""
    excel_file = request.files.get("excel")
    pipeline_id = request.form.get("pipeline_id", "").strip()
    input_path = None

    if excel_file:
        input_path = save_upload_service(shared.WORKSPACE, excel_file, prefix="edit_read", pipeline_id=pipeline_id)
    else:
        data = request.get_json(silent=True) or request.form.to_dict()
        file_name = data.get("file_name", "")
        pipeline_id = (request.form.get("pipeline_id", "").strip()
                       or (request.get_json(silent=True) or {}).get("pipeline_id", "").strip())
        if file_name:
            resolved = locate_workspace_file(shared.WORKSPACE, file_name, pipeline_id=pipeline_id or None)
            if not resolved:
                return jsonify({"status": "error", "error": f"文件不存在或路径非法: {file_name}"})
            input_path = str(resolved)

    if not input_path:
        return jsonify({"status": "error", "error": "请上传 Excel 文件或提供文件名"})

    pipeline_id = request.form.get("pipeline_id", "") or (request.get_json(silent=True) or {}).get("pipeline_id", "")
    step = request.form.get("step", "3") or (request.get_json(silent=True) or {}).get("step", "3")
    return jsonify(read_excel_for_editor(
        shared.WORKSPACE,
        input_path,
        pipeline_id,
        step,
        _pipelines_lock,
        load_pipelines,
        save_pipelines,
    ))


@bp.route("/excel/save", methods=["POST"])
def api_excel_save():
    """Save edited Excel data back to file and return download URL."""
    data = request.get_json(force=True)
    return jsonify(save_excel_from_editor(
        shared.WORKSPACE,
        data.get("file_path", ""),
        data.get("file_name", ""),
        data.get("sheets", {}),
        data.get("pipeline_id", ""),
        data.get("step", "3"),
        _pipelines_lock,
        load_pipelines,
        save_pipelines,
    ))

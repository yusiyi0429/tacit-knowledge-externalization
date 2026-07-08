"""Static files and downloads Blueprint."""

from __future__ import annotations

from flask import Blueprint, request, jsonify, send_from_directory

from pipeline_artifacts import basename_only, is_download_allowed, locate_workspace_file
from shared import FRONTEND_DIR

bp = Blueprint("static", __name__)


@bp.route("/")
def index():
    return send_from_directory(str(FRONTEND_DIR), "index.html")


@bp.route("/css/<path:filename>")
def css(filename):
    return send_from_directory(str(FRONTEND_DIR / "css"), filename)


@bp.route("/js/<path:filename>")
def js(filename):
    return send_from_directory(str(FRONTEND_DIR / "js"), filename)


@bp.route("/vendor/<path:filename>")
def vendor_static(filename):
    """Luckysheet / jQuery 等离线静态资源（内网部署）"""
    return send_from_directory(str(FRONTEND_DIR / "vendor"), filename)


@bp.route("/images/<path:filename>")
def images(filename):
    return send_from_directory(str(FRONTEND_DIR / "images"), filename)


@bp.route("/downloads/<path:filename>")
def downloads(filename):
    import shared

    base = basename_only(filename)
    if not is_download_allowed(base):
        return jsonify({"status": "error", "error": "不允许下载该文件"}), 403

    pipeline_id = request.args.get("pipeline_id", "") or request.form.get("pipeline_id", "")
    path = locate_workspace_file(shared.WORKSPACE, base, pipeline_id=pipeline_id or None)
    if not path:
        return jsonify({"status": "error", "error": "文件不存在"}), 404
    return send_from_directory(str(path.parent), path.name, as_attachment=True)

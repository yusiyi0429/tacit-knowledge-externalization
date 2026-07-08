"""System / health / auth Blueprint."""

from __future__ import annotations

import os

from flask import Blueprint, jsonify

from release_info import get_release_info

bp = Blueprint("system", __name__)


APP_AUTH_TOKEN = os.environ.get("APP_AUTH_TOKEN", "").strip()


@bp.route("/api/frontend/vendor-check")
def api_frontend_vendor_check():
    """检查 Excel 在线编辑所需静态资源是否存在（内网部署自检）"""
    from pathlib import Path
    from shared import FRONTEND_DIR

    checks = {"vendor_route": True, "files": {}}
    paths = {
        "plugin_js": FRONTEND_DIR / "vendor" / "luckysheet" / "plugins" / "js" / "plugin.js",
        "luckysheet_umd": FRONTEND_DIR / "vendor" / "luckysheet" / "luckysheet.umd.js",
    }
    all_ok = True
    for key, p in paths.items():
        exists = p.is_file()
        checks["files"][key] = {"path": str(p), "exists": exists}
        if not exists:
            all_ok = False
    checks["ok"] = all_ok
    checks["hint"] = (
        "就绪"
        if all_ok
        else "缺少 frontend/vendor，请执行: node scripts/copy-frontend-vendor.js"
    )
    return jsonify(checks)


@bp.route("/api/auth/config", methods=["GET"])
def api_auth_config():
    return jsonify({"status": "ok", "auth_required": bool(APP_AUTH_TOKEN)})


@bp.route("/api/build_info", methods=["GET"])
def api_build_info():
    info = get_release_info()
    return jsonify({"status": "ok", "step2_excel": True, **info})


@bp.route("/api/version", methods=["GET"])
def api_version():
    """标准版本查询（内网部署识别 / 升级比对）。"""
    return jsonify({"status": "ok", **get_release_info()})


@bp.route("/api/health")
def health():
    return jsonify({"status": "ok", **get_release_info()})

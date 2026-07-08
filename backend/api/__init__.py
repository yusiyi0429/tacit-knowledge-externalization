"""Flask application factory and Blueprint registration."""

from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, request, jsonify

from release_info import get_release_info


def create_app(config_name: str | None = None) -> Flask:
    """Application factory: create and configure the Flask app."""
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB upload limit

    # Optional API token auth
    app_auth_token = os.environ.get("APP_AUTH_TOKEN", "").strip()
    auth_exempt_paths = frozenset({"/api/health", "/api/version", "/api/auth/config"})

    @app.before_request
    def _require_api_auth():
        if not app_auth_token:
            return None
        if not request.path.startswith("/api/"):
            return None
        if request.path in auth_exempt_paths:
            return None
        auth = (request.headers.get("Authorization") or "").strip()
        if auth == f"Bearer {app_auth_token}":
            return None
        return jsonify({"status": "error", "error": "未授权访问"}), 401

    # Import and register blueprints
    from api.static import bp as static_bp
    from api.system import bp as system_bp
    from api.files import bp as files_bp
    from api.pipelines import bp as pipelines_bp
    from api.models import bp as models_bp
    from api.skills import bp as skills_bp
    from api.knowledge_base import bp as kb_bp
    from api.interview import bp as interview_bp
    from api.step1 import bp as step1_bp
    from api.step2 import bp as step2_bp
    from api.step3 import bp as step3_bp
    from api.step4 import bp as step4_bp
    from api.step5 import bp as step5_bp

    app.register_blueprint(static_bp)
    app.register_blueprint(system_bp)
    app.register_blueprint(files_bp, url_prefix="/api/files")
    app.register_blueprint(pipelines_bp, url_prefix="/api/pipelines")
    app.register_blueprint(models_bp, url_prefix="/api/llm")
    app.register_blueprint(skills_bp, url_prefix="/api/skills")
    app.register_blueprint(kb_bp, url_prefix="/api/kb")
    app.register_blueprint(interview_bp, url_prefix="/api/interview")
    app.register_blueprint(step1_bp, url_prefix="/api/step1")
    app.register_blueprint(step2_bp, url_prefix="/api/step2")
    app.register_blueprint(step3_bp, url_prefix="/api/step3")
    app.register_blueprint(step4_bp, url_prefix="/api/step4")
    app.register_blueprint(step5_bp, url_prefix="/api/step5")

    return app

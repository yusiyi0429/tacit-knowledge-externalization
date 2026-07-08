"""LLM model management and testing Blueprint."""

from __future__ import annotations

from flask import Blueprint, request, jsonify

from services.model_service import (
    add_model,
    delete_model,
    get_model,
    list_models,
    stream_test_model,
    test_model,
    update_model,
)

bp = Blueprint("models", __name__)


@bp.route("/models", methods=["GET"])
def api_llm_list_models():
    """List all available models (presets + custom); API keys are masked."""
    return jsonify(list_models())


@bp.route("/models", methods=["POST"])
def api_llm_add_model():
    """Add a custom model."""
    data = request.get_json(force=True)
    return jsonify(add_model(data))


@bp.route("/models/<path:model_name>", methods=["GET"])
def api_llm_get_model(model_name):
    """Get model config for editing (API key not returned)."""
    return jsonify(get_model(model_name))


@bp.route("/models/<path:model_name>", methods=["PUT"])
def api_llm_update_model(model_name):
    """Update a preset (saved as override) or custom model."""
    data = request.get_json(force=True)
    return jsonify(update_model(model_name, data))


@bp.route("/models/<path:model_name>", methods=["DELETE"])
def api_llm_delete_model(model_name):
    """Delete a custom model (presets cannot be deleted)."""
    return jsonify(delete_model(model_name))


@bp.route("/test", methods=["POST"])
def api_llm_test():
    """Test connection to a model."""
    data = request.get_json(force=True)
    return jsonify(test_model(data.get("name", "")))


@bp.route("/stream-test", methods=["POST"])
def api_llm_stream_test():
    """Stream-test LLM connection; forwards deltas as SSE to the browser."""
    data = request.get_json(force=True) or {}
    model_name = data.get("name", "")
    prompt = (data.get("prompt") or "你好，请用一句话介绍你自己。").strip()
    return stream_test_model(model_name, prompt)

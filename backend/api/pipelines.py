"""Pipeline management Blueprint."""

from __future__ import annotations

from flask import Blueprint, request, jsonify

import shared
from services.pipeline_service import (
    clear_pipeline,
    create_pipeline,
    delete_pipeline,
    get_pipeline,
    list_pipelines,
    rollback_pipeline,
    update_pipeline,
)

bp = Blueprint("pipelines", __name__)


@bp.route("", methods=["GET"])
def api_list_pipelines():
    """List all pipelines, newest first."""
    pipelines = list_pipelines()
    return jsonify({"status": "ok", "pipelines": pipelines})


@bp.route("", methods=["POST"])
def api_create_pipeline():
    """Create a new pipeline."""
    data = request.get_json(force=True)
    return jsonify(create_pipeline(data, shared.WORKSPACE))


@bp.route("/<pipeline_id>", methods=["GET"])
def api_get_pipeline(pipeline_id):
    """Get a single pipeline by ID."""
    pipeline = get_pipeline(pipeline_id)
    if pipeline:
        return jsonify({"status": "ok", "pipeline": pipeline})
    return jsonify({"status": "error", "error": "流水线不存在"})


@bp.route("/<pipeline_id>", methods=["PUT"])
def api_update_pipeline(pipeline_id):
    """Update a pipeline's step status/data."""
    data = request.get_json(force=True)
    return jsonify(update_pipeline(pipeline_id, data, shared.WORKSPACE))


@bp.route("/<pipeline_id>", methods=["DELETE"])
def api_delete_pipeline(pipeline_id):
    """Delete a pipeline."""
    return jsonify(delete_pipeline(pipeline_id, shared.WORKSPACE))


@bp.route("/<pipeline_id>/clear", methods=["POST"])
def api_clear_pipeline(pipeline_id):
    """Clear a pipeline's step data and reset all steps to pending."""
    return jsonify(clear_pipeline(pipeline_id))


@bp.route("/<pipeline_id>/rollback/<int:step>", methods=["POST"])
def api_rollback_pipeline(pipeline_id, step):
    """Roll back a pipeline to a previous step; reset downstream step status and outputs."""
    return jsonify(rollback_pipeline(pipeline_id, step, shared.WORKSPACE))

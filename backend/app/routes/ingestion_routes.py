"""
Blueprint: /api/ingestion
Implements all endpoints from PRD Section 14.1.
"""
import uuid
from flask import Blueprint, jsonify, request

from app.services.ingestion_service import ingestion_service
from app.services.corpus_drift_detector import corpus_drift_detector
from app.utils.task_manager import task_manager

ingestion_bp = Blueprint("ingestion", __name__)


@ingestion_bp.post("/pull")
def pull():
    """
    POST /api/ingestion/pull
    Body: {entity_id, sources:[{platform, ids:[]}], limit}
    Returns: {task_id}
    """
    body = request.get_json(force=True) or {}
    entity_id = body.get("entity_id")
    sources = body.get("sources", [])
    limit = int(body.get("limit", 500))

    if not entity_id:
        return jsonify({"error": "entity_id is required"}), 400
    if not sources:
        return jsonify({"error": "sources list is required"}), 400

    def _run(task, entity_id=entity_id, sources=sources, limit=limit):
        result = ingestion_service.pull_entity(entity_id, sources, limit, task=task)
        # Trigger background persona refresh if corpus has drifted
        new_count = result.get("records_new", 0)
        corpus_drift_detector.check_and_refresh(entity_id, new_count)
        return result

    task = task_manager.run_async("ingestion_pull", _run)
    return jsonify({"task_id": task.task_id}), 202


@ingestion_bp.get("/status/<task_id>")
def status(task_id: str):
    """GET /api/ingestion/status/<task_id>"""
    task = task_manager.get(task_id)
    if not task:
        return jsonify({"error": "task not found"}), 404

    resp = task.to_dict()
    if task.result:
        resp.update({
            "records_pulled": task.result.get("records_pulled", 0),
            "records_new": task.result.get("records_new", 0),
            "errors": task.result.get("errors", []),
        })
    return jsonify(resp)


@ingestion_bp.get("/preview/<entity_id>")
def preview(entity_id: str):
    """GET /api/ingestion/preview/<entity_id>?limit=20"""
    limit = int(request.args.get("limit", 20))
    records = ingestion_service.read_queue(entity_id, limit)
    return jsonify({"entity_id": entity_id, "records": records, "count": len(records)})


@ingestion_bp.post("/schedule")
def schedule():
    """
    POST /api/ingestion/schedule
    Body: {entity_id, sources, interval_seconds}
    Returns: {schedule_id}
    """
    body = request.get_json(force=True) or {}
    entity_id = body.get("entity_id")
    sources = body.get("sources", [])
    interval_seconds = int(body.get("interval_seconds", 3600))

    if not entity_id:
        return jsonify({"error": "entity_id is required"}), 400

    schedule_id = str(uuid.uuid4())
    ingestion_service.run_scheduled_pull(
        schedule_id, entity_id, sources, interval_seconds
    )
    return jsonify({"schedule_id": schedule_id, "interval_seconds": interval_seconds})


@ingestion_bp.delete("/schedule/<schedule_id>")
def delete_schedule(schedule_id: str):
    """DELETE /api/ingestion/schedule/<schedule_id>"""
    ok = ingestion_service.stop_schedule(schedule_id)
    if not ok:
        return jsonify({"error": "schedule not found"}), 404
    return jsonify({"ok": True})

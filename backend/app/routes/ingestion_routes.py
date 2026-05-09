"""
Blueprint: /api/ingestion
Implements all endpoints from PRD Section 14.1.
"""
import uuid
from flask import Blueprint, jsonify, request

from app.services.ingestion_service import ingestion_service
from app.services.corpus_drift_detector import corpus_drift_detector
from app.services.byo_upload_service import byo_upload_service
from app.services.entity_store import entity_store
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


@ingestion_bp.post("/auto-pull")
def auto_pull():
    """
    POST /api/ingestion/auto-pull
    Body: {entity_id, limit?}
    Automatically ingests from all free sources using entity name + keywords.
    Returns: {task_id}
    """
    body = request.get_json(force=True) or {}
    entity_id = body.get("entity_id")
    limit = int(body.get("limit", 500))
    extra_terms = body.get("extra_terms", [])

    if not entity_id:
        return jsonify({"error": "entity_id is required"}), 400

    def _run(task, entity_id=entity_id, limit=limit, extra_terms=extra_terms):
        result = ingestion_service.auto_pull(entity_id, limit, task=task, extra_terms=extra_terms)
        new_count = result.get("records_new", 0)
        corpus_drift_detector.check_and_refresh(entity_id, new_count)
        return result

    task = task_manager.run_async("ingestion_auto_pull", _run)
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


@ingestion_bp.post("/upload")
def upload():
    """
    POST /api/ingestion/upload
    Multipart form with:
      - entity_id        (str, required)
      - file             (the JSONL or CSV file)
      - file_format      (optional; auto-detected from extension if absent)
      - column_mapping   (optional JSON string for CSV)
      - default_platform (optional, defaults to "uploaded")

    Returns: {records_added, records_skipped, errors[], output_path}
    Synchronous (file-bounded work; no task queue).
    """
    import json as _json
    import os as _os
    import tempfile

    entity_id = request.form.get("entity_id") or (request.get_json(silent=True) or {}).get("entity_id")
    if not entity_id:
        return jsonify({"error": "entity_id is required"}), 400
    if not entity_store.get(entity_id):
        return jsonify({"error": f"entity {entity_id} not found"}), 404

    f = request.files.get("file")
    if f is None:
        return jsonify({"error": "file (multipart upload) is required"}), 400

    # Determine format
    fmt = (request.form.get("file_format") or "").lower().strip()
    if not fmt:
        name = (f.filename or "").lower()
        if name.endswith(".jsonl") or name.endswith(".ndjson"):
            fmt = "jsonl"
        elif name.endswith(".csv"):
            fmt = "csv"
        else:
            return jsonify({"error": "could not infer file_format; pass file_format=jsonl|csv"}), 400

    cm_raw = request.form.get("column_mapping")
    column_mapping = None
    if cm_raw:
        try:
            column_mapping = _json.loads(cm_raw)
            if not isinstance(column_mapping, dict):
                raise ValueError("column_mapping must be a JSON object")
        except (ValueError, _json.JSONDecodeError) as exc:
            return jsonify({"error": f"invalid column_mapping: {exc}"}), 400

    default_platform = request.form.get("default_platform", "uploaded")

    # Save to temp and process
    suffix = ".jsonl" if fmt == "jsonl" else ".csv"
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    try:
        with _os.fdopen(fd, "wb") as out_fh:
            f.save(out_fh)
        result = byo_upload_service.ingest_uploaded_file(
            entity_id=entity_id,
            file_path=tmp_path,
            file_format=fmt,
            column_mapping=column_mapping,
            default_platform=default_platform,
        )
    finally:
        try:
            _os.unlink(tmp_path)
        except OSError:
            pass
    return jsonify(result)


@ingestion_bp.get("/twitter/check")
def twitter_check():
    """
    GET /api/ingestion/twitter/check
    Quick health check: validates TWITTER_BEARER_TOKEN by hitting the
    /2/users/me equivalent (a tiny search). Returns {ok, message, tier_hint}.
    """
    from app.config import Config
    if not Config.TWITTER_BEARER_TOKEN:
        return jsonify({
            "ok": False,
            "message": "TWITTER_BEARER_TOKEN not set in .env",
        }), 200

    try:
        import tweepy
        client = tweepy.Client(bearer_token=Config.TWITTER_BEARER_TOKEN)
        resp = client.search_recent_tweets(query="hello lang:en", max_results=10)
        n = len(resp.data) if resp and resp.data else 0
        return jsonify({
            "ok": True,
            "message": f"Bearer token works — fetched {n} sample tweets",
        })
    except Exception as exc:
        msg = str(exc)
        hint = ""
        if "403" in msg or "Unauthorized" in msg or "401" in msg:
            hint = " (token may be invalid; recent search requires Basic tier+)"
        return jsonify({"ok": False, "message": msg, "tier_hint": hint}), 200


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

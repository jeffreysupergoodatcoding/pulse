"""
Blueprint: /api/persona
All endpoints from PRD Section 14.5.
"""
from flask import Blueprint, jsonify, request

from app.services.persona_engine import persona_engine
from app.services.entity_store import entity_store
from app.utils.task_manager import task_manager

persona_bp = Blueprint("persona", __name__)


@persona_bp.post("/generate")
def generate():
    """
    POST /api/persona/generate
    Body: {entity_id, n_clusters, n_agents_per_cluster}
    Returns: {task_id}
    """
    body = request.get_json(force=True) or {}
    entity_id = body.get("entity_id")
    if not entity_id:
        return jsonify({"error": "entity_id is required"}), 400

    entity = entity_store.get(entity_id)
    if not entity:
        return jsonify({"error": f"Entity {entity_id} not found"}), 404

    n_clusters = int(body.get("n_clusters", 8))
    n_agents = int(body.get("n_agents_per_cluster", 12))

    def _run(task, entity_id=entity_id, entity=entity, n_clusters=n_clusters, n_agents=n_agents):
        set_id = persona_engine.run(
            entity_id=entity_id,
            entity_name=entity.name,
            community_name=body.get("community_name", f"{entity.name} community"),
            n_clusters=n_clusters,
            n_agents_per_archetype=n_agents,
            task=task,
        )
        # Update entity's active persona set
        entity.active_persona_set_id = set_id
        entity_store.update(entity)
        return {"persona_set_id": set_id}

    task = task_manager.run_async("persona_generate", _run)
    return jsonify({"task_id": task.task_id}), 202


@persona_bp.get("/status/<task_id>")
def status(task_id: str):
    """GET /api/persona/status/<task_id>"""
    task = task_manager.get(task_id)
    if not task:
        return jsonify({"error": "task not found"}), 404
    resp = task.to_dict()
    if task.result:
        resp["persona_set_id"] = task.result.get("persona_set_id")
    return jsonify(resp)


@persona_bp.get("/<entity_id>/sets")
def list_sets(entity_id: str):
    """GET /api/persona/<entity_id>/sets"""
    sets = persona_engine.list_persona_sets(entity_id)
    return jsonify(sets)


@persona_bp.get("/<entity_id>/set/<set_id>")
def get_set(entity_id: str, set_id: str):
    """GET /api/persona/<entity_id>/set/<set_id>"""
    try:
        data = persona_engine.get_persona_set(entity_id, set_id)
        return jsonify(data)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 404



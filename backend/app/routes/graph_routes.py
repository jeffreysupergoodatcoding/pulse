"""
Blueprint: /api/graph
All endpoints from PRD Section 14.2.
"""
from flask import Blueprint, jsonify, request

from app.services.graph_builder_service import graph_builder_service
from app.services.entity_store import entity_store
from app.utils.task_manager import task_manager

graph_bp = Blueprint("graph", __name__)


@graph_bp.post("/build")
def build():
    """
    POST /api/graph/build
    Body: {entity_id}
    Returns: {task_id}
    """
    body = request.get_json(force=True) or {}
    entity_id = body.get("entity_id")
    if not entity_id:
        return jsonify({"error": "entity_id is required"}), 400

    entity = entity_store.get(entity_id)
    if not entity:
        return jsonify({"error": f"Entity {entity_id} not found"}), 404

    def _run(task, entity_id=entity_id):
        return graph_builder_service.build(entity_id, task=task)

    task = task_manager.run_async("graph_build", _run)
    return jsonify({"task_id": task.task_id}), 202


@graph_bp.get("/status/<task_id>")
def status(task_id: str):
    """GET /api/graph/status/<task_id>"""
    task = task_manager.get(task_id)
    if not task:
        return jsonify({"error": "task not found"}), 404
    resp = task.to_dict()
    if task.result:
        resp.update({
            "nodes_added": task.result.get("nodes_added", 0),
            "edges_added": task.result.get("edges_added", 0),
            "episodes_added": task.result.get("episodes_added", 0),
        })
    return jsonify(resp)


@graph_bp.get("/<entity_id>/data")
def graph_data(entity_id: str):
    """
    GET /api/graph/<entity_id>/data
    Returns {nodes, edges} for D3.js. Merges local SQLite cache + live Zep nodes.
    """
    source = request.args.get("source", "local")  # "local" | "zep"

    if source == "zep":
        data = graph_builder_service.get_zep_nodes_edges(entity_id)
    else:
        data = graph_builder_service.get_local_graph_data(entity_id)

    return jsonify(data)


@graph_bp.get("/<entity_id>/ontology")
def ontology(entity_id: str):
    """GET /api/graph/<entity_id>/ontology"""
    return jsonify(graph_builder_service.get_ontology(entity_id))


@graph_bp.get("/<entity_id>/sentiment")
def sentiment(entity_id: str):
    """GET /api/graph/<entity_id>/sentiment"""
    return jsonify(graph_builder_service.get_sentiment(entity_id))


@graph_bp.post("/<entity_id>/search")
def search(entity_id: str):
    """
    POST /api/graph/<entity_id>/search
    Body: {query, k}
    """
    body = request.get_json(force=True) or {}
    query = body.get("query", "")
    k = int(body.get("k", 10))
    if not query:
        return jsonify({"error": "query is required"}), 400
    episodes = graph_builder_service.search(entity_id, query, k)
    return jsonify({"episodes": episodes, "total": len(episodes)})


# ------------------------------------------------------------------
# Entity management (needed to bootstrap graph builds)
# ------------------------------------------------------------------

@graph_bp.post("/entities")
def create_entity():
    """
    POST /api/graph/entities
    Body: {name, entity_type, description, keywords, source_config}
    Returns: TrackedEntity
    """
    body = request.get_json(force=True) or {}
    name = body.get("name")
    entity_type = body.get("entity_type", "brand")
    if not name:
        return jsonify({"error": "name is required"}), 400

    entity = entity_store.create(
        name=name,
        entity_type=entity_type,
        description=body.get("description", ""),
        keywords=body.get("keywords", []),
    )
    return jsonify(entity.model_dump(mode="json")), 201


@graph_bp.get("/entities")
def list_entities():
    """GET /api/graph/entities"""
    entities = entity_store.list_all()
    return jsonify([e.model_dump(mode="json") for e in entities])


@graph_bp.get("/entities/<entity_id>")
def get_entity(entity_id: str):
    """GET /api/graph/entities/<entity_id>"""
    entity = entity_store.get(entity_id)
    if not entity:
        return jsonify({"error": "not found"}), 404
    return jsonify(entity.model_dump(mode="json"))


@graph_bp.put("/entities/<entity_id>")
def update_entity(entity_id: str):
    """
    PUT /api/graph/entities/<entity_id>
    Accepts partial updates: description, keywords, source_config.
    """
    entity = entity_store.get(entity_id)
    if not entity:
        return jsonify({"error": "not found"}), 404

    body = request.get_json(force=True) or {}
    if "description" in body:
        entity.description = body["description"]
    if "keywords" in body:
        entity.keywords = body["keywords"]
    if "source_config" in body:
        sc = body["source_config"]
        entity.source_config.reddit = sc.get("reddit", entity.source_config.reddit)
        entity.source_config.twitter = sc.get("twitter", entity.source_config.twitter)
        entity.source_config.youtube = sc.get("youtube", entity.source_config.youtube)
        entity.source_config.rss = sc.get("rss", entity.source_config.rss)

    entity_store.update(entity)
    return jsonify(entity.model_dump(mode="json"))

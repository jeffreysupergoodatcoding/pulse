"""
Blueprint: /api/audience  —  Layer 2 audience-discovery endpoints.

Methods B & C from the audience-expansion roadmap:

  Method B — POST /api/audience/adjacent
    Body: {target_entity_id, category_entity_id, n_clusters?, explain?}
    Returns: list[AdjacentCommunity] — clusters in the broader category corpus
             that the target brand isn't reaching, ranked by 'distance_from_target'.

  Method C — POST /api/audience/negative-space
    Body: {target_entity_id, competitor_entity_ids: [...], explain?}
    Returns: {overlap_matrix, negative_space_audiences, positioning_gaps}

  Helper — POST /api/audience/overlap
    Body: {target_entity_id, competitor_entity_ids: [...]}
    Returns: AudienceOverlapMatrix only (no LLM, no negative-space analysis).

All endpoints are synchronous for now (no task queue) since the heavy
work — clustering + LLM positioning-gap analysis — is bounded by corpus size.
For larger corpora we'd want to wrap these in task_manager.run_async.
"""
from flask import Blueprint, jsonify, request

from app.services.audience_discovery_service import audience_discovery_service
from app.services.audience_overlap_service import audience_overlap_service
from app.services.media_brief_service import media_brief_service
from app.services.entity_store import entity_store

audience_bp = Blueprint("audience", __name__)


@audience_bp.post("/adjacent")
def adjacent():
    """Method B — adjacent communities in a category corpus."""
    body = request.get_json(force=True) or {}
    target = body.get("target_entity_id")
    category = body.get("category_entity_id")
    n_clusters = int(body.get("n_clusters", 6))
    explain = bool(body.get("explain", True))

    if not target or not category:
        return jsonify({"error": "target_entity_id and category_entity_id required"}), 400
    if not entity_store.get(target):
        return jsonify({"error": f"target entity {target} not found"}), 404
    if not entity_store.get(category):
        return jsonify({"error": f"category entity {category} not found"}), 404

    communities = audience_discovery_service.discover_adjacent_communities(
        target_entity_id=target,
        category_entity_id=category,
        n_clusters=n_clusters,
        explain=explain,
    )
    return jsonify({
        "target_entity_id": target,
        "category_entity_id": category,
        "n_communities": len(communities),
        "communities": [c.model_dump(mode="json") for c in communities],
    })


@audience_bp.post("/negative-space")
def negative_space():
    """Method C — competitor-only audiences + positioning gaps."""
    body = request.get_json(force=True) or {}
    target = body.get("target_entity_id")
    competitors = body.get("competitor_entity_ids") or []
    explain = bool(body.get("explain", True))

    if not target:
        return jsonify({"error": "target_entity_id required"}), 400
    if not competitors:
        return jsonify({"error": "competitor_entity_ids must be a non-empty list"}), 400
    if not entity_store.get(target):
        return jsonify({"error": f"target entity {target} not found"}), 404
    for cid in competitors:
        if not entity_store.get(cid):
            return jsonify({"error": f"competitor entity {cid} not found"}), 404

    result = audience_discovery_service.discover_negative_space(
        target_entity_id=target,
        competitor_entity_ids=competitors,
        explain=explain,
    )
    return jsonify({
        "target_entity_id": target,
        "competitor_entity_ids": competitors,
        **result,
    })


@audience_bp.post("/brief")
def brief():
    """Chunk 1 / Actionability — produce an ExecutionBrief from any audience.

    Body:
      {
        target_entity_id: str,
        audience: dict,            # the AdjacentCommunity OR NegativeSpaceAudience
                                   # object the client already received from
                                   # /adjacent or /negative-space
        source_method: str = ""    # 'method_b_adjacent' | 'method_c_negative_space'
        extra_context: str = ""    # optional free-text injected into the prompt
      }

    Returns: ExecutionBrief with full markdown_export string ready to copy/save.
    """
    body = request.get_json(force=True) or {}
    target = body.get("target_entity_id")
    audience = body.get("audience")
    source_method = body.get("source_method", "")
    extra_context = body.get("extra_context", "")

    if not target:
        return jsonify({"error": "target_entity_id required"}), 400
    if not audience or not isinstance(audience, dict):
        return jsonify({"error": "audience (object) required"}), 400
    if not entity_store.get(target):
        return jsonify({"error": f"target entity {target} not found"}), 404

    brief = media_brief_service.build_brief(
        audience=audience,
        target_entity_id=target,
        source_method=source_method,
        extra_context=extra_context,
    )
    return jsonify(brief.model_dump(mode="json"))


@audience_bp.post("/overlap")
def overlap():
    """Helper — pairwise audience overlap matrix only (no LLM, no analysis)."""
    body = request.get_json(force=True) or {}
    target = body.get("target_entity_id")
    competitors = body.get("competitor_entity_ids") or []
    if not target:
        return jsonify({"error": "target_entity_id required"}), 400
    if not competitors:
        return jsonify({"error": "competitor_entity_ids required"}), 400
    matrix = audience_overlap_service.overlap_matrix(target, competitors)
    return jsonify(matrix.model_dump(mode="json"))

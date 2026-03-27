"""
Blueprint: /api/simulation
All endpoints from PRD Section 14.3.
"""
from flask import Blueprint, jsonify, request, Response
import json

from app.services.simulation_manager import simulation_manager
from app.services.simulation_runner import simulation_runner
from app.services.sentiment_aggregator import sentiment_aggregator
from app.services.prediction_engine import prediction_engine

simulation_bp = Blueprint("simulation", __name__)


@simulation_bp.post("/create")
def create():
    """
    POST /api/simulation/create
    Body: {entity_id, persona_set_id?, config_overrides?, rounds?, n_agents?}
    Returns: {simulation_id}
    """
    body = request.get_json(force=True) or {}
    entity_id = body.get("entity_id")
    if not entity_id:
        return jsonify({"error": "entity_id is required"}), 400

    try:
        state = simulation_manager.create(
            entity_id=entity_id,
            persona_set_id=body.get("persona_set_id"),
            config_overrides=body.get("config_overrides"),
            rounds=body.get("rounds"),
            n_agents=body.get("n_agents"),
        )
        return jsonify({"simulation_id": state.simulation_id}), 201
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@simulation_bp.post("/<sim_id>/start")
def start(sim_id: str):
    """POST /api/simulation/<sim_id>/start"""
    body = request.get_json(force=True) or {}
    hypothetical_event = body.get("hypothetical_event")

    state = simulation_manager.get_state(sim_id)
    if not state:
        return jsonify({"error": "simulation not found"}), 404

    entity_id = state.get("entity_id", "")
    ok = simulation_runner.start(sim_id, entity_id, hypothetical_event)
    if not ok:
        return jsonify({"error": "failed to start simulation"}), 500
    return jsonify({"ok": True, "simulation_id": sim_id})


@simulation_bp.get("/<sim_id>/status")
def status(sim_id: str):
    """GET /api/simulation/<sim_id>/status"""
    state = simulation_manager.get_state(sim_id)
    if not state:
        return jsonify({"error": "simulation not found"}), 404
    state["subprocess_running"] = simulation_runner.is_running(sim_id)
    return jsonify(state)


@simulation_bp.post("/<sim_id>/stop")
def stop(sim_id: str):
    """POST /api/simulation/<sim_id>/stop"""
    ok = simulation_runner.stop(sim_id)
    return jsonify({"ok": ok})


@simulation_bp.post("/<sim_id>/inject")
def inject(sim_id: str):
    """POST /api/simulation/<sim_id>/inject"""
    body = request.get_json(force=True) or {}
    event_text = body.get("event_text", "")
    round_num = int(body.get("round", 0))
    platforms = body.get("platforms", ["twitter", "reddit"])
    if not event_text:
        return jsonify({"error": "event_text required"}), 400
    ok = simulation_manager.inject_event(sim_id, event_text, round_num, platforms)
    return jsonify({"ok": ok})


@simulation_bp.get("/<sim_id>/actions")
def actions(sim_id: str):
    """GET /api/simulation/<sim_id>/actions?round=N&platform=X&limit=50"""
    round_num = request.args.get("round", type=int)
    platform = request.args.get("platform")
    limit = request.args.get("limit", 50, type=int)
    results = simulation_manager.get_actions(sim_id, round_num, platform, limit)
    return jsonify(results)


@simulation_bp.get("/<sim_id>/stream")
def stream(sim_id: str):
    """GET /api/simulation/<sim_id>/stream — SSE stream of actions (v1: polling fallback)"""
    def _generate():
        import time
        from pathlib import Path
        from app.config import Config
        actions_path = Path(Config.SIMULATIONS_DIR) / sim_id / "actions.jsonl"
        sent = 0
        for _ in range(30):   # stream for up to 30s
            if actions_path.exists():
                with actions_path.open() as fh:
                    lines = fh.readlines()
                for line in lines[sent:]:
                    sent += 1
                    line = line.strip()
                    if line:
                        yield f"data: {line}\n\n"
            time.sleep(1)

    return Response(_generate(), mimetype="text/event-stream")


@simulation_bp.get("/<sim_id>/sentiment")
def sentiment(sim_id: str):
    """GET /api/simulation/<sim_id>/sentiment"""
    state = simulation_manager.get_state(sim_id)
    if not state:
        return jsonify({"error": "simulation not found"}), 404
    data = sentiment_aggregator.get_sentiment(sim_id)
    return jsonify(data)


@simulation_bp.get("/<sim_id>/prediction")
def prediction(sim_id: str):
    """GET /api/simulation/<sim_id>/prediction"""
    state = simulation_manager.get_state(sim_id)
    if not state:
        return jsonify({"error": "simulation not found"}), 404
    data = prediction_engine.get_prediction(sim_id)
    return jsonify(data)

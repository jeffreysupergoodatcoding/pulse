"""
Blueprint: /api/report
All endpoints from PRD Section 14.4.
"""
from __future__ import annotations

from pathlib import Path

from flask import Blueprint, jsonify, request

from app.config import Config
from app.services.report_agent import report_agent
from app.services.simulation_manager import simulation_manager

report_bp = Blueprint("report", __name__)

_SIMS_DIR = Path(Config.SIMULATIONS_DIR)


def _resolve_sim_id(report_id: str) -> str | None:
    """
    Scan simulation dirs to find which one contains this report_id.
    Returns sim_id string or None if not found.
    """
    if not _SIMS_DIR.exists():
        return None
    for sim_dir in _SIMS_DIR.iterdir():
        if not sim_dir.is_dir():
            continue
        state_path = sim_dir / "reports" / report_id / "state.json"
        if state_path.exists():
            return sim_dir.name
    return None


# ---------------------------------------------------------------------------
# POST /api/report/generate
# ---------------------------------------------------------------------------

@report_bp.post("/generate")
def generate():
    """
    POST /api/report/generate
    Body: {simulation_id}
    Returns: {report_id}
    """
    body = request.get_json(force=True) or {}
    sim_id = body.get("simulation_id")
    if not sim_id:
        return jsonify({"error": "simulation_id is required"}), 400

    state = simulation_manager.get_state(sim_id)
    if not state:
        return jsonify({"error": "simulation not found"}), 404

    report_id = report_agent.start_generation(sim_id)
    return jsonify({"report_id": report_id}), 202


# ---------------------------------------------------------------------------
# GET /api/report/<report_id>/status
# ---------------------------------------------------------------------------

@report_bp.get("/<report_id>/status")
def status(report_id: str):
    """GET /api/report/<report_id>/status"""
    sim_id = _resolve_sim_id(report_id)
    if not sim_id:
        return jsonify({"error": "report not found"}), 404
    state = report_agent.get_state(sim_id, report_id)
    if not state:
        return jsonify({"error": "report state not found"}), 404
    return jsonify({
        "report_id": report_id,
        "status": state.get("status"),
        "sections_done": state.get("sections_done", 0),
        "total_sections": state.get("total_sections", 8),
        "error": state.get("error"),
    })


# ---------------------------------------------------------------------------
# GET /api/report/<report_id>/content
# ---------------------------------------------------------------------------

@report_bp.get("/<report_id>/content")
def content(report_id: str):
    """GET /api/report/<report_id>/content"""
    sim_id = _resolve_sim_id(report_id)
    if not sim_id:
        return jsonify({"error": "report not found"}), 404
    md = report_agent.get_content(sim_id, report_id)
    if md is None:
        state = report_agent.get_state(sim_id, report_id) or {}
        if state.get("status") == "running":
            return jsonify({"markdown": "", "status": "running"}), 202
        return jsonify({"error": "report content not available"}), 404
    return jsonify({"markdown": md})


# ---------------------------------------------------------------------------
# POST /api/report/<report_id>/chat/agent
# ---------------------------------------------------------------------------

@report_bp.post("/<report_id>/chat/agent")
def chat_agent(report_id: str):
    """POST /api/report/<report_id>/chat/agent  Body: {agent_id, message, history}"""
    sim_id = _resolve_sim_id(report_id)
    if not sim_id:
        return jsonify({"error": "report not found"}), 404
    body = request.get_json(force=True) or {}
    agent_id = body.get("agent_id", "")
    message = body.get("message", "")
    history = body.get("history", [])
    if not agent_id or not message:
        return jsonify({"error": "agent_id and message are required"}), 400
    response = report_agent.chat_agent(sim_id, agent_id, message, history)
    return jsonify({"response": response})


# ---------------------------------------------------------------------------
# POST /api/report/<report_id>/chat/report_agent
# ---------------------------------------------------------------------------

@report_bp.post("/<report_id>/chat/report_agent")
def chat_report_agent(report_id: str):
    """POST /api/report/<report_id>/chat/report_agent  Body: {message, history}"""
    sim_id = _resolve_sim_id(report_id)
    if not sim_id:
        return jsonify({"error": "report not found"}), 404
    body = request.get_json(force=True) or {}
    message = body.get("message", "")
    history = body.get("history", [])
    if not message:
        return jsonify({"error": "message is required"}), 400
    response = report_agent.chat_report_agent(sim_id, report_id, message, history)
    return jsonify({"response": response})


# ---------------------------------------------------------------------------
# POST /api/report/<report_id>/drilldown
# ---------------------------------------------------------------------------

@report_bp.post("/<report_id>/drilldown")
def drilldown(report_id: str):
    """POST /api/report/<report_id>/drilldown  Body: {entity_id, persona_filter?, time_range?}"""
    sim_id = _resolve_sim_id(report_id)
    if not sim_id:
        return jsonify({"error": "report not found"}), 404
    body = request.get_json(force=True) or {}
    entity_id = body.get("entity_id", "")
    persona_filter = body.get("persona_filter")
    time_range = body.get("time_range")
    result = report_agent.drilldown(sim_id, entity_id, persona_filter, time_range)
    return jsonify(result)


# ---------------------------------------------------------------------------
# POST /api/report/<report_id>/signal
# ---------------------------------------------------------------------------

@report_bp.post("/<report_id>/signal")
def signal(report_id: str):
    """POST /api/report/<report_id>/signal"""
    sim_id = _resolve_sim_id(report_id)
    if not sim_id:
        return jsonify({"error": "report not found"}), 404
    sim_state = simulation_manager.get_state(sim_id) or {}
    entity_id = sim_state.get("entity_id", "")
    miro_signal = report_agent.generate_signal(sim_id, entity_id)
    return jsonify({"miro_signal": miro_signal})

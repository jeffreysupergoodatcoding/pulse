"""
SimulationManager — orchestrates Steps 2a/2b (profile + config preparation).
Prepares all inputs for the simulation subprocess.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.config import Config
from app.models import SimulationRunState
from app.services.entity_store import entity_store
from app.services.persona_engine import persona_engine
from app.services.simulation_config_generator import simulation_config_generator
from app.services.sentiment_scorer import sentiment_scorer
from app.utils.logger import get_logger

logger = get_logger("simulation_manager")


class SimulationManager:
    def __init__(self, config: type[Config] = Config):
        self.config = config

    def create(
        self,
        entity_id: str,
        persona_set_id: str | None = None,
        config_overrides: dict | None = None,
        rounds: int | None = None,
        n_agents: int | None = None,
    ) -> SimulationRunState:
        """
        Prepare simulation directory, profiles, and config.
        Returns the SimulationRunState with simulation_id assigned.
        """
        entity = entity_store.get(entity_id)
        if not entity:
            raise ValueError(f"Entity {entity_id} not found")

        # Resolve persona set
        set_id = persona_set_id or entity.active_persona_set_id
        if not set_id:
            raise ValueError(f"No persona set for entity {entity_id}. Run /api/persona/generate first.")

        sim_id = str(uuid.uuid4())
        sim_dir = Path(self.config.SIMULATIONS_DIR) / sim_id
        sim_dir.mkdir(parents=True, exist_ok=True)

        # Load profiles
        persona_data = persona_engine.get_persona_set(entity_id, set_id)
        profiles = persona_data.get("profiles", [])
        if not profiles:
            raise ValueError(f"Persona set {set_id} has no profiles")

        # Cap n_agents
        n = min(n_agents or self.config.DEFAULT_N_AGENTS, len(profiles))
        profiles = profiles[:n]

        # Write profiles.json for subprocess
        profiles_path = sim_dir / "profiles.json"
        profiles_path.write_text(json.dumps(profiles, indent=2, default=str))

        # Generate simulation config
        cfg = simulation_config_generator.generate(
            entity_name=entity.name,
            entity_type=entity.entity_type,
            n_agents=n,
            rounds=rounds or self.config.DEFAULT_SIM_ROUNDS,
        )
        if config_overrides:
            cfg.update(config_overrides)

        config_path = sim_dir / "simulation_config.json"
        config_path.write_text(json.dumps(cfg, indent=2))

        # Write initial run_state
        state = SimulationRunState(
            simulation_id=sim_id,
            entity_id=entity_id,
            persona_set_id=set_id,
            status="idle",
            total_rounds=cfg["rounds"],
        )
        (sim_dir / "state.json").write_text(state.model_dump_json(indent=2))

        logger.info(f"Created simulation {sim_id}: {n} agents, {cfg['rounds']} rounds")
        return state

    def get_state(self, sim_id: str) -> dict | None:
        """Read run_state.json (written by subprocess) or state.json (initial)."""
        sim_dir = Path(self.config.SIMULATIONS_DIR) / sim_id
        run_state_path = sim_dir / "run_state.json"
        state_path = sim_dir / "state.json"

        if run_state_path.exists():
            try:
                return json.loads(run_state_path.read_text())
            except Exception:
                pass
        if state_path.exists():
            try:
                return json.loads(state_path.read_text())
            except Exception:
                pass
        return None

    def get_actions(self, sim_id: str, round_num: int | None = None, platform: str | None = None, limit: int = 50) -> list[dict]:
        """Read actions.jsonl with optional filters."""
        actions_path = Path(self.config.SIMULATIONS_DIR) / sim_id / "actions.jsonl"
        if not actions_path.exists():
            return []
        results = []
        with actions_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    if round_num is not None and record.get("round") != round_num:
                        continue
                    if platform and record.get("platform") != platform:
                        continue
                    if record.get("sentiment_score") is None:
                        scored = sentiment_scorer.score(record)
                        record["sentiment_score"] = scored["sentiment_score"]
                        record["emotion"] = scored["emotion"]
                        record["confidence"] = scored["confidence"]
                    results.append(record)
                except json.JSONDecodeError:
                    pass
        return results[-limit:]

    def inject_event(self, sim_id: str, event_text: str, round_num: int, platforms: list[str]) -> bool:
        """Write to inject_queue.json for the simulation subprocess to pick up."""
        sim_dir = Path(self.config.SIMULATIONS_DIR) / sim_id
        if not sim_dir.exists():
            return False
        queue_path = sim_dir / "inject_queue.json"
        existing = []
        if queue_path.exists():
            try:
                existing = json.loads(queue_path.read_text())
            except Exception:
                pass
        existing.append({
            "event_text": event_text,
            "round": round_num,
            "platforms": platforms,
            "queued_at": datetime.now(timezone.utc).isoformat(),
        })
        queue_path.write_text(json.dumps(existing, indent=2))
        return True


    def list_simulations(self, entity_id: str) -> list[dict]:
        """List all simulations for an entity, most recent first."""
        sims_dir = Path(self.config.SIMULATIONS_DIR)
        if not sims_dir.exists():
            return []
        results = []
        for sim_dir in sims_dir.iterdir():
            if not sim_dir.is_dir():
                continue
            state_path = sim_dir / "state.json"
            if not state_path.exists():
                continue
            try:
                initial = json.loads(state_path.read_text())
            except Exception:
                continue
            if initial.get("entity_id") != entity_id:
                continue
            merged = dict(initial)
            run_path = sim_dir / "run_state.json"
            if run_path.exists():
                try:
                    merged.update(json.loads(run_path.read_text()))
                except Exception:
                    pass
            results.append({
                "simulation_id": merged.get("simulation_id", sim_dir.name),
                "status": merged.get("status", "idle"),
                "current_round": merged.get("current_round", 0),
                "total_rounds": merged.get("total_rounds", 0),
                "actions_count": merged.get("actions_count", 0),
                "started_at": merged.get("started_at"),
                "completed_at": merged.get("completed_at"),
            })
        results.sort(key=lambda x: x.get("started_at") or "", reverse=True)
        return results


simulation_manager = SimulationManager(Config)

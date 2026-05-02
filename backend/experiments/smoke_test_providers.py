"""Smoke test: 3 agents, 2 rounds for each LLM provider.

Confirms the model_factory + simulation_runner plumbing works for all 3
providers before running the full experiment.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

API = "http://localhost:5001"
ENTITY_ID = "51f12c06-d7e0-4658-b458-9f1b72cbc0a5"
PERSONA_SET_ID = "0229a343-7b98-4e19-8801-09c3ea6f0139"
SIM_DIR = Path("/Users/jeffreysu/Desktop/personal projects/pulse/backend/data/simulations")


def post(path: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{API}{path}", data=data,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def get(path: str) -> dict:
    return json.loads(urllib.request.urlopen(f"{API}{path}", timeout=30).read())


def smoke(provider: str, n_agents: int = 3, rounds: int = 2, max_wait: int = 240) -> dict:
    print(f"\n=== {provider} ===", flush=True)
    sim = post("/api/simulation/create", {
        "entity_id": ENTITY_ID,
        "persona_set_id": PERSONA_SET_ID,
        "rounds": rounds,
        "n_agents": n_agents,
    })
    sim_id = sim["simulation_id"]
    print(f"  sim_id={sim_id}", flush=True)

    start = post(f"/api/simulation/{sim_id}/start", {"llm_provider": provider})
    print(f"  started: provider={start.get('llm_provider')}", flush=True)

    elapsed = 0
    while elapsed < max_wait:
        st = get(f"/api/simulation/{sim_id}/status")
        if st.get("status") in ("completed", "error"):
            break
        time.sleep(3)
        elapsed += 3
    if st.get("status") != "completed":
        print(f"  TIMEOUT/ERROR: status={st.get('status')}, error={st.get('error_message')}", flush=True)
        return {"provider": provider, "sim_id": sim_id, "ok": False, "status": st.get("status")}

    actions_path = SIM_DIR / sim_id / "actions.jsonl"
    counts: Counter = Counter()
    with actions_path.open() as f:
        for line in f:
            counts[json.loads(line)["action_type"]] += 1

    state = json.loads((SIM_DIR / sim_id / "run_state.json").read_text())
    print(f"  total_actions={sum(counts.values())}, types={dict(counts)}", flush=True)
    print(f"  tagged: provider={state.get('llm_provider')}, model={state.get('llm_model')}", flush=True)
    return {
        "provider": provider,
        "sim_id": sim_id,
        "ok": True,
        "n_actions": sum(counts.values()),
        "action_types": dict(counts),
        "tagged_provider": state.get("llm_provider"),
        "tagged_model": state.get("llm_model"),
    }


if __name__ == "__main__":
    results = [smoke(p) for p in ("gemini", "openai", "anthropic")]
    print("\n=== SUMMARY ===")
    print(json.dumps(results, indent=2))

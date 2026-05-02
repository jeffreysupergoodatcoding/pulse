"""
Pulse final-project experiment orchestrator.

Runs the 4-test x 3-provider model comparison.

Tests:
  1. Hochul climate-law backtest    (NY state policy, recent state-level event)
  2. Nothing Phone (4a) Pro          (positive product launch backtest)
  3. Apple Vision Pro shelving       (negative product launch backtest)
  4. NBA Finals MVP forecast         (forward-looking)

Each test:
  - ingest ~200 tweets from past 7 days (HN auto-fallback)
  - build knowledge graph
  - generate 20 persona agents (5 archetypes x 4 agents)
  - run sim with each of {gemini, openai, anthropic}
  - for backtests: pull post-event tweets as ground truth, VADER-score, compare

Outputs to: backend/data/experiment_results/<timestamp>/
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "http://localhost:5001"
ROOT = Path(__file__).resolve().parents[1]
SIM_DIR = ROOT / "data" / "simulations"
EXP_DIR = ROOT / "data" / "experiment_results" / datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
EXP_DIR.mkdir(parents=True, exist_ok=True)

PROVIDERS = ["gemini", "openai", "anthropic"]


# ---------------------------------------------------------------------------
# Test definitions
# ---------------------------------------------------------------------------

TESTS = [
    {
        "key": "hochul_climate",
        "title": "NY Climate Law Standoff (Hochul)",
        "domain": "political",
        "mode": "backtest",
        "twitter_query": '("Hochul" OR "CLCPA" OR "climate law") (NY OR "New York")',
        "hn_query": "Hochul climate New York",
        "event": (
            "Gov. Hochul has agreed to a 2028 deadline compromise on the NY Climate "
            "Leadership and Community Protection Act, ending the late-budget standoff. "
            "Environmental advocates wanted 2027; Hochul originally pushed 2030."
        ),
    },
    {
        "key": "nothing_4a_pro",
        "title": "Nothing Phone (4a) Pro Launch",
        "domain": "marketing_positive",
        "mode": "backtest",
        "twitter_query": '("Nothing Phone" OR "Nothing 4a")',
        "hn_query": "Nothing Phone 4a Pro",
        "event": (
            "Nothing has launched the Phone (4a) Pro at $499 with a 144Hz AMOLED, "
            "improved cameras, Glyph Matrix interface, and Nothing OS 4.1 on Android 16. "
            "No wireless charging."
        ),
    },
    {
        "key": "vision_pro_shelved",
        "title": "Apple Vision Pro Shelved",
        "domain": "marketing_negative",
        "mode": "backtest",
        "twitter_query": '("Vision Pro" OR "AVP" OR "Apple headset")',
        "hn_query": "Apple Vision Pro M5",
        "event": (
            "Apple has effectively shelved the Vision Pro. The M5 refresh failed to drive "
            "sales, return rates set internal records, the Vision Pro team has been disbanded, "
            "and there is no successor headset in development. The product remains for sale "
            "at $3,499 but the line is in maintenance mode."
        ),
    },
    {
        "key": "nba_mvp_2026",
        "title": "2026 NBA Finals MVP Forecast",
        "domain": "sports_forward",
        "mode": "forward",
        "twitter_query": '(NBA OR Finals OR MVP OR playoffs)',
        "hn_query": "NBA playoffs MVP",
        "event": (
            "The 2026 NBA Finals tip off in early June. Discuss who will win the championship "
            "and who will win Finals MVP, citing recent playoff form and matchups."
        ),
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def post(path: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{API}{path}", data=data,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def get(path: str) -> dict:
    return json.loads(urllib.request.urlopen(f"{API}{path}", timeout=60).read())


def wait_for_task(api_path: str, status_url: str, timeout: int = 600, label: str = "task") -> dict:
    """Poll a task endpoint until completed or error. Returns final body."""
    elapsed = 0
    last_progress = -1
    while elapsed < timeout:
        body = get(status_url)
        st = body.get("status")
        prog = body.get("progress", 0)
        if prog != last_progress:
            print(f"    [{label}] progress={prog}% status={st}", flush=True)
            last_progress = prog
        if st == "completed":
            return body
        if st == "error":
            raise RuntimeError(f"{label} failed: {body.get('error')}")
        time.sleep(3)
        elapsed += 3
    raise TimeoutError(f"{label} timed out after {timeout}s")


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Phase 1: entities
# ---------------------------------------------------------------------------

def ensure_entity(name: str, description: str, keywords: list[str]) -> str:
    """Find existing entity by name or create a new one."""
    existing = get("/api/graph/entities")
    for e in existing:
        if e["name"] == name:
            log(f"reusing entity {name} ({e['id']})")
            return e["id"]
    body = post("/api/graph/entities", {
        "name": name,
        "entity_type": "topic",
        "description": description,
        "keywords": keywords,
    })
    log(f"created entity {name} ({body['id']})")
    return body["id"]


# ---------------------------------------------------------------------------
# Phase 2: ingest (Twitter primary, HN fallback)
# ---------------------------------------------------------------------------

def ingest(entity_id: str, twitter_q: str, hn_q: str, limit: int = 200) -> dict:
    """Try Twitter; if it returns sparse, also pull HN."""
    sources = [
        {"platform": "twitter", "ids": [twitter_q]},
        {"platform": "hackernews", "ids": [hn_q]},
    ]
    body = post("/api/ingestion/pull", {
        "entity_id": entity_id, "sources": sources, "limit": limit,
    })
    task_id = body["task_id"]
    return wait_for_task(
        f"/api/ingestion/pull",
        f"/api/ingestion/status/{task_id}",
        timeout=300,
        label=f"ingest({entity_id[:8]})",
    )


# ---------------------------------------------------------------------------
# Phase 3: build graph
# ---------------------------------------------------------------------------

def build_graph(entity_id: str) -> dict:
    body = post("/api/graph/build", {"entity_id": entity_id})
    return wait_for_task(
        "/api/graph/build",
        f"/api/graph/status/{body['task_id']}",
        timeout=900,
        label=f"graph({entity_id[:8]})",
    )


# ---------------------------------------------------------------------------
# Phase 4: persona generation
# ---------------------------------------------------------------------------

def gen_personas(entity_id: str, n_clusters: int = 5, n_per: int = 4) -> str:
    body = post("/api/persona/generate", {
        "entity_id": entity_id,
        "n_clusters": n_clusters,
        "n_agents_per_cluster": n_per,
    })
    result = wait_for_task(
        "/api/persona/generate",
        f"/api/persona/status/{body['task_id']}",
        timeout=900,
        label=f"persona({entity_id[:8]})",
    )
    return result["persona_set_id"]


# ---------------------------------------------------------------------------
# Phase 5: simulation
# ---------------------------------------------------------------------------

def run_sim(
    entity_id: str, persona_set_id: str, provider: str,
    rounds: int, n_agents: int, event: str | None,
) -> dict:
    sim = post("/api/simulation/create", {
        "entity_id": entity_id,
        "persona_set_id": persona_set_id,
        "rounds": rounds,
        "n_agents": n_agents,
    })
    sim_id = sim["simulation_id"]
    body = {"llm_provider": provider}
    if event:
        body["hypothetical_event"] = event
    post(f"/api/simulation/{sim_id}/start", body)

    # Poll until completed
    elapsed = 0
    timeout = 3600   # 1 hour — Anthropic Sonnet can be slow
    last = ""
    while elapsed < timeout:
        st = get(f"/api/simulation/{sim_id}/status")
        status = st.get("status")
        if status in ("completed", "error", "stopped"):
            break
        rnd = st.get("current_round", 0)
        total = st.get("total_rounds", rounds)
        cur = f"round {rnd}/{total} actions={st.get('actions_count',0)}"
        if cur != last:
            print(f"    [sim/{provider}] {cur}", flush=True)
            last = cur
        time.sleep(5)
        elapsed += 5
    if status != "completed":
        raise RuntimeError(f"sim {provider} failed: status={status}")
    return {"sim_id": sim_id, "provider": provider, "n_agents": n_agents, "rounds": rounds}


# ---------------------------------------------------------------------------
# Sentiment computation (post-hoc) — VADER on each action's content
# ---------------------------------------------------------------------------

def compute_sentiment_trajectory(sim_id: str) -> list[dict]:
    """Return [{round, mean_score, n_actions}, ...] using VADER."""
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    sia = SentimentIntensityAnalyzer()
    actions_path = SIM_DIR / sim_id / "actions.jsonl"
    by_round: dict[int, list[float]] = {}
    with actions_path.open() as f:
        for line in f:
            r = json.loads(line)
            content = r.get("action_args", {}).get("content", "") or ""
            if not content.strip():
                # Use the precomputed sentiment_score (handles likes/dislikes)
                s = r.get("sentiment_score")
                if s is None:
                    continue
                score = float(s)
            else:
                score = sia.polarity_scores(content)["compound"]
            by_round.setdefault(r["round"], []).append(score)
    return [
        {"round": rnd, "mean_score": sum(s)/len(s) if s else 0.0, "n_actions": len(s)}
        for rnd, s in sorted(by_round.items())
    ]


# ---------------------------------------------------------------------------
# Ground truth: pull post-event tweets and VADER-score
# ---------------------------------------------------------------------------

def pull_ground_truth(entity_id: str, twitter_q: str, days: int = 4) -> list[float]:
    """Pull recent tweets and return VADER compound scores."""
    body = post("/api/ingestion/pull", {
        "entity_id": entity_id,
        "sources": [{"platform": "twitter", "ids": [twitter_q]}],
        "limit": 50,
    })
    wait_for_task(
        "/api/ingestion/pull",
        f"/api/ingestion/status/{body['task_id']}",
        timeout=180,
        label=f"groundtruth({entity_id[:8]})",
    )
    # Read the freshly appended posts from today's JSONL
    today = datetime.now().strftime("%Y-%m-%d")
    jsonl = ROOT / "data" / "entities" / entity_id / "ingestion" / f"posts_{today}.jsonl"
    if not jsonl.exists():
        return []
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    sia = SentimentIntensityAnalyzer()
    scores: list[float] = []
    with jsonl.open() as f:
        for line in f:
            r = json.loads(line)
            if r.get("platform") != "twitter":
                continue
            content = r.get("content", "")
            if content:
                scores.append(sia.polarity_scores(content)["compound"])
    return scores


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # CLI: --only <test_key> to run a single test for verification
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--only", default=None, help="Run only this test_key")
    p.add_argument("--skip-personas", action="store_true",
                   help="Reuse existing persona set if entity has one")
    args = p.parse_args()

    tests = TESTS
    if args.only:
        tests = [t for t in TESTS if t["key"] == args.only]
        if not tests:
            raise SystemExit(f"No test with key={args.only}; valid: {[t['key'] for t in TESTS]}")

    log(f"Experiment results dir: {EXP_DIR}")
    log(f"Running {len(tests)} test(s): {[t['key'] for t in tests]}")
    summary: dict = {"experiment_dir": str(EXP_DIR), "tests": []}

    for test in tests:
        log(f"\n=== TEST: {test['title']} ===")

        # Phase 1: entity
        ent_id = ensure_entity(
            name=test["key"],
            description=test["title"],
            keywords=[test["twitter_query"]],
        )

        # Phase 2: ingest
        log(f"  ingesting twitter+hn corpus")
        ing = ingest(ent_id, test["twitter_query"], test["hn_query"], limit=200)
        log(f"  ingest result: pulled={ing.get('records_pulled')} new={ing.get('records_new')}")

        # Phase 3: graph
        log(f"  building knowledge graph")
        gb = build_graph(ent_id)
        log(f"  graph: nodes={gb.get('nodes_added')} edges={gb.get('edges_added')}")

        # Phase 4: personas
        log(f"  generating personas")
        pset = gen_personas(ent_id, n_clusters=5, n_per=4)
        log(f"  persona_set_id={pset}")

        # Phase 5: 3 sims (gemini, openai, anthropic)
        sims_info = []
        for prov in PROVIDERS:
            log(f"  running sim provider={prov}")
            sim = run_sim(
                entity_id=ent_id,
                persona_set_id=pset,
                provider=prov,
                rounds=10,
                n_agents=20,
                event=test["event"],
            )
            traj = compute_sentiment_trajectory(sim["sim_id"])
            sim["trajectory"] = traj
            sims_info.append(sim)
            log(f"    provider={prov} sim_id={sim['sim_id']} trajectory_points={len(traj)}")

        # Ground truth (only for backtests)
        gt_scores: list[float] = []
        if test["mode"] == "backtest":
            log(f"  pulling ground truth tweets")
            gt_scores = pull_ground_truth(ent_id, test["twitter_query"])
            log(f"    ground_truth_n={len(gt_scores)}")

        test_summary = {
            **test,
            "entity_id": ent_id,
            "persona_set_id": pset,
            "ingest": {
                "records_pulled": ing.get("records_pulled"),
                "records_new": ing.get("records_new"),
            },
            "graph": {
                "nodes": gb.get("nodes_added"),
                "edges": gb.get("edges_added"),
                "episodes": gb.get("episodes_added"),
            },
            "sims": sims_info,
            "ground_truth_scores": gt_scores,
            "ground_truth_mean": sum(gt_scores)/len(gt_scores) if gt_scores else None,
        }
        summary["tests"].append(test_summary)

        # Save partial after each test (so we don't lose work on failure)
        (EXP_DIR / "partial_summary.json").write_text(json.dumps(summary, indent=2))
        log(f"  partial summary written")

    (EXP_DIR / "final_summary.json").write_text(json.dumps(summary, indent=2))
    log(f"\nDONE. Final summary at {EXP_DIR}/final_summary.json")


if __name__ == "__main__":
    main()

"""
Aggregate all 4-test x 3-provider experiment runs and compute comparison metrics.

Walks the entity → sim → actions data on disk, ignoring the orchestrator's
ad-hoc summary files (some collided), and produces a single canonical
results bundle for the DOCX writeup.

Outputs:
  data/experiment_results/aggregate/results.json
  data/experiment_results/aggregate/per_test/<test>.json
"""
from __future__ import annotations

import json
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIM_DIR = ROOT / "data" / "simulations"
ENT_DIR = ROOT / "data" / "entities"
OUT = ROOT / "data" / "experiment_results" / "aggregate"
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "per_test").mkdir(exist_ok=True)


# Test → entity name (matches entity store)
TESTS = [
    {"key": "vision_pro_shelved", "title": "Apple Vision Pro Shelved", "domain": "marketing_negative", "mode": "backtest"},
    {"key": "nothing_4a_pro",     "title": "Nothing Phone (4a) Pro",   "domain": "marketing_positive", "mode": "backtest"},
    {"key": "hochul_climate",     "title": "NY Climate Law Standoff",  "domain": "political",          "mode": "backtest"},
    {"key": "nba_mvp_2026",       "title": "2026 NBA Finals Forecast", "domain": "sports_forward",     "mode": "forward"},
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_entity_id(name: str) -> str | None:
    for d in ENT_DIR.iterdir():
        if not d.is_dir():
            continue
        cfg = d / "config.json"
        if not cfg.exists():
            continue
        try:
            data = json.loads(cfg.read_text())
            if data.get("name") == name:
                return d.name
        except Exception:
            pass
    return None


def find_sims_for_entity(entity_id: str) -> dict[str, dict]:
    """Return {provider: sim_dict} for sims tied to this entity, taking the
    most recent completed sim per provider (matched by N agents = 20)."""
    sims_by_provider: dict[str, dict] = {}
    for sim_dir in sorted(SIM_DIR.iterdir(), key=lambda d: d.stat().st_mtime):
        state_path = sim_dir / "state.json"
        run_state_path = sim_dir / "run_state.json"
        if not (state_path.exists() and run_state_path.exists()):
            continue
        try:
            state = json.loads(state_path.read_text())
            run = json.loads(run_state_path.read_text())
        except Exception:
            continue
        if state.get("entity_id") != entity_id:
            continue
        # Filter to completed sims (experiment uses 10 rounds; smoke tests use 2)
        if run.get("status") != "completed":
            continue
        if run.get("total_rounds", 0) != 10:
            continue
        provider = run.get("llm_provider", "")
        if not provider:
            continue
        sims_by_provider[provider] = {
            "sim_id": sim_dir.name,
            "provider": provider,
            "model": run.get("llm_model", ""),
            "rounds": run.get("total_rounds", 0),
            "current_round": run.get("current_round", 0),
            "actions_count": run.get("actions_count", 0),
            "note": run.get("note", ""),
        }
    return sims_by_provider


def trajectory_from_sim(sim_id: str) -> list[dict]:
    """Per-round VADER mean compound score from the sim's actions.jsonl."""
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    sia = SentimentIntensityAnalyzer()
    actions_path = SIM_DIR / sim_id / "actions.jsonl"
    if not actions_path.exists():
        return []
    by_round: dict[int, list[float]] = defaultdict(list)
    for line in actions_path.open():
        a = json.loads(line)
        content = a.get("action_args", {}).get("content", "") or ""
        if content.strip():
            score = sia.polarity_scores(content)["compound"]
        else:
            s = a.get("sentiment_score")
            if s is None:
                continue
            score = float(s)
        by_round[a["round"]].append(score)
    return [
        {"round": r, "mean": sum(s) / len(s) if s else 0.0, "n": len(s)}
        for r, s in sorted(by_round.items())
    ]


def action_type_counts(sim_id: str) -> dict[str, int]:
    actions_path = SIM_DIR / sim_id / "actions.jsonl"
    if not actions_path.exists():
        return {}
    c = Counter()
    for line in actions_path.open():
        a = json.loads(line)
        c[a["action_type"]] += 1
    return dict(c)


def ground_truth_scores(entity_id: str) -> list[float]:
    """Read all twitter posts for entity from today's JSONL and VADER-score them."""
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    sia = SentimentIntensityAnalyzer()
    ing = ENT_DIR / entity_id / "ingestion"
    if not ing.exists():
        return []
    scores: list[float] = []
    for jsonl in sorted(ing.glob("posts_*.jsonl")):
        for line in jsonl.open():
            r = json.loads(line)
            if r.get("platform") != "twitter":
                continue
            c = r.get("content", "")
            if c:
                scores.append(sia.polarity_scores(c)["compound"])
    return scores


# ---------------------------------------------------------------------------
# Comparison metrics
# ---------------------------------------------------------------------------

def pearson(x: list[float], y: list[float]) -> float | None:
    if len(x) < 2 or len(y) < 2:
        return None
    n = min(len(x), len(y))
    x, y = x[:n], y[:n]
    mx = sum(x) / n
    my = sum(y) / n
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    dx = sum((a - mx) ** 2 for a in x) ** 0.5
    dy = sum((b - my) ** 2 for b in y) ** 0.5
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def mae(x: list[float], y: list[float]) -> float | None:
    if not x or not y:
        return None
    n = min(len(x), len(y))
    return sum(abs(a - b) for a, b in zip(x[:n], y[:n])) / n


def directional_agreement(sim_mean: float, gt_mean: float) -> bool:
    """Both negative (<-0.05), both positive (>0.05), or both neutral."""
    def cls(v: float) -> int:
        if v < -0.05:
            return -1
        if v > 0.05:
            return 1
        return 0
    return cls(sim_mean) == cls(gt_mean)


# ---------------------------------------------------------------------------
# NBA-specific extraction: who is predicted to win + Finals MVP
# ---------------------------------------------------------------------------

NBA_TEAMS = [
    "Celtics", "Boston", "Lakers", "Warriors", "Nuggets", "Thunder", "OKC",
    "Knicks", "Pacers", "Bucks", "Heat", "76ers", "Sixers", "Cavaliers",
    "Mavericks", "Dallas", "Timberwolves", "Wolves", "Suns",
]
NBA_PLAYERS = [
    "Tatum", "Brown", "Jokic", "Doncic", "Luka", "SGA", "Gilgeous-Alexander",
    "Giannis", "Antetokounmpo", "Embiid", "Curry", "LeBron", "Mitchell",
    "Haliburton", "Anthony Edwards", "Edwards", "KAT", "Towns",
    "Jaylen Brown", "Jayson Tatum", "Brunson", "Booker", "Durant",
]

def extract_nba_predictions(sim_id: str) -> dict:
    actions_path = SIM_DIR / sim_id / "actions.jsonl"
    if not actions_path.exists():
        return {}
    team_mentions: Counter = Counter()
    player_mentions: Counter = Counter()
    win_phrases: list[str] = []
    mvp_phrases: list[str] = []
    for line in actions_path.open():
        a = json.loads(line)
        content = a.get("action_args", {}).get("content", "") or ""
        if not content:
            continue
        for team in NBA_TEAMS:
            if re.search(rf"\b{team}\b", content, re.IGNORECASE):
                team_mentions[team] += 1
        for player in NBA_PLAYERS:
            if re.search(rf"\b{re.escape(player)}\b", content, re.IGNORECASE):
                player_mentions[player] += 1
        # Capture sentences that contain "win" near team/player names
        for sent in re.split(r"[.!?]", content):
            sl = sent.lower()
            if any(w in sl for w in ("win", "champion", "title")):
                if any(t.lower() in sl for t in NBA_TEAMS):
                    win_phrases.append(sent.strip()[:200])
            if "mvp" in sl:
                mvp_phrases.append(sent.strip()[:200])
    return {
        "team_mentions": dict(team_mentions.most_common(8)),
        "player_mentions": dict(player_mentions.most_common(10)),
        "win_phrases_sample": win_phrases[:5],
        "mvp_phrases_sample": mvp_phrases[:5],
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    aggregate = {
        "generated_at": datetime.now().isoformat(),
        "tests": [],
    }

    for test in TESTS:
        print(f"\n=== {test['title']} ===")
        ent_id = find_entity_id(test["key"])
        if not ent_id:
            print(f"  [skip] entity {test['key']} not found")
            continue
        print(f"  entity_id={ent_id}")

        sims = find_sims_for_entity(ent_id)
        print(f"  sims found by provider: {list(sims.keys())}")

        # Per-provider trajectory + action type stats
        per_provider = {}
        for prov, info in sims.items():
            traj = trajectory_from_sim(info["sim_id"])
            actypes = action_type_counts(info["sim_id"])
            per_provider[prov] = {
                **info,
                "trajectory": traj,
                "action_types": actypes,
                "total_actions": sum(actypes.values()),
                "n_action_types": len(actypes),
                "mean_sentiment": (
                    sum(p["mean"] for p in traj) / len(traj) if traj else None
                ),
            }
            print(f"  {prov}: rounds={len(traj)}, mean_sent={per_provider[prov]['mean_sentiment']:.3f}, "
                  f"types={len(actypes)}, total_actions={sum(actypes.values())}")

        # Ground truth (backtests only)
        gt = []
        gt_mean = None
        if test["mode"] == "backtest":
            gt = ground_truth_scores(ent_id)
            gt_mean = sum(gt) / len(gt) if gt else None
            print(f"  ground_truth: n={len(gt)} mean={gt_mean}")

        # Comparison metrics per provider
        comparisons = {}
        for prov, p in per_provider.items():
            if not p["trajectory"]:
                continue
            sim_means = [pt["mean"] for pt in p["trajectory"]]
            sim_overall = p["mean_sentiment"]
            if test["mode"] == "backtest" and gt_mean is not None:
                # Compare sim trajectory mean vs ground truth mean
                comparisons[prov] = {
                    "sim_mean": sim_overall,
                    "gt_mean": gt_mean,
                    "mae_overall": abs(sim_overall - gt_mean),
                    "directional_agreement": directional_agreement(sim_overall, gt_mean),
                    "trajectory_pearson": None,  # gt is not a trajectory, can't compute
                }

        # Cross-provider agreement (variance of mean sentiment across providers)
        provider_means = [
            p["mean_sentiment"] for p in per_provider.values()
            if p["mean_sentiment"] is not None
        ]
        cross_provider = {
            "n_providers": len(provider_means),
            "mean_of_means": sum(provider_means) / len(provider_means) if provider_means else None,
            "stdev_of_means": statistics.pstdev(provider_means) if len(provider_means) > 1 else None,
            "min": min(provider_means) if provider_means else None,
            "max": max(provider_means) if provider_means else None,
        }
        print(f"  cross-provider stdev={cross_provider['stdev_of_means']}")

        # NBA-specific predictions
        nba_predictions = {}
        if test["key"] == "nba_mvp_2026":
            for prov, info in sims.items():
                nba_predictions[prov] = extract_nba_predictions(info["sim_id"])

        test_data = {
            **test,
            "entity_id": ent_id,
            "providers": per_provider,
            "ground_truth": {
                "n": len(gt),
                "mean": gt_mean,
            },
            "comparisons": comparisons,
            "cross_provider": cross_provider,
            "nba_predictions": nba_predictions,
        }
        aggregate["tests"].append(test_data)

        # Per-test file
        (OUT / "per_test" / f"{test['key']}.json").write_text(json.dumps(test_data, indent=2))

    (OUT / "results.json").write_text(json.dumps(aggregate, indent=2))
    print(f"\n=== AGGREGATE WRITTEN ===")
    print(f"  {OUT / 'results.json'}")
    print(f"  per-test files in {OUT / 'per_test'}")


if __name__ == "__main__":
    main()

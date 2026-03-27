"""
PredictionEngine — trajectory, narratives, spread, and breakout agent analysis.

Output shape:
  {
    trajectory:      {predicted_final_score, confidence, direction, slope_per_round},
    narratives:      [{text, sentiment_score, frequency, rounds}],
    spread:          {peak_round, spread_velocity, total_rounds_active, platform_spread},
    breakout_agents: [{agent_id, influence_score, archetype, sentiment_shift,
                       action_count, mean_sentiment}],
  }
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from statistics import mean

import numpy as np

from app.config import Config
from app.utils.logger import get_logger

logger = get_logger("prediction_engine")


class PredictionEngine:
    def __init__(self, config: type[Config] = Config):
        self._sims_dir = Path(config.SIMULATIONS_DIR)

    def get_prediction(self, sim_id: str) -> dict:
        actions = self._load_actions(sim_id)
        scored = [a for a in actions if a.get("sentiment_score") is not None]

        if not scored:
            return {
                "trajectory": {},
                "narratives": [],
                "spread": {},
                "breakout_agents": [],
            }

        return {
            "trajectory": self._compute_trajectory(scored),
            "narratives": self._extract_narratives(scored),
            "spread": self._compute_spread(actions),   # all actions, not just scored
            "breakout_agents": self._find_breakout_agents(scored),
        }

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _load_actions(self, sim_id: str) -> list[dict]:
        path = self._sims_dir / sim_id / "actions.jsonl"
        if not path.exists():
            return []
        actions = []
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        actions.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return actions

    def _compute_trajectory(self, scored: list[dict]) -> dict:
        """Linear regression over per-round mean scores → forecast final score."""
        by_round: dict[int, list[float]] = defaultdict(list)
        for a in scored:
            by_round[int(a.get("round", 0))].append(float(a["sentiment_score"]))

        rounds = sorted(by_round.keys())
        if len(rounds) < 2:
            avg = mean(by_round[rounds[0]]) if rounds else 0.0
            return {
                "predicted_final_score": round(avg, 4),
                "confidence": 0.3,
                "direction": "stable",
                "slope_per_round": 0.0,
            }

        x = np.array(rounds, dtype=float)
        y = np.array([mean(by_round[r]) for r in rounds], dtype=float)
        slope, intercept = np.polyfit(x, y, 1)

        max_round = float(max(rounds))
        predicted = float(np.clip(slope * max_round + intercept, -1.0, 1.0))

        # R² as confidence proxy
        y_pred = slope * x + intercept
        ss_res = float(np.sum((y - y_pred) ** 2))
        ss_tot = float(np.sum((y - y.mean()) ** 2))
        r2 = max(0.0, 1.0 - ss_res / ss_tot) if ss_tot > 0 else 0.0

        direction = (
            "rising" if slope > 0.02
            else "falling" if slope < -0.02
            else "stable"
        )

        return {
            "predicted_final_score": round(predicted, 4),
            "confidence": round(r2, 4),
            "direction": direction,
            "slope_per_round": round(float(slope), 6),
        }

    def _extract_narratives(self, scored: list[dict]) -> list[dict]:
        """
        Identify top recurring content themes by clustering on first-60-char prefix.
        Returns up to 5 narrative threads sorted by frequency.
        """
        buckets: dict[str, dict] = {}

        for a in scored:
            content = (
                (a.get("action_args") or {}).get("content")
                or a.get("content")
                or ""
            ).strip()
            if not content:
                continue

            key = content[:60].lower()
            if key not in buckets:
                buckets[key] = {
                    "text": content[:160],
                    "scores": [],
                    "rounds": set(),
                    "count": 0,
                }
            buckets[key]["scores"].append(float(a["sentiment_score"]))
            buckets[key]["rounds"].add(int(a.get("round", 0)))
            buckets[key]["count"] += 1

        top = sorted(buckets.values(), key=lambda b: b["count"], reverse=True)[:5]
        return [
            {
                "text": b["text"],
                "sentiment_score": round(mean(b["scores"]), 4),
                "frequency": b["count"],
                "rounds": sorted(b["rounds"]),
            }
            for b in top
        ]

    def _compute_spread(self, actions: list[dict]) -> dict:
        """Activity spread: peak round, velocity, and per-platform counts."""
        by_round: dict[int, int] = defaultdict(int)
        platform_counts: dict[str, int] = defaultdict(int)

        for a in actions:
            by_round[int(a.get("round", 0))] += 1
            platform_counts[a.get("platform", "unknown")] += 1

        if not by_round:
            return {}

        rounds = sorted(by_round.keys())
        counts = [by_round[r] for r in rounds]
        peak_round = rounds[counts.index(max(counts))]
        spread_velocity = round(mean(counts), 2)

        return {
            "peak_round": peak_round,
            "spread_velocity": spread_velocity,
            "total_rounds_active": len(rounds),
            "platform_spread": dict(platform_counts),
        }

    def _find_breakout_agents(self, scored: list[dict]) -> list[dict]:
        """
        Top 5 agents by influence_score = mean(|sentiment|) × action_count / n_agents.
        Also reports sentiment_shift (max - min) as volatility indicator.
        """
        agent_map: dict[str, dict] = {}
        for a in scored:
            agent_id = str(a.get("agent_id", "unknown"))
            score = float(a["sentiment_score"])
            archetype = (
                a.get("archetype_id")
                or a.get("persona_archetype")
                or "unknown"
            )
            if agent_id not in agent_map:
                agent_map[agent_id] = {
                    "agent_id": agent_id,
                    "archetype": archetype,
                    "scores": [],
                }
            agent_map[agent_id]["scores"].append(score)

        n_agents = max(len(agent_map), 1)
        results = []
        for data in agent_map.values():
            s = data["scores"]
            if len(s) < 2:
                continue
            influence = round(mean(abs(v) for v in s) * len(s) / n_agents, 4)
            results.append({
                "agent_id": data["agent_id"],
                "influence_score": influence,
                "archetype": data["archetype"],
                "sentiment_shift": round(max(s) - min(s), 4),
                "action_count": len(s),
                "mean_sentiment": round(mean(s), 4),
            })

        results.sort(key=lambda r: r["influence_score"], reverse=True)
        return results[:5]


prediction_engine = PredictionEngine(Config)

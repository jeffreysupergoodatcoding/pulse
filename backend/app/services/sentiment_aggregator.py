"""
SentimentAggregator — reads actions.jsonl and returns aggregate sentiment metrics.

Output shape:
  {
    sentiment_by_round: [{round, mean_score, action_count, emotion_distribution}],
    overall:            {mean_score, trend, dominant_emotion, total_actions_scored},
    by_platform:        {<platform>: {mean_score, action_count}},
    by_archetype:       {<archetype>: {mean_score, action_count}},
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

logger = get_logger("sentiment_aggregator")


class SentimentAggregator:
    def __init__(self, config: type[Config] = Config):
        self._sims_dir = Path(config.SIMULATIONS_DIR)

    def get_sentiment(self, sim_id: str) -> dict:
        actions = self._load_actions(sim_id)
        scored = [a for a in actions if a.get("sentiment_score") is not None]

        if not scored:
            return {
                "sentiment_by_round": [],
                "overall": {},
                "by_platform": {},
                "by_archetype": {},
            }

        by_round: dict[int, list[dict]] = defaultdict(list)
        by_platform: dict[str, list[float]] = defaultdict(list)
        by_archetype: dict[str, list[float]] = defaultdict(list)
        all_scores: list[float] = []
        all_emotions: list[str] = []

        for a in scored:
            score = float(a["sentiment_score"])
            rnd = int(a.get("round", 0))
            platform = a.get("platform", "unknown")
            archetype = (
                a.get("archetype_id")
                or a.get("persona_archetype")
                or "unknown"
            )
            emotion = a.get("emotion", "neutral")

            by_round[rnd].append({"score": score, "emotion": emotion})
            by_platform[platform].append(score)
            by_archetype[archetype].append(score)
            all_scores.append(score)
            all_emotions.append(emotion)

        sentiment_by_round = []
        for rnd in sorted(by_round.keys()):
            items = by_round[rnd]
            scores = [i["score"] for i in items]
            emotions = [i["emotion"] for i in items]
            sentiment_by_round.append({
                "round": rnd,
                "mean_score": round(mean(scores), 4),
                "action_count": len(items),
                "emotion_distribution": _emotion_dist(emotions),
            })

        return {
            "sentiment_by_round": sentiment_by_round,
            "overall": {
                "mean_score": round(mean(all_scores), 4),
                "trend": _trend(sentiment_by_round),
                "dominant_emotion": _dominant(all_emotions),
                "total_actions_scored": len(all_scores),
            },
            "by_platform": {
                p: {"mean_score": round(mean(s), 4), "action_count": len(s)}
                for p, s in by_platform.items()
            },
            "by_archetype": {
                a: {"mean_score": round(mean(s), 4), "action_count": len(s)}
                for a, s in by_archetype.items()
            },
        }

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _emotion_dist(emotions: list[str]) -> dict[str, float]:
    counts: dict[str, int] = defaultdict(int)
    for e in emotions:
        counts[e] += 1
    total = len(emotions)
    return {e: round(c / total, 3) for e, c in sorted(counts.items())} if total else {}


def _dominant(emotions: list[str]) -> str:
    if not emotions:
        return "neutral"
    counts: dict[str, int] = defaultdict(int)
    for e in emotions:
        counts[e] += 1
    return max(counts, key=lambda k: counts[k])


def _trend(sentiment_by_round: list[dict]) -> str:
    """Returns 'rising', 'falling', or 'stable' from linear regression slope."""
    if len(sentiment_by_round) < 3:
        return "stable"
    x = np.array([r["round"] for r in sentiment_by_round], dtype=float)
    y = np.array([r["mean_score"] for r in sentiment_by_round], dtype=float)
    slope = float(np.polyfit(x, y, 1)[0])
    if slope > 0.02:
        return "rising"
    if slope < -0.02:
        return "falling"
    return "stable"


sentiment_aggregator = SentimentAggregator(Config)

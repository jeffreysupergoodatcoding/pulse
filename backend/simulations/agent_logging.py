"""
Agent action JSONL logger for the OASIS simulation.
Writes every agent action to actions.jsonl in the simulation output dir.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path


class AgentLogger:
    """Thread-safe JSONL writer for agent actions."""

    def __init__(self, output_dir: str | Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._path = self.output_dir / "actions.jsonl"
        self._lock = threading.Lock()
        self._count = 0

    def log(
        self,
        agent_id: int | str,
        platform: str,
        round_num: int,
        action_type: str,
        content: str | None = None,
        target_id: str | None = None,
        extra: dict | None = None,
    ) -> dict:
        record = {
            "action_id": f"{agent_id}_{round_num}_{self._count}",
            "agent_id": str(agent_id),
            "platform": platform,
            "round": round_num,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action_type": action_type,
            "action_args": {
                "content": content,
                "target_id": target_id,
            },
            "sentiment_score": None,   # filled later by SentimentScorer
        }
        if extra:
            record.update(extra)

        with self._lock:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record) + "\n")
            self._count += 1

        return record

    @property
    def count(self) -> int:
        return self._count

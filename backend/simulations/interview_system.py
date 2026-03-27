"""
File-based IPC handler for the ReportAgent interview system.
Mirrors MiroFish's interview pattern exactly.

Flow:
  ReportAgent writes  → simulations/{id}/command.json
  This module polls   → command.json every 500ms
  Loads agent profiles, calls LLM per agent
  Writes response     → simulations/{id}/response.json
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openai import OpenAI


class InterviewSystem:
    """
    Runs inside the simulation subprocess.
    Polls for interview commands and responds via LLM in-character.
    """

    POLL_INTERVAL = 0.5   # seconds

    def __init__(
        self,
        sim_dir: Path,
        profiles: list[dict],
        llm_client: OpenAI,
        model: str,
    ):
        self.sim_dir = sim_dir
        self.command_path = sim_dir / "command.json"
        self.response_path = sim_dir / "response.json"
        # profiles keyed by user_id string
        self.profiles = {str(p["user_id"]): p for p in profiles}
        self.llm = llm_client
        self.model = model
        self._last_command_ts: str | None = None

    def check_and_respond(self):
        """Call this each round. Non-blocking."""
        if not self.command_path.exists():
            return

        try:
            cmd = json.loads(self.command_path.read_text())
        except (json.JSONDecodeError, OSError):
            return

        # Skip if already handled this command
        ts = cmd.get("timestamp", "")
        if ts == self._last_command_ts:
            return
        self._last_command_ts = ts

        agent_ids: list[str] = cmd.get("agent_ids", [])
        prompt: str = cmd.get("prompt", "")
        if not agent_ids or not prompt:
            return

        responses: dict[str, str] = {}
        for agent_id in agent_ids:
            profile = self.profiles.get(str(agent_id))
            if not profile:
                responses[agent_id] = "[agent not found]"
                continue
            responses[agent_id] = self._interview_agent(profile, prompt)

        self.response_path.write_text(
            json.dumps({
                "agent_ids": agent_ids,
                "prompt": prompt,
                "responses": responses,
                "responded_at": datetime.now(timezone.utc).isoformat(),
            })
        )

    def _interview_agent(self, profile: dict, prompt: str) -> str:
        system = (
            f"You are {profile.get('name', 'a social media user')}. "
            f"{profile.get('persona_text', '')} "
            f"Bio: {profile.get('bio', '')} "
            f"Respond in character. Be concise (2-4 sentences)."
        )
        try:
            resp = self.llm.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=150,
                temperature=0.9,
            )
            return resp.choices[0].message.content or ""
        except Exception as exc:
            return f"[error: {exc}]"

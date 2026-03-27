"""
SimulationConfigGenerator — generates simulation_config.json via LLM.
Uses entity context to set realistic rounds, agent behaviors, and events.
"""
from __future__ import annotations

import json
from openai import OpenAI
from app.config import Config
from app.utils.logger import get_logger

logger = get_logger("simulation_config_generator")

_CONFIG_PROMPT = """Generate a simulation configuration JSON for a social media sentiment simulation.

Entity: {entity_name}
Entity type: {entity_type}
Community: {community_name}
Number of agents: {n_agents}
Requested rounds: {rounds}
Hypothetical event: {hypothetical_event}

Return a JSON object with these exact fields:
{{
  "rounds": <int, use requested rounds>,
  "step_duration_hours": <int 1-4, simulated hours per round>,
  "n_agents": <int>,
  "twitter_config": {{
    "timeline_size": 20,
    "recommendation_k": 10
  }},
  "reddit_config": {{
    "subreddits": [<2-3 relevant subreddit names>],
    "hot_post_count": 15
  }},
  "agent_activation_schedule": {{
    "low": [0.1, 0.2],
    "medium": [0.3, 0.5],
    "high": [0.6, 0.9]
  }},
  "initial_events": [
    {{"round": 0, "content": "<seed post content relevant to entity>", "platform": "both"}}
  ]
}}

Return only valid JSON."""


class SimulationConfigGenerator:
    def __init__(self, config: type[Config] = Config):
        self.client = OpenAI(api_key=config.LLM_API_KEY, base_url=config.LLM_BASE_URL)
        self.model = config.LLM_MODEL_NAME
        self.config = config

    def generate(
        self,
        entity_name: str,
        entity_type: str = "brand",
        community_name: str = "",
        n_agents: int = 0,
        rounds: int = 0,
        hypothetical_event: str | None = None,
    ) -> dict:
        n_agents = n_agents or self.config.DEFAULT_N_AGENTS
        rounds = rounds or self.config.DEFAULT_SIM_ROUNDS

        prompt = _CONFIG_PROMPT.format(
            entity_name=entity_name,
            entity_type=entity_type,
            community_name=community_name or f"{entity_name} community",
            n_agents=n_agents,
            rounds=rounds,
            hypothetical_event=hypothetical_event or "none",
        )
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.2,
            )
            cfg = json.loads(resp.choices[0].message.content or "{}")
            # Ensure required fields with safe defaults
            cfg.setdefault("rounds", rounds)
            cfg.setdefault("n_agents", n_agents)
            cfg.setdefault("step_duration_hours", 1)
            cfg.setdefault("twitter_config", {"timeline_size": 20, "recommendation_k": 10})
            cfg.setdefault("reddit_config", {"subreddits": ["all"], "hot_post_count": 15})
            cfg.setdefault("agent_activation_schedule", {"low": [0.1, 0.2], "medium": [0.3, 0.5], "high": [0.6, 0.9]})
            cfg.setdefault("initial_events", [])
            return cfg
        except Exception as exc:
            logger.error(f"Config generation failed: {exc}, using defaults")
            return self._default_config(entity_name, n_agents, rounds)

    def _default_config(self, entity_name: str, n_agents: int, rounds: int) -> dict:
        return {
            "rounds": rounds,
            "step_duration_hours": 1,
            "n_agents": n_agents,
            "twitter_config": {"timeline_size": 20, "recommendation_k": 10},
            "reddit_config": {"subreddits": ["all"], "hot_post_count": 15},
            "agent_activation_schedule": {"low": [0.1, 0.2], "medium": [0.3, 0.5], "high": [0.6, 0.9]},
            "initial_events": [{"round": 0, "content": f"What do people think about {entity_name}?", "platform": "both"}],
        }


simulation_config_generator = SimulationConfigGenerator(Config)

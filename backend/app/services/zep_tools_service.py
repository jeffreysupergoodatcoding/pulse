"""
ZepToolsService — 8 ReACT tools available to the ReportAgent (PRD Section 11.2).

Instantiated per-report with entity_id + sim_id context so every tool
can resolve its data without requiring extra parameters in the ReACT loop.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from statistics import mean

from openai import OpenAI

from app.config import Config
from app.services.graph_builder_service import graph_builder_service
from app.services.sentiment_aggregator import sentiment_aggregator
from app.services.prediction_engine import prediction_engine
from app.utils.logger import get_logger

logger = get_logger("zep_tools_service")

# Human-readable descriptions used in the ReACT system prompt
TOOL_DESCRIPTIONS = {
    "graph_search":        'graph_search(query, k=10) — semantic search of knowledge graph episodes',
    "sentiment_summary":   'sentiment_summary(breakdown_by=["archetype","round","platform"]) — structured sentiment metrics',
    "narrative_clusters":  "narrative_clusters(top_n=5) — top N narrative threads with sentiment",
    "persona_breakdown":   "persona_breakdown() — per-archetype avg sentiment, dominant emotion, quotes",
    "viral_spread":        "viral_spread() — expected reach, p90, time to peak, velocity",
    "interview_agents":    "interview_agents(agent_ids, prompt) — in-character responses from selected agents",
    "trajectory_chart":    "trajectory_chart() — sentiment_by_round chart data",
    "breakout_agents":     "breakout_agents(top_n=5) — top-N most influential agents",
}


class ZepToolsService:
    """
    Provides the 8 analysis tools for the ReportAgent's ReACT loop.
    All methods are synchronous and safe to call from a background thread.
    """

    def __init__(self, entity_id: str, sim_id: str, config: type[Config] = Config):
        self.entity_id = entity_id
        self.sim_id = sim_id
        self._sim_dir = Path(config.SIMULATIONS_DIR) / sim_id
        self._llm = OpenAI(api_key=config.LLM_API_KEY, base_url=config.LLM_BASE_URL)
        self._model = config.LLM_MODEL_NAME

    # ------------------------------------------------------------------
    # Tool 1 — graph_search
    # ------------------------------------------------------------------

    def graph_search(self, query: str, k: int = 10) -> list[dict]:
        """Semantic search of Zep knowledge graph episodes."""
        return graph_builder_service.search(self.entity_id, query, k)

    # ------------------------------------------------------------------
    # Tool 2 — sentiment_summary
    # ------------------------------------------------------------------

    def sentiment_summary(self, breakdown_by: list[str] | None = None) -> dict:
        """Structured sentiment metrics from SentimentAggregator."""
        breakdown_by = breakdown_by or ["archetype", "round", "platform"]
        data = sentiment_aggregator.get_sentiment(self.sim_id)
        result: dict = {"overall": data.get("overall", {})}
        if "round" in breakdown_by:
            result["by_round"] = data.get("sentiment_by_round", [])
        if "platform" in breakdown_by:
            result["by_platform"] = data.get("by_platform", {})
        if "archetype" in breakdown_by:
            result["by_archetype"] = data.get("by_archetype", {})
        return result

    # ------------------------------------------------------------------
    # Tool 3 — narrative_clusters
    # ------------------------------------------------------------------

    def narrative_clusters(self, top_n: int = 5) -> list[dict]:
        """Top N narrative clusters from PredictionEngine."""
        pred = prediction_engine.get_prediction(self.sim_id)
        return pred.get("narratives", [])[:top_n]

    # ------------------------------------------------------------------
    # Tool 4 — persona_breakdown
    # ------------------------------------------------------------------

    def persona_breakdown(self) -> dict:
        """Per-archetype: avg sentiment, dominant emotion, representative quotes."""
        actions = self._load_actions()
        scored = [a for a in actions if a.get("sentiment_score") is not None]

        buckets: dict[str, dict] = {}
        for a in scored:
            arch = a.get("archetype_id") or a.get("persona_archetype") or "unknown"
            content = (
                (a.get("action_args") or {}).get("content")
                or a.get("content")
                or ""
            ).strip()
            if arch not in buckets:
                buckets[arch] = {"scores": [], "emotions": [], "quotes": []}
            buckets[arch]["scores"].append(float(a["sentiment_score"]))
            buckets[arch]["emotions"].append(a.get("emotion", "neutral"))
            if content and len(buckets[arch]["quotes"]) < 3:
                buckets[arch]["quotes"].append(content[:120])

        result = {}
        for arch, data in buckets.items():
            emotion_counts: dict[str, int] = defaultdict(int)
            for e in data["emotions"]:
                emotion_counts[e] += 1
            dominant = max(emotion_counts, key=lambda k: emotion_counts[k]) if emotion_counts else "neutral"
            result[arch] = {
                "avg_sentiment": round(mean(data["scores"]), 4) if data["scores"] else 0.0,
                "dominant_emotion": dominant,
                "representative_quotes": data["quotes"],
                "action_count": len(data["scores"]),
            }
        return result

    # ------------------------------------------------------------------
    # Tool 5 — viral_spread
    # ------------------------------------------------------------------

    def viral_spread(self) -> dict:
        """SpreadEstimate: expected_reach, p90, time_to_peak, velocity."""
        pred = prediction_engine.get_prediction(self.sim_id)
        spread = pred.get("spread", {})
        actions = self._load_actions()
        n_agents = len({a.get("agent_id") for a in actions if a.get("agent_id")})

        return {
            "expected_reach": int(n_agents * 0.6),
            "p90": int(n_agents * 0.9),
            "time_to_peak": spread.get("peak_round", 0),
            "spread_velocity": spread.get("spread_velocity", 0.0),
            "platform_spread": spread.get("platform_spread", {}),
        }

    # ------------------------------------------------------------------
    # Tool 6 — interview_agents
    # ------------------------------------------------------------------

    def interview_agents(self, agent_ids: list[str], prompt: str) -> dict[str, str]:
        """In-character LLM responses from selected agent profiles."""
        profiles_path = self._sim_dir / "profiles.json"
        if not profiles_path.exists():
            return {aid: "[profiles not found]" for aid in agent_ids}

        try:
            profiles_list: list[dict] = json.loads(profiles_path.read_text())
        except Exception:
            return {aid: "[profile load error]" for aid in agent_ids}

        profiles = {str(p.get("user_id", i)): p for i, p in enumerate(profiles_list)}
        responses: dict[str, str] = {}

        for agent_id in agent_ids:
            profile = profiles.get(str(agent_id))
            if not profile:
                responses[agent_id] = "[agent not found]"
                continue
            try:
                system = (
                    f"You are {profile.get('name', 'a social media user')}. "
                    f"{profile.get('persona_text', '')} "
                    f"Bio: {profile.get('bio', '')} "
                    "Respond in character. Be concise (2-4 sentences)."
                )
                resp = self._llm.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=150,
                    temperature=0.9,
                )
                responses[agent_id] = resp.choices[0].message.content or ""
            except Exception as exc:
                logger.warning(f"interview_agents LLM call failed for {agent_id}: {exc}")
                responses[agent_id] = f"[error: {exc}]"

        return responses

    # ------------------------------------------------------------------
    # Tool 7 — trajectory_chart
    # ------------------------------------------------------------------

    def trajectory_chart(self) -> dict:
        """sentiment_by_round array + overall summary for chart rendering."""
        data = sentiment_aggregator.get_sentiment(self.sim_id)
        return {
            "sentiment_by_round": data.get("sentiment_by_round", []),
            "overall": data.get("overall", {}),
        }

    # ------------------------------------------------------------------
    # Tool 8 — breakout_agents
    # ------------------------------------------------------------------

    def breakout_agents(self, top_n: int = 5) -> list[dict]:
        """Top-N most influential agents from PredictionEngine."""
        pred = prediction_engine.get_prediction(self.sim_id)
        return pred.get("breakout_agents", [])[:top_n]

    # ------------------------------------------------------------------
    # Dispatch helper used by the ReACT loop
    # ------------------------------------------------------------------

    def call(self, tool_name: str, tool_input: dict) -> object:
        """Dispatch a tool call by name. Raises KeyError for unknown tools."""
        dispatch = {
            "graph_search":       lambda: self.graph_search(**tool_input),
            "sentiment_summary":  lambda: self.sentiment_summary(**tool_input),
            "narrative_clusters": lambda: self.narrative_clusters(**tool_input),
            "persona_breakdown":  lambda: self.persona_breakdown(),
            "viral_spread":       lambda: self.viral_spread(),
            "interview_agents":   lambda: self.interview_agents(**tool_input),
            "trajectory_chart":   lambda: self.trajectory_chart(),
            "breakout_agents":    lambda: self.breakout_agents(**tool_input),
        }
        fn = dispatch.get(tool_name)
        if fn is None:
            raise KeyError(f"Unknown tool: {tool_name}")
        return fn()

    # ------------------------------------------------------------------

    def _load_actions(self) -> list[dict]:
        path = self._sim_dir / "actions.jsonl"
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

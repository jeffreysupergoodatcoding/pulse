"""
ReportAgent — ReACT loop report generator (PRD Section 11.4).

Flow per report:
  1. _plan_report()     → LLM generates ReportOutline (8 section defs)
  2. _generate_section() → ReACT loop (up to MAX_REACT_STEPS per section):
       think → pick tool → observe → repeat → write final_answer
  3. generate()         → orchestrates plan + sections + saves full_report.md

State is persisted to:
  data/simulations/{sim_id}/reports/{report_id}/state.json
  data/simulations/{sim_id}/reports/{report_id}/full_report.md

Reports run in a background thread so /generate returns immediately.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI

from app.config import Config
from app.services.zep_tools_service import ZepToolsService, TOOL_DESCRIPTIONS
from app.services.simulation_manager import simulation_manager
from app.utils.logger import get_logger

logger = get_logger("report_agent")

MAX_REACT_STEPS = 3   # max tool calls per section before forcing final_answer

# 8 default section definitions (PRD Section 11.3)
_DEFAULT_SECTIONS = [
    {
        "id": "executive_summary",
        "title": "Executive Summary",
        "goal": "3-5 sentence overview of predicted sentiment trajectory and key findings.",
    },
    {
        "id": "sentiment_overview",
        "title": "Sentiment Overview",
        "goal": "Overall sentiment score, trajectory (rising/falling/stable), trend vs. baseline.",
    },
    {
        "id": "audience_breakdown",
        "title": "Audience Breakdown",
        "goal": "How each persona archetype reacted differently — sentiment, emotions, quotes.",
    },
    {
        "id": "dominant_narratives",
        "title": "Dominant Narratives",
        "goal": "Top narrative clusters with representative quotes and their sentiment.",
    },
    {
        "id": "key_opinion_leaders",
        "title": "Key Opinion Leaders",
        "goal": "Breakout agents and their influence on overall sentiment.",
    },
    {
        "id": "predicted_spread",
        "title": "Predicted Spread",
        "goal": "Viral reach estimate, time to peak, p90 scenario, platform spread.",
    },
    {
        "id": "risk_opportunity",
        "title": "Risk & Opportunity Signals",
        "goal": "Negative narrative risks and positive amplification opportunities.",
    },
    {
        "id": "recommendations",
        "title": "Recommendations",
        "goal": "3-5 actionable suggestions based on simulation findings.",
    },
]

_PLAN_SYSTEM = """\
You are a market intelligence analyst planning a simulation report.
Given a simulation summary, return a JSON array of 8 section definitions.
Each item: {"id": str, "title": str, "goal": str}
Use exactly these section ids in this order:
executive_summary, sentiment_overview, audience_breakdown, dominant_narratives,
key_opinion_leaders, predicted_spread, risk_opportunity, recommendations
Respond with a JSON array only, no extra text.
"""

_REACT_SYSTEM = """\
You are a market intelligence analyst writing one section of a simulation report.
You have access to these tools:

{tool_list}

For each step respond with JSON in ONE of these two forms:

To call a tool:
{{"thought": "<your reasoning>", "action": "<tool_name>", "action_input": {{...}}}}

When you have enough data to write the section:
{{"thought": "<your reasoning>", "final_answer": "<full markdown section text>"}}

Section to write: {section_title}
Goal: {section_goal}

Accumulated context so far:
{context}
"""


class ReportAgent:
    def __init__(self, config: type[Config] = Config):
        self._config = config
        self._sims_dir = Path(config.SIMULATIONS_DIR)
        self._llm = OpenAI(api_key=config.LLM_API_KEY, base_url=config.LLM_BASE_URL)
        self._model = config.LLM_MODEL_NAME

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_generation(self, sim_id: str) -> str:
        """
        Kick off report generation in a background thread.
        Returns report_id immediately.
        """
        report_id = str(uuid.uuid4())[:8]
        report_dir = self._report_dir(sim_id, report_id)
        report_dir.mkdir(parents=True, exist_ok=True)

        state = {
            "report_id": report_id,
            "sim_id": sim_id,
            "status": "running",
            "sections_done": 0,
            "total_sections": 8,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "error": None,
        }
        self._write_state(sim_id, report_id, state)

        thread = threading.Thread(
            target=self._run,
            args=(sim_id, report_id),
            daemon=True,
            name=f"report-{report_id}",
        )
        thread.start()
        return report_id

    def get_state(self, sim_id: str, report_id: str) -> dict | None:
        path = self._report_dir(sim_id, report_id) / "state.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except Exception:
            return None

    def get_content(self, sim_id: str, report_id: str) -> str | None:
        path = self._report_dir(sim_id, report_id) / "full_report.md"
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def chat_report_agent(
        self,
        sim_id: str,
        report_id: str,
        message: str,
        history: list[dict],
    ) -> str:
        """ReportAgent chat: answers questions about the simulation using tool context."""
        report_md = self.get_content(sim_id, report_id) or "Report not yet generated."
        sim_state = simulation_manager.get_state(sim_id) or {}

        system = (
            "You are a market intelligence analyst who has just completed a simulation report. "
            "Answer questions about the simulation findings concisely and insightfully.\n\n"
            f"Simulation state: {json.dumps(sim_state, default=str)}\n\n"
            f"Report:\n{report_md[:6000]}"
        )

        messages = [{"role": "system", "content": system}]
        for turn in history[-10:]:
            messages.append({"role": turn.get("role", "user"), "content": turn.get("content", "")})
        messages.append({"role": "user", "content": message})

        try:
            resp = self._llm.chat.completions.create(
                model=self._model,
                messages=messages,
                max_tokens=500,
                temperature=0.7,
            )
            return resp.choices[0].message.content or ""
        except Exception as exc:
            logger.error(f"report_agent chat failed: {exc}")
            return f"[error: {exc}]"

    def chat_agent(
        self,
        sim_id: str,
        agent_id: str,
        message: str,
        history: list[dict],
    ) -> str:
        """Direct in-character chat with a specific simulation agent."""
        tools = ZepToolsService(entity_id="", sim_id=sim_id, config=self._config)
        # interview_agents handles the in-character LLM call
        responses = tools.interview_agents([agent_id], message)
        return responses.get(agent_id, "[agent not found]")

    def drilldown(
        self,
        sim_id: str,
        entity_id: str,
        persona_filter: str | None,
        time_range: dict | None,
    ) -> dict:
        """Filtered sentiment + narratives for drilldown view."""
        from app.services.sentiment_aggregator import sentiment_aggregator
        from app.services.prediction_engine import prediction_engine

        sentiment = sentiment_aggregator.get_sentiment(sim_id)
        pred = prediction_engine.get_prediction(sim_id)

        # Apply time_range filter to sentiment_by_round
        by_round = sentiment.get("sentiment_by_round", [])
        if time_range:
            start = time_range.get("start", 0)
            end = time_range.get("end", 99999)
            by_round = [r for r in by_round if start <= r["round"] <= end]

        # Apply persona_filter to by_archetype
        by_arch = sentiment.get("by_archetype", {})
        if persona_filter:
            by_arch = {k: v for k, v in by_arch.items() if persona_filter.lower() in k.lower()}

        return {
            "sentiment": {
                "sentiment_by_round": by_round,
                "by_archetype": by_arch,
                "overall": sentiment.get("overall", {}),
            },
            "narratives": pred.get("narratives", []),
        }

    def generate_signal(self, sim_id: str, entity_id: str) -> dict:
        """Generate a structured MiroSignal prediction JSON."""
        from app.services.prediction_engine import prediction_engine
        from app.services.sentiment_aggregator import sentiment_aggregator

        pred = prediction_engine.get_prediction(sim_id)
        sentiment = sentiment_aggregator.get_sentiment(sim_id)
        overall = sentiment.get("overall", {})
        trajectory = pred.get("trajectory", {})

        signal_prompt = (
            "You are a market intelligence signal generator. "
            "Given simulation data, produce a concise MiroSignal JSON with keys: "
            "signal_type (positive|negative|neutral|mixed), "
            "confidence (0.0-1.0), "
            "summary (1 sentence), "
            "predicted_sentiment_7d (float -1 to 1), "
            "top_risk (string), "
            "top_opportunity (string). "
            "Respond with JSON only.\n\n"
            f"Overall sentiment: {overall}\n"
            f"Trajectory: {trajectory}\n"
            f"Narratives: {pred.get('narratives', [])[:3]}"
        )

        try:
            resp = self._llm.chat.completions.create(
                model=self._model,
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": signal_prompt}],
                temperature=0.3,
            )
            return json.loads(resp.choices[0].message.content)
        except Exception as exc:
            logger.error(f"generate_signal failed: {exc}")
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Internal: background report generation
    # ------------------------------------------------------------------

    def _run(self, sim_id: str, report_id: str):
        try:
            self.generate(sim_id, report_id)
        except Exception as exc:
            logger.error(f"Report {report_id} failed: {exc}")
            state = self.get_state(sim_id, report_id) or {}
            state.update({"status": "error", "error": str(exc)})
            self._write_state(sim_id, report_id, state)

    def generate(self, sim_id: str, report_id: str):
        """Full report generation: plan → 8 sections → save full_report.md."""
        sim_state = simulation_manager.get_state(sim_id) or {}
        entity_id = sim_state.get("entity_id", "")
        tools = ZepToolsService(entity_id=entity_id, sim_id=sim_id, config=self._config)

        # Step 1: Plan
        outline = self._plan_report(entity_id, sim_id, sim_state)
        state = self.get_state(sim_id, report_id) or {}
        state["outline"] = [s["title"] for s in outline]
        self._write_state(sim_id, report_id, state)

        # Step 2: Generate each section
        sections: list[str] = []
        for i, section_def in enumerate(outline):
            logger.info(f"[report:{report_id}] Generating section {i+1}/{len(outline)}: {section_def['title']}")
            try:
                section_md = self._generate_section(section_def, tools)
            except Exception as exc:
                logger.warning(f"Section {section_def['title']} failed: {exc}")
                section_md = f"## {section_def['title']}\n\n*Section generation failed: {exc}*\n"
            sections.append(section_md)

            state["sections_done"] = i + 1
            self._write_state(sim_id, report_id, state)

        # Step 3: Assemble and save
        header = (
            f"# PULSE Simulation Report\n\n"
            f"**Simulation ID:** {sim_id}  \n"
            f"**Entity:** {entity_id}  \n"
            f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}  \n\n"
            "---\n\n"
        )
        full_report = header + "\n\n".join(sections)
        report_dir = self._report_dir(sim_id, report_id)
        (report_dir / "full_report.md").write_text(full_report, encoding="utf-8")

        state.update({
            "status": "completed",
            "sections_done": len(outline),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })
        self._write_state(sim_id, report_id, state)
        logger.info(f"[report:{report_id}] Completed — {len(sections)} sections")

    def _plan_report(self, entity_id: str, sim_id: str, sim_state: dict) -> list[dict]:
        """Ask LLM to confirm/refine the 8 section outline. Falls back to defaults."""
        summary = (
            f"Entity: {entity_id}\n"
            f"Simulation rounds: {sim_state.get('total_rounds', '?')}\n"
            f"Agents: {sim_state.get('n_agents', '?')}\n"
            f"Status: {sim_state.get('status', '?')}\n"
        )
        try:
            resp = self._llm.chat.completions.create(
                model=self._model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _PLAN_SYSTEM},
                    {"role": "user", "content": f"Simulation summary:\n{summary}"},
                ],
                temperature=0,
            )
            raw = json.loads(resp.choices[0].message.content)
            # LLM may return {"sections": [...]} or just [...]
            outline = raw if isinstance(raw, list) else raw.get("sections", raw.get("outline", []))
            if isinstance(outline, list) and len(outline) == 8:
                return outline
        except Exception as exc:
            logger.warning(f"_plan_report LLM failed, using defaults: {exc}")
        return _DEFAULT_SECTIONS

    def _generate_section(self, section_def: dict, tools: ZepToolsService) -> str:
        """
        ReACT loop for a single section.
        Runs up to MAX_REACT_STEPS tool calls then forces final_answer.
        """
        tool_list = "\n".join(f"  - {desc}" for desc in TOOL_DESCRIPTIONS.values())
        context_parts: list[str] = []

        for step in range(MAX_REACT_STEPS + 1):
            # On last step, instruct the LLM to write its final answer
            force_suffix = (
                "\n\nYou have used the maximum number of tool calls. "
                "You MUST now respond with {\"thought\": \"...\", \"final_answer\": \"...\"}."
                if step == MAX_REACT_STEPS
                else ""
            )
            prompt = (
                _REACT_SYSTEM.format(
                    tool_list=tool_list,
                    section_title=section_def.get("title", ""),
                    section_goal=section_def.get("goal", ""),
                    context="\n\n".join(context_parts) if context_parts else "(none yet)",
                )
                + force_suffix
            )

            try:
                resp = self._llm.chat.completions.create(
                    model=self._model,
                    response_format={"type": "json_object"},
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.5,
                    max_tokens=800,
                )
                raw = json.loads(resp.choices[0].message.content)
            except Exception as exc:
                logger.warning(f"ReACT step {step} LLM call failed: {exc}")
                return f"## {section_def.get('title', 'Section')}\n\n*Generation error: {exc}*\n"

            # Final answer — done
            if "final_answer" in raw:
                return raw["final_answer"]

            # Tool call
            action = raw.get("action", "")
            action_input = raw.get("action_input") or {}
            thought = raw.get("thought", "")

            if not action:
                # LLM didn't follow format — treat thought as content
                if thought:
                    context_parts.append(f"Thought: {thought}")
                continue

            try:
                observation = tools.call(action, action_input)
                obs_text = json.dumps(observation, default=str)[:1500]
            except Exception as exc:
                obs_text = f"[tool error: {exc}]"

            context_parts.append(
                f"Thought: {thought}\n"
                f"Action: {action}({json.dumps(action_input)})\n"
                f"Observation: {obs_text}"
            )

        # Fallback: should not reach here, but just in case
        return (
            f"## {section_def.get('title', 'Section')}\n\n"
            + "\n\n".join(context_parts)
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _report_dir(self, sim_id: str, report_id: str) -> Path:
        return self._sims_dir / sim_id / "reports" / report_id

    def _write_state(self, sim_id: str, report_id: str, state: dict):
        path = self._report_dir(sim_id, report_id) / "state.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2, default=str))


report_agent = ReportAgent(Config)

"""
OASIS Parallel Simulation Orchestrator — Phase 5

Entry point for the subprocess spawned by SimulationRunner.

Architecture:
  - Each platform has a shared Channel that agents write actions to
  - platform.running() runs as a background asyncio task processing those actions
  - Agents call perform_action_by_llm() which: refreshes feed via channel,
    lets LLM pick an action (create_post, like, comment, repost, follow, etc.),
    then executes it through the channel back to the platform
  - This enables full agent-to-agent interaction: replies, likes, reposts, follows

Usage:
  python run_parallel_simulation.py \
    --simulation_id <id> \
    --profiles_path  <path/to/profiles.json> \
    --config_path    <path/to/simulation_config.json> \
    --output_dir     <path/to/sim/output/> \
    --entity_id      <entity_id> \
    [--hypothetical_event "<event text>"]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# Ensure backend/ is on path so app.* imports work
_BACKEND_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(_BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv(_BACKEND_DIR / ".env") or load_dotenv(_BACKEND_DIR.parent / ".env")

import oasis
from camel.models import ModelFactory
from camel.types import ModelPlatformType
from camel.messages import BaseMessage
from openai import OpenAI
from oasis.social_platform.channel import Channel
from oasis.social_platform.typing import ActionType
from oasis.social_agent.agent import SocialAgent
from oasis.social_agent.agent_graph import AgentGraph
from oasis.social_platform.platform import Platform
from oasis.social_agent.agent_environment import SocialEnvironment
from oasis.social_agent.agent_action import SocialAction
from simulations.agent_logging import AgentLogger
from simulations.interview_system import InterviewSystem
from app.services.sentiment_scorer import SentimentScorer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_state(path: Path, state: dict):
    path.write_text(json.dumps(state, indent=2, default=str))


def _read_inject_queue(sim_dir: Path) -> list[dict]:
    p = sim_dir / "inject_queue.json"
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text())
        return data if isinstance(data, list) else [data]
    except Exception:
        return []


def _score_pending_actions(actions_path: Path, scorer: SentimentScorer) -> int:
    """
    Read actions.jsonl, score any records where sentiment_score is None,
    and rewrite the file with scores filled in.  Returns count of newly scored actions.
    """
    if not actions_path.exists():
        return 0
    actions = []
    with actions_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    actions.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    updated = 0
    for action in actions:
        if action.get("sentiment_score") is None:
            result = scorer.score(action)
            action["sentiment_score"] = result["sentiment_score"]
            action["emotion"] = result["emotion"]
            action["confidence"] = result["confidence"]
            updated += 1

    if updated > 0:
        with actions_path.open("w", encoding="utf-8") as fh:
            for action in actions:
                fh.write(json.dumps(action) + "\n")

    return updated


def _pop_inject_for_round(inject_queue: list[dict], round_num: int):
    due = [e for e in inject_queue if e.get("round", 0) <= round_num]
    remaining = [e for e in inject_queue if e.get("round", 0) > round_num]
    return due, remaining


# ---------------------------------------------------------------------------
# Profile builders (CSV for twitter, JSON for reddit)
# ---------------------------------------------------------------------------

def _build_twitter_csv(profiles: list[dict], path: Path):
    rows = []
    for p in profiles:
        opinions_str = ", ".join(
            f"{k}: {v:+.1f}" for k, v in (p.get("initial_opinions") or {}).items()
        )
        user_char = (
            f"{p.get('persona_text', '')} "
            f"Initial opinions — {opinions_str}. "
            f"MBTI: {p.get('mbti', 'INFP')}. "
            f"Activity: {p.get('activity_level', 'medium')}."
        )
        rows.append({
            "username": p.get("name", f"user_{str(p.get('user_id','?'))[:6]}"),
            "description": p.get("bio", ""),
            "user_char": user_char[:500],
        })
    pd.DataFrame(rows).to_csv(str(path), index=False)


def _build_reddit_json(profiles: list[dict], path: Path):
    rows = []
    for p in profiles:
        opinions_str = ", ".join(
            f"{k}: {v:+.1f}" for k, v in (p.get("initial_opinions") or {}).items()
        )
        rows.append({
            "username": p.get("name", f"user_{str(p.get('user_id','?'))[:6]}"),
            "bio": p.get("bio", ""),
            "persona": (
                f"{p.get('persona_text', '')} "
                f"Initial opinions — {opinions_str}. "
                f"Activity: {p.get('activity_level', 'medium')}."
            )[:500],
            "mbti": p.get("mbti", "INFP"),
            "gender": "unknown",
            "age": str(p.get("age", 25)),
            "country": "US",
        })
    path.write_text(json.dumps(rows, indent=2))


# ---------------------------------------------------------------------------
# Agent graph builders — pass shared channel so agents talk to platform
# ---------------------------------------------------------------------------

def _build_twitter_agent_graph(profiles: list[dict], model, channel: Channel) -> AgentGraph:
    """Build Twitter agent graph with agents wired to the platform channel."""
    agent_graph = AgentGraph()
    for agent_id, p in enumerate(profiles):
        opinions_str = ", ".join(
            f"{k}: {v:+.1f}" for k, v in (p.get("initial_opinions") or {}).items()
        )
        user_char = (
            f"{p.get('persona_text', '')} "
            f"Initial opinions — {opinions_str}. "
            f"MBTI: {p.get('mbti', 'INFP')}. "
            f"Activity: {p.get('activity_level', 'medium')}."
        )
        from oasis.social_platform.typing import RecsysType
        user_info = oasis.UserInfo(
            name=p.get("name", f"user_{agent_id}"),
            description=p.get("bio", ""),
            profile={
                "nodes": [],
                "edges": [],
                "other_info": {"user_profile": user_char[:500]},
            },
            recsys_type="twitter",
        )
        agent = SocialAgent(
            agent_id=agent_id,
            user_info=user_info,
            channel=channel,
            model=model,
            agent_graph=agent_graph,
        )
        agent_graph.add_agent(agent)
    return agent_graph


def _build_reddit_agent_graph(profiles: list[dict], model, channel: Channel) -> AgentGraph:
    """Build Reddit agent graph with agents wired to the platform channel."""
    agent_graph = AgentGraph()
    for agent_id, p in enumerate(profiles):
        opinions_str = ", ".join(
            f"{k}: {v:+.1f}" for k, v in (p.get("initial_opinions") or {}).items()
        )
        persona = (
            f"{p.get('persona_text', '')} "
            f"Initial opinions — {opinions_str}. "
            f"Activity: {p.get('activity_level', 'medium')}."
        )
        user_info = oasis.UserInfo(
            name=p.get("name", f"user_{agent_id}"),
            description=p.get("bio", ""),
            profile={
                "nodes": [],
                "edges": [],
                "other_info": {
                    "user_profile": persona[:500],
                    "mbti": p.get("mbti", "INFP"),
                    "gender": "unknown",
                    "age": str(p.get("age", 25)),
                    "country": "US",
                },
            },
            recsys_type="reddit",
        )
        agent = SocialAgent(
            agent_id=agent_id,
            user_info=user_info,
            channel=channel,
            model=model,
            agent_graph=agent_graph,
        )
        agent_graph.add_agent(agent)
    return agent_graph


# ---------------------------------------------------------------------------
# Activation schedule
# ---------------------------------------------------------------------------

_ACTIVATION_PROB = {
    "low": 0.25,
    "medium": 0.60,
    "high": 0.90,
}


def _should_activate(profile: dict) -> bool:
    level = profile.get("activity_level", "medium")
    return random.random() < _ACTIVATION_PROB.get(level, 0.60)


# ---------------------------------------------------------------------------
# Agent turn — uses OASIS native perform_action_by_llm()
# ---------------------------------------------------------------------------

async def _agent_turn(
    agent_id: int,
    agent: SocialAgent,
    platform_name: str,
    round_num: int,
    logger: AgentLogger,
):
    """
    Run one agent turn using OASIS's native perform_action_by_llm().

    This method:
      1. Calls env.to_text_prompt() which refreshes the feed via the channel
      2. Sends the feed to the LLM with the agent's persona
      3. LLM picks an action (create_post, like_post, create_comment, repost, follow, etc.)
      4. The chosen action executes through the channel back to the platform
      5. We log the actual chosen action + args
    """
    try:
        response = await agent.perform_action_by_llm()

        # Extract all tool calls from the response
        if response and hasattr(response, 'info') and response.info.get('tool_calls'):
            for tool_call in response.info['tool_calls']:
                action_name = tool_call.tool_name
                args = tool_call.args or {}

                # Extract content and target_id based on action type
                content = (
                    args.get('content')
                    or args.get('quote_content')
                    or args.get('query')
                    or args.get('username')
                    or ""
                )
                target_id = (
                    args.get('post_id')
                    or args.get('followee_id')
                    or args.get('comment_id')
                    or args.get('user_id')
                )
                logger.log(agent_id, platform_name, round_num, action_name, str(content)[:300], target_id)
        else:
            # No tool calls — agent chose do_nothing or returned plain text
            logger.log(agent_id, platform_name, round_num, "do_nothing", "", None)

    except Exception as exc:
        logger.log(agent_id, platform_name, round_num, "error", str(exc)[:200], None)


# ---------------------------------------------------------------------------
# Main simulation
# ---------------------------------------------------------------------------

async def run_simulation(
    simulation_id: str,
    profiles: list[dict],
    config: dict,
    output_dir: Path,
    entity_id: str,
    hypothetical_event: str | None,
    model,
    llm_client: OpenAI,
):
    logger = AgentLogger(output_dir)
    scorer = SentimentScorer()
    actions_path = output_dir / "actions.jsonl"
    interview_sys = InterviewSystem(
        output_dir, profiles, llm_client,
        os.getenv("LLM_MODEL_NAME", "gemini-2.5-flash")
    )

    total_rounds = config.get("rounds", 10)

    state = {
        "simulation_id": simulation_id,
        "status": "running",
        "current_round": 0,
        "total_rounds": total_rounds,
        "twitter_done": False,
        "reddit_done": False,
        "actions_count": 0,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
        "error_message": None,
    }
    _write_state(output_dir / "run_state.json", state)

    # ------------------------------------------------------------------
    # Set up directories
    # ------------------------------------------------------------------
    twitter_dir = output_dir / "twitter"
    reddit_dir = output_dir / "reddit"
    twitter_dir.mkdir(exist_ok=True)
    reddit_dir.mkdir(exist_ok=True)

    twitter_db = str(twitter_dir / "twitter_simulation.db")
    reddit_db = str(reddit_dir / "reddit_simulation.db")

    # ------------------------------------------------------------------
    # Create shared channels — agents and platform MUST share a channel
    # so agent actions are routed through and executed by the platform
    # ------------------------------------------------------------------
    twitter_channel = Channel()
    reddit_channel = Channel()

    # ------------------------------------------------------------------
    # Create platforms with the shared channels
    # ------------------------------------------------------------------
    print("[sim] Creating platforms...", flush=True)
    # Both use "reddit" recsys — score-based ranking, robust to non-post traces.
    # OASIS's "twitter" recsys has a KeyError bug when non-post traces exist.
    twitter_platform = Platform(
        db_path=twitter_db,
        channel=twitter_channel,
        recsys_type="reddit",
        refresh_rec_post_count=5,
        max_rec_post_len=30,
    )
    reddit_platform = Platform(
        db_path=reddit_db,
        channel=reddit_channel,
        recsys_type="reddit",
        refresh_rec_post_count=5,
        max_rec_post_len=30,
    )

    # ------------------------------------------------------------------
    # Build agent graphs with shared channels
    # ------------------------------------------------------------------
    print("[sim] Building agent graphs...", flush=True)
    twitter_graph = _build_twitter_agent_graph(profiles, model, twitter_channel)
    reddit_graph = _build_reddit_agent_graph(profiles, model, reddit_channel)

    # ------------------------------------------------------------------
    # Start platform.running() background tasks BEFORE any channel ops
    # ------------------------------------------------------------------
    print("[sim] Starting platform event loops...", flush=True)
    twitter_runner = asyncio.create_task(twitter_platform.running())
    reddit_runner = asyncio.create_task(reddit_platform.running())

    # ------------------------------------------------------------------
    # Sign up all agents on both platforms (direct call, no channel needed)
    # ------------------------------------------------------------------
    print("[sim] Signing up agents...", flush=True)
    for agent_id, agent in twitter_graph.get_agents():
        ui = agent.user_info
        await twitter_platform.sign_up(
            agent_id,
            (ui.name or f"user_{agent_id}", ui.name or f"user_{agent_id}", ui.description or "")
        )
    for agent_id, agent in reddit_graph.get_agents():
        ui = agent.user_info
        await reddit_platform.sign_up(
            agent_id,
            (ui.name or f"user_{agent_id}", ui.name or f"user_{agent_id}", ui.description or "")
        )

    # ------------------------------------------------------------------
    # Inject seed post (hypothetical event) via channel
    # ------------------------------------------------------------------
    inject_queue = _read_inject_queue(output_dir)

    seed_content = hypothetical_event or (
        f"Breaking: Major news about this topic is trending. "
        f"What are your thoughts? Share your perspective."
    )

    all_t = twitter_graph.get_agents()
    all_r = reddit_graph.get_agents()

    if all_t:
        seed_id, seed_agent = all_t[0]
        await seed_agent.env.action.create_post(seed_content[:280])
        logger.log(seed_id, "twitter", 0, "create_post", seed_content[:280], None)

    if all_r:
        seed_id_r, seed_agent_r = all_r[0]
        await seed_agent_r.env.action.create_post(seed_content[:500])
        logger.log(seed_id_r, "reddit", 0, "create_post", seed_content[:500], None)

    # Populate rec tables so agents can see the seed post in round 1
    try:
        await twitter_platform.update_rec_table()
        await reddit_platform.update_rec_table()
    except Exception as e:
        print(f"[sim] Warning: update_rec_table failed: {e}", flush=True)

    print(f"[sim] Seed posted. Starting {total_rounds} rounds with {len(profiles)} agents...", flush=True)

    # ------------------------------------------------------------------
    # Simulation rounds — agents use perform_action_by_llm() for full
    # native OASIS interaction: like, comment, repost, follow, etc.
    # ------------------------------------------------------------------
    agents_t = twitter_graph.get_agents()
    agents_r = reddit_graph.get_agents()

    for round_num in range(1, total_rounds + 1):
        state["current_round"] = round_num
        _write_state(output_dir / "run_state.json", state)
        print(f"[sim] Round {round_num}/{total_rounds}", flush=True)

        # Mid-round event injections
        due_events, inject_queue = _pop_inject_for_round(inject_queue, round_num)
        for event in due_events:
            content = event.get("event_text", "")
            if content and agents_t:
                first_id, first_agent = agents_t[0]
                await first_agent.env.action.create_post(content[:280])
                logger.log(first_id, "twitter", round_num, "inject", content[:280], None)

        # Build agent tasks — activate based on activity level
        turn_tasks = []
        for agent_id, agent in agents_t:
            profile = profiles[agent_id] if agent_id < len(profiles) else {}
            if _should_activate(profile):
                turn_tasks.append(
                    _agent_turn(agent_id, agent, "twitter", round_num, logger)
                )
        for agent_id, agent in agents_r:
            profile = profiles[agent_id] if agent_id < len(profiles) else {}
            if _should_activate(profile):
                turn_tasks.append(
                    _agent_turn(agent_id, agent, "reddit", round_num, logger)
                )

        # Run all active agents concurrently this round
        if turn_tasks:
            await asyncio.gather(*turn_tasks, return_exceptions=True)

        # Score any newly logged actions (fills sentiment_score, emotion, confidence)
        try:
            _score_pending_actions(actions_path, scorer)
        except Exception as _score_exc:
            print(f"[sim] Warning: sentiment scoring failed round {round_num}: {_score_exc}", flush=True)

        # Update rec tables so agents see this round's posts next round
        try:
            await twitter_platform.update_rec_table()
            await reddit_platform.update_rec_table()
        except Exception as e:
            print(f"[sim] Warning: update_rec_table round {round_num} failed: {e}", flush=True)

        # Check interview commands
        interview_sys.check_and_respond()

        state["actions_count"] = logger.count
        _write_state(output_dir / "run_state.json", state)
        print(f"[sim] Round {round_num} done. Total actions so far: {logger.count}", flush=True)

    # ------------------------------------------------------------------
    # Shutdown platform tasks gracefully
    # ------------------------------------------------------------------
    print("[sim] Shutting down platforms...", flush=True)
    try:
        await twitter_channel.write_to_receive_queue((0, None, ActionType.EXIT.value))
        await reddit_channel.write_to_receive_queue((0, None, ActionType.EXIT.value))
        await asyncio.wait_for(asyncio.gather(twitter_runner, reddit_runner), timeout=5.0)
    except (asyncio.TimeoutError, Exception):
        twitter_runner.cancel()
        reddit_runner.cancel()

    # ------------------------------------------------------------------
    # Finalise
    # ------------------------------------------------------------------
    state.update({
        "status": "completed",
        "twitter_done": True,
        "reddit_done": True,
        "actions_count": logger.count,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    })
    _write_state(output_dir / "run_state.json", state)
    print(f"[sim] Completed. Total actions logged: {logger.count}", flush=True)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--simulation_id", required=True)
    parser.add_argument("--profiles_path", required=True)
    parser.add_argument("--config_path", required=True)
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--entity_id", required=True)
    parser.add_argument("--hypothetical_event", default=None)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    profiles = json.loads(Path(args.profiles_path).read_text())
    config = json.loads(Path(args.config_path).read_text())

    api_key = os.getenv("LLM_API_KEY", "")
    base_url = os.getenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
    model_name = os.getenv("LLM_MODEL_NAME", "gemini-2.5-flash")

    # CamelAI OPENAI_COMPATIBLE_MODEL reads from env vars
    os.environ["OPENAI_API_KEY"] = api_key
    os.environ["OPENAI_BASE_URL"] = base_url

    model = ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
        model_type=model_name,
        api_key=api_key,
        url=base_url,
    )

    llm_client = OpenAI(api_key=api_key, base_url=base_url)

    print(f"[sim] Starting simulation {args.simulation_id}: "
          f"{len(profiles)} agents, {config.get('rounds', 10)} rounds", flush=True)

    asyncio.run(run_simulation(
        simulation_id=args.simulation_id,
        profiles=profiles,
        config=config,
        output_dir=output_dir,
        entity_id=args.entity_id,
        hypothetical_event=args.hypothetical_event,
        model=model,
        llm_client=llm_client,
    ))


if __name__ == "__main__":
    main()

"""
Shared Pydantic data models for Pulse.
All services import from here.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

class PostRecord(BaseModel):
    id: str                          # "platform:platform_id" e.g. "reddit:t3_abc123"
    platform: str                    # "reddit" | "twitter" | "youtube" | "rss"
    entity_id: str                   # which tracked entity this is associated with
    author_id: str                   # anonymized author identifier
    author_metadata: dict            # followers, karma, account_age, flair
    content: str                     # full text of post/tweet/comment
    parent_id: str | None = None     # for replies/comments, parent post id
    created_at: datetime             # UTC
    engagement: dict                 # {likes, shares, replies, views}
    url: str
    raw: dict                        # original platform response


# ---------------------------------------------------------------------------
# Entity configuration
# ---------------------------------------------------------------------------

class SourceConfig(BaseModel):
    reddit: dict = Field(default_factory=lambda: {"subreddits": []})
    twitter: dict = Field(default_factory=lambda: {"queries": []})
    youtube: dict = Field(default_factory=lambda: {"video_ids": [], "channel_ids": []})
    rss: dict = Field(default_factory=lambda: {"feed_urls": []})


class TrackedEntity(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    entity_type: str                  # brand|person|influencer
    description: str = ""
    keywords: list[str] = Field(default_factory=list)
    source_config: SourceConfig = Field(default_factory=SourceConfig)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    graph_id: str | None = None
    active_persona_set_id: str | None = None


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

class OasisAgentProfile(BaseModel):
    user_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    persona_text: str
    bio: str
    age: int
    mbti: str
    political_leaning: str = "moderate"
    initial_opinions: dict[str, float] = Field(default_factory=dict)
    social_relationships: list[str] = Field(default_factory=list)
    activity_level: str = "medium"   # low|medium|high
    influence_tier: str = "regular"  # regular|power_user|lurker
    archetype_id: str | None = None


class SimulationRunState(BaseModel):
    simulation_id: str
    entity_id: str
    persona_set_id: str
    status: str = "idle"             # idle|running|paused|completed|error
    current_round: int = 0
    total_rounds: int = 50
    twitter_done: bool = False
    reddit_done: bool = False
    actions_count: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

class ScoredAction(BaseModel):
    action_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str
    platform: str
    round: int
    action_type: str
    content: str | None = None
    target_entity_id: str
    sentiment_score: float           # -1.0 to 1.0
    emotion: str                     # joy|anger|fear|disgust|surprise|neutral
    confidence: float                # 0.0 to 1.0
    persona_archetype: str
    scored_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

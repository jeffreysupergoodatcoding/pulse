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


# ---------------------------------------------------------------------------
# Layer 2 — Audience discovery (Methods B & C)
#
# Method B: cross-pollination — find adjacent communities discussing related
# problems your brand isn't reaching.
#
# Method C: negative space — communities engaged with competitors but not
# with you, and the positioning gap that explains why.
# ---------------------------------------------------------------------------

class Influencer(BaseModel):
    """An author ranked by engagement-weighted reach within a corpus or cluster."""
    author_id: str                       # anonymized SHA-256 hash
    display_name: str = ""               # e.g. twitter handle or "anonymous"
    platform: str = ""
    posts_in_scope: int                  # how many of their posts matched the scope
    total_engagement: int                # sum of likes + shares + replies + views
    influence_score: float               # normalized [0, 1]
    sample_post: str = ""                # one representative quote (≤240 chars)
    sample_post_url: str = ""


class AdjacentCommunity(BaseModel):
    """Method B — a cluster in a broader category corpus that the target brand isn't reaching."""
    cluster_id: int
    label: str                           # short LLM-generated or top-term label
    description: str = ""                # one-paragraph summary
    n_posts: int
    n_authors: int
    top_terms: list[str] = Field(default_factory=list)
    sample_posts: list[str] = Field(default_factory=list)   # 3-5 representative posts
    influencers: list["Influencer"] = Field(default_factory=list)
    sentiment: dict = Field(default_factory=dict)           # {mean, distribution}
    overlap_with_target: dict = Field(default_factory=dict) # {jaccard_authors, n_shared, brand_post_share}
    distance_from_target: float = 0.0    # higher = more "adjacent but unreached"
    why_adjacent: str = ""               # LLM-rendered explanation
    # Layer 2 / Chunks 2 & 3 enrichment (all optional, populated by services)
    reach_estimate: "ReachEstimate | None" = None
    velocity: "VelocityScore | None" = None
    confidence: "ConfidenceLabel | None" = None
    cannibalization: "CannibalizationFlag | None" = None
    platform_breakdown: list["PlatformBreakdown"] = Field(default_factory=list)
    multi_platform_warning: bool = False


class NegativeSpaceAudience(BaseModel):
    """Method C — authors engaged with a competitor entity who do not appear in the target's corpus."""
    competitor_entity_id: str
    competitor_name: str
    n_authors_competitor_only: int       # |competitor_authors - target_authors|
    n_authors_competitor_total: int
    coverage_gap_pct: float              # competitor_only / competitor_total
    top_authors: list["Influencer"] = Field(default_factory=list)
    top_terms: list[str] = Field(default_factory=list)
    sentiment_toward_competitor: float   # mean compound score over competitor-only authors' posts
    sample_posts: list[str] = Field(default_factory=list)
    # Layer 2 / Chunks 2 & 3 enrichment (all optional, populated by services)
    reach_estimate: "ReachEstimate | None" = None
    velocity: "VelocityScore | None" = None
    confidence: "ConfidenceLabel | None" = None
    cannibalization: "CannibalizationFlag | None" = None
    platform_breakdown: list["PlatformBreakdown"] = Field(default_factory=list)
    multi_platform_warning: bool = False


class PositioningGap(BaseModel):
    """Method C deeper analysis — what positioning explains why competitor-only authors chose them."""
    competitor_entity_id: str
    competitor_name: str
    gap_summary: str                     # LLM-synthesized one-paragraph explanation
    drivers: list[str] = Field(default_factory=list)        # ranked list of distinguishing themes
    evidence_quotes: list[str] = Field(default_factory=list) # direct quotes from competitor-only authors
    audience_size: int                   # how many authors this gap applies to


class AudienceOverlapMatrix(BaseModel):
    """Pairwise author overlap (Jaccard) between target and 1+ competitor entities."""
    target_entity_id: str
    target_n_authors: int
    pairs: list[dict] = Field(default_factory=list)
    # each pair: {entity_id, name, n_authors, intersection, jaccard, target_only, competitor_only}


# ---------------------------------------------------------------------------
# Layer 2 / Chunks 2 + 3 — audience enrichment
#
# Decorators that turn a raw audience finding into a rankable, defensible one.
# All five attach to AdjacentCommunity (Method B) and NegativeSpaceAudience
# (Method C). They are population-level signals, not top-N picks.
# ---------------------------------------------------------------------------

class ReachEstimate(BaseModel):
    """Chunk 2A — directional reachable-audience size, aggregate-only.

    Honest framing: this is NOT a Meta-validated reach number. It's a relative
    indicator for ranking audiences by approximate scale. The real number lives
    in the platform's ad manager.
    """
    estimated_reach: int                                # n_authors * platform_lift_factor
    n_unique_authors: int                               # primary signal
    n_posts: int                                        # activity signal
    total_engagement: int                               # likes + shares + replies + views
    posts_per_author: float                             # density signal
    platform_lift_factor: float = 15.0                  # transparent multiplier
    method: str = "author_count_with_engagement_lift"   # documented, auditable
    caveats: list[str] = Field(default_factory=list)


class VelocityScore(BaseModel):
    """Chunk 2B — population momentum from corpus timestamps + sentiment trend."""
    momentum: str = "stable"                            # rising | stable | declining
    score: float = 0.0                                  # signed [-1, 1]
    components: dict = Field(default_factory=dict)
    # components keys: post_volume_trend, sentiment_trajectory, sentiment_intensity,
    # engagement_per_post_trend, share_of_voice_change (optional)
    window_days: int = 0                                # span of observed corpus
    n_buckets: int = 0                                  # how many time buckets used
    caveats: list[str] = Field(default_factory=list)


class ConfidenceLabel(BaseModel):
    """Chunk 2C — high/medium/low confidence in the audience finding."""
    level: str = "medium"                               # high | medium | low
    score: float = 0.5                                  # 0.0 - 1.0
    reasons: list[str] = Field(default_factory=list)    # human-readable factors
    # e.g. ["small author sample (14)", "engagement density above median"]


class CannibalizationFlag(BaseModel):
    """Chunk 3A — net-new vs already-reaching."""
    label: str = "net_new"                              # net_new | lookalike_likely | overlap_likely
    overlap_pct: float = 0.0                            # |audience ∩ target| / |audience|
    behavioral_similarity: float | None = None          # 0.0 - 1.0; None = LLM not run
    interpretation: str = ""                            # human-readable explanation
    used_llm: bool = False


class PlatformBreakdown(BaseModel):
    """Chunk 3B — one row per platform represented in this audience."""
    platform: str
    n_authors: int
    n_posts: int
    pct_of_audience_authors: float                      # this platform / total audience authors
    pct_of_audience_posts: float


# Existing AdjacentCommunity / NegativeSpaceAudience above are extended in-place
# (see edits to those classes earlier in this file). New optional enrichment
# fields are added there directly so Pydantic resolves cleanly.


# ---------------------------------------------------------------------------
# Layer 2 / Chunk 1 — Actionability outputs (per audience)
#
# Every AdjacentCommunity or NegativeSpaceAudience can be turned into an
# ExecutionBrief: a one-page deliverable a media buyer or CMO can hand to
# their agency. The brief bundles three things:
#
#   1. PlatformTargeting — concrete Meta / Google / TikTok / lookalike recipes
#   2. CreativeDirection — hooks, pain points, language patterns, message angles
#   3. Audience description + influencer list (already in the source object)
#
# All three are LLM-synthesized from the audience's verbatim posts, top terms,
# top influencers, and sentiment.
# ---------------------------------------------------------------------------

class MetaTargeting(BaseModel):
    interest_stack: list[str] = Field(default_factory=list)        # e.g. "Apple Vision Pro", "AR enthusiasts"
    behaviors: list[str] = Field(default_factory=list)             # e.g. "Engaged shoppers", "Tech early adopters"
    exclusions: list[str] = Field(default_factory=list)            # interests to EXCLUDE
    recommended_placements: list[str] = Field(default_factory=list) # ["Reels", "Feed", "Stories"]


class GoogleTargeting(BaseModel):
    keyword_themes: list[dict] = Field(default_factory=list)       # [{theme, keywords[]}]
    search_intent: str = ""                                        # "informational" | "commercial" | "transactional"
    negative_keywords: list[str] = Field(default_factory=list)


class TikTokTargeting(BaseModel):
    creator_clusters: list[str] = Field(default_factory=list)      # named creator-archetypes to partner with
    hashtag_stacks: list[list[str]] = Field(default_factory=list)  # bundles of related hashtags
    sound_trends: list[str] = Field(default_factory=list)          # trending audio / sound categories


class LookalikeStrategy(BaseModel):
    seed_source: str = ""                                          # e.g. "Top-engagement authors from this audience"
    seed_size_target: str = ""                                     # e.g. "1-3% lookalike across US"
    exclusion_strategy: str = ""                                   # who to exclude (existing customers, etc.)


class PlatformTargeting(BaseModel):
    meta: MetaTargeting = Field(default_factory=MetaTargeting)
    google: GoogleTargeting = Field(default_factory=GoogleTargeting)
    tiktok: TikTokTargeting = Field(default_factory=TikTokTargeting)
    lookalike: LookalikeStrategy = Field(default_factory=LookalikeStrategy)


class MessageAngle(BaseModel):
    angle: str                                                     # one-line angle ("permission-to-spend-on-self")
    tonal_direction: str                                           # "problem-aware UGC" | "polished aspirational" | etc.
    format: str = ""                                               # "30s testimonial" | "static carousel" | "podcast read"
    example_copy: str = ""                                         # 1-2 sentence sample copy in audience voice


class CreativeDirection(BaseModel):
    top_hooks: list[str] = Field(default_factory=list)             # 5 short opening hooks
    pain_points: list[str] = Field(default_factory=list)           # 3-5 articulated pain points
    language_patterns: list[str] = Field(default_factory=list)     # 5-8 phrases the audience actually uses
    message_angles: list[MessageAngle] = Field(default_factory=list)  # 3-5


class ExecutionBrief(BaseModel):
    audience_id: str                                               # cluster_id or competitor_entity_id
    audience_label: str
    audience_summary: str = ""                                     # 1-paragraph plain prose: who they are
    audience_size: int = 0                                         # n_authors
    target_entity_id: str = ""
    target_entity_name: str = ""
    influencers: list["Influencer"] = Field(default_factory=list)
    targeting: PlatformTargeting = Field(default_factory=PlatformTargeting)
    creative: CreativeDirection = Field(default_factory=CreativeDirection)
    sample_posts: list[str] = Field(default_factory=list)
    sentiment: float = 0.0                                         # mean compound, [-1, 1]
    source_method: str = ""                                        # "method_b_adjacent" | "method_c_negative_space"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    markdown_export: str = ""                                      # populated by service for direct CMO handoff
    # Layer 2 / Chunks 2 & 3 — passed through from the source audience
    reach_estimate: "ReachEstimate | None" = None
    velocity: "VelocityScore | None" = None
    confidence: "ConfidenceLabel | None" = None
    cannibalization: "CannibalizationFlag | None" = None
    platform_breakdown: list["PlatformBreakdown"] = Field(default_factory=list)
    multi_platform_warning: bool = False

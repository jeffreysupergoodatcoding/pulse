"""
MediaBriefService — Layer 2 / Chunk 1 actionability layer.

Takes any Pulse audience object (AdjacentCommunity from Method B or
NegativeSpaceAudience from Method C) and synthesizes a one-page execution brief:

  - PlatformTargeting (Meta interest stack, Google keyword themes, TikTok creator/
    hashtag clusters, lookalike seed strategy)
  - CreativeDirection (top hooks, pain points, language patterns, 3-5 message
    angles with tonal direction)
  - Audience summary + influencer list (passed through from the source object)
  - Markdown export for direct CMO/agency handoff

Uses one structured-JSON LLM call per brief so the model can cross-reference
across sections (e.g. message angles cite the same language patterns it
surfaced). ~$0.001 per brief on Gemini Flash Lite.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from openai import OpenAI

from app.config import Config
from app.models import (
    CreativeDirection,
    ExecutionBrief,
    GoogleTargeting,
    Influencer,
    LookalikeStrategy,
    MessageAngle,
    MetaTargeting,
    PlatformTargeting,
    TikTokTargeting,
)
from app.services.entity_store import entity_store
from app.utils.logger import get_logger

logger = get_logger("media_brief_service")


_BRIEF_PROMPT = """You are a senior media strategist producing a one-page execution brief for a marketing team. The brief covers a specific audience that an analytics tool ({tool_context}) has surfaced as a growth opportunity for the target brand.

TARGET BRAND: {target_name}
SOURCE METHOD: {source_method}
AUDIENCE LABEL: {audience_label}
AUDIENCE SIZE (unique authors): {audience_size}
MEAN SENTIMENT (vader compound, range -1.0..+1.0): {sentiment}
CONFIDENCE LEVEL: {confidence_level} (reasons: {confidence_reasons})

AUDIENCE TOP TERMS:
{top_terms}

REPRESENTATIVE POSTS (verbatim, in this audience's actual voice):
{sample_posts}

TOP INFLUENCERS IN THIS AUDIENCE:
{influencers}

ADDITIONAL CONTEXT:
{extra_context}

HEDGING REQUIREMENT: If confidence_level above is "low", you MUST hedge in the audience_summary — explicitly use phrases like "preliminary signal", "small sample", "directional only", "limited evidence", "needs validation". Do NOT remove specificity from targeting/creative; just frame the audience_summary honestly so a CMO knows the evidentiary basis is thin. If "medium", soften assertive language slightly. If "high", state findings plainly.

You must return one JSON object with this exact shape. Be specific, not generic. Where the audience's posts give you a real phrase, USE IT verbatim — don't paraphrase. Avoid hollow marketing buzzwords.

{{
  "audience_summary": "<1 paragraph (3-5 sentences) describing who these people are, what underlying motivation/pain they share, what permission-to-spend or identity transition is at play, and what makes them currently unreached>",

  "targeting": {{
    "meta": {{
      "interest_stack": ["<5-10 specific Meta-style interests an Ads Manager could actually pick>"],
      "behaviors": ["<3-6 Meta behavioral targeting categories>"],
      "exclusions": ["<2-4 interests/behaviors to EXCLUDE so you don't bleed into existing customers or wrong audiences>"],
      "recommended_placements": ["<2-4 from: Reels, Feed, Stories, Audience Network, Shop, Search>"]
    }},
    "google": {{
      "keyword_themes": [
        {{ "theme": "<theme name>", "keywords": ["<3-6 specific keywords/phrases>"] }}
        // 3-5 themes total
      ],
      "search_intent": "<one of: informational | commercial | transactional | mixed>",
      "negative_keywords": ["<5-10 keywords to EXCLUDE (existing-customer terms, wrong-intent terms)>"]
    }},
    "tiktok": {{
      "creator_clusters": ["<3-5 named creator archetypes to partner with — e.g. 'Sleep-routine wellness creators 100k-500k followers', 'Skeptical-tech reviewers'>"],
      "hashtag_stacks": [
        ["<#tag1>", "<#tag2>", "<#tag3>"],
        ["<bundle 2>"],
        ["<bundle 3>"]
      ],
      "sound_trends": ["<2-4 sound or audio trend categories appropriate for this audience>"]
    }},
    "lookalike": {{
      "seed_source": "<concrete seed source — e.g. 'Top 50 engaged authors from this audience uploaded as custom Meta audience'>",
      "seed_size_target": "<lookalike size and geo — e.g. '1-3% lookalike, US + UK'>",
      "exclusion_strategy": "<who to exclude from the lookalike — existing customers, current audiences, etc.>"
    }}
  }},

  "creative": {{
    "top_hooks": ["<5 specific 1-line hooks in the audience's actual voice>"],
    "pain_points": ["<3-5 articulated pain points, ideally quoting or paraphrasing real language from the posts>"],
    "language_patterns": ["<5-8 phrases the audience actually uses — pulled from the posts above where possible>"],
    "message_angles": [
      {{
        "angle": "<short angle name>",
        "tonal_direction": "<e.g. 'problem-aware UGC', 'solution-aware aspirational', 'community-insider', 'skeptical-rational'>",
        "format": "<e.g. '30s creator testimonial', 'static carousel', 'podcast read', 'long-form blog'>",
        "example_copy": "<1-2 sentences of sample copy in this angle, written in the audience's voice>"
      }}
      // 3-5 angles total
    ]
  }}
}}

Return ONLY the JSON object. No markdown, no commentary."""


class MediaBriefService:
    def __init__(self, config: type[Config] = Config):
        self.config = config
        try:
            self.client = OpenAI(api_key=config.LLM_API_KEY, base_url=config.LLM_BASE_URL)
        except Exception as exc:
            logger.warning(f"OpenAI client init failed; brief generation disabled: {exc}")
            self.client = None
        self.model = getattr(config, "LLM_MODEL_NAME", "gemini-2.5-flash-lite")

    # ------------------------------------------------------------------
    # Public — brief construction
    # ------------------------------------------------------------------

    def build_brief(
        self,
        audience: dict,
        target_entity_id: str,
        source_method: str = "unknown",
        extra_context: str = "",
    ) -> ExecutionBrief:
        """Produce an ExecutionBrief from any audience dict.

        `audience` must be a dict — typically the model_dump() of an
        AdjacentCommunity (Method B) or NegativeSpaceAudience (Method C).
        Required fields used:
          - either 'cluster_id' + 'label' + 'top_terms' + 'sample_posts'
            + 'influencers' + 'n_authors' + 'sentiment.mean'
          - or 'competitor_entity_id' + 'competitor_name' + 'top_terms'
            + 'sample_posts' + 'top_authors' + 'n_authors_competitor_only'
            + 'sentiment_toward_competitor'
        """
        target = entity_store.get(target_entity_id)
        target_name = target.name if target else target_entity_id

        # Normalize across the two source shapes
        norm = _normalize_audience(audience, source_method)

        if self.client is None:
            logger.warning("LLM client unavailable — returning empty brief")
            brief = ExecutionBrief(
                audience_id=norm["audience_id"],
                audience_label=norm["audience_label"],
                audience_size=norm["audience_size"],
                target_entity_id=target_entity_id,
                target_entity_name=target_name,
                influencers=norm["influencers"],
                sample_posts=norm["sample_posts"],
                sentiment=norm["sentiment"],
                source_method=source_method,
                reach_estimate=norm.get("reach_estimate"),
                velocity=norm.get("velocity"),
                confidence=norm.get("confidence"),
                cannibalization=norm.get("cannibalization"),
                platform_breakdown=norm.get("platform_breakdown") or [],
                multi_platform_warning=norm.get("multi_platform_warning", False),
            )
            brief.markdown_export = render_markdown(brief)
            return brief

        # Compose LLM prompt — pass confidence into the prompt so the LLM hedges when evidence is thin
        conf = norm.get("confidence")
        if isinstance(conf, dict):
            conf_level = conf.get("level", "medium")
            conf_reasons = ", ".join(conf.get("reasons", []) or [])
        elif conf is not None:
            conf_level = getattr(conf, "level", "medium")
            conf_reasons = ", ".join(getattr(conf, "reasons", []) or [])
        else:
            conf_level = "medium"
            conf_reasons = "(no confidence label provided)"

        prompt = _BRIEF_PROMPT.format(
            tool_context=("Method B (adjacent communities)" if source_method == "method_b_adjacent"
                         else "Method C (negative-space audience vs a competitor)" if source_method == "method_c_negative_space"
                         else "Pulse audience-discovery"),
            target_name=target_name,
            source_method=source_method,
            audience_label=norm["audience_label"],
            audience_size=norm["audience_size"],
            sentiment=round(norm["sentiment"], 3),
            confidence_level=conf_level,
            confidence_reasons=conf_reasons,
            top_terms=", ".join(norm["top_terms"][:15]),
            sample_posts="\n".join(f"- {p}" for p in norm["sample_posts"][:10]),
            influencers="\n".join(
                f"- {i.display_name or i.author_id[:10]} ({i.posts_in_scope} posts, {i.total_engagement} engagement): \"{i.sample_post[:140]}\""
                for i in norm["influencers"][:5]
            ) or "(none captured)",
            extra_context=extra_context or "(none)",
        )

        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.2,
            )
            raw = (resp.choices[0].message.content or "{}").strip()
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                parsed = parsed[0] if parsed else {}
        except Exception as exc:
            logger.error(f"LLM brief generation failed: {exc}")
            parsed = {}

        brief = ExecutionBrief(
            audience_id=norm["audience_id"],
            audience_label=norm["audience_label"],
            audience_summary=str(parsed.get("audience_summary", "")),
            audience_size=norm["audience_size"],
            target_entity_id=target_entity_id,
            target_entity_name=target_name,
            influencers=norm["influencers"],
            targeting=_parse_targeting(parsed.get("targeting") or {}),
            creative=_parse_creative(parsed.get("creative") or {}),
            sample_posts=norm["sample_posts"][:10],
            sentiment=norm["sentiment"],
            source_method=source_method,
            reach_estimate=norm.get("reach_estimate"),
            velocity=norm.get("velocity"),
            confidence=norm.get("confidence"),
            cannibalization=norm.get("cannibalization"),
            platform_breakdown=norm.get("platform_breakdown") or [],
            multi_platform_warning=norm.get("multi_platform_warning", False),
        )
        brief.markdown_export = render_markdown(brief)
        return brief


# ---------------------------------------------------------------------------
# Audience normalization (across the two source shapes)
# ---------------------------------------------------------------------------

def _normalize_audience(a: dict, source_method: str) -> dict:
    """Normalize AdjacentCommunity vs NegativeSpaceAudience into a common shape."""
    common_enrichment = {
        "reach_estimate": a.get("reach_estimate"),
        "velocity": a.get("velocity"),
        "confidence": a.get("confidence"),
        "cannibalization": a.get("cannibalization"),
        "platform_breakdown": a.get("platform_breakdown") or [],
        "multi_platform_warning": bool(a.get("multi_platform_warning")),
    }
    if "cluster_id" in a:
        # AdjacentCommunity (Method B)
        return {
            "audience_id": f"cluster:{a.get('cluster_id')}",
            "audience_label": a.get("label", "") or f"Cluster {a.get('cluster_id', '?')}",
            "audience_size": int(a.get("n_authors") or 0),
            "top_terms": list(a.get("top_terms") or []),
            "sample_posts": list(a.get("sample_posts") or []),
            "influencers": [Influencer.model_validate(i) if not isinstance(i, Influencer) else i
                            for i in (a.get("influencers") or [])],
            "sentiment": float((a.get("sentiment") or {}).get("mean", 0.0)),
            **common_enrichment,
        }
    if "competitor_entity_id" in a:
        # NegativeSpaceAudience (Method C)
        return {
            "audience_id": f"competitor:{a.get('competitor_entity_id')}",
            "audience_label": (
                f"{a.get('competitor_name', a.get('competitor_entity_id'))}"
                f" — competitor-only audience"
            ),
            "audience_size": int(a.get("n_authors_competitor_only") or 0),
            "top_terms": list(a.get("top_terms") or []),
            "sample_posts": list(a.get("sample_posts") or []),
            "influencers": [Influencer.model_validate(i) if not isinstance(i, Influencer) else i
                            for i in (a.get("top_authors") or [])],
            "sentiment": float(a.get("sentiment_toward_competitor", 0.0)),
            **common_enrichment,
        }
    # Fallback — caller passed a custom shape
    return {
        "audience_id": str(a.get("id") or "audience"),
        "audience_label": str(a.get("label") or "Custom audience"),
        "audience_size": int(a.get("size") or 0),
        "top_terms": list(a.get("top_terms") or []),
        "sample_posts": list(a.get("sample_posts") or []),
        "influencers": [Influencer.model_validate(i) if not isinstance(i, Influencer) else i
                        for i in (a.get("influencers") or [])],
        "sentiment": float(a.get("sentiment", 0.0)),
    }


# ---------------------------------------------------------------------------
# Parsing LLM output back into typed models
# ---------------------------------------------------------------------------

def _parse_targeting(d: dict) -> PlatformTargeting:
    meta = d.get("meta") or {}
    google = d.get("google") or {}
    tiktok = d.get("tiktok") or {}
    lookalike = d.get("lookalike") or {}
    return PlatformTargeting(
        meta=MetaTargeting(
            interest_stack=list(meta.get("interest_stack") or []),
            behaviors=list(meta.get("behaviors") or []),
            exclusions=list(meta.get("exclusions") or []),
            recommended_placements=list(meta.get("recommended_placements") or []),
        ),
        google=GoogleTargeting(
            keyword_themes=list(google.get("keyword_themes") or []),
            search_intent=str(google.get("search_intent") or ""),
            negative_keywords=list(google.get("negative_keywords") or []),
        ),
        tiktok=TikTokTargeting(
            creator_clusters=list(tiktok.get("creator_clusters") or []),
            hashtag_stacks=[list(s) for s in (tiktok.get("hashtag_stacks") or [])],
            sound_trends=list(tiktok.get("sound_trends") or []),
        ),
        lookalike=LookalikeStrategy(
            seed_source=str(lookalike.get("seed_source") or ""),
            seed_size_target=str(lookalike.get("seed_size_target") or ""),
            exclusion_strategy=str(lookalike.get("exclusion_strategy") or ""),
        ),
    )


def _parse_creative(d: dict) -> CreativeDirection:
    angles_raw = d.get("message_angles") or []
    angles: list[MessageAngle] = []
    for a in angles_raw:
        if not isinstance(a, dict):
            continue
        angles.append(MessageAngle(
            angle=str(a.get("angle") or ""),
            tonal_direction=str(a.get("tonal_direction") or ""),
            format=str(a.get("format") or ""),
            example_copy=str(a.get("example_copy") or ""),
        ))
    return CreativeDirection(
        top_hooks=list(d.get("top_hooks") or []),
        pain_points=list(d.get("pain_points") or []),
        language_patterns=list(d.get("language_patterns") or []),
        message_angles=angles,
    )


# ---------------------------------------------------------------------------
# Markdown rendering — for direct CMO/agency handoff
# ---------------------------------------------------------------------------

def render_markdown(b: ExecutionBrief) -> str:
    """Render an ExecutionBrief as a one-page markdown document."""
    lines: list[str] = []
    lines.append(f"# Audience Brief — {b.audience_label}")
    lines.append("")
    lines.append(f"**Target brand:** {b.target_entity_name or b.target_entity_id}  ")
    lines.append(f"**Source method:** {b.source_method}  ")
    lines.append(f"**Audience size:** {b.audience_size:,} unique authors  ")
    lines.append(f"**Mean sentiment:** {b.sentiment:+.3f}  ")
    if b.confidence:
        lines.append(f"**Confidence:** {b.confidence.level.upper()} ({b.confidence.score:.2f}) — {'; '.join(b.confidence.reasons)}  ")
    if b.reach_estimate:
        lines.append(f"**Estimated reach:** ~{b.reach_estimate.estimated_reach:,} ({b.reach_estimate.n_unique_authors} authors × {b.reach_estimate.platform_lift_factor:.1f}x — directional only)  ")
    if b.velocity:
        comp = b.velocity.components
        lines.append(f"**Momentum:** {b.velocity.momentum.upper()} (score {b.velocity.score:+.2f}, window {b.velocity.window_days}d)  ")
    if b.cannibalization:
        lines.append(f"**Net-new vs target:** {b.cannibalization.label.replace('_', ' ').upper()} — {b.cannibalization.interpretation}  ")
    if b.multi_platform_warning:
        lines.append(f"⚠ **Multi-platform warning:** authors span 2+ platforms; do not sum cross-platform totals (exact-hash matching only)  ")
    if b.platform_breakdown:
        plat_summary = ", ".join(f"{p.platform}: {p.n_authors}a/{p.n_posts}p" for p in b.platform_breakdown)
        lines.append(f"**Platform mix:** {plat_summary}  ")
    lines.append(f"**Generated:** {b.generated_at.strftime('%Y-%m-%d')}")
    lines.append("")

    if b.audience_summary:
        lines.append("## Audience")
        lines.append("")
        lines.append(b.audience_summary)
        lines.append("")

    if b.influencers:
        lines.append("## Top influencers")
        lines.append("")
        for i in b.influencers[:10]:
            handle = i.display_name or i.author_id[:10]
            lines.append(f"- **{handle}** ({i.platform}) — {i.posts_in_scope} posts, {i.total_engagement:,} engagement")
            if i.sample_post:
                lines.append(f"  > \"{i.sample_post[:200]}\"")
        lines.append("")

    # Targeting
    t = b.targeting
    lines.append("## Platform targeting")
    lines.append("")
    lines.append("### Meta")
    if t.meta.interest_stack:
        lines.append(f"- **Interest stack:** {', '.join(t.meta.interest_stack)}")
    if t.meta.behaviors:
        lines.append(f"- **Behaviors:** {', '.join(t.meta.behaviors)}")
    if t.meta.exclusions:
        lines.append(f"- **Exclude:** {', '.join(t.meta.exclusions)}")
    if t.meta.recommended_placements:
        lines.append(f"- **Placements:** {', '.join(t.meta.recommended_placements)}")
    lines.append("")
    lines.append("### Google")
    if t.google.search_intent:
        lines.append(f"- **Search intent:** {t.google.search_intent}")
    for theme in t.google.keyword_themes:
        kws = theme.get("keywords", []) if isinstance(theme, dict) else []
        name = theme.get("theme", "") if isinstance(theme, dict) else str(theme)
        lines.append(f"- **{name}:** {', '.join(kws)}")
    if t.google.negative_keywords:
        lines.append(f"- **Negative keywords:** {', '.join(t.google.negative_keywords)}")
    lines.append("")
    lines.append("### TikTok")
    if t.tiktok.creator_clusters:
        for c in t.tiktok.creator_clusters:
            lines.append(f"- **Creator cluster:** {c}")
    if t.tiktok.hashtag_stacks:
        for stack in t.tiktok.hashtag_stacks:
            lines.append(f"- **Hashtag stack:** {' '.join(stack)}")
    if t.tiktok.sound_trends:
        lines.append(f"- **Sound trends:** {', '.join(t.tiktok.sound_trends)}")
    lines.append("")
    lines.append("### Lookalike")
    if t.lookalike.seed_source:
        lines.append(f"- **Seed source:** {t.lookalike.seed_source}")
    if t.lookalike.seed_size_target:
        lines.append(f"- **Lookalike size / geo:** {t.lookalike.seed_size_target}")
    if t.lookalike.exclusion_strategy:
        lines.append(f"- **Exclusions:** {t.lookalike.exclusion_strategy}")
    lines.append("")

    # Creative
    c = b.creative
    lines.append("## Creative direction")
    lines.append("")
    if c.top_hooks:
        lines.append("### Hooks")
        for h in c.top_hooks:
            lines.append(f"- {h}")
        lines.append("")
    if c.pain_points:
        lines.append("### Pain points")
        for p in c.pain_points:
            lines.append(f"- {p}")
        lines.append("")
    if c.language_patterns:
        lines.append("### Language patterns")
        for lp in c.language_patterns:
            lines.append(f"- *\"{lp}\"*")
        lines.append("")
    if c.message_angles:
        lines.append("### Message angles")
        for i, a in enumerate(c.message_angles, 1):
            lines.append(f"{i}. **{a.angle}** — {a.tonal_direction}" + (f" · {a.format}" if a.format else ""))
            if a.example_copy:
                lines.append(f"   > {a.example_copy}")
        lines.append("")

    if b.sample_posts:
        lines.append("## Verbatim sample posts")
        lines.append("")
        for p in b.sample_posts[:5]:
            lines.append(f"- \"{p}\"")
        lines.append("")

    return "\n".join(lines)


# Module-level singleton
media_brief_service = MediaBriefService(Config)

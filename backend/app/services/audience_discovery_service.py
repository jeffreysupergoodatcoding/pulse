"""
AudienceDiscoveryService — Layer 2 orchestrator.

Top-level entry point for the audience-discovery capability. Combines:

  - audience_overlap_service (Method C set algebra)
  - community_cluster_service (Method B clustering)
  - influencer_extractor (shared)
  - LLM (for the human-readable why-adjacent / why-they-chose-competitor
    explanations — the "positioning gap" analysis)

Two public methods correspond to the two Layer 2 capabilities:

  - discover_adjacent_communities(target_entity_id, category_entity_id, ...)
    → list[AdjacentCommunity], with LLM-generated "why adjacent" narratives.

  - discover_negative_space(target_entity_id, [competitor_entity_ids], ...)
    → (overlap_matrix, list[NegativeSpaceAudience], list[PositioningGap])

All LLM calls use the configured Gemini model via the OpenAI-compatible
endpoint, kept consistent with the rest of Pulse.
"""
from __future__ import annotations

import json
from openai import OpenAI

from app.config import Config
from app.models import AdjacentCommunity, NegativeSpaceAudience, PositioningGap, AudienceOverlapMatrix
from app.services.audience_overlap_service import audience_overlap_service
from app.services.community_cluster_service import community_cluster_service
from app.services.entity_store import entity_store
from app.utils.logger import get_logger

logger = get_logger("audience_discovery_service")


_WHY_ADJACENT_PROMPT = """You are analyzing an online community cluster surfaced by a discourse-analysis tool. Your task is to explain — in 2-3 sentences — why this cluster represents an audience that is "behaviorally adjacent but currently unreached" by the target brand.

Target brand: {target_name}
Cluster top terms: {top_terms}
Sample posts from this cluster:
{samples}

Cluster overlap with target brand's audience:
- Authors in cluster also in brand corpus: {n_shared} of {n_cluster_authors}
- Author overlap (Jaccard): {jaccard}

CONFIDENCE LEVEL FOR THIS CLUSTER: {confidence_level} (reasons: {confidence_reasons})

Write a 2-3 sentence explanation: who are these people, what underlying motivation/pain do they share with the brand's existing buyers, and why isn't the brand reaching them today. Be specific. Avoid generic marketing language. Reference at least one phrase from the sample posts.

HEDGING REQUIREMENT: If the confidence level above is "low", you MUST hedge — use phrases like "preliminary signal", "small sample", "directional only", "needs validation". If "medium", soften assertive language. If "high", state findings plainly.
"""


_POSITIONING_GAP_PROMPT = """You are analyzing why an online audience chose a competitor over the target brand.

Target brand: {target_name}
Competitor: {competitor_name}

The audience below is active in the competitor's online conversation but absent from the target brand's. Their representative posts:

{samples}

Top recurring terms in their posts: {top_terms}
Mean sentiment of these posts toward {competitor_name}: {sentiment} ({sentiment_label})

CONFIDENCE LEVEL FOR THIS AUDIENCE: {confidence_level} (reasons: {confidence_reasons})

Identify the 3 strongest positioning drivers — distinguishing themes that explain why this audience chose {competitor_name} over {target_name}. For each driver, cite a verbatim quote from the samples above as evidence.

HEDGING REQUIREMENT: If the confidence level above is "low", soften the summary with "preliminary signal", "small sample", "directional only", or "needs validation". If "medium", soften assertive language. If "high", state findings plainly.

Return strict JSON in this shape:
{{
  "summary": "<one paragraph, 2-4 sentences, plain prose; hedge if confidence is low>",
  "drivers": ["<driver 1>", "<driver 2>", "<driver 3>"],
  "evidence_quotes": ["<quote 1>", "<quote 2>", "<quote 3>"]
}}

Use the actual text of the posts as evidence. Do not invent quotes. Return only the JSON object, no markdown.
"""


class AudienceDiscoveryService:
    def __init__(self, config: type[Config] = Config):
        self.config = config
        try:
            self.client = OpenAI(api_key=config.LLM_API_KEY, base_url=config.LLM_BASE_URL)
        except Exception as exc:
            logger.warning(f"OpenAI client init failed; LLM-augmented explanations disabled: {exc}")
            self.client = None
        self.model = getattr(config, "LLM_MODEL_NAME", "gemini-2.5-flash-lite")

    # ------------------------------------------------------------------
    # Method B: adjacent communities
    # ------------------------------------------------------------------

    def discover_adjacent_communities(
        self,
        target_entity_id: str,
        category_entity_id: str,
        n_clusters: int = 6,
        explain: bool = True,
    ) -> list[AdjacentCommunity]:
        """Surface clusters from a category corpus that the target brand isn't reaching.

        Methodology:
          1. Cluster the category corpus into communities (k-means on
             embeddings, TF-IDF fallback).
          2. For each cluster, compute overlap with target brand's authors.
          3. Rank by 'distance_from_target' (1.0 = no overlap).
          4. (Optional) LLM-render a 'why_adjacent' explanation per cluster.
        """
        communities = community_cluster_service.discover_adjacent_communities(
            target_entity_id=target_entity_id,
            category_entity_id=category_entity_id,
            n_clusters=n_clusters,
        )

        if not communities:
            return []

        if explain and self.client is not None:
            target_name = (entity_store.get(target_entity_id) or {}).name if entity_store.get(target_entity_id) else "the target brand"
            for c in communities:
                try:
                    c.why_adjacent = self._llm_why_adjacent(target_name, c)
                except Exception as exc:
                    logger.warning(f"why_adjacent LLM call failed for cluster {c.cluster_id}: {exc}")

        return communities

    # ------------------------------------------------------------------
    # Method C: negative space + positioning gaps
    # ------------------------------------------------------------------

    def discover_negative_space(
        self,
        target_entity_id: str,
        competitor_entity_ids: list[str],
        explain: bool = True,
    ) -> dict:
        """Identify audiences engaged with each competitor but absent from target,
        and run an LLM-driven positioning-gap analysis on each."""
        target = entity_store.get(target_entity_id)
        target_name = target.name if target else "the target brand"

        # 1. Pairwise audience overlap (target ↔ each competitor)
        overlap = audience_overlap_service.overlap_matrix(target_entity_id, competitor_entity_ids)

        # 2. Negative-space audience per competitor
        audiences: list[NegativeSpaceAudience] = []
        for cid in competitor_entity_ids:
            try:
                aud = audience_overlap_service.negative_space(target_entity_id, cid)
                audiences.append(aud)
            except Exception as exc:
                logger.error(f"negative_space failed for competitor {cid}: {exc}")

        # 3. Positioning-gap analysis per audience (LLM)
        gaps: list[PositioningGap] = []
        if explain and self.client is not None:
            for aud in audiences:
                try:
                    gap = self._llm_positioning_gap(target_name, aud)
                    if gap:
                        gaps.append(gap)
                except Exception as exc:
                    logger.warning(f"positioning_gap LLM call failed for {aud.competitor_entity_id}: {exc}")

        return {
            "overlap_matrix": overlap.model_dump(mode="json"),
            "negative_space_audiences": [a.model_dump(mode="json") for a in audiences],
            "positioning_gaps": [g.model_dump(mode="json") for g in gaps],
        }

    # ------------------------------------------------------------------
    # LLM rendering helpers
    # ------------------------------------------------------------------

    def _llm_why_adjacent(self, target_name: str, c: AdjacentCommunity) -> str:
        sample_block = "\n".join(f"- {p}" for p in c.sample_posts[:4])
        conf_level = (c.confidence.level if c.confidence else "medium")
        conf_reasons = (", ".join(c.confidence.reasons) if c.confidence else "")
        prompt = _WHY_ADJACENT_PROMPT.format(
            target_name=target_name,
            top_terms=", ".join(c.top_terms[:10]),
            samples=sample_block,
            n_shared=c.overlap_with_target.get("n_shared_authors", 0),
            n_cluster_authors=c.n_authors,
            jaccard=c.overlap_with_target.get("jaccard_authors", 0),
            confidence_level=conf_level,
            confidence_reasons=conf_reasons,
        )
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        return (resp.choices[0].message.content or "").strip()

    def _llm_positioning_gap(self, target_name: str, aud: NegativeSpaceAudience) -> PositioningGap | None:
        if not aud.sample_posts:
            return None
        sample_block = "\n".join(f"- {p}" for p in aud.sample_posts)
        sentiment_label = (
            "positive" if aud.sentiment_toward_competitor > 0.1
            else "negative" if aud.sentiment_toward_competitor < -0.1
            else "neutral"
        )
        conf_level = (aud.confidence.level if aud.confidence else "medium")
        conf_reasons = (", ".join(aud.confidence.reasons) if aud.confidence else "")
        prompt = _POSITIONING_GAP_PROMPT.format(
            target_name=target_name,
            competitor_name=aud.competitor_name,
            samples=sample_block,
            top_terms=", ".join(aud.top_terms[:10]),
            sentiment=aud.sentiment_toward_competitor,
            sentiment_label=sentiment_label,
            confidence_level=conf_level,
            confidence_reasons=conf_reasons,
        )
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        raw = (resp.choices[0].message.content or "{}").strip()
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                parsed = parsed[0] if parsed else {}
        except json.JSONDecodeError:
            logger.warning(f"positioning_gap JSON parse failed for {aud.competitor_entity_id}")
            return None

        return PositioningGap(
            competitor_entity_id=aud.competitor_entity_id,
            competitor_name=aud.competitor_name,
            gap_summary=str(parsed.get("summary", "")),
            drivers=list(parsed.get("drivers", []))[:5],
            evidence_quotes=list(parsed.get("evidence_quotes", []))[:5],
            audience_size=aud.n_authors_competitor_only,
        )


# Module-level singleton
audience_discovery_service = AudienceDiscoveryService(Config)

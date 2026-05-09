"""
AudienceOverlapService — Layer 2 / Method C foundation.

Cross-entity author analysis. Given a target entity and one or more competitor
entities (each already ingested into Pulse), compute:

  - Per-entity author sets (anonymized hash IDs)
  - Pairwise overlap (Jaccard, intersection size, asymmetric set differences)
  - Negative-space audiences (authors active in a competitor entity but absent
    from the target's corpus)
  - Top influencers within each negative-space audience, ranked by
    engagement-weighted reach

This module does NOT call LLMs. It is pure set algebra over the ingestion
JSONL files. The downstream PositioningGap analysis (which IS LLM-driven) lives
in audience_discovery_service.py and consumes the output of this module.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from app.config import Config
from app.models import AudienceOverlapMatrix, Influencer, NegativeSpaceAudience
from app.services.cannibalization_detector import cannibalization_detector
from app.services.confidence_labeler import label_confidence
from app.services.entity_store import entity_store
from app.services.platform_breakdowner import breakdown as platform_breakdown
from app.services.reach_estimator import estimate_reach
from app.services.velocity_scorer import score_velocity
from app.utils.logger import get_logger

logger = get_logger("audience_overlap_service")


class AudienceOverlapService:
    def __init__(self, config: type[Config] = Config):
        self.config = config

    # ------------------------------------------------------------------
    # Corpus iteration
    # ------------------------------------------------------------------

    def _iter_records(self, entity_id: str) -> Iterable[dict]:
        """Yield every PostRecord JSON dict from every posts_*.jsonl for entity."""
        ing = Path(self.config.ENTITIES_DIR) / entity_id / "ingestion"
        if not ing.exists():
            return
        for jsonl in sorted(ing.glob("posts_*.jsonl")):
            for line in jsonl.open(encoding="utf-8"):
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue

    # ------------------------------------------------------------------
    # Author sets
    # ------------------------------------------------------------------

    def author_set(self, entity_id: str) -> set[str]:
        """All unique anonymized author IDs in an entity's corpus."""
        return {r.get("author_id", "") for r in self._iter_records(entity_id) if r.get("author_id")}

    def author_post_counts(self, entity_id: str) -> Counter:
        """Count of posts per author in an entity's corpus."""
        c: Counter = Counter()
        for r in self._iter_records(entity_id):
            aid = r.get("author_id")
            if aid:
                c[aid] += 1
        return c

    # ------------------------------------------------------------------
    # Overlap matrix (Method C — pairwise audience overlap)
    # ------------------------------------------------------------------

    def overlap_matrix(
        self,
        target_entity_id: str,
        competitor_entity_ids: list[str],
    ) -> AudienceOverlapMatrix:
        """Compute pairwise overlap between target and each competitor."""
        target_authors = self.author_set(target_entity_id)
        pairs: list[dict] = []
        for cid in competitor_entity_ids:
            comp_authors = self.author_set(cid)
            inter = target_authors & comp_authors
            ent = entity_store.get(cid)
            union = target_authors | comp_authors
            jaccard = len(inter) / len(union) if union else 0.0
            pairs.append({
                "entity_id": cid,
                "name": ent.name if ent else cid,
                "n_authors": len(comp_authors),
                "intersection": len(inter),
                "jaccard": round(jaccard, 4),
                "target_only": len(target_authors - comp_authors),
                "competitor_only": len(comp_authors - target_authors),
            })
        return AudienceOverlapMatrix(
            target_entity_id=target_entity_id,
            target_n_authors=len(target_authors),
            pairs=pairs,
        )

    # ------------------------------------------------------------------
    # Negative space (Method C core)
    # ------------------------------------------------------------------

    def negative_space(
        self,
        target_entity_id: str,
        competitor_entity_id: str,
        top_n_authors: int = 10,
        top_n_terms: int = 15,
    ) -> NegativeSpaceAudience:
        """Authors active in competitor's corpus but absent from target's.

        Returns a NegativeSpaceAudience with influencer ranking, top terms,
        sample posts, and mean sentiment toward competitor.
        """
        target_authors = self.author_set(target_entity_id)
        comp_records = list(self._iter_records(competitor_entity_id))
        comp_authors = {r["author_id"] for r in comp_records if r.get("author_id")}
        only_authors = comp_authors - target_authors

        # Filter records to only-authors
        only_records = [r for r in comp_records if r.get("author_id") in only_authors]

        # Engagement-weighted ranking
        author_engagement: dict[str, dict] = {}
        for r in only_records:
            aid = r["author_id"]
            eng = r.get("engagement") or {}
            total_eng = (eng.get("likes", 0) or 0) + (eng.get("shares", 0) or 0) + \
                        (eng.get("replies", 0) or 0) + (eng.get("views", 0) or 0)
            d = author_engagement.setdefault(aid, {
                "posts": 0,
                "total_engagement": 0,
                "sample": "",
                "platform": r.get("platform", ""),
                "url": r.get("url", ""),
                "display_name": (r.get("author_metadata") or {}).get("username", ""),
            })
            d["posts"] += 1
            d["total_engagement"] += total_eng
            if not d["sample"] and r.get("content"):
                d["sample"] = r["content"][:240]
                d["url"] = r.get("url", "")

        # Normalize influence scores
        max_eng = max((d["total_engagement"] for d in author_engagement.values()), default=1) or 1
        influencers: list[Influencer] = []
        for aid, d in sorted(author_engagement.items(), key=lambda x: -x[1]["total_engagement"])[:top_n_authors]:
            influencers.append(Influencer(
                author_id=aid,
                display_name=d["display_name"],
                platform=d["platform"],
                posts_in_scope=d["posts"],
                total_engagement=d["total_engagement"],
                influence_score=round(d["total_engagement"] / max_eng, 4),
                sample_post=d["sample"],
                sample_post_url=d["url"],
            ))

        # Top terms (simple word-frequency, lowercased, ≥4 chars, no stopwords)
        top_terms = _top_terms((r.get("content", "") for r in only_records), top_n_terms)

        # Mean sentiment toward competitor (VADER)
        sentiment_mean = _vader_mean(only_records)

        # Sample posts (highest engagement)
        sample_posts = [
            r.get("content", "")[:280]
            for r in sorted(only_records, key=lambda x: -_engagement_total(x))[:5]
            if r.get("content")
        ]

        ent = entity_store.get(competitor_entity_id)

        # Layer 2 / Chunks 2 + 3 enrichment
        target_records = list(self._iter_records(target_entity_id))
        target_top_terms = _top_terms((r.get("content", "") for r in target_records), 15)
        target_sample_posts = [r.get("content", "")[:280] for r in target_records[:5] if r.get("content")]

        reach = estimate_reach(only_records, only_authors)
        velocity = score_velocity(only_records, full_corpus_records=comp_records)
        eng_per_post = (sum(_engagement_total(r) for r in only_records) / len(only_records)) if only_records else 0.0
        confidence = label_confidence(
            n_authors=len(only_authors),
            n_posts=len(only_records),
            engagement_per_post=eng_per_post,
        )
        cannibalization = cannibalization_detector.detect(
            audience_authors=only_authors,
            target_authors=target_authors,
            audience_top_terms=top_terms,
            target_top_terms=target_top_terms,
            audience_sample_posts=sample_posts,
            target_sample_posts=target_sample_posts,
            use_llm=False,    # opt-in; controllable from caller in future
        )
        breakdowns, multi_warn = platform_breakdown(only_records)

        return NegativeSpaceAudience(
            competitor_entity_id=competitor_entity_id,
            competitor_name=ent.name if ent else competitor_entity_id,
            n_authors_competitor_only=len(only_authors),
            n_authors_competitor_total=len(comp_authors),
            coverage_gap_pct=round(len(only_authors) / len(comp_authors), 4) if comp_authors else 0.0,
            top_authors=influencers,
            top_terms=top_terms,
            sentiment_toward_competitor=round(sentiment_mean, 4),
            sample_posts=sample_posts,
            reach_estimate=reach,
            velocity=velocity,
            confidence=confidence,
            cannibalization=cannibalization,
            platform_breakdown=breakdowns,
            multi_platform_warning=multi_warn,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Tiny English stoplist — extend as needed
_STOPWORDS = set("""
the a an and or but if then is are was were be been being have has had do does did
will would could should may might must shall can to of in on at by for with about
from as it its this that these those i you he she we they me him her us them my
your his hers our their just like very really also too so even still back into out
up down off over under again more most much many few any all some each every no not
""".split())


def _top_terms(contents: Iterable[str], top_n: int) -> list[str]:
    counter: Counter = Counter()
    for text in contents:
        for tok in text.lower().split():
            tok = "".join(c for c in tok if c.isalnum())
            if len(tok) < 4 or tok in _STOPWORDS:
                continue
            counter[tok] += 1
    return [t for t, _ in counter.most_common(top_n)]


def _engagement_total(record: dict) -> int:
    eng = record.get("engagement") or {}
    return ((eng.get("likes") or 0) + (eng.get("shares") or 0)
            + (eng.get("replies") or 0) + (eng.get("views") or 0))


def _vader_mean(records: list[dict]) -> float:
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    except ImportError:
        logger.warning("vaderSentiment not installed — returning 0.0 mean sentiment")
        return 0.0
    sia = SentimentIntensityAnalyzer()
    scores: list[float] = []
    for r in records:
        c = r.get("content", "") or ""
        if c:
            scores.append(sia.polarity_scores(c)["compound"])
    return sum(scores) / len(scores) if scores else 0.0


# Module-level singleton
audience_overlap_service = AudienceOverlapService(Config)

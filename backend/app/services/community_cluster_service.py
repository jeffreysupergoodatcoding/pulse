"""
CommunityClusterService — Layer 2 / Method B foundation.

Given a broader-category entity corpus (which the user has manually ingested
with category-wide query terms), cluster it into communities, then compute
each cluster's overlap with the target brand entity's corpus. The output is a
ranked list of AdjacentCommunity objects: clusters with high engagement /
distinct vocabulary that the target brand isn't reaching.

Embedding + k-means is reused conceptually from persona_engine. We use a
simpler local TF-IDF fallback when the embedding API isn't available so the
scaffold runs offline. The default path uses LLM embeddings when configured.
"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from app.config import Config
from app.models import AdjacentCommunity, Influencer
from app.services.audience_overlap_service import audience_overlap_service
from app.services.cannibalization_detector import cannibalization_detector
from app.services.confidence_labeler import label_confidence
from app.services.entity_store import entity_store
from app.services.influencer_extractor import rank_influencers
from app.services.platform_breakdowner import breakdown as platform_breakdown
from app.services.reach_estimator import estimate_reach
from app.services.velocity_scorer import score_velocity
from app.utils.logger import get_logger

logger = get_logger("community_cluster_service")


class CommunityClusterService:
    def __init__(self, config: type[Config] = Config):
        self.config = config

    # ------------------------------------------------------------------
    # Public: discover adjacent communities (Method B)
    # ------------------------------------------------------------------

    def discover_adjacent_communities(
        self,
        target_entity_id: str,
        category_entity_id: str,
        n_clusters: int = 6,
        top_n_terms: int = 12,
        top_n_influencers: int = 5,
    ) -> list[AdjacentCommunity]:
        """Cluster the category corpus and rank clusters by 'adjacent but unreached' score.

        Args:
            target_entity_id: the brand / topic / person whose audience we want to expand
            category_entity_id: a separately-ingested broader corpus (manually supplied
                category query terms). If you want to find adjacencies for a sleep brand,
                ingest a "sleep + wellness + recovery" entity and pass its id here.
            n_clusters: number of communities to surface from the category corpus
            top_n_terms / top_n_influencers: per-cluster output sizes
        """
        target_records = list(audience_overlap_service._iter_records(target_entity_id))
        category_records = list(audience_overlap_service._iter_records(category_entity_id))

        if not category_records:
            logger.warning(f"Category corpus empty for {category_entity_id}")
            return []

        target_authors = {r["author_id"] for r in target_records if r.get("author_id")}

        # Cluster the category corpus
        labels, n_actual = self._cluster(category_records, n_clusters)
        if not labels:
            return []

        communities: list[AdjacentCommunity] = []
        for cluster_id in range(n_actual):
            cluster_records = [r for i, r in enumerate(category_records) if labels[i] == cluster_id]
            if not cluster_records:
                continue

            cluster_authors = {r["author_id"] for r in cluster_records if r.get("author_id")}
            shared = cluster_authors & target_authors
            jaccard = (len(shared) / len(cluster_authors | target_authors)) if (cluster_authors | target_authors) else 0.0

            # Distance score: 1.0 = no overlap (purely adjacent / unreached),
            # 0.0 = total overlap (already in your customer base).
            distance = 1.0 - (len(shared) / len(cluster_authors)) if cluster_authors else 0.0

            top_terms = _top_terms((r.get("content", "") for r in cluster_records), top_n_terms)
            label = top_terms[0].title() if top_terms else f"Cluster {cluster_id}"
            sample_posts = _representative_posts(cluster_records, k=4)
            influencers = rank_influencers(cluster_records, top_n=top_n_influencers)

            sentiment = _vader_distribution(cluster_records)

            # Layer 2 / Chunks 2 + 3 enrichment
            target_top_terms = _top_terms((r.get("content", "") for r in target_records), 15)
            target_sample_posts = [r.get("content", "")[:280] for r in target_records[:5] if r.get("content")]

            reach = estimate_reach(cluster_records, cluster_authors)
            velocity = score_velocity(cluster_records, full_corpus_records=category_records)
            eng_per_post = (
                sum(((r.get("engagement") or {}).get("likes", 0) or 0)
                    + ((r.get("engagement") or {}).get("shares", 0) or 0)
                    + ((r.get("engagement") or {}).get("replies", 0) or 0)
                    + ((r.get("engagement") or {}).get("views", 0) or 0)
                    for r in cluster_records) / len(cluster_records)
            ) if cluster_records else 0.0
            confidence = label_confidence(
                n_authors=len(cluster_authors),
                n_posts=len(cluster_records),
                engagement_per_post=eng_per_post,
                # Coherence proxy: top-term concentration (top-1 frequency / total token frequency in cluster)
                # Skipped for now — TF distribution proxy would need extra computation; defaults to None
            )
            cannibalization = cannibalization_detector.detect(
                audience_authors=cluster_authors,
                target_authors=target_authors,
                audience_top_terms=top_terms,
                target_top_terms=target_top_terms,
                audience_sample_posts=sample_posts,
                target_sample_posts=target_sample_posts,
                use_llm=False,
            )
            breakdowns, multi_warn = platform_breakdown(cluster_records)

            communities.append(AdjacentCommunity(
                cluster_id=cluster_id,
                label=label,
                description="",   # populated by audience_discovery_service via LLM
                n_posts=len(cluster_records),
                n_authors=len(cluster_authors),
                top_terms=top_terms,
                sample_posts=sample_posts,
                influencers=influencers,
                sentiment=sentiment,
                overlap_with_target={
                    "n_shared_authors": len(shared),
                    "jaccard_authors": round(jaccard, 4),
                    "brand_post_share": round(
                        sum(1 for r in cluster_records if r.get("author_id") in target_authors) / len(cluster_records),
                        4,
                    ),
                },
                distance_from_target=round(distance, 4),
                why_adjacent="",   # populated downstream via LLM
                reach_estimate=reach,
                velocity=velocity,
                confidence=confidence,
                cannibalization=cannibalization,
                platform_breakdown=breakdowns,
                multi_platform_warning=multi_warn,
            ))

        # Sort by "adjacent but unreached" — high distance + reasonable n_authors
        communities.sort(key=lambda c: (c.distance_from_target, c.n_authors), reverse=True)
        return communities

    # ------------------------------------------------------------------
    # Clustering — embedding-based with TF-IDF fallback
    # ------------------------------------------------------------------

    def _cluster(self, records: list[dict], n_clusters: int) -> tuple[list[int], int]:
        """Return (labels per record, actual number of clusters)."""
        contents = [r.get("content", "") for r in records]
        if len(contents) < 2:
            return [0] * len(contents), 1

        n_clusters = min(n_clusters, len(contents))

        try:
            embeddings = self._embed(contents)
            if embeddings is None:
                raise RuntimeError("embedding returned None")
            return self._kmeans_fit(embeddings, n_clusters), n_clusters
        except Exception as exc:
            logger.warning(f"Embedding clustering failed ({exc}); falling back to TF-IDF k-means")
            return self._tfidf_kmeans(contents, n_clusters), n_clusters

    def _embed(self, texts: list[str]) -> list[list[float]] | None:
        """Embed texts via the configured LLM embedding endpoint (OpenAI-compatible)."""
        try:
            from openai import OpenAI
        except ImportError:
            return None
        try:
            client = OpenAI(api_key=self.config.LLM_API_KEY, base_url=self.config.LLM_BASE_URL)
            model = getattr(self.config, "LLM_EMBEDDING_MODEL", "gemini-embedding-001")
            # Batch in groups of 100 to respect API limits
            out: list[list[float]] = []
            B = 50
            for i in range(0, len(texts), B):
                resp = client.embeddings.create(model=model, input=texts[i : i + B])
                out.extend(d.embedding for d in resp.data)
            return out
        except Exception as exc:
            logger.warning(f"Embedding API error: {exc}")
            return None

    def _kmeans_fit(self, embeddings: list[list[float]], n_clusters: int) -> list[int]:
        from sklearn.cluster import KMeans
        import numpy as np
        X = np.array(embeddings)
        km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        return km.fit_predict(X).tolist()

    def _tfidf_kmeans(self, contents: list[str], n_clusters: int) -> list[int]:
        """Offline fallback: TF-IDF + k-means on sparse vectors."""
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.cluster import KMeans
        vec = TfidfVectorizer(stop_words="english", max_features=2000, ngram_range=(1, 2))
        X = vec.fit_transform(contents)
        km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        return km.fit_predict(X).tolist()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _representative_posts(records: list[dict], k: int = 4) -> list[str]:
    sorted_records = sorted(records, key=lambda r: -((r.get("engagement") or {}).get("likes") or 0))
    out: list[str] = []
    for r in sorted_records:
        c = (r.get("content") or "").strip()
        if c:
            out.append(c[:280])
        if len(out) >= k:
            break
    return out


def _vader_distribution(records: list[dict]) -> dict:
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    except ImportError:
        return {"mean": 0.0, "pct_positive": 0, "pct_negative": 0, "pct_neutral": 0}
    sia = SentimentIntensityAnalyzer()
    pos = neg = neu = 0
    scores: list[float] = []
    for r in records:
        c = r.get("content", "") or ""
        if not c:
            continue
        s = sia.polarity_scores(c)["compound"]
        scores.append(s)
        if s > 0.05:
            pos += 1
        elif s < -0.05:
            neg += 1
        else:
            neu += 1
    n = len(scores) or 1
    return {
        "mean": round(sum(scores) / n, 4),
        "pct_positive": round(pos / n * 100, 1),
        "pct_negative": round(neg / n * 100, 1),
        "pct_neutral": round(neu / n * 100, 1),
    }


# Module-level singleton
community_cluster_service = CommunityClusterService(Config)

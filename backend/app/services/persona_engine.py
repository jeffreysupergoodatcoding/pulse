"""
Persona Engine — author-level archetype clustering + sanitized agent generation.

Pipeline (v2 — applies the lessons from the Behavioral Clustering vault note):
  1. collect_community_corpus  — reads PostRecords from ingestion JSONLs
  2. _clean_corpus             — drops URL-only / too-short / bot-duplicate / ad spam
  3. _build_author_profiles    — aggregates posts by author with behavioral features
  4. cluster_archetypes        — embeds author voice + standardized features → auto-K
                                 silhouette → k-means → per-cluster signature
                                 (c-TF-IDF distinctive terms, behavioral z-score drivers,
                                 VADER sentiment, top influencers, cohesion, confidence)
  5. generate_profiles         — sanitized LLM prompt: translator-not-narrator. Forbids
                                 motivational claims; every behavioral assertion must
                                 be tied to an observed signal.

Backward compat:
  - OasisAgentProfile shape unchanged
  - archetypes.json keeps every legacy key (id, description, pct_positive, pct_negative,
    pct_neutral, avg_engagement, top_terms, representative_posts, size) and ADDS new
    keys (archetype_name, summary, distinctive_terms, behavioral_drivers, cohesion,
    confidence, top_influencers)
  - profiles.json shape unchanged
  - clustering_diagnostics.json is NEW (silhouette, K, drop counts, per-cluster cohesion)
"""
from __future__ import annotations

import json
import math
import re
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

import numpy as np
from openai import OpenAI
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import silhouette_score
from sklearn.metrics.pairwise import cosine_similarity
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from app.config import Config
from app.models import OasisAgentProfile
from app.services.graph_builder_service import graph_builder_service
from app.utils.logger import get_logger

logger = get_logger("persona_engine")


# ---------------------------------------------------------------------------
# Sanitized prompts — LLM is a translator, not a narrator.
# ---------------------------------------------------------------------------

_ARCHETYPE_NAMING_PROMPT = """You are labeling an audience archetype derived from real
social-media posts. You will be given a SIGNATURE describing the cluster's observed
behavior. Your job is to translate this signature into a short label and a one-paragraph
summary. Do NOT invent motivations the signature does not contain.

STRICT RULES:
- The label MUST be 3-6 words and BEHAVIORAL ("Engagement-heavy Apple defenders",
  "Skeptical AR pragmatists"), NOT motivational ("Visionaries").
- The summary may only assert behaviors visible in the signature: distinctive vocabulary,
  observed sentiment, engagement level, posting cadence, dominant platform.
- Forbidden phrases: "they likely feel", "they treat the brand as", "deep down",
  "reaction triggers", "their motivation is", "they crave", "they are passionate",
  "they believe deeply".
- Allowed: "frequently use the word X", "post predominantly in the Y hour band",
  "engagement per post is in the Nth percentile", "VADER sentiment is mean Z".
- Quote the signature, do not embellish.

SIGNATURE:
Cluster: {cluster_id} ({n_authors} authors, {n_posts} posts)
Distinctive vocabulary (vs other clusters): {distinctive_terms}
Sentiment distribution: {pct_positive}% positive, {pct_negative}% negative,
  {pct_neutral}% neutral (mean VADER compound = {mean_sentiment:+.3f})
Behavioral drivers (z-score above population mean, top 5): {behavioral_drivers}
Dominant platform: {dominant_platform}
Top distinguishing posts (verbatim, do not paraphrase):
{representative_posts}

Return a JSON object with two keys: "archetype_name" (string) and "summary" (string,
2-4 sentences, behavioral only)."""


_PERSONA_PROMPT = """You are generating social-media user profiles for a sentiment
simulation. The archetype you are populating was derived from real public posts. Each
generated user must read like one of the real authors below — same vocabulary range,
same engagement style, same sentiment direction.

STRICT RULES:
- Every persona_text must be GROUNDED. Anchor each one in the verbatim sample posts
  below: cite vocabulary they actually use, the sentiment they actually express, the
  engagement style they actually demonstrate.
- Forbidden phrases in persona_text: "they likely feel", "they treat the brand as",
  "deep down", "reaction triggers", "their motivation is", "they crave", "they are
  passionate", "they believe deeply", "their core belief".
- Allowed: "uses phrases like X", "posts at engagement level Y", "expresses sentiment Z",
  "frequently mentions A in relation to B".
- Initial opinion on {entity_name} must reflect the archetype's mean sentiment:
  positive cluster → score in [+0.4, +0.9]; negative → [-0.9, -0.4]; mixed → [-0.3, +0.3].

ARCHETYPE: {archetype_name}
Summary: {archetype_summary}
Cluster sentiment: {pct_positive}% pos / {pct_negative}% neg / {pct_neutral}% neu
  (mean compound = {mean_sentiment:+.3f})
Distinctive vocabulary: {distinctive_terms}
Behavioral drivers: {behavioral_drivers}
Average engagement per author: {avg_engagement_per_author}

KNOWLEDGE GRAPH CONTEXT (for opinion grounding only):
Entities: {graph_entities}
Relationships: {graph_relationships}
Sentiment toward {entity_name} on graph: {graph_sentiment}

REAL VERBATIM POSTS (anchors — do not paraphrase, vary the voice within the band):
{sample_posts}

Generate {n} distinct user profiles as a JSON array. Each profile must have:
  - name: realistic username for this community style
  - age: integer (realistic for this archetype, no defaulting to 25-30)
  - bio: 1-2 sentence behavioral description (not motivational)
  - persona_text: 3-5 sentence behavioral description tied to the signature signals
    above. Mention specific vocabulary they use, their sentiment direction, their
    engagement style. NO motivational claims.
  - initial_opinions: object with "{entity_name}": float (-1.0 to 1.0, must respect
    cluster sentiment band above), plus 2-3 related entities/topics from the graph
  - mbti: inferred MBTI string e.g. "INTJ" (vary across the {n} agents)
  - activity_level: "low" | "medium" | "high" — match the cluster's posting cadence
  - influence_tier: "regular" | "power_user" | "lurker" — match the cluster's
    engagement tier
  - social_connections: empty array

Return only a valid JSON array, no markdown, no explanation."""


# Forbidden motivational phrases — used to retroactively flag low-quality output
_FORBIDDEN_PHRASES = [
    "they likely feel",
    "treat the brand as",
    "treats the brand as",
    "deep down",
    "reaction triggers",
    "their motivation is",
    "they crave",
    "they are passionate",
    "they believe deeply",
    "their core belief",
]


# ---------------------------------------------------------------------------
# Sentiment helper (shared VADER instance — heavy to construct repeatedly)
# ---------------------------------------------------------------------------

_VADER = SentimentIntensityAnalyzer()


def _vader_compound(text: str) -> float:
    if not text:
        return 0.0
    return _VADER.polarity_scores(text)["compound"]


# ---------------------------------------------------------------------------
# Pre-clean + author aggregation
# ---------------------------------------------------------------------------

# Patterns that catch ad / job / promo posts
_SPAM_PATTERNS = [
    re.compile(r"\$\d{2,3},?\d{3}", re.I),                   # salary numbers
    re.compile(r"\b(now hiring|apply (today|now)|job opportunity|positions? available)\b", re.I),
    re.compile(r"\b(buy now|click here|shop now|coupon code|promo code)\b", re.I),
    re.compile(r"\b(crypto|nft|airdrop|presale)\b", re.I),
]
_URL_RE = re.compile(r"https?://\S+")


def _is_spam(content: str) -> bool:
    if not content:
        return True
    stripped = _URL_RE.sub("", content).strip()
    if len(stripped) < 20:                                  # mostly URL or empty
        return True
    if len(content) > 0 and len(stripped) / len(content) < 0.3:
        return True                                         # >70% URLs
    for pat in _SPAM_PATTERNS:
        if pat.search(content):
            return True
    return False


def _clean_corpus(records: list[dict]) -> tuple[list[dict], dict]:
    """Filter junk records. Returns (kept, drop_stats)."""
    drop_stats = {"too_short_or_url": 0, "spam_pattern": 0, "bot_duplicate": 0, "kept": 0}
    kept: list[dict] = []

    # First pass: spam / too-short
    interim: list[dict] = []
    for r in records:
        c = (r.get("content") or "").strip()
        if not c:
            drop_stats["too_short_or_url"] += 1
            continue
        if _is_spam(c):
            drop_stats["spam_pattern"] += 1
            continue
        interim.append(r)

    # Second pass: per-author deduplication of near-identical posts (bots / cross-posts)
    by_author: dict[str, list[dict]] = defaultdict(list)
    for r in interim:
        by_author[r.get("author_id") or "anonymous"].append(r)

    for author, recs in by_author.items():
        seen_norm: set[str] = set()
        for r in recs:
            norm = re.sub(r"\s+", " ", (r.get("content") or "").strip().lower())[:200]
            if norm in seen_norm:
                drop_stats["bot_duplicate"] += 1
                continue
            seen_norm.add(norm)
            kept.append(r)

    drop_stats["kept"] = len(kept)
    return kept, drop_stats


def _engagement(record: dict) -> int:
    eng = record.get("engagement") or {}
    return int(
        (eng.get("likes") or 0)
        + (eng.get("shares") or 0)
        + (eng.get("replies") or 0)
        + (eng.get("views") or 0) * 0.01           # views are noisy, downweight
    )


def _build_author_profiles(records: list[dict]) -> list[dict]:
    """Aggregate cleaned records by author. Each author = one row for clustering."""
    by_author: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_author[r.get("author_id") or "anonymous"].append(r)

    profiles: list[dict] = []
    # Compute corpus span for posts_per_day
    timestamps: list[datetime] = []
    for r in records:
        ts = r.get("created_at")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            timestamps.append(dt)
        except Exception:
            pass
    span_days = max(
        1.0,
        (max(timestamps) - min(timestamps)).total_seconds() / 86400.0
        if timestamps else 1.0,
    )

    for author_id, recs in by_author.items():
        contents = [(r.get("content") or "") for r in recs]
        concat = " || ".join(c[:600] for c in contents)[:4000]
        engs = [_engagement(r) for r in recs]
        sentiments = [_vader_compound(c) for c in contents]
        platforms = [r.get("platform", "unknown") for r in recs]
        dominant_platform = Counter(platforms).most_common(1)[0][0] if platforms else "unknown"
        is_multi_platform = len(set(platforms)) > 1

        # Posting hour distribution (UTC)
        hours: list[int] = []
        for r in recs:
            ts = r.get("created_at")
            if not ts:
                continue
            try:
                dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                hours.append(dt.hour)
            except Exception:
                pass
        if hours:
            mode_hour = Counter(hours).most_common(1)[0][0]
            if 5 <= mode_hour < 12:
                hour_band = "morning"
            elif 12 <= mode_hour < 17:
                hour_band = "afternoon"
            elif 17 <= mode_hour < 22:
                hour_band = "evening"
            else:
                hour_band = "night"
        else:
            hour_band = "unknown"

        pct_pos = sum(1 for s in sentiments if s > 0.05) / max(len(sentiments), 1)
        pct_neg = sum(1 for s in sentiments if s < -0.05) / max(len(sentiments), 1)

        profiles.append({
            "author_id": author_id,
            "n_posts": len(recs),
            "concat_text": concat,
            "avg_post_length": float(mean(len(c) for c in contents)) if contents else 0.0,
            "total_engagement": int(sum(engs)),
            "engagement_per_post": float(mean(engs)) if engs else 0.0,
            "posts_per_day": len(recs) / span_days,
            "mean_sentiment": float(mean(sentiments)) if sentiments else 0.0,
            "pct_positive": float(pct_pos),
            "pct_negative": float(pct_neg),
            "dominant_platform": dominant_platform,
            "is_multi_platform": bool(is_multi_platform),
            "hour_band": hour_band,
            "_records": recs,
        })

    return profiles


# ---------------------------------------------------------------------------
# c-TF-IDF — distinctive terms per cluster vs the rest
# ---------------------------------------------------------------------------

def _distinctive_terms_per_cluster(
    cluster_texts: list[list[str]],
    n_top: int = 15,
) -> list[list[str]]:
    """For each cluster, return the top-N terms that are over-represented relative to the
    full corpus (c-TF-IDF / log-odds-ish). Stop-words removed."""
    if not cluster_texts or all(not c for c in cluster_texts):
        return [[] for _ in cluster_texts]

    # Treat each cluster as a single document (concatenated)
    cluster_docs = [" ".join(t for t in cluster) for cluster in cluster_texts]
    if not any(d.strip() for d in cluster_docs):
        return [[] for _ in cluster_texts]

    try:
        vec = TfidfVectorizer(
            stop_words="english",
            ngram_range=(1, 2),
            min_df=1,
            max_features=2000,
            sublinear_tf=True,
        )
        matrix = vec.fit_transform(cluster_docs)
        terms = vec.get_feature_names_out()
        out: list[list[str]] = []
        for i in range(matrix.shape[0]):
            row = matrix[i].toarray().flatten()
            top_idx = row.argsort()[::-1][:n_top]
            # Skip cluster-bound junk: pure numeric tokens
            picked = [
                terms[j] for j in top_idx
                if row[j] > 0 and not terms[j].replace(" ", "").isdigit()
            ]
            out.append(picked[:n_top])
        return out
    except Exception as exc:
        logger.warning(f"c-TF-IDF failed: {exc}")
        return [[] for _ in cluster_texts]


# ---------------------------------------------------------------------------
# Behavioral driver z-scores per cluster vs population
# ---------------------------------------------------------------------------

_NUMERIC_DRIVER_KEYS = (
    "n_posts",
    "avg_post_length",
    "engagement_per_post",
    "total_engagement",
    "posts_per_day",
    "mean_sentiment",
    "pct_positive",
    "pct_negative",
)


def _behavioral_drivers(
    cluster_profiles: list[dict],
    population_profiles: list[dict],
    top_n: int = 5,
) -> list[dict]:
    """Top-N driver z-scores: (cluster_mean - pop_mean) / pop_std. Drops zero-std features."""
    drivers: list[tuple[str, float, float]] = []   # (key, z, cluster_mean)
    for key in _NUMERIC_DRIVER_KEYS:
        pop_vals = [p.get(key, 0.0) for p in population_profiles]
        if not pop_vals:
            continue
        pop_mean = mean(pop_vals)
        pop_std = pstdev(pop_vals) or 1e-9
        cluster_mean = mean(p.get(key, 0.0) for p in cluster_profiles) if cluster_profiles else 0.0
        z = (cluster_mean - pop_mean) / pop_std
        drivers.append((key, z, cluster_mean))

    drivers.sort(key=lambda x: abs(x[1]), reverse=True)
    return [
        {
            "feature": k,
            "z": round(z, 3),
            "cluster_mean": round(cm, 3),
            "direction": "above" if z > 0 else "below",
        }
        for k, z, cm in drivers[:top_n]
    ]


# ---------------------------------------------------------------------------
# Confidence labelling
# ---------------------------------------------------------------------------

def _confidence(n_authors: int, cohesion: float) -> dict:
    if n_authors >= 10 and cohesion >= 0.4:
        level = "high"
    elif n_authors >= 4 and cohesion >= 0.2:
        level = "medium"
    else:
        level = "low"
    reasons = [f"{n_authors} authors", f"cohesion {cohesion:.2f}"]
    if cohesion < 0.2:
        reasons.append("loose cluster — consider re-running with different K")
    return {"level": level, "reasons": reasons, "score": round(cohesion, 3)}


# ---------------------------------------------------------------------------
# Auto-K via silhouette
# ---------------------------------------------------------------------------

def _auto_k(X: np.ndarray, k_min: int, k_max: int) -> tuple[int, float, dict]:
    """Pick K with the highest silhouette over [k_min, k_max]. Returns (k, score, scores)."""
    n = X.shape[0]
    if n <= k_min:
        return max(2, n - 1) if n > 2 else 1, 0.0, {}
    k_max = min(k_max, n - 1)
    best_k = k_min
    best_score = -1.0
    scores: dict[int, float] = {}
    for k in range(k_min, k_max + 1):
        try:
            km = KMeans(n_clusters=k, random_state=42, n_init=10)
            labels = km.fit_predict(X)
            if len(set(labels)) < 2:
                continue
            s = float(silhouette_score(X, labels, metric="cosine"))
            scores[k] = s
            if s > best_score:
                best_score = s
                best_k = k
        except Exception:
            continue
    return best_k, best_score, scores


# ---------------------------------------------------------------------------
# Persona Engine
# ---------------------------------------------------------------------------

class PersonaEngine:
    def __init__(self, config: type[Config] = Config):
        self.config = config
        self.llm = OpenAI(api_key=config.LLM_API_KEY, base_url=config.LLM_BASE_URL)
        self.model = config.LLM_MODEL_NAME
        self.embed_model = config.LLM_EMBEDDING_MODEL

    # ------------------------------------------------------------------
    # Stage 1 — corpus collection
    # ------------------------------------------------------------------

    def collect_community_corpus(self, entity_id: str, n: int = 1000) -> list[dict]:
        ingestion_dir = Path(self.config.ENTITIES_DIR) / entity_id / "ingestion"
        if not ingestion_dir.exists():
            return []
        records: list[dict] = []
        for jsonl_file in sorted(ingestion_dir.glob("posts_*.jsonl"), reverse=True):
            with jsonl_file.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                        if (r.get("content") or "").strip():
                            records.append(r)
                    except json.JSONDecodeError:
                        pass
                    if len(records) >= n:
                        break
            if len(records) >= n:
                break
        logger.info(f"Collected {len(records)} corpus posts for entity {entity_id}")
        return records[:n]

    # ------------------------------------------------------------------
    # Knowledge graph context (unchanged)
    # ------------------------------------------------------------------

    def _load_graph_context(self, entity_id: str) -> dict:
        try:
            graph_data = graph_builder_service.get_local_graph_data(entity_id)
            ontology = graph_builder_service.get_ontology(entity_id)
            sentiment = graph_builder_service.get_sentiment(entity_id)
        except Exception as exc:
            logger.warning(f"Graph context unavailable: {exc}")
            return {"entities": "none", "relationships": "none",
                    "topics": "none", "sentiment": "unknown"}

        nodes = graph_data.get("nodes", [])
        edges = graph_data.get("edges", [])
        entity_strs = [
            f"{n.get('label', n.get('id'))} ({n.get('type', 'Unknown')})"
            for n in nodes[:40]
        ]
        rel_strs = [
            f"{e.get('source')} -[{e.get('relation', 'RELATED_TO')}]-> {e.get('target')}"
            for e in edges[:40]
        ]
        topics = ontology.get("entity_types", []) + ontology.get("relation_types", [])
        score = sentiment.get("current_score", 0.0)
        sentiment_label = (
            "positive" if score > 0.1 else
            "negative" if score < -0.1 else "neutral"
        )
        return {
            "entities": ", ".join(entity_strs) if entity_strs else "none extracted yet",
            "relationships": "; ".join(rel_strs) if rel_strs else "none extracted yet",
            "topics": ", ".join(topics) if topics else "none extracted yet",
            "sentiment": f"{sentiment_label} ({score:+.2f})",
        }

    # ------------------------------------------------------------------
    # Stage 2 — author-level archetype clustering
    # ------------------------------------------------------------------

    def cluster_archetypes(
        self,
        corpus: list[dict],
        n_clusters: int = 8,
    ) -> tuple[list[dict], dict]:
        """Cluster AUTHORS (not posts). Returns (archetypes, diagnostics)."""
        if not corpus:
            return [], {"reason": "empty_corpus"}

        cleaned, drop_stats = _clean_corpus(corpus)
        if len(cleaned) < 4:
            logger.warning(f"Only {len(cleaned)} clean posts — skipping clustering")
            return [], {"drop_stats": drop_stats, "reason": "too_few_clean_posts"}

        author_profiles = _build_author_profiles(cleaned)
        n_authors = len(author_profiles)
        logger.info(f"Aggregated {n_authors} authors from {len(cleaned)} clean posts")

        if n_authors < 4:
            logger.warning(f"Only {n_authors} authors — clustering not meaningful")
            return [], {
                "drop_stats": drop_stats,
                "n_authors": n_authors,
                "reason": "too_few_authors",
            }

        # Embed author concat_text
        concat_texts = [p["concat_text"] for p in author_profiles]
        logger.info(f"Embedding {n_authors} author corpora with {self.embed_model}")
        embeddings = self._embed_batch(concat_texts)
        if not embeddings:
            logger.error("Embedding failed; falling back to TF-IDF")
            try:
                from sklearn.feature_extraction.text import TfidfVectorizer as TV
                X_text = TV(stop_words="english", max_features=2000,
                            ngram_range=(1, 2)).fit_transform(concat_texts).toarray()
            except Exception as exc:
                logger.error(f"TF-IDF fallback failed: {exc}")
                return [], {"drop_stats": drop_stats, "reason": "embedding_failed"}
        else:
            X_text = np.array(embeddings)

        # L2-normalize embeddings for cosine k-means
        norms = np.linalg.norm(X_text, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        X_text = X_text / norms

        # Append standardized behavioral features (down-weighted to avoid swamping text)
        beh = np.array([
            [
                p["n_posts"],
                p["engagement_per_post"],
                p["mean_sentiment"],
                p["posts_per_day"],
            ]
            for p in author_profiles
        ], dtype=float)
        beh_mean = beh.mean(axis=0)
        beh_std = beh.std(axis=0)
        beh_std[beh_std == 0] = 1.0
        beh_z = (beh - beh_mean) / beh_std
        BEHAVIORAL_WEIGHT = 0.15  # text dominates; behavior nudges
        beh_z = beh_z * BEHAVIORAL_WEIGHT
        X = np.concatenate([X_text, beh_z], axis=1)

        # Auto-K
        k_max = min(n_clusters, max(2, n_authors // 3))
        k_min = min(3, k_max)
        chosen_k, sil_score, sil_scores = _auto_k(X, k_min=k_min, k_max=k_max)
        logger.info(
            f"Auto-K selected K={chosen_k} (silhouette={sil_score:.3f}, "
            f"explored={list(sil_scores.keys())})"
        )

        if chosen_k < 2:
            return [], {
                "drop_stats": drop_stats,
                "n_authors": n_authors,
                "reason": "auto_k_failed",
            }

        kmeans = KMeans(n_clusters=chosen_k, random_state=42, n_init=10)
        labels = kmeans.fit_predict(X)

        # Assemble per-cluster contents for c-TF-IDF
        cluster_contents: list[list[str]] = [[] for _ in range(chosen_k)]
        cluster_profiles_idx: list[list[int]] = [[] for _ in range(chosen_k)]
        for i, lbl in enumerate(labels):
            cluster_profiles_idx[int(lbl)].append(i)
            for r in author_profiles[i]["_records"]:
                if (r.get("content") or "").strip():
                    cluster_contents[int(lbl)].append(r["content"])

        distinctive_per_cluster = _distinctive_terms_per_cluster(cluster_contents, n_top=15)

        archetypes: list[dict] = []
        for cluster_id in range(chosen_k):
            idxs = cluster_profiles_idx[cluster_id]
            if not idxs:
                continue
            members = [author_profiles[i] for i in idxs]
            member_records = [r for p in members for r in p["_records"]]
            member_texts = [r.get("content", "") for r in member_records]

            # Cohesion: mean cosine sim to centroid (within text-embedding space only)
            centroid = X_text[idxs].mean(axis=0)
            cn = np.linalg.norm(centroid) or 1.0
            centroid /= cn
            sims = X_text[idxs] @ centroid
            cohesion = float(sims.mean()) if len(sims) else 0.0

            # Sentiment distribution (author-aggregated VADER)
            sent_scores = [p["mean_sentiment"] for p in members]
            mean_sentiment = float(mean(sent_scores)) if sent_scores else 0.0
            pct_pos = round(100 * sum(1 for p in members if p["pct_positive"] > p["pct_negative"]) / len(members))
            pct_neg = round(100 * sum(1 for p in members if p["pct_negative"] > p["pct_positive"]) / len(members))
            pct_neu = max(0, 100 - pct_pos - pct_neg)

            # Engagement
            engs = [p["engagement_per_post"] for p in members]
            avg_engagement = round(mean(engs)) if engs else 0

            # Top influencers (engagement-weighted authors)
            top_authors = sorted(
                members, key=lambda p: -(p["total_engagement"] + 0.1 * p["n_posts"])
            )[:5]
            top_influencers = [
                {
                    "author_id": p["author_id"],
                    "n_posts": p["n_posts"],
                    "total_engagement": p["total_engagement"],
                    "sample_post": (p["_records"][0].get("content") or "")[:240]
                    if p["_records"] else "",
                }
                for p in top_authors
            ]

            # Representative posts: highest engagement first, then keep variety
            sorted_records = sorted(member_records, key=lambda r: -_engagement(r))
            seen_norm = set()
            representative: list[str] = []
            for r in sorted_records:
                c = (r.get("content") or "").strip()
                if not c:
                    continue
                norm = re.sub(r"\s+", " ", c.lower())[:120]
                if norm in seen_norm:
                    continue
                seen_norm.add(norm)
                representative.append(c[:280])
                if len(representative) >= 8:
                    break

            # Behavioral driver z-scores
            drivers = _behavioral_drivers(members, author_profiles)

            # Dominant platform
            platforms = [p["dominant_platform"] for p in members]
            dominant_platform = Counter(platforms).most_common(1)[0][0] if platforms else "unknown"

            confidence = _confidence(len(members), cohesion)

            distinctive_terms = distinctive_per_cluster[cluster_id]

            description = (
                f"{len(members)} authors clustered on shared voice + behavior. "
                f"Distinctive vocabulary: {', '.join(distinctive_terms[:5]) or 'n/a'}. "
                f"Sentiment: mean compound {mean_sentiment:+.2f}. "
                f"Drivers: " + ", ".join(
                    f"{d['feature']} {d['direction']} pop (z={d['z']:+.2f})"
                    for d in drivers[:3]
                )
            )

            archetypes.append({
                "id": f"archetype_{cluster_id}",
                "cluster_id": cluster_id,
                "size": len(members),                       # legacy: now n_authors
                "n_authors": len(members),
                "n_posts": sum(p["n_posts"] for p in members),
                "description": description,
                "representative_posts": representative,
                # legacy keys preserved for downstream consumers
                "pct_positive": pct_pos,
                "pct_negative": pct_neg,
                "pct_neutral": pct_neu,
                "mean_sentiment": round(mean_sentiment, 4),
                "avg_engagement": avg_engagement,
                "top_terms": distinctive_terms,             # legacy alias
                # new enrichment
                "distinctive_terms": distinctive_terms,
                "behavioral_drivers": drivers,
                "cohesion": round(cohesion, 4),
                "confidence": confidence,
                "top_influencers": top_influencers,
                "dominant_platform": dominant_platform,
            })

        diagnostics = {
            "n_authors": n_authors,
            "n_posts_clean": len(cleaned),
            "drop_stats": drop_stats,
            "k_chosen": chosen_k,
            "silhouette": round(sil_score, 4),
            "silhouette_per_k": {str(k): round(v, 4) for k, v in sil_scores.items()},
            "behavioral_weight": BEHAVIORAL_WEIGHT,
        }
        logger.info(
            f"Built {len(archetypes)} archetypes "
            f"(K={chosen_k}, silhouette={sil_score:.3f}, dropped={drop_stats})"
        )
        return archetypes, diagnostics

    # ------------------------------------------------------------------
    # Stage 3 — sanitized agent generation
    # ------------------------------------------------------------------

    def generate_profiles(
        self,
        archetypes: list[dict],
        entity_id: str,
        entity_name: str,
        community_name: str,
        n_agents_per_archetype: int = 12,
        graph_ctx: dict | None = None,
        task=None,
    ) -> list[OasisAgentProfile]:
        all_profiles: list[OasisAgentProfile] = []
        graph_ctx = graph_ctx or {}
        total = len(archetypes) or 1

        for idx, archetype in enumerate(archetypes):
            logger.info(
                f"Naming + generating {n_agents_per_archetype} agents for "
                f"{archetype['id']} ({idx+1}/{total})"
            )
            if task:
                from app.utils.task_manager import task_manager
                pct = 50 + int(35 * idx / total)
                task_manager.update(task.task_id, progress=pct)

            # Step A — LLM names + summarises the archetype (sanitized)
            naming = self._name_archetype(archetype)
            archetype["archetype_name"] = naming.get("archetype_name", archetype["id"])
            archetype["summary"] = naming.get("summary", archetype["description"])

            # Step B — generate N agents grounded in real posts + signature
            raw_profiles = self._generate_archetype_profiles(
                archetype=archetype,
                entity_name=entity_name,
                community_name=community_name,
                n=n_agents_per_archetype,
                graph_ctx=graph_ctx,
            )

            for raw in raw_profiles:
                try:
                    persona_text = (raw.get("persona_text") or "").strip()
                    # Soft sanitiser: strip out forbidden phrases (LLM may slip)
                    for bad in _FORBIDDEN_PHRASES:
                        persona_text = re.sub(
                            re.escape(bad), "[redacted]", persona_text, flags=re.I,
                        )

                    # Constrain initial opinion to the archetype's sentiment band
                    opinions = raw.get("initial_opinions") or {}
                    if entity_name in opinions:
                        opinions[entity_name] = _clamp_opinion_to_band(
                            float(opinions.get(entity_name, 0.0)),
                            archetype.get("mean_sentiment", 0.0),
                        )

                    profile = OasisAgentProfile(
                        user_id=str(uuid.uuid4()),
                        name=raw.get("name", f"user_{uuid.uuid4().hex[:6]}"),
                        persona_text=persona_text,
                        bio=raw.get("bio", ""),
                        age=int(raw.get("age", 30)),
                        mbti=raw.get("mbti", "INFP"),
                        initial_opinions=opinions,
                        social_relationships=raw.get("social_connections", []),
                        activity_level=raw.get("activity_level", "medium"),
                        influence_tier=raw.get("influence_tier", "regular"),
                        archetype_id=archetype["id"],
                    )
                    all_profiles.append(profile)
                except Exception as exc:
                    logger.warning(f"Profile parse error: {exc} | raw={raw}")

        logger.info(f"Generated {len(all_profiles)} total profiles")
        return all_profiles

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    def run(
        self,
        entity_id: str,
        entity_name: str,
        community_name: str,
        n_clusters: int = 8,
        n_agents_per_archetype: int = 12,
        task=None,
    ) -> str:
        def _progress(pct: int):
            if task:
                from app.utils.task_manager import task_manager
                task_manager.update(task.task_id, progress=pct)

        _progress(5)
        graph_ctx = self._load_graph_context(entity_id)

        _progress(10)
        corpus = self.collect_community_corpus(entity_id)
        _progress(25)

        archetypes, diagnostics = self.cluster_archetypes(corpus, n_clusters)
        _progress(50)

        profiles = self.generate_profiles(
            archetypes, entity_id, entity_name, community_name,
            n_agents_per_archetype, graph_ctx=graph_ctx, task=task,
        )
        _progress(90)

        set_id = self._persist(entity_id, archetypes, profiles, corpus, diagnostics)
        _progress(100)
        return set_id

    def generate(self, entity_id: str) -> str:
        """Convenience wrapper used by corpus_drift_detector — pulls entity name from store."""
        from app.services.entity_store import entity_store
        entity = entity_store.get(entity_id)
        if not entity:
            raise ValueError(f"Entity {entity_id} not found")
        return self.run(
            entity_id=entity_id,
            entity_name=entity.name,
            community_name=f"{entity.name} community",
            n_clusters=Config.DEFAULT_N_ARCHETYPES,
            n_agents_per_archetype=12,
        )

    # ------------------------------------------------------------------
    # Persistence + listing
    # ------------------------------------------------------------------

    def list_persona_sets(self, entity_id: str) -> list[dict]:
        personas_dir = Path(self.config.ENTITIES_DIR) / entity_id / "personas"
        if not personas_dir.exists():
            return []
        sets = []
        for set_dir in personas_dir.iterdir():
            if not set_dir.is_dir():
                continue
            meta_path = set_dir / "corpus_stats.json"
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text())
                    sets.append({
                        "set_id": set_dir.name,
                        "entity_id": entity_id,
                        "n_profiles": meta.get("n_profiles", 0),
                        "n_archetypes": meta.get("n_archetypes", 0),
                        "created_at": meta.get("created_at", ""),
                    })
                except Exception:
                    sets.append({"set_id": set_dir.name, "entity_id": entity_id})
        return sets

    def get_persona_set(self, entity_id: str, set_id: str) -> dict:
        base = Path(self.config.ENTITIES_DIR) / entity_id / "personas" / set_id
        archetypes = (
            json.loads((base / "archetypes.json").read_text())
            if (base / "archetypes.json").exists() else []
        )
        profiles_raw = (
            json.loads((base / "profiles.json").read_text())
            if (base / "profiles.json").exists() else []
        )
        diagnostics = (
            json.loads((base / "clustering_diagnostics.json").read_text())
            if (base / "clustering_diagnostics.json").exists() else {}
        )
        return {"archetypes": archetypes, "profiles": profiles_raw, "diagnostics": diagnostics}

    # ------------------------------------------------------------------
    # Internal: LLM + embedding helpers
    # ------------------------------------------------------------------

    def _embed_batch(self, texts: list[str]) -> list[list[float]] | None:
        all_embeddings: list[list[float]] = []
        batch_size = 50
        for i in range(0, len(texts), batch_size):
            batch = [t[:4000] if t else " " for t in texts[i : i + batch_size]]
            try:
                resp = self.llm.embeddings.create(model=self.embed_model, input=batch)
                all_embeddings.extend([d.embedding for d in resp.data])
            except Exception as exc:
                logger.error(f"Embedding batch {i} failed: {exc}")
                return None
        return all_embeddings

    def _name_archetype(self, archetype: dict) -> dict:
        prompt = _ARCHETYPE_NAMING_PROMPT.format(
            cluster_id=archetype["id"],
            n_authors=archetype.get("n_authors", archetype.get("size", 0)),
            n_posts=archetype.get("n_posts", 0),
            distinctive_terms=", ".join(archetype.get("distinctive_terms", [])[:10]) or "n/a",
            pct_positive=archetype.get("pct_positive", 0),
            pct_negative=archetype.get("pct_negative", 0),
            pct_neutral=archetype.get("pct_neutral", 0),
            mean_sentiment=archetype.get("mean_sentiment", 0.0),
            behavioral_drivers="; ".join(
                f"{d['feature']} {d['direction']} (z={d['z']:+.2f})"
                for d in archetype.get("behavioral_drivers", [])[:5]
            ) or "n/a",
            dominant_platform=archetype.get("dominant_platform", "unknown"),
            representative_posts="\n".join(
                f"  - {p[:200]}" for p in archetype.get("representative_posts", [])[:5]
            ) or "  (none)",
        )
        try:
            resp = self.llm.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            data = json.loads(resp.choices[0].message.content or "{}")
            return {
                "archetype_name": str(data.get("archetype_name", archetype["id"]))[:80],
                "summary": str(data.get("summary", archetype.get("description", ""))),
            }
        except Exception as exc:
            logger.warning(f"Archetype naming failed for {archetype['id']}: {exc}")
            return {
                "archetype_name": archetype["id"],
                "summary": archetype.get("description", ""),
            }

    def _generate_archetype_profiles(
        self,
        archetype: dict,
        entity_name: str,
        community_name: str,
        n: int,
        graph_ctx: dict | None = None,
    ) -> list[dict]:
        graph_ctx = graph_ctx or {}
        sample_posts = "\n".join(
            f"  - {p[:200]}" for p in archetype.get("representative_posts", [])[:8]
        )
        prompt = _PERSONA_PROMPT.format(
            n=n,
            entity_name=entity_name,
            archetype_name=archetype.get("archetype_name", archetype["id"]),
            archetype_summary=archetype.get("summary", archetype.get("description", "")),
            pct_positive=archetype.get("pct_positive", 0),
            pct_negative=archetype.get("pct_negative", 0),
            pct_neutral=archetype.get("pct_neutral", 0),
            mean_sentiment=archetype.get("mean_sentiment", 0.0),
            distinctive_terms=", ".join(archetype.get("distinctive_terms", [])[:15]) or "n/a",
            behavioral_drivers="; ".join(
                f"{d['feature']} {d['direction']} pop (z={d['z']:+.2f})"
                for d in archetype.get("behavioral_drivers", [])[:5]
            ) or "n/a",
            avg_engagement_per_author=archetype.get("avg_engagement", 0),
            sample_posts=sample_posts or "  (none)",
            graph_entities=graph_ctx.get("entities", "none"),
            graph_relationships=graph_ctx.get("relationships", "none"),
            graph_sentiment=graph_ctx.get("sentiment", "unknown"),
        )
        try:
            resp = self.llm.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.7,
            )
            raw = resp.choices[0].message.content or "[]"
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                fallback = next((v for v in parsed.values() if isinstance(v, list)), [])
                return parsed.get("profiles", fallback)
            return parsed if isinstance(parsed, list) else []
        except Exception as exc:
            logger.error(f"Profile generation failed for {archetype['id']}: {exc}")
            return []

    def _persist(
        self,
        entity_id: str,
        archetypes: list[dict],
        profiles: list[OasisAgentProfile],
        corpus: list[dict],
        diagnostics: dict,
    ) -> str:
        set_id = str(uuid.uuid4())
        base = Path(self.config.ENTITIES_DIR) / entity_id / "personas" / set_id
        base.mkdir(parents=True, exist_ok=True)

        (base / "archetypes.json").write_text(
            json.dumps(archetypes, indent=2, default=str)
        )
        profiles_data = [p.model_dump(mode="json") for p in profiles]
        (base / "profiles.json").write_text(
            json.dumps(profiles_data, indent=2, default=str)
        )
        (base / "clustering_diagnostics.json").write_text(
            json.dumps(diagnostics, indent=2, default=str)
        )

        stats = {
            "set_id": set_id,
            "entity_id": entity_id,
            "n_profiles": len(profiles),
            "n_archetypes": len(archetypes),
            "corpus_size": len(corpus),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "engine_version": "v2_author_level",
            "silhouette": diagnostics.get("silhouette"),
            "k_chosen": diagnostics.get("k_chosen"),
        }
        (base / "corpus_stats.json").write_text(json.dumps(stats, indent=2))

        logger.info(
            f"Persisted persona set {set_id}: "
            f"{len(profiles)} profiles, {len(archetypes)} archetypes "
            f"(silhouette={diagnostics.get('silhouette')})"
        )
        return set_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clamp_opinion_to_band(opinion: float, mean_sentiment: float) -> float:
    """Force the agent's initial entity opinion into the archetype's sentiment band."""
    if mean_sentiment > 0.15:                             # positive cluster
        return max(0.4, min(0.9, opinion if opinion > 0 else 0.5))
    if mean_sentiment < -0.15:                            # negative cluster
        return min(-0.4, max(-0.9, opinion if opinion < 0 else -0.5))
    return max(-0.3, min(0.3, opinion))                   # mixed


# Module-level singleton
persona_engine = PersonaEngine(Config)

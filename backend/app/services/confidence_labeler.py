"""
ConfidenceLabeler — Chunk 2C.

Tags an audience as high/medium/low based on signal density:
  - n_authors (sample size)
  - n_posts and posts-per-author (activity / density)
  - engagement-per-post (audience attention)
  - cluster coherence (Method B only; how tightly the cluster's vocabulary holds)

Output gates Chunk 3C — LLM hedging in why_adjacent / positioning_gap prose.

Pure function, no LLM, no I/O.
"""
from __future__ import annotations

from app.models import ConfidenceLabel


# Thresholds chosen so that with our typical ~100-post Twitter pulls a typical
# cluster lands in 'medium'. Edit here to retune across the whole product.
_AUTHOR_HIGH = 50
_AUTHOR_LOW = 15
_POSTS_PER_AUTHOR_HIGH = 2.0
_ENGAGEMENT_HIGH = 5.0      # avg engagement per post; depends heavily on platform
_COHERENCE_HIGH = 0.35      # silhouette; or top-term concentration as proxy


def label_confidence(
    n_authors: int,
    n_posts: int,
    engagement_per_post: float = 0.0,
    coherence: float | None = None,
) -> ConfidenceLabel:
    """Compute a confidence label from population-level signals."""
    reasons: list[str] = []
    components: list[float] = []

    # Author-count sub-score (always present)
    if n_authors >= _AUTHOR_HIGH:
        components.append(1.0)
        reasons.append(f"strong author sample ({n_authors})")
    elif n_authors >= _AUTHOR_LOW:
        components.append(0.5)
        reasons.append(f"moderate author sample ({n_authors})")
    else:
        components.append(0.15)
        reasons.append(f"small author sample ({n_authors})")

    # Density sub-score
    posts_per_author = (n_posts / n_authors) if n_authors else 0.0
    if posts_per_author >= _POSTS_PER_AUTHOR_HIGH:
        components.append(0.85)
        reasons.append(f"active audience ({posts_per_author:.1f} posts/author)")
    elif posts_per_author >= 1.2:
        components.append(0.55)
    else:
        components.append(0.35)
        reasons.append(f"thin participation ({posts_per_author:.1f} posts/author)")

    # Engagement sub-score
    if engagement_per_post >= _ENGAGEMENT_HIGH:
        components.append(0.85)
        reasons.append(f"high engagement per post ({engagement_per_post:.1f})")
    elif engagement_per_post >= 1.0:
        components.append(0.55)
    else:
        components.append(0.4)

    # Coherence sub-score (optional, Method B only)
    if coherence is not None:
        if coherence >= _COHERENCE_HIGH:
            components.append(0.9)
            reasons.append(f"tight topical coherence ({coherence:.2f})")
        elif coherence >= 0.15:
            components.append(0.55)
        else:
            components.append(0.3)
            reasons.append(f"low topical coherence ({coherence:.2f})")

    # Geometric-ish blend (avoid one big-number component dominating)
    score = sum(components) / len(components) if components else 0.5
    score = max(0.0, min(1.0, score))

    if score >= 0.66:
        level = "high"
    elif score >= 0.40:
        level = "medium"
    else:
        level = "low"

    return ConfidenceLabel(level=level, score=round(score, 3), reasons=reasons)

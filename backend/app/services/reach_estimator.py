"""
ReachEstimator — Chunk 2A (corrected: aggregate-only).

Produces a directional reachable-audience number per audience using
population aggregates only (NOT a top-N follower-sum heuristic, which was
rejected as a flawed proxy).

Inputs:
  - records: posts in the audience's scope
  - audience_authors: set of unique anonymized author IDs
  - platform_lift_factor: multiplier reflecting that each active author
    typically corresponds to ~10-50× passive observers depending on platform.
    Default 15. Transparent and overrideable.

Output: ReachEstimate with the components shown plainly so any user can
re-check or adjust the multiplier.

Pure function, no LLM, no I/O.
"""
from __future__ import annotations

from app.models import ReachEstimate


# Default multipliers per platform — rough orders of magnitude, not validated.
# Override at call site if you have better priors.
_PLATFORM_LIFT = {
    "twitter": 18.0,
    "hackernews": 8.0,
    "reddit": 25.0,
    "youtube": 12.0,
    "rss": 5.0,
}


def _engagement_total(record: dict) -> int:
    e = record.get("engagement") or {}
    return ((e.get("likes") or 0) + (e.get("shares") or 0)
            + (e.get("replies") or 0) + (e.get("views") or 0))


def estimate_reach(
    records: list[dict],
    audience_authors: set[str],
    platform_lift_factor: float | None = None,
) -> ReachEstimate:
    """Aggregate-only reach estimate. Reports the components used."""
    n_authors = len(audience_authors)
    n_posts = len(records)
    total_engagement = sum(_engagement_total(r) for r in records)
    posts_per_author = (n_posts / n_authors) if n_authors else 0.0

    # If lift not given, derive a weighted lift from the platform mix in records
    if platform_lift_factor is None:
        platform_lift_factor = _weighted_lift(records)

    estimated_reach = int(round(n_authors * platform_lift_factor))

    caveats = [
        "Directional indicator only — relative ranking, not Meta-validated reach.",
        f"Multiplier {platform_lift_factor:.1f}x assumes ~{int(platform_lift_factor)} passive observers per active author. Override to retune.",
    ]
    if n_authors < 15:
        caveats.append(f"Author sample is small ({n_authors}); estimate is highly uncertain.")
    if total_engagement == 0:
        caveats.append("No engagement signal in this corpus — multiplier may overstate.")

    return ReachEstimate(
        estimated_reach=estimated_reach,
        n_unique_authors=n_authors,
        n_posts=n_posts,
        total_engagement=total_engagement,
        posts_per_author=round(posts_per_author, 2),
        platform_lift_factor=round(platform_lift_factor, 2),
        method="author_count_with_engagement_lift",
        caveats=caveats,
    )


def _weighted_lift(records: list[dict]) -> float:
    """Weight platform multipliers by post share."""
    if not records:
        return 15.0
    total = 0.0
    for r in records:
        total += _PLATFORM_LIFT.get(r.get("platform", ""), 15.0)
    return total / len(records)

"""
VelocityScorer — Chunk 2B.

Computes population-level momentum for an audience from corpus timestamps,
sentiment, and engagement. Operates on the audience's records (not a top-N).

Components:
  - post_volume_trend: second_half_count / first_half_count - 1   (signed)
  - sentiment_trajectory: slope of per-bucket mean compound (linear regression)
  - sentiment_intensity: stdev of compound (high = active debate, weighted +)
  - engagement_per_post_trend: (eng/post second half) / (eng/post first half) - 1
  - share_of_voice_change: audience share of broader corpus second_half - first_half
    (only present if full_corpus_records provided)

Combined into a signed score ∈ [-1, +1]. Label: rising > +0.15, declining < -0.15.

Pure function, no LLM, no I/O.
"""
from __future__ import annotations

from datetime import datetime, timezone
from statistics import pstdev

from app.models import VelocityScore


def _engagement_total(record: dict) -> int:
    e = record.get("engagement") or {}
    return ((e.get("likes") or 0) + (e.get("shares") or 0)
            + (e.get("replies") or 0) + (e.get("views") or 0))


def _vader_compound(text: str, sia=None) -> float:
    if not text:
        return 0.0
    if sia is None:
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
            sia = SentimentIntensityAnalyzer()
        except ImportError:
            return 0.0
    return sia.polarity_scores(text)["compound"]


def _parse_ts(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _split_by_time(records: list[dict]) -> tuple[list[dict], list[dict], int]:
    """Sort by created_at, split into first-half / second-half. Returns (first, second, window_days)."""
    timed = []
    for r in records:
        ts = _parse_ts(r.get("created_at", ""))
        if ts:
            timed.append((ts, r))
    if not timed:
        return [], [], 0
    timed.sort(key=lambda t: t[0])
    n = len(timed)
    half = n // 2
    first = [r for _, r in timed[:half]]
    second = [r for _, r in timed[half:]]
    span = (timed[-1][0] - timed[0][0]).days
    return first, second, max(1, span)


def _slope(xs: list[float], ys: list[float]) -> float:
    """Simple OLS slope; returns 0 if degenerate."""
    n = len(xs)
    if n < 2:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = sum((x - mx) ** 2 for x in xs)
    return num / den if den else 0.0


def score_velocity(
    records: list[dict],
    full_corpus_records: list[dict] | None = None,
) -> VelocityScore:
    """Compute momentum score from population aggregates."""
    if len(records) < 4:
        return VelocityScore(
            momentum="stable",
            score=0.0,
            components={"reason": "too_few_records"},
            window_days=0,
            n_buckets=0,
            caveats=[f"only {len(records)} records — velocity not computed"],
        )

    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        sia = SentimentIntensityAnalyzer()
    except ImportError:
        sia = None

    first, second, window_days = _split_by_time(records)
    if not first or not second:
        return VelocityScore(
            momentum="stable",
            score=0.0,
            components={"reason": "no_temporal_signal"},
            window_days=0,
            n_buckets=0,
            caveats=["no parseable timestamps in records"],
        )

    # post_volume_trend: relative change, capped at +/- 1
    pvt_raw = (len(second) / max(1, len(first))) - 1.0
    pvt = max(-1.0, min(1.0, pvt_raw))

    # sentiment per bucket
    s1 = [_vader_compound(r.get("content", ""), sia) for r in first]
    s2 = [_vader_compound(r.get("content", ""), sia) for r in second]
    s_all = s1 + s2
    sentiment_trajectory = _slope([0.0] * len(s1) + [1.0] * len(s2), s_all)
    sentiment_intensity = pstdev(s_all) if len(s_all) > 1 else 0.0

    # engagement / post
    eps1 = sum(_engagement_total(r) for r in first) / max(1, len(first))
    eps2 = sum(_engagement_total(r) for r in second) / max(1, len(second))
    if eps1 > 0:
        ept_raw = (eps2 / eps1) - 1.0
    else:
        ept_raw = 1.0 if eps2 > 0 else 0.0
    ept = max(-1.0, min(1.0, ept_raw))

    # share-of-voice change (optional)
    sov_change = None
    if full_corpus_records:
        c_first, c_second, _ = _split_by_time(full_corpus_records)
        if c_first and c_second:
            audience_ids = {id(r) for r in records}  # identity-based dedupe in practice
            audience_first_ids = {r.get("id") for r in first}
            audience_second_ids = {r.get("id") for r in second}
            sov_first = (
                sum(1 for r in c_first if r.get("id") in audience_first_ids)
                / max(1, len(c_first))
            )
            sov_second = (
                sum(1 for r in c_second if r.get("id") in audience_second_ids)
                / max(1, len(c_second))
            )
            sov_change = sov_second - sov_first

    components = {
        "post_volume_trend": round(pvt, 3),
        "sentiment_trajectory": round(sentiment_trajectory, 3),
        "sentiment_intensity": round(sentiment_intensity, 3),
        "engagement_per_post_trend": round(ept, 3),
    }
    if sov_change is not None:
        components["share_of_voice_change"] = round(sov_change, 4)

    # Combined score: weighted average, clamped
    weights = {"post_volume_trend": 0.40, "sentiment_trajectory": 0.20,
               "engagement_per_post_trend": 0.30, "sentiment_intensity": 0.10}
    if sov_change is not None:
        weights["share_of_voice_change"] = 0.35
        # Renormalize
        total = sum(weights.values())
        weights = {k: v / total for k, v in weights.items()}

    score = 0.0
    score += weights["post_volume_trend"] * pvt
    score += weights["sentiment_trajectory"] * max(-1.0, min(1.0, sentiment_trajectory))
    score += weights["engagement_per_post_trend"] * ept
    # intensity is unsigned — treat as a small additive lift on |score| (active debate is momentum-positive)
    intensity_lift = min(0.15, sentiment_intensity * 0.2)
    score += weights["sentiment_intensity"] * (intensity_lift if score >= 0 else -intensity_lift)
    if sov_change is not None:
        score += weights["share_of_voice_change"] * max(-1.0, min(1.0, sov_change * 10))

    score = max(-1.0, min(1.0, score))

    if score > 0.15:
        momentum = "rising"
    elif score < -0.15:
        momentum = "declining"
    else:
        momentum = "stable"

    caveats: list[str] = []
    if window_days <= 2:
        caveats.append(f"short observation window ({window_days}d) — trend is noisy")
    if len(records) < 30:
        caveats.append(f"small corpus ({len(records)} posts) — velocity is approximate")

    return VelocityScore(
        momentum=momentum,
        score=round(score, 3),
        components=components,
        window_days=window_days,
        n_buckets=2,
        caveats=caveats,
    )

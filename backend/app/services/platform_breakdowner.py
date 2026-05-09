"""
PlatformBreakdowner — Chunk 3B.

Breaks down an audience by platform. Pulse's exact-hash author matching cannot
resolve the same person across platforms, so an audience that spans multiple
platforms should NOT have its numbers summed naively. This service surfaces the
per-platform split AND a flag warning the caller when summing would mislead.

Pure function, no LLM, no I/O.
"""
from __future__ import annotations

from collections import defaultdict

from app.models import PlatformBreakdown


def breakdown(records: list[dict]) -> tuple[list[PlatformBreakdown], bool]:
    """Group records by platform; return (breakdowns, multi_platform_warning_needed)."""
    by_platform: dict[str, dict[str, set | int]] = defaultdict(
        lambda: {"authors": set(), "n_posts": 0}
    )
    for r in records:
        plat = r.get("platform") or "unknown"
        aid = r.get("author_id") or ""
        by_platform[plat]["n_posts"] += 1
        if aid:
            by_platform[plat]["authors"].add(aid)

    if not by_platform:
        return [], False

    total_authors = sum(len(d["authors"]) for d in by_platform.values())  # double-counts cross-platform authors, intentionally — see warning
    total_posts = sum(d["n_posts"] for d in by_platform.values())

    breakdowns: list[PlatformBreakdown] = []
    for plat, d in sorted(by_platform.items(), key=lambda x: -x[1]["n_posts"]):
        n_a = len(d["authors"])
        n_p = d["n_posts"]
        breakdowns.append(PlatformBreakdown(
            platform=plat,
            n_authors=n_a,
            n_posts=n_p,
            pct_of_audience_authors=round((n_a / total_authors) if total_authors else 0.0, 4),
            pct_of_audience_posts=round((n_p / total_posts) if total_posts else 0.0, 4),
        ))

    multi_platform = len(breakdowns) >= 2
    return breakdowns, multi_platform

"""
InfluencerExtractor — shared utility used by both Method B (community clusters)
and Method C (negative-space audiences) to rank authors by engagement-weighted
reach within a record set.

Pure function, no LLM, no I/O. Takes a list of PostRecord dicts and returns
top-N Influencer objects sorted by total engagement.
"""
from __future__ import annotations

from typing import Iterable

from app.models import Influencer


def rank_influencers(records: Iterable[dict], top_n: int = 10) -> list[Influencer]:
    """Return top-N authors in `records` ranked by total engagement.

    Each Influencer includes posts_in_scope, total_engagement, a normalized
    influence_score in [0, 1], and one sample post for context.
    """
    by_author: dict[str, dict] = {}
    for r in records:
        aid = r.get("author_id")
        if not aid:
            continue
        eng = r.get("engagement") or {}
        total_eng = ((eng.get("likes") or 0)
                     + (eng.get("shares") or 0)
                     + (eng.get("replies") or 0)
                     + (eng.get("views") or 0))
        d = by_author.setdefault(aid, {
            "posts": 0,
            "total_engagement": 0,
            "sample": "",
            "platform": r.get("platform", ""),
            "url": r.get("url", ""),
            "display_name": (r.get("author_metadata") or {}).get("username", ""),
        })
        d["posts"] += 1
        d["total_engagement"] += total_eng
        # Capture the highest-engagement single post as the representative sample
        if total_eng >= d.get("_sample_eng", -1) and r.get("content"):
            d["sample"] = (r.get("content") or "")[:240]
            d["url"] = r.get("url", "")
            d["_sample_eng"] = total_eng

    if not by_author:
        return []

    max_eng = max((d["total_engagement"] for d in by_author.values()), default=1) or 1
    top = sorted(by_author.items(), key=lambda x: -x[1]["total_engagement"])[:top_n]
    return [
        Influencer(
            author_id=aid,
            display_name=d["display_name"],
            platform=d["platform"],
            posts_in_scope=d["posts"],
            total_engagement=d["total_engagement"],
            influence_score=round(d["total_engagement"] / max_eng, 4),
            sample_post=d["sample"],
            sample_post_url=d["url"],
        )
        for aid, d in top
    ]

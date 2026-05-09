"""
End-to-end demo of Layer 2 audience discovery (Methods B & C).

This script assumes the backend is running at http://localhost:5001 and that
you have at least:
  - A target entity ingested (the brand / topic / person you want to expand from)
  - For Method B: a SECOND, broader category entity ingested with manually
    supplied wider query terms (e.g. for an Anthropic target: a "AI assistants"
    category entity)
  - For Method C: 1+ competitor entities each with their own ingested corpus

Usage:
  uv run python experiments/audience_discovery_demo.py \\
      --target  <target_entity_id> \\
      --category <category_entity_id> \\
      --competitors <c1_id> <c2_id> ...

If --target/--category/--competitors are omitted, the script falls back to
an interactive prompt that lists existing entities.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

API = "http://localhost:5001"


def get(path: str) -> dict:
    return json.loads(urllib.request.urlopen(f"{API}{path}", timeout=60).read())


def post(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return json.loads(urllib.request.urlopen(req, timeout=600).read())


def list_entities() -> list[dict]:
    return get("/api/graph/entities")


def pick_entity(label: str, entities: list[dict]) -> str | None:
    print(f"\nSelect {label}:")
    for i, e in enumerate(entities):
        print(f"  [{i}] {e['name']:30s} {e['id']}")
    raw = input(f"  index for {label} (blank to skip): ").strip()
    if not raw:
        return None
    try:
        return entities[int(raw)]["id"]
    except (ValueError, IndexError):
        print(f"  invalid index, skipping {label}")
        return None


def run_method_b(target_id: str, category_id: str, n_clusters: int = 6, briefs: bool = False) -> list[dict]:
    print(f"\n=== Method B — adjacent communities ({category_id[:8]} → not in {target_id[:8]}) ===")
    body = post("/api/audience/adjacent", {
        "target_entity_id": target_id,
        "category_entity_id": category_id,
        "n_clusters": n_clusters,
        "explain": True,
    })
    print(f"  {body['n_communities']} communities surfaced\n")
    for c in body["communities"]:
        print(f"  ── {c['label']} (cluster {c['cluster_id']}) ──")
        print(f"     distance from target : {c['distance_from_target']}")
        print(f"     authors / posts      : {c['n_authors']} / {c['n_posts']}")
        print(f"     overlap with target  : {c['overlap_with_target']}")
        print(f"     top terms            : {', '.join(c['top_terms'][:8])}")
        print(f"     sentiment            : {c['sentiment']}")
        if c.get("why_adjacent"):
            print(f"     why adjacent         : {c['why_adjacent']}")
        if c.get("influencers"):
            top = c["influencers"][:3]
            print(f"     top influencers      :")
            for inf in top:
                handle = inf.get("display_name") or inf["author_id"][:10]
                print(f"        - {handle:20s} {inf['posts_in_scope']}p / {inf['total_engagement']}e")
        if briefs:
            generate_brief(target_id, c, "method_b_adjacent", c.get("label") or f"cluster_{c['cluster_id']}")
        print()
    return body["communities"]


def run_method_c(target_id: str, competitor_ids: list[str], briefs: bool = False) -> list[dict]:
    print(f"\n=== Method C — negative space ({target_id[:8]} vs {len(competitor_ids)} competitors) ===")
    body = post("/api/audience/negative-space", {
        "target_entity_id": target_id,
        "competitor_entity_ids": competitor_ids,
        "explain": True,
    })

    print("\n  Audience overlap matrix:")
    print(f"    target authors: {body['overlap_matrix']['target_n_authors']}")
    for p in body["overlap_matrix"]["pairs"]:
        print(f"    {p['name']:30s} authors={p['n_authors']:>5}  shared={p['intersection']:>4}  jaccard={p['jaccard']:.4f}  competitor_only={p['competitor_only']:>4}")

    print("\n  Negative-space audiences:")
    for aud in body["negative_space_audiences"]:
        gap = round(aud["coverage_gap_pct"] * 100)
        print(f"    {aud['competitor_name']}: {aud['n_authors_competitor_only']} unique authors not in target ({gap}% of competitor audience)")
        print(f"       sentiment toward competitor: {aud['sentiment_toward_competitor']}")
        print(f"       top terms: {', '.join(aud['top_terms'][:8])}")
        if aud["top_authors"]:
            top = aud["top_authors"][:3]
            for inf in top:
                handle = inf.get("display_name") or inf["author_id"][:10]
                print(f"         · {handle:20s} {inf['total_engagement']}e   {inf.get('sample_post','')[:80]!r}")
        print()

    print("  Positioning gaps:")
    for gap in body.get("positioning_gaps", []):
        print(f"    {gap['competitor_name']} (audience size: {gap['audience_size']})")
        print(f"      summary: {gap['gap_summary']}")
        for d in gap.get("drivers", []):
            print(f"        • driver: {d}")
        for q in gap.get("evidence_quotes", [])[:3]:
            print(f"          quote : \"{q[:120]}\"")
        print()

    if briefs:
        for aud in body.get("negative_space_audiences", []):
            generate_brief(
                target_id, aud, "method_c_negative_space",
                aud.get("competitor_name") or aud.get("competitor_entity_id", "competitor"),
            )

    return body.get("negative_space_audiences", [])


def generate_brief(target_id: str, audience: dict, source_method: str, label: str):
    print(f"\n  ── Generating execution brief for: {label} ──")
    body = post("/api/audience/brief", {
        "target_entity_id": target_id,
        "audience": audience,
        "source_method": source_method,
    })
    md = body.get("markdown_export", "")
    out_dir = Path(__file__).resolve().parent / "briefs"
    out_dir.mkdir(exist_ok=True)
    safe_label = "".join(c if c.isalnum() else "_" for c in label).lower().strip("_")
    md_path = out_dir / f"brief_{safe_label}.md"
    md_path.write_text(md)
    print(f"     audience_size : {body.get('audience_size')}")
    print(f"     hooks         : {len(body.get('creative', {}).get('top_hooks', []))}")
    print(f"     message angles: {len(body.get('creative', {}).get('message_angles', []))}")
    print(f"     meta interests: {len(body.get('targeting', {}).get('meta', {}).get('interest_stack', []))}")
    print(f"     google themes : {len(body.get('targeting', {}).get('google', {}).get('keyword_themes', []))}")
    print(f"     markdown      : {md_path} ({len(md)} bytes)")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--target", default=None, help="target entity_id")
    p.add_argument("--category", default=None, help="broader category corpus entity_id (Method B)")
    p.add_argument("--competitors", nargs="*", default=[], help="competitor entity_ids (Method C)")
    p.add_argument("--n-clusters", type=int, default=6)
    p.add_argument("--brief", action="store_true",
                   help="After surfacing audiences, generate an ExecutionBrief for each "
                        "and write markdown files to experiments/briefs/")
    args = p.parse_args()

    if not args.target or (not args.category and not args.competitors):
        entities = list_entities()
        if not entities:
            print("No entities found. Ingest at least one entity first.")
            sys.exit(1)
        target_id = args.target or pick_entity("target", entities)
        category_id = args.category or pick_entity("category corpus (skip if no Method B)", entities)
        if not args.competitors:
            comp_raw = input("competitor indices (comma-separated, blank to skip): ").strip()
            comp_ids = []
            if comp_raw:
                for tok in comp_raw.split(","):
                    try:
                        comp_ids.append(entities[int(tok.strip())]["id"])
                    except (ValueError, IndexError):
                        pass
        else:
            comp_ids = args.competitors
    else:
        target_id = args.target
        category_id = args.category
        comp_ids = args.competitors

    if not target_id:
        print("No target — exiting.")
        sys.exit(1)

    if category_id:
        run_method_b(target_id, category_id, n_clusters=args.n_clusters, briefs=args.brief)
    if comp_ids:
        run_method_c(target_id, comp_ids, briefs=args.brief)


if __name__ == "__main__":
    main()

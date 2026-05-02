# Pulse Experimental Dataset

Twitter corpora and aggregate results for the Pulse final-project experiment
(4 tests × 3 LLM providers, May 2026).

## Files

| File | Records | Test |
|---|---|---|
| `vision_pro_shelved.jsonl` | 101 | Apple Vision Pro shelving (negative product launch backtest) |
| `nothing_4a_pro.jsonl` | 87 | Nothing Phone (4a) Pro launch (positive product launch backtest) |
| `hochul_climate.jsonl` | 101 | NY Climate Law standoff / Hochul (state political backtest) |
| `nba_mvp_2026.jsonl` | 92 | 2026 NBA Finals MVP forecast (forward-looking) |
| `aggregate_results.json` | — | Per-test, per-provider sentiment trajectories, MAE, directional agreement, NBA prediction extraction |

## Schema (one JSONL line)

Each line is a `PostRecord` JSON object with the following fields:

```json
{
  "id": "twitter:1234567890",
  "platform": "twitter",
  "entity_id": "2926bc40-e1bc-45a8-a2b8-33d43c9dbc0a",
  "author_id": "<sha256 hash, anonymized>",
  "author_metadata": {
    "username": "...",
    "followers": 1234,
    "verified": false
  },
  "content": "<cleaned tweet text — t.co URLs stripped, HTML entities decoded>",
  "parent_id": null,
  "created_at": "2026-05-02T04:24:25.000Z",
  "engagement": {
    "likes": 11,
    "shares": 0,
    "replies": 0,
    "views": 0
  },
  "url": "https://twitter.com/i/web/status/1234567890",
  "raw": {
    "id": "1234567890",
    "metrics": { ... },
    "lang": "en"
  }
}
```

Author IDs are **anonymized via SHA-256 hash** before storage — no
personally identifying information is retained beyond what was already
public on Twitter at collection time.

## Collection methodology

All tweets were pulled via Twitter API v2 `/2/tweets/search/recent` on
**May 2, 2026** (UTC). The endpoint exposes a rolling 7-day window, so
the corpus covers approximately April 25 – May 2, 2026.

### Query strings (per test)

| Test | Twitter query |
|---|---|
| `vision_pro_shelved` | `("Vision Pro" OR "AVP" OR "Apple headset") -is:retweet -is:reply lang:en` |
| `nothing_4a_pro` | `("Nothing Phone" OR "Nothing 4a") -is:retweet -is:reply lang:en` |
| `hochul_climate` | `("Hochul" OR "CLCPA" OR "climate law") (NY OR "New York") -is:retweet -is:reply lang:en` |
| `nba_mvp_2026` | `(NBA OR Finals OR MVP OR playoffs) -is:retweet -is:reply lang:en` |

### Cleaning applied

1. `t.co` shortlinks stripped
2. HTML entities decoded (`&amp;`, `&#x27;`, etc.)
3. Whitespace normalized
4. Tweets shorter than 40 characters discarded
5. Retweets and replies excluded via Twitter operators
6. Non-English tweets excluded via `lang:en`
7. Deduplicated by tweet ID (`pulled_ids.db` SQLite)

## License & terms

Tweet **content** is published here under fair-use academic-research
exception, with the following caveats per Twitter's developer terms:

- This dataset must not be used for training commercial models
- Authors are anonymized (SHA-256 of original author ID); no usernames
  retained except in `author_metadata.username` for traceability
- If a tweet is later deleted or the author requests removal, the
  corresponding line in this dataset should be removed on request

For maximum compliance with X/Twitter's developer terms, downstream
researchers should:

1. Use only the **derived data** (sentiment scores, aggregates, IDs)
   from `aggregate_results.json` for redistribution
2. Use the JSONL `content` fields **only for their own analysis** —
   not republish them

If you need a strictly ToS-clean version, contact the repository
maintainer for a tweet-IDs-only export that requires rehydration via
the Twitter API.

## How this dataset was used

Each test ran an identical pipeline:

1. **Ingest** — corpus from Twitter (via this dataset) plus Hacker News fallback
2. **Build knowledge graph** — LLM ontology extraction → Zep Cloud + local SQLite
3. **Generate personas** — 5 archetypes × 4 agents = 20 agents, grounded in the corpus
4. **Run simulation** — 10 rounds, hypothetical event injected at round 0
5. **Score & aggregate** — VADER on every agent action, per-round and overall mean
6. **Pull ground truth** — additional ~100 tweets from the same query, VADER-scored
7. **Compare** — MAE between sim mean and ground-truth mean, plus directional agreement

The full per-cell results are in `aggregate_results.json`.

## Reproducibility

- Pulse repo: see root `README.md`
- Orchestrator: `backend/experiments/run_full_experiment.py`
- Aggregator: `backend/experiments/analyze_results.py`
- DOCX writeup: `backend/experiments/build_docx.py`
- Sentiment library: `vaderSentiment` (Python, lexicon-based; same library used on
  both sim actions and ground truth so any VADER bias cancels symmetrically)

## Known limitations of this dataset

- **Original tweets only — no replies, retweets, or quote tweets.** Every
  query was augmented with `-is:retweet -is:reply` to keep the corpus to
  standalone, self-contained tweets. Engagement *counts* (likes, retweets,
  replies, views) are preserved per record in the `engagement` field, but the
  *text* of those replies/RTs is not in this dataset. Researchers who want
  the full reply trees can rehydrate them via the Twitter v2 API using the
  preserved tweet IDs (`raw.id` field on each record). The same filter was
  applied to both sim corpora and ground-truth corpora, so the in-experiment
  comparison is internally consistent.
- **Sample size is small.** ~100 tweets per test is a thin slice for statistical
  inference. The Pulse writeup reports MAE point estimates, not confidence intervals.
- **Selection bias from `/search/recent`.** Twitter's relevance ranking may
  over-represent high-engagement tweets; the corpus is not a uniform random
  sample of all matching tweets.
- **VADER as the canonical sentiment scorer** is a simplification. VADER is
  lexicon-based, which limits its handling of sarcasm, irony, and
  community-specific slang. The same scorer is applied to sim and ground truth
  symmetrically, so VADER bias cancels for *comparison* purposes — but the
  absolute level of "real" sentiment is VADER's interpretation, not human-verified.
- **English-language only.** `lang:en` filter excludes non-English discourse,
  even when the underlying topic is multinational.
- **Pre/post-event split is not enforced.** The Twitter 7-day window often
  contains both pre-event and post-event tweets in a single pull; we did not
  surgically separate these. This may dilute or amplify the ground-truth signal
  depending on when in the window the event occurred.
- **Non-text agent actions** (likes, dislikes, reposts) carry implicit fixed
  sentiment scores in the simulation; this can drag the simulated mean toward
  neutral compared to a text-only baseline.
- **NBA test has no ground truth at submission time.** The actual 2026 NBA
  Finals occur in June; the prediction stands as a frozen forecast.

See the full project writeup (`Pulse_FinalProject.docx` in
`backend/data/experiment_results/aggregate/`) for the comprehensive Limitations
and Future Work sections.

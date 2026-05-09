# PULSE: Social Sentiment Simulation Platform

Existing social listening tools measure past sentiment; Pulse simulates future sentiment before a communication decision is made.

PULSE is a social intelligence platform that simulates how real communities react to news, product launches, controversies, and hypothetical events. Given any brand, person, or topic, it spins up AI agents — each with a distinct persona grounded in real social data — and runs them through a multi-round social media simulation across Twitter and Reddit. You get live sentiment scores, emergent opinion dynamics, and a prediction of how public sentiment will shift.

Think of it as a flight simulator for PR and brand strategy.

> **Final-project status (May 2026):** Pulse has been evaluated against real Twitter ground truth on three recent events (Apple Vision Pro shelving, Nothing Phone 4a Pro launch, NY Climate Law / Hochul standoff) plus one forward-looking forecast (2026 NBA Finals MVP). Across 9 backtest cells, **6/9 correctly matched real Twitter sentiment direction**; the political test (Hochul climate) was the failure case across all three LLM providers, surfacing a **shared positivity-bias risk on contested political content**. See [Final Project Experiment](#final-project-experiment) below for the full results, [`/dataset`](dataset/) for the raw Twitter corpora, [`LIMITATIONS.md`](LIMITATIONS.md) for known weaknesses, and [`NIST_COMPLIANCE.md`](NIST_COMPLIANCE.md) for how Pulse maps to the NIST AI Risk Management Framework.

---

## What it does

1. **Ingests real social data** — pulls posts from Reddit, Twitter/X, YouTube, and RSS feeds for any tracked entity
2. **Builds a knowledge graph** — runs GraphRAG on the corpus and stores semantic episodes in Zep Cloud
3. **Generates persona archetypes** — clusters the community into distinct agent types (e.g. "Sneakerheads", "Finance Bros", "Gen Z shoppers") with opinions, MBTI, activity levels, and authentic voice
4. **Runs a parallel simulation** — agents interact on simulated Twitter and Reddit platforms using [OASIS](https://github.com/camel-ai/oasis), powered by LLM-driven action selection (post, comment, like, repost, follow, quote)
5. **Scores sentiment in real time** — VADER + LLM dual-mode scorer tracks emotion and sentiment per action
6. **Predicts sentiment trajectory** — aggregates round-by-round data into a forward-looking sentiment forecast
7. **Generates reports** — structured analysis of simulation results

---

## Stack

| Layer | Tech |
|---|---|
| Backend | Flask 3, Python 3.11, uv |
| Simulation engine | [OASIS](https://github.com/camel-ai/oasis) (CAMEL-AI), CamelAI |
| LLM (default) | Gemini 2.5 Flash Lite via OpenAI-compatible endpoint; multi-provider via [`model_factory`](backend/app/services/model_factory.py) (Gemini, OpenAI, Anthropic) |
| Memory / graph | Zep Cloud (GraphRAG + episodic memory) |
| Sentiment | VADER + LLM hybrid |
| Frontend | Vue 3 + Vite |
| Data ingestion | PRAW (Reddit), Tweepy (Twitter), YouTube Data API v3, feedparser (RSS) |
| Containerisation | Docker Compose (backend + frontend + Redis) |

---

## Project structure

```
pulse/
├── backend/
│   ├── app/
│   │   ├── routes/          # Flask blueprints (ingestion, graph, simulation, persona, report)
│   │   ├── services/        # Business logic (ingestion, persona engine, simulation manager, sentiment scorer, …)
│   │   ├── models.py        # Pydantic models
│   │   └── config.py        # Env-based config
│   ├── simulations/
│   │   ├── run_parallel_simulation.py   # OASIS simulation subprocess
│   │   ├── agent_logging.py             # Thread-safe action JSONL logger
│   │   └── interview_system.py          # Mid-simulation agent interviews
│   ├── data/
│   │   └── templates/       # Persona archetype templates
│   └── pyproject.toml
└── frontend/
    └── src/
        ├── views/           # Page components (Home, Ingest, Persona, Simulation, Graph, Report, Interact)
        ├── components/      # Reusable components (SimulationMonitor, SentimentChart, GraphPanel, …)
        └── api/             # Axios API clients
```

---

## API keys required

| Service | Used for | Where to get |
|---|---|---|
| LLM (Gemini / OpenAI) | Agent reasoning, persona generation, sentiment scoring | [Google AI Studio](https://aistudio.google.com) or [OpenAI](https://platform.openai.com) |
| Zep Cloud | Knowledge graph, GraphRAG, episodic memory | [getzep.com](https://www.getzep.com) |
| Reddit (PRAW) | Ingesting subreddit posts | [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) — create a **script** app |
| Twitter Bearer Token | Ingesting tweets (optional, paid) | [developer.twitter.com](https://developer.twitter.com) |
| YouTube Data API v3 | Ingesting video comments (optional) | [Google Cloud Console](https://console.cloud.google.com) |

RSS feeds require no key.

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/jeffreysupergoodatcoding/pulse.git
cd pulse/backend
uv sync                  # installs Python deps into .venv

cd ../frontend
npm install
```

### 2. Configure environment

Copy the example and fill in your keys:

```bash
cp .env.example .env
```

```env
# Required
LLM_API_KEY=your_gemini_or_openai_key
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
LLM_MODEL_NAME=gemini-2.5-flash
ZEP_API_KEY=your_zep_key

# Optional (for real data ingestion)
REDDIT_CLIENT_ID=your_client_id
REDDIT_CLIENT_SECRET=your_client_secret
REDDIT_USER_AGENT=pulse/1.0 by u/your_username
TWITTER_BEARER_TOKEN=your_bearer_token
YOUTUBE_API_KEY=your_yt_key
```

### 3. Run

```bash
# Terminal 1 — backend
cd backend
uv run python run.py

# Terminal 2 — frontend
cd frontend
npm run dev
```

Open [http://localhost:5173](http://localhost:5173).

### Or with Docker

```bash
docker compose up --build
```

---

## How to run a simulation

1. **Create an entity** — name, type (brand/person/topic), keywords
2. **Ingest data** — pull from Reddit/RSS/Twitter, pick your subreddits and queries
3. **Build knowledge graph** — GraphRAG pass over the corpus
4. **Generate personas** — cluster the community into agent archetypes
5. **Run simulation** — optionally inject a hypothetical event (e.g. "Nike just announced a $500 AI collab with Travis Scott")
6. **Watch** — live feed of agent actions, sentiment chart, round-by-round dynamics
7. **Read the report** — structured analysis of how sentiment evolved and why

---

## Layer 2 — Audience Discovery (Methods B & C)

Beyond simulating reactions to events, Pulse can surface **audiences a brand isn't currently reaching**. The capability has two methods:

### Method B — Adjacent communities (cross-pollination)
Given a target entity and a separately-ingested broader **category corpus** (you supply the wider query terms manually — e.g. for a sleep brand: `sleep OR insomnia OR recovery OR wellness`), Pulse:
1. Clusters the category corpus into communities (k-means on LLM embeddings, TF-IDF fallback)
2. Computes each cluster's author overlap with the target's existing audience
3. Ranks clusters by `distance_from_target` (1.0 = no audience overlap, 0.0 = total overlap)
4. Generates a per-cluster *"why adjacent"* explanation via LLM, citing sample posts
5. Returns each cluster's top influencers (engagement-weighted) — concrete handles to partner with or learn from

### Method C — Negative space (competitor audiences)
Given a target entity and 1+ **competitor entities** (each with its own ingested corpus):
1. Computes pairwise audience-overlap matrix (Jaccard, intersection, competitor-only sets)
2. Identifies authors active in each competitor's corpus but absent from the target's
3. Extracts the competitor-only audience's top terms, sentiment toward the competitor, and top influencers
4. Runs an LLM-driven **positioning gap analysis**: why did this audience choose the competitor, with verbatim quotes as evidence

### Chunks 2 & 3 — Make audiences rankable + defensible

Every audience surfaced by Method B or Method C now carries five enrichment fields, attached automatically. No new endpoints needed — `/api/audience/adjacent` and `/api/audience/negative-space` return enriched objects.

| Field | What it answers | Method |
|---|---|---|
| `reach_estimate` | "Roughly how big is this audience?" | Aggregate-only: author count × platform-lift multiplier. Directional, NOT Meta-validated. |
| `velocity` | "Is this audience rising, stable, or declining?" | Population trend over the corpus window — post volume, sentiment trajectory, engagement-per-post change |
| `confidence` | "How much should I trust this finding?" | high/medium/low based on author sample + density + engagement |
| `cannibalization` | "Is this genuinely net-new or am I already reaching them?" | Author-overlap math + optional LLM behavioral similarity → `net_new` / `lookalike_likely` / `overlap_likely` |
| `platform_breakdown` + `multi_platform_warning` | "Are these numbers honest across platforms?" | Per-platform split with explicit warning when summing would double-count (exact-hash matching) |

The `confidence` label is also threaded into the LLM hedging — `why_adjacent` and positioning-gap prose hedge ("preliminary signal", "needs validation") when confidence is low.

### BYO data upload

Skip Twitter/HN ingestion entirely if you already have data. Drop a JSONL or CSV; downstream pipeline (graph, personas, simulation, audience discovery, briefs) is identical to API-ingested data.

```
POST /api/ingestion/upload
  multipart form: { entity_id, file, file_format?, column_mapping?, default_platform? }
  returns: { records_added, records_skipped, errors[], output_path }
```

Required fields per row: `id`, `content`, `created_at`. `author_id` is SHA-256 anonymized on ingest.

In the UI: navigate to the entity's Ingest tab → "Upload" mode → drop file.

### Chunk 1 — Actionability: turn any audience into an executable brief
Every adjacent community AND every competitor-only audience can be turned into a
**one-page execution brief** ready for a CMO/agency handoff. The brief is LLM-generated from the audience's verbatim posts, top terms, top influencers, and sentiment, and contains:

| Section | What's in it |
|---|---|
| **Audience** | One-paragraph summary, size, mean sentiment, list of top influencers + their best post |
| **Platform Targeting** | Meta interest stack + behaviors + exclusions + placements; Google keyword themes + search intent + negative keywords; TikTok creator clusters + hashtag stacks + sound trends; Lookalike seed source / size / exclusion strategy |
| **Creative Direction** | 5 hooks (audience's voice), 3-5 pain points, 5-8 language patterns, 3-5 message angles each with tonal direction (e.g. "problem-aware UGC") + format + sample copy |
| **Markdown export** | Pre-rendered markdown for one-click copy/download |

Each brief is a single LLM call (~$0.001 on Gemini Flash Lite). Click "Generate Brief →" on any audience card in the UI, or call the endpoint directly.

### API endpoints

```
POST /api/audience/adjacent
  body: { target_entity_id, category_entity_id, n_clusters?, explain? }
  returns: { n_communities, communities: [AdjacentCommunity, ...] }

POST /api/audience/negative-space
  body: { target_entity_id, competitor_entity_ids: [...], explain? }
  returns: { overlap_matrix, negative_space_audiences, positioning_gaps }

POST /api/audience/overlap
  body: { target_entity_id, competitor_entity_ids: [...] }
  returns: pairwise audience overlap matrix only (no LLM)

POST /api/audience/brief                                  # Chunk 1
  body: { target_entity_id, audience, source_method?, extra_context? }
  returns: ExecutionBrief — full targeting + creative + markdown_export
```

### How to run

1. Ingest the target entity (existing flow under [`/entity/<id>/ingest`](frontend/src/views/IngestView.vue))
2. For Method B: create a second "category" entity with broad query terms and ingest its corpus
3. For Method C: create one entity per competitor and ingest each
4. Open the **Audience** tab on the target entity — choose Method B or Method C and select inputs

Or via the demo script:

```bash
cd backend
uv run python experiments/audience_discovery_demo.py \
  --target <target_entity_id> \
  --category <category_entity_id> \
  --competitors <c1_id> <c2_id> ...
```

### Code map

| File | Role |
|---|---|
| [`backend/app/services/audience_overlap_service.py`](backend/app/services/audience_overlap_service.py) | Set algebra over author IDs (no LLM) |
| [`backend/app/services/community_cluster_service.py`](backend/app/services/community_cluster_service.py) | Method B clustering (embeddings → k-means → ranked communities) |
| [`backend/app/services/influencer_extractor.py`](backend/app/services/influencer_extractor.py) | Engagement-weighted author ranking, shared between methods |
| [`backend/app/services/audience_discovery_service.py`](backend/app/services/audience_discovery_service.py) | Top-level orchestrator, LLM-renders "why adjacent" + positioning-gap explanations |
| [`backend/app/services/media_brief_service.py`](backend/app/services/media_brief_service.py) | Chunk 1 / actionability — synthesizes ExecutionBrief (targeting + creative + markdown) per audience |
| [`backend/app/routes/audience_routes.py`](backend/app/routes/audience_routes.py) | `/api/audience/*` Flask blueprint |
| [`frontend/src/views/AudienceDiscoveryView.vue`](frontend/src/views/AudienceDiscoveryView.vue) | UI for both methods + brief modal (Audience / Targeting / Creative / Markdown tabs, copy-as-md, download .md) |
| [`backend/experiments/audience_discovery_demo.py`](backend/experiments/audience_discovery_demo.py) | CLI demo for end-to-end Method B + C; pass `--brief` to also write per-audience markdown briefs to `experiments/briefs/` |

### Limitations of this scaffolding
- Single-snapshot clustering — no temporal community-evolution tracking yet
- The "category" corpus is manually supplied; auto-inference of category from a target's graph is a planned extension
- LLM positioning-gap analysis uses the configured Gemini model only; no multi-provider triangulation here yet (parallel to the simulation experiment, where multi-provider was the variable)
- Author overlap is exact-match on anonymized hash IDs — no fuzzy account-linking across platforms

---

## Final Project Experiment

Pulse was evaluated as part of a class final project (May 2026). The experiment ran 4 tests × 3 LLM providers (Gemini 2.5 Flash Lite, OpenAI gpt-4o-mini, Anthropic Claude Sonnet 4.5) on real recent events, all post-LLM-cutoff.

### Headline results

| Test | Ground truth (mean) | Best provider MAE | All 3 dir-match? |
|---|---|---|---|
| Apple Vision Pro shelved (negative) | +0.379 (n=97) | OpenAI 0.077 | ✓ 3/3 |
| Nothing Phone (4a) Pro (positive) | +0.250 (n=87) | OpenAI 0.048 | ✓ 3/3 |
| NY Climate Law / Hochul (political) | **−0.116 (n=101)** | (best) Gemini 0.140 | **✗ 0/3 — all directionally wrong** |
| 2026 NBA Finals MVP forecast | (June 2026 truth) | n/a (forward-looking) | Lakers / LeBron consensus |

**Overall directional accuracy: 6 / 9 backtest cells (67%).** The political failure is the load-bearing finding: all three frontier LLMs simulated *positive* sentiment when real Twitter discourse was *negative*, with cross-provider stdev of only 0.04 (providers agreed with each other while all three were wrong vs. reality).

### Surfaced limitations (concrete, not hypothetical)

- **Positivity / sycophancy bias** on contested political content (NIST Map Risk #3)
- **Provider-choice bias**: Gemini overshoots positive (mean +0.33), Anthropic undershoots (+0.14), OpenAI in between (+0.23) — the choice of LLM materially biases predictions (Risk #4)
- **Temporal staleness**: OpenAI and Anthropic agents repeatedly placed Luka Dončić on the Dallas Mavericks despite the February 2025 trade to the Lakers — agent factual reasoning is bounded by the LLM's training cutoff (Risk #5)

### Artifacts

- **Full writeup (DOCX)**: [`Pulse_FinalProject.docx`](Pulse_FinalProject.docx) at the repo root (also at [`backend/data/experiment_results/aggregate/Pulse_FinalProject.docx`](backend/data/experiment_results/aggregate/Pulse_FinalProject.docx) — same file). 12-section academic writeup (Audience, Problem, Methodology, Findings, NIST RMF, Limitations, Future Work, Honest Assessment, Reproducibility).
- **Twitter dataset**: [`/dataset`](dataset/) — 4 JSONL files of cleaned, anonymized tweets used in the experiment, plus the aggregate results JSON. See [`/dataset/README.md`](dataset/README.md) for schema, query strings, and ToS notes.
- **NIST AI RMF mapping**: [`NIST_COMPLIANCE.md`](NIST_COMPLIANCE.md)
- **Limitations**: [`LIMITATIONS.md`](LIMITATIONS.md)
- **Reproducibility scripts**:
  - [`backend/experiments/run_full_experiment.py`](backend/experiments/run_full_experiment.py) — full orchestrator
  - [`backend/experiments/analyze_results.py`](backend/experiments/analyze_results.py) — aggregator + comparison metrics
  - [`backend/experiments/build_docx.py`](backend/experiments/build_docx.py) — DOCX generator
  - [`backend/app/services/model_factory.py`](backend/app/services/model_factory.py) — provider-agnostic CAMEL backend builder

### Reproducing the experiment

```bash
cd backend
uv run python experiments/run_full_experiment.py             # all 4 tests
# or
uv run python experiments/run_full_experiment.py --only nothing_4a_pro

uv run python experiments/analyze_results.py                  # compute MAE etc.
uv run python experiments/build_docx.py                       # rebuild the DOCX
```

---

## License

[MIT](LICENSE) — see `LICENSE` file.

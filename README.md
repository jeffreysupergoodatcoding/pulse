# PULSE: Social Sentiment Simulation Platform

Existing social listening tools measure past sentiment; Pulse simulates future sentiment before a communication decision is made.

PULSE is a social intelligence platform that simulates how real communities react to news, product launches, controversies, and hypothetical events. Given any brand, person, or topic, it spins up hundreds of AI agents — each with a distinct persona grounded in real social data — and runs them through a multi-round social media simulation across Twitter and Reddit. You get live sentiment scores, emergent opinion dynamics, and a prediction of how public sentiment will shift.

Think of it as a flight simulator for PR and brand strategy.

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
| LLM | Gemini 2.5 Flash via OpenAI-compatible endpoint |
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

## License

MIT

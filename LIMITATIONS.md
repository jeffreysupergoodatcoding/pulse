# LIMITATIONS

This document enumerates the known limitations and threats to validity of
Pulse, as evaluated in the May 2026 final-project experiment. Anyone using
Pulse — for research, reporting, or decision support — should read this
document first. The full discussion is in §IX of the project writeup
(`backend/data/experiment_results/aggregate/Pulse_FinalProject.docx`); this
file is the load-bearing summary.

## TL;DR

**Pulse is a tool with documented failure modes, not a black-box predictor.**
It works approximately for simple consumer events (within ~0.05–0.08 MAE on a
[−1, +1] sentiment scale). It demonstrably fails on contested political
content (all three frontier LLMs were directionally wrong on the Hochul climate
test). It carries a temporal-staleness risk: agents inherit the underlying
LLM's training cutoff, so factual context (rosters, leadership, prices,
policies) may be out of date.

---

## 1. Sample-size and statistical-power concerns

- **N=1 backtest per category.** Three backtests cover three distinct domains
  (negative product launch, positive product launch, contested political
  event) but with one event each. The conclusion "Pulse fails on contested
  political content" is suggestive, not proven; replication on multiple
  political events is required to validate the finding.
- **Each cell is a single simulation run.** No error bars. Re-running the same
  configuration would produce a different trajectory due to LLM stochasticity.
  A proper version of this experiment would run each cell 5–10 times.
- **Ground-truth corpora are ~100 tweets per test.** This is small for stable
  mean estimation: a single high-engagement viral tweet can shift the mean by
  0.05+ on its own.
- **Four tests is not statistically powered to claim general validity.** The
  6/9 directional accuracy is an observation, not a hypothesis test.

## 2. Sentiment-scoring methodology

- **VADER is lexicon-based** and does not robustly handle sarcasm, irony, or
  community-specific slang.
- **VADER is the canonical scorer for both sim and ground truth.** Bias
  cancels symmetrically *for the comparison*, but the absolute level of "real"
  sentiment is VADER's interpretation, not human-validated truth.
- **Implicit sentiment scores for non-text actions** (likes, dislikes,
  reposts) are arbitrary fixed values. They drag the sim mean toward the
  middle and may distort comparisons against text-only ground truth.
- **No multi-scorer triangulation.** A robust experiment would score each
  piece of content with VADER, RoBERTa-tweet, and an LLM-as-judge, and report
  inter-method agreement.

## 3. Comparison-metric concerns

- **Single-mean comparison loses time structure.** Pulse's per-round
  trajectory has shape; collapsing to one number cannot detect a sim that
  captures the shape correctly but happens to have a different mean.
- **No trajectory-vs-trajectory Pearson correlation.** Twitter's
  `/search/recent` does not give us enough volume to bucket by hour at our
  query scale.
- **MAE is in absolute units on the [−1, +1] scale.** Two cells with the same
  MAE may be qualitatively different.
- **Ground-truth pre/post split is not enforced.** The 7-day Twitter window
  often contains both pre-event and post-event tweets in a single pull; this
  may dilute the post-event signal.

## 4. Corpus and selection bias

- **Twitter's `/search/recent` is relevance-ranked**, not uniform-random. The
  corpus over-represents high-engagement tweets — which may not represent how
  the median user feels.
- **English-language only** (`lang:en` filter).
- **Original tweets only — replies, retweets, and quote tweets are excluded.**
  The ingestion query appends `-is:retweet -is:reply` to every search. We
  capture engagement *counts* (likes, retweets, replies, views) per tweet, but
  not the *content* of replies, RTs, or QTs. This is a significant blind spot:
  replies are often where the strongest sentiment lives, especially in
  outrage / pile-on cycles. Both the sim corpus and the ground truth use the
  same filter, so the comparison is internally consistent — but the *absolute*
  level of "how Twitter feels" is biased toward original-tweet voice (which
  tends to be more measured / declarative than reply voice).
- **Tests were chosen partly for high Twitter volume.** The selection itself
  is biased toward "tweet-able" events.
- **HN and Twitter both skew toward technologically literate audiences.**

## 5. Simulation-design concerns

- **20 agents per simulation** is far smaller than real communities of
  thousands. Emergent dynamics at scale (cascade thresholds, viral
  propagation, echo-chamber formation) may differ.
- **Agent activity is gated by a fixed activation probability**
  (low: 25%, medium: 60%, high: 90%).
- **Agent opinions are static** — `initial_opinions` are set at persona
  generation and never updated by what the agent observes. "Sentiment
  evolution" in the trajectory comes from changing action selection, not
  actual belief change.
- **The injected event sits in every agent's context window.** Agents may
  anchor to its framing rather than reasoning independently.
- **Personas are LLM-generated by clustering posts**; clustering choices
  (k=5, k-means on embeddings) and the LLM's persona-writing tendencies
  propagate into the simulation.

## 6. LLM-specific concerns

- **Positivity / sycophancy bias** surfaced clearly in the Hochul test:
  every provider produced positive sentiment when reality was −0.12. Consistent
  with prior literature on RLHF-trained models.
- **Provider-choice bias**: Gemini systematically overshoots positive,
  Anthropic systematically lower. Picking one provider gives a biased
  estimate; picking three and averaging may not be enough either.
- **Temporal staleness** in agent reasoning. Concrete example: OpenAI and
  Anthropic agents repeatedly placed Luka Dončić on the Dallas Mavericks,
  despite the February 2025 trade to the Lakers. Pulse predictions are only as
  factually current as the underlying LLM's training cutoff.
- **Anthropic Vision Pro simulation was truncated** at round 7/10 (217 actions
  out of an expected ~300) due to an orchestrator timeout. Documented in
  `run_state.json` with a note field.
- **Cost asymmetry across providers.** Claude Sonnet 4.5 is ~30× more
  expensive per call than Gemini Flash Lite or GPT-4o-mini.

## 7. Threats to validity

- **Construct validity** — does VADER + corpus mean actually measure
  "community sentiment"? Approximately, with the lexicon caveats.
- **Internal validity** — does Pulse's pipeline cause its outputs, or are they
  an artifact of the LLM's priors? The Hochul / Luka findings suggest LLM
  priors leak through more than we'd like.
- **External validity** — do these four tests generalize to other events?
  Insufficient evidence.
- **Statistical conclusion validity** — N=12 cells is too small for hypothesis
  testing. All numbers are point estimates.
- **Selection validity** — the four tests were not randomly sampled. Chosen
  for tweet-ability and recency.

---

## Responsible use

Pulse outputs should be treated as one signal among many, not as ground truth.
Any deployment should:

1. Run **≥2 LLM providers** and report variance, not a single point estimate
2. Treat **positive Pulse outputs on political content with strong skepticism**
   given the documented Hochul failure
3. **Inject any post-LLM-cutoff factual context** (current rosters, leadership,
   prices) directly into the event prompt
4. Pair with traditional research methods (real surveys, focus groups,
   interviews) — Pulse complements but does not replace them
5. Disclose its use to anyone who consumes the output

See the full project writeup for further discussion and the complete future-work
roadmap.

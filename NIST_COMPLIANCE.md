# NIST AI Risk Management Framework Compliance

Pulse is designed for explicit compliance with the [NIST AI Risk Management
Framework (2023)](https://www.nist.gov/itl/ai-risk-management-framework). This
document maps each of the four NIST functions — **Govern, Map, Measure,
Manage** — to specific design decisions, code locations, and experimental
findings in this repository.

The full discussion is in §VII of the project writeup
(`backend/data/experiment_results/aggregate/Pulse_FinalProject.docx`); this
file is the standalone reference.

---

## Govern

How Pulse is structured, who it's for, and what it commits to.

| Principle | Implementation |
|---|---|
| Designed for risk assessment and academic research, **NOT** astroturfing or manufacturing fake consensus | Documented in `README.md` and the project writeup; no features for posting agent output to real platforms |
| Open-source publication makes the methodology auditable | This repository ([github.com/jeffreysupergoodatcoding/pulse](https://github.com/jeffreysupergoodatcoding/pulse)); MIT-licensed |
| No PII stored. All ingested content is publicly available social-media discourse. Authors are anonymized via SHA-256 hash | [`backend/app/services/ingestion_service.py`](backend/app/services/ingestion_service.py) — see `_anonymize()` |
| The system's predictions are explicitly framed as probabilistic, not deterministic | UI labels sentiment as range with confidence; writeup §XI states predictions "should inform decisions, not make them" |
| Documented limitations | [`LIMITATIONS.md`](LIMITATIONS.md), writeup §IX (7 subsections) |

## Map

Concrete risks identified and documented for Pulse itself.

| Risk | Description | Mitigation |
|---|---|---|
| **R1** | Outputs could be reverse-engineered for manipulation — by identifying which narratives spread fastest, a malicious actor could amplify those narratives rather than defend against them | Open methodology, LIMITATIONS.md, academic framing |
| **R2** | Persona archetypes can reinforce demographic stereotypes if the corpus is skewed | Multi-source ingestion supported; corpus skew documented per-test |
| **R3** *(newly documented by this experiment)* | **Positivity / sycophancy bias** in frontier LLMs causes Pulse to underestimate negative sentiment, especially on contested political content. The Hochul climate test demonstrated this directly: real Twitter sentiment was −0.116, all three LLM providers produced +0.02 to +0.13 (wrong direction) | Always run ≥2 providers, report variance, treat positive Pulse outputs on political topics with skepticism |
| **R4** *(newly documented)* | **Provider-choice bias** — different LLM backbones produce systematically different magnitudes (Gemini most positive, Anthropic most measured). A single-provider deployment gets a biased estimate | Multi-provider deployment; report cross-provider variance |
| **R5** *(newly documented)* | **Temporal / factual staleness** in agent reasoning. LLM-driven agents inherit the training-cutoff of the underlying model and may produce posts grounded in outdated facts. This experiment surfaced concrete examples (Luka Dončić placed on the Mavericks despite the February 2025 trade to the Lakers) | Inject current factual context directly into event prompts; document staleness risks per test |

## Measure

The 4-test × 3-provider experiment described in the writeup *is* the Measure
function. Pulse's predictive validity was evaluated against real Twitter
sentiment on three recent events (one positive product launch, one negative
product launch, one contested political event), each post-LLM-cutoff to
eliminate training-data contamination.

### Headline metrics

- **Directional accuracy:** 6 of 9 provider-test cells matched real Twitter
  sentiment direction (67%)
- **Best-cell MAE:** 0.048 (OpenAI on Nothing Phone 4a Pro launch)
- **Headline failure:** Hochul climate test — all three providers
  directionally wrong (real −0.116, sims +0.02 to +0.13)

### Failure case is reported, not hidden

Per NIST's "honest reporting of limitations" principle, the political
failure is reported as the headline finding, not buried. See writeup §VI
(Findings) and §XI (Honest Assessment).

### Reproducibility

Every sim is tagged with provider, model, and timestamp:

- `backend/data/simulations/<sim_id>/run_state.json` — provider, model, status
- `backend/data/simulations/<sim_id>/model_info.json` — provider tagging
- `backend/data/simulations/<sim_id>/actions.jsonl` — every action,
  human-inspectable

The full ground-truth Twitter corpora are published in [`/dataset`](dataset/).

## Manage

Built-in guardrails that constrain how Pulse can be used.

| Guardrail | Implementation |
|---|---|
| **VADER as primary sentiment scorer** — transparent, lexicon-based, auditable; not a black box | [`backend/app/services/sentiment_scorer.py`](backend/app/services/sentiment_scorer.py) |
| **Rate limiting on all external API calls** prevents abuse at scale | `_with_backoff()` in [`backend/app/services/ingestion_service.py`](backend/app/services/ingestion_service.py) |
| **Outputs labeled as probabilistic predictions, not facts** | Frontend always displays sentiment with confidence ranges |
| **Budget cap in simulation_config** — per-run agent count and round count are user-controlled, preventing runaway LLM spend | [`backend/app/services/simulation_config_generator.py`](backend/app/services/simulation_config_generator.py) |
| **Full reproducibility** — every sim is tagged with provider/model/timestamp; `actions.jsonl` is human-inspectable | Architecturally enforced; see Reproducibility above |
| **Multi-provider model swap** — system supports running the same simulation under Gemini, OpenAI, and Anthropic to detect provider-induced bias | [`backend/app/services/model_factory.py`](backend/app/services/model_factory.py) |

---

## Reading guide for graders / auditors

The most direct evidence of NIST compliance lives in:

1. The DOCX writeup (§VI Findings, §VII NIST RMF, §IX Limitations, §XI Honest Assessment)
2. This file (NIST_COMPLIANCE.md)
3. [`LIMITATIONS.md`](LIMITATIONS.md)
4. [`/dataset`](dataset/) (raw Twitter corpora — full audit trail)
5. [`backend/data/experiment_results/aggregate/results.json`](backend/data/experiment_results/aggregate/results.json) (per-cell metrics)

Each new risk surfaced by the experiment (R3, R4, R5) was added to this
document as part of the same commit that produced the experimental evidence.

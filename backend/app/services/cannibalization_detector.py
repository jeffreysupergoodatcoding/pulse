"""
CannibalizationDetector — Chunk 3A.

For each surfaced audience, distinguishes 'genuinely net-new' from
'you're already reaching these people through your existing channels.'

Two signals combined:

  1. Direct author overlap with the target's own corpus
       overlap_pct = |audience_authors ∩ target_authors| / |audience_authors|

  2. (Optional, costs ~$0.001) LLM-rated behavioral similarity
     between the audience's terms+sample posts and the target's
     terms+sample posts. Returns 0..1.

Threshold logic:
  overlap_pct > 0.30   OR  behavioral > 0.70  →  overlap_likely
  overlap_pct > 0.10   OR  behavioral > 0.40  →  lookalike_likely
  else                                          →  net_new

The behavioral check is opt-in. By default we run pure-overlap only.
"""
from __future__ import annotations

import json

from openai import OpenAI

from app.config import Config
from app.models import CannibalizationFlag
from app.utils.logger import get_logger

logger = get_logger("cannibalization_detector")


_BEHAVIOR_PROMPT = """You are scoring how behaviorally similar two online audiences are. Return strict JSON {{"score": 0.0-1.0, "rationale": "<one sentence>"}}.

A score of 1.0 means: same underlying motivation, same purchase context, same decision-making pattern. Score of 0.0 means: totally different population.

AUDIENCE A (the target brand's existing audience)
- Top terms: {a_terms}
- Sample posts: {a_samples}

AUDIENCE B (the surfaced audience we're checking for cannibalization)
- Top terms: {b_terms}
- Sample posts: {b_samples}

Score B's behavioral similarity to A on a 0.0-1.0 scale. JSON only."""


_OVERLAP_HIGH = 0.30
_OVERLAP_LOW = 0.10
_BEHAVIORAL_HIGH = 0.70
_BEHAVIORAL_LOW = 0.40


class CannibalizationDetector:
    def __init__(self, config: type[Config] = Config):
        self.config = config
        try:
            self.client = OpenAI(api_key=config.LLM_API_KEY, base_url=config.LLM_BASE_URL)
        except Exception:
            self.client = None
        self.model = getattr(config, "LLM_MODEL_NAME", "gemini-2.5-flash-lite")

    def detect(
        self,
        audience_authors: set[str],
        target_authors: set[str],
        audience_top_terms: list[str] | None = None,
        target_top_terms: list[str] | None = None,
        audience_sample_posts: list[str] | None = None,
        target_sample_posts: list[str] | None = None,
        use_llm: bool = False,
    ) -> CannibalizationFlag:
        # 1. Author overlap (always)
        if audience_authors:
            overlap_pct = len(audience_authors & target_authors) / len(audience_authors)
        else:
            overlap_pct = 0.0

        # 2. Behavioral similarity (optional)
        behavioral = None
        if use_llm and self.client is not None and audience_top_terms and target_top_terms:
            behavioral = self._llm_behavioral_score(
                audience_top_terms, target_top_terms,
                audience_sample_posts or [], target_sample_posts or [],
            )

        # Threshold logic
        if overlap_pct > _OVERLAP_HIGH or (behavioral is not None and behavioral > _BEHAVIORAL_HIGH):
            label = "overlap_likely"
        elif overlap_pct > _OVERLAP_LOW or (behavioral is not None and behavioral > _BEHAVIORAL_LOW):
            label = "lookalike_likely"
        else:
            label = "net_new"

        # Interpretation
        parts: list[str] = []
        parts.append(f"{overlap_pct*100:.0f}% of this audience already appears in the target's corpus")
        if behavioral is not None:
            parts.append(f"behavioral similarity {behavioral:.2f}")
        if label == "overlap_likely":
            parts.append("Likely already reached through existing channels.")
        elif label == "lookalike_likely":
            parts.append("Likely captured by lookalike audiences from your current converters.")
        else:
            parts.append("Genuinely net-new audience.")

        return CannibalizationFlag(
            label=label,
            overlap_pct=round(overlap_pct, 4),
            behavioral_similarity=behavioral,
            interpretation=" — ".join(parts),
            used_llm=behavioral is not None,
        )

    def _llm_behavioral_score(
        self,
        a_terms: list[str], b_terms: list[str],
        a_samples: list[str], b_samples: list[str],
    ) -> float | None:
        if self.client is None:
            return None
        prompt = _BEHAVIOR_PROMPT.format(
            a_terms=", ".join(a_terms[:10]),
            a_samples="\n".join(f"- {s}" for s in a_samples[:5]) or "(none)",
            b_terms=", ".join(b_terms[:10]),
            b_samples="\n".join(f"- {s}" for s in b_samples[:5]) or "(none)",
        )
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.1,
            )
            raw = (resp.choices[0].message.content or "{}").strip()
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                parsed = parsed[0] if parsed else {}
            v = float(parsed.get("score", 0.0))
            return max(0.0, min(1.0, v))
        except Exception as exc:
            logger.warning(f"behavioral score LLM call failed: {exc}")
            return None


cannibalization_detector = CannibalizationDetector(Config)

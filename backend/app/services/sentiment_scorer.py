"""
SentimentScorer — LLM + VADER dual-mode sentiment analysis.

Mode is controlled by Config.SENTIMENT_SCORER_MODE:
  "vader"  — fast, offline, no API cost (default)
  "llm"    — OpenAI-compatible LLM with VADER fallback on failure
"""
from __future__ import annotations

import json
from typing import TypedDict

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from app.config import Config
from app.utils.logger import get_logger

logger = get_logger("sentiment_scorer")

# Implicit sentiment for action types that carry no text content
_ACTION_IMPLICIT: dict[str, tuple[float, str, float]] = {
    "like_post":           ( 0.6, "joy",      0.80),
    "like_comment":        ( 0.6, "joy",      0.80),
    "repost":              ( 0.4, "joy",      0.70),
    "follow":              ( 0.3, "joy",      0.70),
    "dislike_post":        (-0.6, "disgust",  0.80),
    "dislike_comment":     (-0.6, "disgust",  0.80),
    "unlike_comment":      ( 0.0, "neutral",  0.60),
    "undo_dislike_comment":( 0.0, "neutral",  0.60),
    "do_nothing":          ( 0.0, "neutral",  1.00),
    "error":               ( 0.0, "neutral",  0.50),
    "inject":              ( 0.0, "neutral",  0.50),
}

_LLM_SYSTEM_PROMPT = (
    "You are a sentiment analysis engine. "
    "Given a social media action type and its content, return JSON with keys: "
    "sentiment_score (float -1.0 to 1.0, negative=negative, 0=neutral, positive=positive), "
    "emotion (one of: joy, anger, fear, disgust, surprise, neutral), "
    "confidence (float 0.0 to 1.0)."
)


class ScoreResult(TypedDict):
    sentiment_score: float   # -1.0 to 1.0
    emotion: str             # joy|anger|fear|disgust|surprise|neutral
    confidence: float        # 0.0 to 1.0


def _vader_emotion(compound: float) -> str:
    if compound >= 0.5:
        return "joy"
    if compound >= 0.1:
        return "surprise"
    if compound >= -0.1:
        return "neutral"
    if compound >= -0.5:
        return "disgust"
    return "anger"


class SentimentScorer:
    def __init__(self, config: type[Config] = Config):
        self._mode = getattr(config, "SENTIMENT_SCORER_MODE", "vader")
        self._vader = SentimentIntensityAnalyzer()
        self._llm = None
        self._model = None
        if self._mode == "llm":
            try:
                from openai import OpenAI
                self._llm = OpenAI(
                    api_key=config.LLM_API_KEY,
                    base_url=config.LLM_BASE_URL,
                )
                self._model = config.LLM_MODEL_NAME
            except Exception as exc:
                logger.warning(f"LLM init failed, falling back to VADER: {exc}")
                self._mode = "vader"

    def score(self, action: dict) -> ScoreResult:
        """Score a single action record. Returns sentiment_score, emotion, confidence."""
        action_type = action.get("action_type", "")
        # Content may be nested under action_args or top-level
        content = (
            (action.get("action_args") or {}).get("content")
            or action.get("content")
            or ""
        )
        content = (content or "").strip()

        # No text: use implicit sentiment mapping
        if not content:
            if action_type in _ACTION_IMPLICIT:
                score, emotion, conf = _ACTION_IMPLICIT[action_type]
                return {"sentiment_score": score, "emotion": emotion, "confidence": conf}
            return {"sentiment_score": 0.0, "emotion": "neutral", "confidence": 0.5}

        if self._mode == "llm" and self._llm:
            return self._score_llm(content, action_type)
        return self._score_vader(content)

    def score_batch(self, actions: list[dict]) -> list[ScoreResult]:
        """Score a list of action records."""
        return [self.score(a) for a in actions]

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _score_vader(self, text: str) -> ScoreResult:
        scores = self._vader.polarity_scores(text)
        compound = scores["compound"]
        emotion = _vader_emotion(compound)
        # Confidence: higher when compound is further from 0
        confidence = round(min(1.0, 0.5 + abs(compound) * 0.5), 4)
        return {
            "sentiment_score": round(compound, 4),
            "emotion": emotion,
            "confidence": confidence,
        }

    def _score_llm(self, text: str, action_type: str) -> ScoreResult:
        try:
            resp = self._llm.chat.completions.create(
                model=self._model,
                temperature=0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _LLM_SYSTEM_PROMPT},
                    {"role": "user", "content": f"action_type: {action_type}\ncontent: {text}"},
                ],
            )
            data = json.loads(resp.choices[0].message.content)
            return {
                "sentiment_score": round(float(data.get("sentiment_score", 0.0)), 4),
                "emotion": str(data.get("emotion", "neutral")),
                "confidence": round(float(data.get("confidence", 0.7)), 4),
            }
        except Exception as exc:
            logger.warning(f"LLM scoring failed, falling back to VADER: {exc}")
            return self._score_vader(text)


sentiment_scorer = SentimentScorer(Config)

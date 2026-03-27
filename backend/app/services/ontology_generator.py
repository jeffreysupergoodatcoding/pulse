"""
OntologyGenerator — Module 2 (GraphRAG)

LLM JSON-mode extraction of entities, relationships, and sentiment
from social media post batches. Uses OpenAI-compatible client (Gemini).

Prompt template from PRD Appendix B.1.
"""
from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from app.config import Config
from app.utils.logger import get_logger

logger = get_logger("ontology_generator")

_EXTRACTION_PROMPT = """Extract all entities and relationships from the following social media posts about {entity_name}.
Return a JSON object with:
- entities: list of {{name, type, properties}}
- relationships: list of {{source, relation, target}}
- sentiment: overall sentiment toward {entity_name} (positive/negative/neutral)
- sentiment_score: float from -1.0 (very negative) to 1.0 (very positive)
- key_topics: list of topics mentioned

Entity types: Brand, Person, Influencer, Event, Topic, Community, Product
Relation types: MENTIONS, CRITICIZES, PRAISES, RELATED_TO, POSTED_BY, PART_OF, COMPETES_WITH

Posts:
{posts_text}

Return only valid JSON, no markdown."""


class OntologyGenerator:
    """
    Extracts structured ontology from social media post batches via LLM.
    Batches up to 20 posts per call to reduce API cost (per PRD Section 9.2).
    """

    BATCH_SIZE = 20

    def __init__(self, config: type[Config] = Config):
        self.client = OpenAI(
            api_key=config.LLM_API_KEY,
            base_url=config.LLM_BASE_URL,
        )
        self.model = config.LLM_MODEL_NAME

    def extract(self, entity_name: str, posts: list[str]) -> dict[str, Any]:
        """
        Extract ontology from a list of post content strings.
        Returns merged result across all batches.
        """
        all_entities: list[dict] = []
        all_relationships: list[dict] = []
        all_topics: list[str] = []
        sentiment_scores: list[float] = []

        for i in range(0, len(posts), self.BATCH_SIZE):
            batch = posts[i : i + self.BATCH_SIZE]
            result = self._extract_batch(entity_name, batch)
            all_entities.extend(result.get("entities", []))
            all_relationships.extend(result.get("relationships", []))
            all_topics.extend(result.get("key_topics", []))
            score = result.get("sentiment_score")
            if isinstance(score, (int, float)):
                sentiment_scores.append(float(score))

        avg_score = (
            sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0.0
        )
        sentiment = (
            "positive" if avg_score > 0.1
            else "negative" if avg_score < -0.1
            else "neutral"
        )

        return {
            "entities": _dedupe_entities(all_entities),
            "relationships": all_relationships,
            "sentiment": sentiment,
            "sentiment_score": round(avg_score, 4),
            "key_topics": list(dict.fromkeys(all_topics)),  # dedupe, preserve order
        }

    def _extract_batch(self, entity_name: str, posts: list[str]) -> dict[str, Any]:
        posts_text = "\n---\n".join(
            f"[{i+1}] {p[:500]}" for i, p in enumerate(posts)
        )
        prompt = _EXTRACTION_PROMPT.format(
            entity_name=entity_name,
            posts_text=posts_text,
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.1,
            )
            raw = response.choices[0].message.content or "{}"
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error(f"OntologyGenerator JSON parse error: {exc}")
            return {"entities": [], "relationships": [], "key_topics": [], "sentiment_score": 0.0}
        except Exception as exc:
            logger.error(f"OntologyGenerator LLM error: {exc}")
            return {"entities": [], "relationships": [], "key_topics": [], "sentiment_score": 0.0}


def _dedupe_entities(entities: list[dict]) -> list[dict]:
    """Merge duplicate entity names (case-insensitive), keeping first occurrence."""
    seen: dict[str, dict] = {}
    for e in entities:
        key = e.get("name", "").lower()
        if key and key not in seen:
            seen[key] = e
    return list(seen.values())


# Module-level singleton
ontology_generator = OntologyGenerator(Config)

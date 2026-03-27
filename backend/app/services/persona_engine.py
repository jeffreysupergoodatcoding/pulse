"""
Persona Engine — Module 3

Generates demographically calibrated OasisAgentProfile objects from real
community data. Three-stage pipeline:
  1. collect_community_corpus  — reads PostRecords from ingestion queue
  2. cluster_archetypes        — embed + k-means → behavioral archetypes
  3. generate_profiles         — LLM persona generation per archetype

Prompt template from PRD Appendix B.2 / Section 7.4.
"""
from __future__ import annotations

import json
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from openai import OpenAI
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.config import Config
from app.models import OasisAgentProfile
from app.utils.logger import get_logger

logger = get_logger("persona_engine")

_PERSONA_PROMPT = """You are generating social media user profiles for a sentiment simulation.
Community: {community_name} | Entity: {entity_name}
Archetype: users who {cluster_description}
Opinion bias: {pct_pos}% positive, {pct_neg}% negative toward {entity_name}
Average engagement: {avg_engagement} likes/upvotes

Sample posts from this archetype:
{sample_posts}

Top vocabulary: {top_terms}

Generate {n} distinct agent profiles as a JSON array. Each profile must have:
- name: realistic username style for this community
- age: integer, realistic for this archetype
- bio: 1-2 sentence description of this user type
- persona_text: detailed behavioral description including posting style, opinion tendencies, reaction triggers, vocabulary, things they would say about {entity_name}
- initial_opinions: object with "{entity_name}": float (-1.0 to 1.0), plus 2-3 relevant topic keys
- mbti: inferred MBTI string e.g. "INTJ"
- activity_level: one of "low", "medium", "high"
- influence_tier: one of "regular", "power_user", "lurker"
- social_connections: empty array

Return only a valid JSON array, no markdown, no explanation."""


class PersonaEngine:
    def __init__(self, config: type[Config] = Config):
        self.config = config
        self.llm = OpenAI(api_key=config.LLM_API_KEY, base_url=config.LLM_BASE_URL)
        self.model = config.LLM_MODEL_NAME
        self.embed_model = config.LLM_EMBEDDING_MODEL

    # ------------------------------------------------------------------
    # Stage 1: Corpus collection
    # ------------------------------------------------------------------

    def collect_community_corpus(
        self, entity_id: str, n: int = 1000
    ) -> list[dict]:
        """
        Read up to n PostRecords from the entity's ingestion queue.
        Returns list of raw dicts with content + engagement fields.
        """
        ingestion_dir = (
            Path(self.config.ENTITIES_DIR) / entity_id / "ingestion"
        )
        if not ingestion_dir.exists():
            return []

        records: list[dict] = []
        for jsonl_file in sorted(ingestion_dir.glob("posts_*.jsonl"), reverse=True):
            with jsonl_file.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                        if r.get("content", "").strip():
                            records.append(r)
                    except json.JSONDecodeError:
                        pass
                    if len(records) >= n:
                        break
            if len(records) >= n:
                break

        logger.info(f"Collected {len(records)} corpus posts for entity {entity_id}")
        return records[:n]

    # ------------------------------------------------------------------
    # Stage 2: Archetype clustering
    # ------------------------------------------------------------------

    def cluster_archetypes(
        self, corpus: list[dict], n_clusters: int = 8
    ) -> list[dict]:
        """
        Embed posts, k-means cluster, return archetype summaries.
        Each archetype: {id, description, posts, opinion_dist, avg_engagement, top_terms, size}
        """
        if not corpus:
            return []

        # Clamp clusters to corpus size
        n_clusters = min(n_clusters, len(corpus))
        contents = [r.get("content", "") for r in corpus]

        logger.info(f"Embedding {len(contents)} posts with {self.embed_model}")
        embeddings = self._embed_batch(contents)
        if embeddings is None or len(embeddings) == 0:
            logger.error("Embedding failed — cannot cluster")
            return []

        emb_array = np.array(embeddings)

        logger.info(f"K-means clustering into {n_clusters} archetypes")
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        labels = kmeans.fit_predict(emb_array)

        # Build archetype summaries
        archetypes: list[dict] = []
        for cluster_id in range(n_clusters):
            cluster_indices = [i for i, l in enumerate(labels) if l == cluster_id]
            if not cluster_indices:
                continue

            cluster_posts = [corpus[i] for i in cluster_indices]
            cluster_contents = [corpus[i].get("content", "") for i in cluster_indices]

            # Representative posts: closest to centroid
            centroid = kmeans.cluster_centers_[cluster_id]
            cluster_embs = emb_array[cluster_indices]
            sims = cosine_similarity([centroid], cluster_embs)[0]
            top_idx = np.argsort(sims)[::-1][:10]
            representative_posts = [cluster_contents[i] for i in top_idx]

            # Opinion distribution (naive: positive words vs negative)
            pos_count = sum(1 for p in cluster_contents if _is_positive(p))
            neg_count = sum(1 for p in cluster_contents if _is_negative(p))
            total = len(cluster_contents)
            pct_pos = round(pos_count / total * 100)
            pct_neg = round(neg_count / total * 100)
            pct_neu = 100 - pct_pos - pct_neg

            # Average engagement
            engagements = [
                sum(p.get("engagement", {}).values())
                for p in cluster_posts
                if p.get("engagement")
            ]
            avg_engagement = round(sum(engagements) / len(engagements)) if engagements else 0

            # Top vocabulary (TF-IDF)
            top_terms = _top_tfidf_terms(cluster_contents, n=20)

            # Generate a brief cluster description from top terms + opinion
            sentiment_label = (
                "positive" if pct_pos > pct_neg else
                "negative" if pct_neg > pct_pos else
                "mixed"
            )
            description = (
                f"post {sentiment_label} content about the entity, "
                f"using terms like: {', '.join(top_terms[:5])}"
            )

            archetypes.append({
                "id": f"archetype_{cluster_id}",
                "cluster_id": cluster_id,
                "size": len(cluster_indices),
                "description": description,
                "representative_posts": representative_posts,
                "pct_positive": pct_pos,
                "pct_negative": pct_neg,
                "pct_neutral": pct_neu,
                "avg_engagement": avg_engagement,
                "top_terms": top_terms,
            })

        logger.info(f"Clustered into {len(archetypes)} archetypes")
        return archetypes

    # ------------------------------------------------------------------
    # Stage 3: Profile generation
    # ------------------------------------------------------------------

    def generate_profiles(
        self,
        archetypes: list[dict],
        entity_id: str,
        entity_name: str,
        community_name: str,
        n_agents_per_archetype: int = 12,
    ) -> list[OasisAgentProfile]:
        """
        For each archetype, call LLM to generate n_agents_per_archetype profiles.
        Returns full list of OasisAgentProfile objects.
        """
        all_profiles: list[OasisAgentProfile] = []

        for archetype in archetypes:
            logger.info(
                f"Generating {n_agents_per_archetype} profiles for {archetype['id']}"
            )
            raw_profiles = self._generate_archetype_profiles(
                archetype=archetype,
                entity_name=entity_name,
                community_name=community_name,
                n=n_agents_per_archetype,
            )
            for raw in raw_profiles:
                try:
                    profile = OasisAgentProfile(
                        user_id=str(uuid.uuid4()),
                        name=raw.get("name", f"user_{uuid.uuid4().hex[:6]}"),
                        persona_text=raw.get("persona_text", ""),
                        bio=raw.get("bio", ""),
                        age=int(raw.get("age", 25)),
                        mbti=raw.get("mbti", "INFP"),
                        initial_opinions=raw.get("initial_opinions", {}),
                        social_relationships=raw.get("social_connections", []),
                        activity_level=raw.get("activity_level", "medium"),
                        influence_tier=raw.get("influence_tier", "regular"),
                        archetype_id=archetype["id"],
                    )
                    all_profiles.append(profile)
                except Exception as exc:
                    logger.warning(f"Profile parse error: {exc} | raw={raw}")

        logger.info(f"Generated {len(all_profiles)} total profiles")
        return all_profiles

    # ------------------------------------------------------------------
    # Orchestration: full pipeline
    # ------------------------------------------------------------------

    def run(
        self,
        entity_id: str,
        entity_name: str,
        community_name: str,
        n_clusters: int = 8,
        n_agents_per_archetype: int = 12,
        task=None,
    ) -> str:
        """
        Full pipeline: corpus → cluster → profiles → persist.
        Returns the persona_set_id.
        """

        def _progress(pct: int):
            if task:
                from app.utils.task_manager import task_manager
                task_manager.update(task.task_id, progress=pct)

        _progress(5)
        corpus = self.collect_community_corpus(entity_id)

        _progress(20)
        archetypes = self.cluster_archetypes(corpus, n_clusters)

        _progress(50)
        profiles = self.generate_profiles(
            archetypes, entity_id, entity_name, community_name, n_agents_per_archetype
        )

        _progress(90)
        set_id = self._persist(entity_id, archetypes, profiles, corpus)
        _progress(100)
        return set_id

    # ------------------------------------------------------------------
    # Template-based generation (no corpus needed)
    # ------------------------------------------------------------------

    def from_template(self, entity_id: str, template_id: str) -> str:
        """
        Load a built-in template and adapt it for the given entity.
        Returns persona_set_id.
        """
        template_path = (
            Path(self.config.BASE_DIR) / "data" / "templates" / f"{template_id}.json"
        )
        if not template_path.exists():
            raise ValueError(f"Template {template_id} not found")

        data = json.loads(template_path.read_text())
        profiles_data: list[dict] = data.get("profiles", [])
        profiles = []
        for raw in profiles_data:
            raw["user_id"] = str(uuid.uuid4())
            try:
                profiles.append(OasisAgentProfile.model_validate(raw))
            except Exception as exc:
                logger.warning(f"Template profile parse error: {exc}")

        archetypes = data.get("archetypes", [])
        set_id = self._persist(entity_id, archetypes, profiles, [])
        logger.info(f"Created persona set {set_id} from template {template_id}")
        return set_id

    def list_templates(self) -> list[dict]:
        templates_dir = Path(self.config.BASE_DIR) / "data" / "templates"
        templates_dir.mkdir(parents=True, exist_ok=True)
        result = []
        for f in templates_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                result.append({
                    "id": f.stem,
                    "name": data.get("name", f.stem),
                    "description": data.get("description", ""),
                    "n_profiles": len(data.get("profiles", [])),
                })
            except Exception:
                pass
        return result

    def list_persona_sets(self, entity_id: str) -> list[dict]:
        personas_dir = (
            Path(self.config.ENTITIES_DIR) / entity_id / "personas"
        )
        if not personas_dir.exists():
            return []
        sets = []
        for set_dir in personas_dir.iterdir():
            if not set_dir.is_dir():
                continue
            meta_path = set_dir / "corpus_stats.json"
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text())
                    sets.append({
                        "set_id": set_dir.name,
                        "entity_id": entity_id,
                        "n_profiles": meta.get("n_profiles", 0),
                        "n_archetypes": meta.get("n_archetypes", 0),
                        "created_at": meta.get("created_at", ""),
                    })
                except Exception:
                    sets.append({"set_id": set_dir.name, "entity_id": entity_id})
        return sets

    def get_persona_set(self, entity_id: str, set_id: str) -> dict:
        base = Path(self.config.ENTITIES_DIR) / entity_id / "personas" / set_id
        archetypes = json.loads((base / "archetypes.json").read_text()) if (base / "archetypes.json").exists() else []
        profiles_raw = json.loads((base / "profiles.json").read_text()) if (base / "profiles.json").exists() else []
        return {"archetypes": archetypes, "profiles": profiles_raw}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _embed_batch(self, texts: list[str]) -> list[list[float]] | None:
        """Embed texts in batches of 100 (API limit)."""
        all_embeddings = []
        batch_size = 100
        for i in range(0, len(texts), batch_size):
            batch = [t[:2000] for t in texts[i : i + batch_size]]
            try:
                resp = self.llm.embeddings.create(model=self.embed_model, input=batch)
                all_embeddings.extend([d.embedding for d in resp.data])
            except Exception as exc:
                logger.error(f"Embedding batch {i} failed: {exc}")
                # Fill with zeros for failed batch so indices stay aligned
                all_embeddings.extend([[0.0] * 3072] * len(batch))
        return all_embeddings

    def _generate_archetype_profiles(
        self,
        archetype: dict,
        entity_name: str,
        community_name: str,
        n: int,
    ) -> list[dict]:
        sample_posts = "\n".join(
            f"- {p[:200]}" for p in archetype["representative_posts"][:10]
        )
        prompt = _PERSONA_PROMPT.format(
            community_name=community_name,
            entity_name=entity_name,
            cluster_description=archetype["description"],
            pct_pos=archetype["pct_positive"],
            pct_neg=archetype["pct_negative"],
            avg_engagement=archetype["avg_engagement"],
            sample_posts=sample_posts,
            top_terms=", ".join(archetype["top_terms"][:15]),
            n=n,
        )
        try:
            resp = self.llm.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.8,
            )
            raw = resp.choices[0].message.content or "[]"
            parsed = json.loads(raw)
            # Handle both {"profiles": [...]} and plain array
            if isinstance(parsed, dict):
                return parsed.get("profiles", list(parsed.values())[0] if parsed else [])
            return parsed if isinstance(parsed, list) else []
        except Exception as exc:
            logger.error(f"Profile generation failed for {archetype['id']}: {exc}")
            return []

    def _persist(
        self,
        entity_id: str,
        archetypes: list[dict],
        profiles: list[OasisAgentProfile],
        corpus: list[dict],
    ) -> str:
        set_id = str(uuid.uuid4())
        base = Path(self.config.ENTITIES_DIR) / entity_id / "personas" / set_id
        base.mkdir(parents=True, exist_ok=True)

        (base / "archetypes.json").write_text(
            json.dumps(archetypes, indent=2, default=str)
        )
        profiles_data = [p.model_dump(mode="json") for p in profiles]
        (base / "profiles.json").write_text(
            json.dumps(profiles_data, indent=2, default=str)
        )

        stats = {
            "set_id": set_id,
            "entity_id": entity_id,
            "n_profiles": len(profiles),
            "n_archetypes": len(archetypes),
            "corpus_size": len(corpus),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        (base / "corpus_stats.json").write_text(json.dumps(stats, indent=2))

        logger.info(f"Persisted persona set {set_id}: {len(profiles)} profiles, {len(archetypes)} archetypes")
        return set_id


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

_POS_WORDS = {"great","good","love","best","amazing","excellent","fire","clean","nice","perfect","worth","win","wins","incredible"}
_NEG_WORDS = {"bad","hate","worst","terrible","overpriced","expensive","ridiculous","trash","awful","poor","waste","disappointed"}

def _is_positive(text: str) -> bool:
    t = text.lower()
    return any(w in t for w in _POS_WORDS)

def _is_negative(text: str) -> bool:
    t = text.lower()
    return any(w in t for w in _NEG_WORDS)

def _top_tfidf_terms(texts: list[str], n: int = 20) -> list[str]:
    if not texts:
        return []
    try:
        vec = TfidfVectorizer(
            max_features=200,
            stop_words="english",
            ngram_range=(1, 2),
            min_df=1,
        )
        vec.fit(texts)
        # Sum TF-IDF scores across all docs in cluster
        matrix = vec.transform(texts)
        scores = np.asarray(matrix.sum(axis=0)).flatten()
        top_indices = scores.argsort()[::-1][:n]
        terms = vec.get_feature_names_out()
        return [terms[i] for i in top_indices]
    except Exception:
        return []


# Module-level singleton
persona_engine = PersonaEngine(Config)

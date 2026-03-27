"""
CorpusDriftDetector — detects when new ingested posts diverge from the
corpus used to build the current persona set, then triggers a background
persona refresh.

Drift metric: Jaccard similarity of top-N vocabulary between the current
persona corpus and the new posts accumulated since the last persona build.
If similarity drops below DRIFT_THRESHOLD, a refresh is enqueued.

Usage: called after each ingestion pull completes (from ingestion_routes.py).
"""
from __future__ import annotations

import json
import re
import threading
from collections import Counter
from pathlib import Path

from app.config import Config
from app.utils.logger import get_logger

logger = get_logger("corpus_drift_detector")

DRIFT_THRESHOLD = 0.65      # Jaccard similarity below this → refresh
MIN_NEW_POSTS = 50          # Don't trigger on tiny ingestion batches
TOP_N_VOCAB = 200           # Number of top words used for similarity


def _tokenize(text: str) -> list[str]:
    """Simple lowercased word tokenizer, strips punctuation."""
    return re.findall(r"[a-z]{3,}", text.lower())


def _top_vocab(texts: list[str], n: int = TOP_N_VOCAB) -> set[str]:
    counter: Counter = Counter()
    for t in texts:
        counter.update(_tokenize(t))
    # Remove very common stopwords
    stopwords = {"the", "and", "for", "that", "this", "with", "are", "was",
                 "has", "have", "been", "its", "not", "but", "they", "from"}
    for sw in stopwords:
        del counter[sw]
    return {w for w, _ in counter.most_common(n)}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class CorpusDriftDetector:
    def __init__(self, config: type[Config] = Config):
        self._config = config
        self._entities_dir = Path(config.ENTITIES_DIR)
        self._lock = threading.Lock()
        # Track in-progress refresh to avoid duplicate triggers
        self._refreshing: set[str] = set()

    def check_and_refresh(self, entity_id: str, new_post_count: int) -> bool:
        """
        Call this after a completed ingestion pull.

        Returns True if a persona refresh was triggered.
        """
        if new_post_count < MIN_NEW_POSTS:
            logger.debug(
                f"[drift:{entity_id}] {new_post_count} new posts < {MIN_NEW_POSTS} minimum — skipping drift check"
            )
            return False

        with self._lock:
            if entity_id in self._refreshing:
                logger.debug(f"[drift:{entity_id}] Refresh already in progress — skipping")
                return False

        similarity = self._compute_similarity(entity_id)
        logger.info(f"[drift:{entity_id}] Corpus similarity: {similarity:.3f} (threshold: {DRIFT_THRESHOLD})")

        if similarity >= DRIFT_THRESHOLD:
            return False

        logger.info(
            f"[drift:{entity_id}] Drift detected (similarity={similarity:.3f}) — "
            "triggering background persona refresh"
        )
        self._trigger_refresh(entity_id)
        return True

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _compute_similarity(self, entity_id: str) -> float:
        """
        Compare vocabulary of:
          - current persona corpus (texts used when personas were last generated)
          - recent ingestion queue posts (last 7 days)
        """
        persona_texts = self._load_persona_corpus(entity_id)
        new_texts = self._load_recent_posts(entity_id, days=7)

        if not persona_texts or not new_texts:
            # Can't compare — assume no drift
            return 1.0

        vocab_personas = _top_vocab(persona_texts)
        vocab_new = _top_vocab(new_texts)
        return _jaccard(vocab_personas, vocab_new)

    def _load_persona_corpus(self, entity_id: str) -> list[str]:
        """
        Load the text corpus from the most recent persona set's corpus snapshot.
        Falls back to all ingestion posts if no snapshot exists.
        """
        entity_dir = self._entities_dir / entity_id
        corpus_path = entity_dir / "persona_corpus_snapshot.json"
        if corpus_path.exists():
            try:
                data = json.loads(corpus_path.read_text())
                return data if isinstance(data, list) else []
            except Exception:
                pass

        # Fallback: all ingestion posts
        return self._load_posts_from_dir(entity_dir / "ingestion", limit=500)

    def _load_recent_posts(self, entity_id: str, days: int = 7) -> list[str]:
        from datetime import datetime, timedelta, timezone
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        entity_dir = self._entities_dir / entity_id / "ingestion"
        if not entity_dir.exists():
            return []

        texts: list[str] = []
        for path in sorted(entity_dir.glob("posts_*.jsonl"), reverse=True):
            with path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        content = record.get("content", "")
                        if content:
                            texts.append(content)
                    except json.JSONDecodeError:
                        pass
            if len(texts) >= 500:
                break
        return texts

    def _load_posts_from_dir(self, ingestion_dir: Path, limit: int = 500) -> list[str]:
        if not ingestion_dir.exists():
            return []
        texts: list[str] = []
        for path in sorted(ingestion_dir.glob("posts_*.jsonl"), reverse=True):
            with path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        try:
                            record = json.loads(line)
                            content = record.get("content", "")
                            if content:
                                texts.append(content)
                        except json.JSONDecodeError:
                            pass
            if len(texts) >= limit:
                break
        return texts[:limit]

    def _trigger_refresh(self, entity_id: str):
        """Kick off persona re-generation in a background thread."""
        with self._lock:
            self._refreshing.add(entity_id)

        def _run():
            try:
                from app.services.persona_engine import persona_engine
                logger.info(f"[drift:{entity_id}] Starting background persona refresh")
                persona_engine.generate(entity_id)
                logger.info(f"[drift:{entity_id}] Background persona refresh complete")
                # Snapshot the new corpus so next drift check has an updated baseline
                self._snapshot_corpus(entity_id)
            except Exception as exc:
                logger.error(f"[drift:{entity_id}] Background persona refresh failed: {exc}")
            finally:
                with self._lock:
                    self._refreshing.discard(entity_id)

        threading.Thread(target=_run, daemon=True, name=f"drift-refresh-{entity_id}").start()

    def _snapshot_corpus(self, entity_id: str):
        """Save current ingestion posts as the new corpus baseline."""
        texts = self._load_posts_from_dir(
            self._entities_dir / entity_id / "ingestion", limit=500
        )
        if texts:
            snapshot_path = self._entities_dir / entity_id / "persona_corpus_snapshot.json"
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            snapshot_path.write_text(json.dumps(texts))
            logger.debug(f"[drift:{entity_id}] Corpus snapshot saved ({len(texts)} texts)")


corpus_drift_detector = CorpusDriftDetector(Config)

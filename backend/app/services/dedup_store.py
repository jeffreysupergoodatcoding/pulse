"""
SQLite-backed deduplication store.
Prevents the same post from being added to the knowledge graph twice
across multiple ingestion runs.

Table: ingested_ids(platform TEXT, platform_id TEXT, entity_id TEXT, ingested_at DATETIME)
"""
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.utils.logger import get_logger

logger = get_logger("dedup_store")


class DedupStore:
    """Thread-safe SQLite deduplication store."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ingested_ids (
                    platform    TEXT NOT NULL,
                    platform_id TEXT NOT NULL,
                    entity_id   TEXT NOT NULL,
                    ingested_at TEXT NOT NULL,
                    PRIMARY KEY (platform, platform_id)
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_entity ON ingested_ids(entity_id)"
            )
            conn.commit()
        logger.debug(f"DedupStore initialized at {self.db_path}")

    def is_seen(self, platform: str, platform_id: str) -> bool:
        """Return True if this (platform, platform_id) has already been ingested."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM ingested_ids WHERE platform=? AND platform_id=?",
                (platform, platform_id),
            ).fetchone()
        return row is not None

    def mark_seen(self, platform: str, platform_id: str, entity_id: str):
        """Record that this post has been ingested."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO ingested_ids (platform, platform_id, entity_id, ingested_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (platform, platform_id, entity_id, now),
                )
                conn.commit()

    def filter_new(
        self, records: list[tuple[str, str]]
    ) -> list[tuple[str, str]]:
        """
        Given a list of (platform, platform_id) tuples, return only those
        not yet in the store.
        """
        return [r for r in records if not self.is_seen(r[0], r[1])]

    def count(self, entity_id: str | None = None) -> int:
        with self._connect() as conn:
            if entity_id:
                return conn.execute(
                    "SELECT COUNT(*) FROM ingested_ids WHERE entity_id=?", (entity_id,)
                ).fetchone()[0]
            return conn.execute("SELECT COUNT(*) FROM ingested_ids").fetchone()[0]

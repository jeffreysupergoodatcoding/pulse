"""
GraphBuilderService — Module 2 (GraphRAG)

Consumes the ingestion queue (JSONL files), runs OntologyGenerator,
writes episodes to Zep Cloud graph, and maintains a local SQLite cache
of nodes/edges for D3.js rendering.

Zep Cloud 3.x API used:
  client.graph.create(graph_id=...)
  client.graph.add(data=..., type="text", graph_id=...)
  client.graph.search(query=..., graph_id=..., limit=...)
  client.graph.node.get_by_graph_id(graph_id=...)
  client.graph.edge.get_by_graph_id(graph_id=...)
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from zep_cloud.client import Zep

from app.config import Config
from app.models import PostRecord
from app.services.entity_store import entity_store
from app.services.ontology_generator import ontology_generator
from app.utils.logger import get_logger

logger = get_logger("graph_builder_service")

_EMA_ALPHA = 0.3   # exponential moving average weight for sentiment updates


class GraphBuilderService:
    """
    Reads queued PostRecords, extracts ontology via LLM, writes to Zep.
    Maintains a local SQLite graph cache for fast D3 rendering.
    """

    def __init__(self, config: type[Config] = Config):
        self.config = config
        self.zep = Zep(api_key=config.ZEP_API_KEY)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public: build graph for an entity
    # ------------------------------------------------------------------

    def build(self, entity_id: str, task=None) -> dict:
        """
        Main entry point called by POST /api/graph/build.
        Reads all unprocessed queue files and populates Zep graph.
        Returns summary stats.
        """
        entity = entity_store.get(entity_id)
        if not entity:
            raise ValueError(f"Entity {entity_id} not found")

        # Ensure Zep graph exists for this entity
        graph_id = self._ensure_graph(entity_id, entity.name)
        entity.graph_id = graph_id
        entity_store.update(entity)

        # Ensure local SQLite graph cache exists
        self._init_graph_db(entity_id)

        # Read all PostRecords from queue
        records = self._read_all_queue_records(entity_id)
        if not records:
            logger.info(f"No queue records found for entity {entity_id}")
            return {"nodes_added": 0, "edges_added": 0, "episodes_added": 0}

        logger.info(f"Building graph for {entity.name}: {len(records)} posts to process")

        if task:
            from app.utils.task_manager import task_manager
            task_manager.update(task.task_id, progress=10)

        # Extract ontology from all posts
        post_contents = [r.get("content", "") for r in records if r.get("content")]
        ontology = ontology_generator.extract(entity.name, post_contents)

        if task:
            from app.utils.task_manager import task_manager
            task_manager.update(task.task_id, progress=50)

        # Write episodes to Zep (batch by 20)
        episodes_added = self._write_episodes_to_zep(graph_id, records, entity_id)

        if task:
            from app.utils.task_manager import task_manager
            task_manager.update(task.task_id, progress=80)

        # Store extracted nodes/edges in local SQLite for D3
        nodes_added = self._store_nodes(entity_id, entity.name, ontology)
        edges_added = self._store_edges(entity_id, ontology)

        # Update entity sentiment (EMA)
        self._update_entity_sentiment(entity_id, ontology["sentiment_score"])

        # Store ontology topics
        self._store_topics(entity_id, ontology["key_topics"])

        summary = {
            "nodes_added": nodes_added,
            "edges_added": edges_added,
            "episodes_added": episodes_added,
            "sentiment_score": ontology["sentiment_score"],
            "sentiment": ontology["sentiment"],
            "key_topics": ontology["key_topics"][:10],
        }
        logger.info(f"Graph build complete for {entity.name}: {summary}")
        return summary

    # ------------------------------------------------------------------
    # Zep operations
    # ------------------------------------------------------------------

    def _ensure_graph(self, entity_id: str, entity_name: str) -> str:
        """Create Zep graph if it doesn't exist; return graph_id."""
        graph_id = f"pulse-{entity_id}"
        try:
            self.zep.graph.get(graph_id)
            logger.debug(f"Zep graph exists: {graph_id}")
        except Exception:
            try:
                self.zep.graph.create(
                    graph_id=graph_id,
                    name=f"Pulse: {entity_name}",
                    description=f"Knowledge graph for entity: {entity_name}",
                )
                logger.info(f"Created Zep graph: {graph_id}")
            except Exception as exc:
                logger.error(f"Failed to create Zep graph {graph_id}: {exc}")
        return graph_id

    def _write_episodes_to_zep(
        self, graph_id: str, records: list[dict], entity_id: str
    ) -> int:
        """Write PostRecords as text episodes to Zep graph."""
        added = 0
        batch_size = 20

        for i in range(0, len(records), batch_size):
            batch = records[i : i + batch_size]
            for record in batch:
                content = record.get("content", "").strip()
                if not content:
                    continue
                try:
                    self.zep.graph.add(
                        data=content[:2000],   # Zep episode size limit
                        type="text",
                        graph_id=graph_id,
                        source_description=f"{record.get('platform','unknown')}:{record.get('id','')}"
                    )
                    added += 1
                except Exception as exc:
                    logger.warning(f"Zep episode add failed: {exc}")

        logger.info(f"Added {added} episodes to Zep graph {graph_id}")
        return added

    def search(self, entity_id: str, query: str, k: int = 10) -> list[dict]:
        """Semantic search of Zep graph for an entity."""
        entity = entity_store.get(entity_id)
        if not entity or not entity.graph_id:
            return []
        try:
            results = self.zep.graph.search(
                query=query,
                graph_id=entity.graph_id,
                limit=k,
                scope="episodes",
            )
            episodes = getattr(results, "episodes", []) or []
            return [
                {
                    "content": getattr(ep, "content", ""),
                    "score": getattr(ep, "score", 0.0),
                    "created_at": str(getattr(ep, "created_at", "")),
                    "source": getattr(ep, "source_description", ""),
                }
                for ep in episodes
            ]
        except Exception as exc:
            logger.error(f"Zep search failed: {exc}")
            return []

    def get_zep_nodes_edges(self, entity_id: str) -> dict:
        """Fetch live nodes and edges from Zep for an entity's graph."""
        entity = entity_store.get(entity_id)
        if not entity or not entity.graph_id:
            return {"nodes": [], "edges": []}
        try:
            raw_nodes = self.zep.graph.node.get_by_graph_id(entity.graph_id, limit=200)
            raw_edges = self.zep.graph.edge.get_by_graph_id(entity.graph_id, limit=500)
            nodes = [
                {
                    "id": getattr(n, "uuid", str(i)),
                    "label": getattr(n, "name", ""),
                    "type": getattr(n, "labels", ["unknown"])[0] if getattr(n, "labels", None) else "unknown",
                    "summary": getattr(n, "summary", ""),
                }
                for i, n in enumerate(raw_nodes or [])
            ]
            edges = [
                {
                    "source": getattr(e, "source_node_uuid", ""),
                    "target": getattr(e, "target_node_uuid", ""),
                    "label": getattr(e, "fact", ""),
                }
                for e in (raw_edges or [])
            ]
            return {"nodes": nodes, "edges": edges}
        except Exception as exc:
            logger.error(f"Zep node/edge fetch failed: {exc}")
            return {"nodes": [], "edges": []}

    # ------------------------------------------------------------------
    # Local SQLite graph cache (for D3 + fast queries)
    # ------------------------------------------------------------------

    def _db_path(self, entity_id: str) -> Path:
        return Path(self.config.ENTITIES_DIR) / entity_id / "graph.db"

    def _init_graph_db(self, entity_id: str):
        db = self._db_path(entity_id)
        db.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(db)) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS nodes (
                    id          TEXT PRIMARY KEY,
                    label       TEXT NOT NULL,
                    type        TEXT NOT NULL,
                    properties  TEXT DEFAULT '{}',
                    updated_at  TEXT
                );
                CREATE TABLE IF NOT EXISTS edges (
                    id          TEXT PRIMARY KEY,
                    source      TEXT NOT NULL,
                    target      TEXT NOT NULL,
                    relation    TEXT NOT NULL,
                    updated_at  TEXT
                );
                CREATE TABLE IF NOT EXISTS entity_sentiment (
                    entity_id   TEXT PRIMARY KEY,
                    score       REAL DEFAULT 0.0,
                    updated_at  TEXT
                );
                CREATE TABLE IF NOT EXISTS topics (
                    entity_id   TEXT NOT NULL,
                    topic       TEXT NOT NULL,
                    PRIMARY KEY (entity_id, topic)
                );
            """)
            conn.commit()

    def _store_nodes(self, entity_id: str, entity_name: str, ontology: dict) -> int:
        db = self._db_path(entity_id)
        now = datetime.now(timezone.utc).isoformat()
        added = 0

        # Always ensure the tracked entity itself is a node
        all_entities = [{"name": entity_name, "type": "Brand", "properties": {}}]
        all_entities.extend(ontology.get("entities", []))

        with sqlite3.connect(str(db)) as conn:
            for ent in all_entities:
                name = ent.get("name", "").strip()
                if not name:
                    continue
                node_id = name.lower().replace(" ", "_")
                props = json.dumps(ent.get("properties", {}))
                conn.execute(
                    """
                    INSERT INTO nodes (id, label, type, properties, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        type=excluded.type, properties=excluded.properties,
                        updated_at=excluded.updated_at
                    """,
                    (node_id, name, ent.get("type", "Unknown"), props, now),
                )
                added += 1
            conn.commit()
        return added

    def _store_edges(self, entity_id: str, ontology: dict) -> int:
        db = self._db_path(entity_id)
        now = datetime.now(timezone.utc).isoformat()
        added = 0

        with sqlite3.connect(str(db)) as conn:
            for rel in ontology.get("relationships", []):
                src = rel.get("source", "").lower().replace(" ", "_")
                tgt = rel.get("target", "").lower().replace(" ", "_")
                relation = rel.get("relation", "RELATED_TO")
                if not src or not tgt:
                    continue
                edge_id = f"{src}_{relation}_{tgt}"
                conn.execute(
                    """
                    INSERT INTO edges (id, source, target, relation, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at
                    """,
                    (edge_id, src, tgt, relation, now),
                )
                added += 1
            conn.commit()
        return added

    def _update_entity_sentiment(self, entity_id: str, new_score: float):
        db = self._db_path(entity_id)
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(str(db)) as conn:
            row = conn.execute(
                "SELECT score FROM entity_sentiment WHERE entity_id=?", (entity_id,)
            ).fetchone()
            if row:
                ema = _EMA_ALPHA * new_score + (1 - _EMA_ALPHA) * row[0]
                conn.execute(
                    "UPDATE entity_sentiment SET score=?, updated_at=? WHERE entity_id=?",
                    (ema, now, entity_id),
                )
            else:
                conn.execute(
                    "INSERT INTO entity_sentiment (entity_id, score, updated_at) VALUES (?,?,?)",
                    (entity_id, new_score, now),
                )
            conn.commit()

    def _store_topics(self, entity_id: str, topics: list[str]):
        db = self._db_path(entity_id)
        with sqlite3.connect(str(db)) as conn:
            for topic in topics:
                conn.execute(
                    "INSERT OR IGNORE INTO topics (entity_id, topic) VALUES (?,?)",
                    (entity_id, topic),
                )
            conn.commit()

    def get_local_graph_data(self, entity_id: str) -> dict:
        """Return nodes/edges from local SQLite for D3 rendering."""
        db = self._db_path(entity_id)
        if not db.exists():
            return {"nodes": [], "edges": []}
        with sqlite3.connect(str(db)) as conn:
            conn.row_factory = sqlite3.Row
            nodes = [dict(r) for r in conn.execute("SELECT * FROM nodes").fetchall()]
            edges = [dict(r) for r in conn.execute("SELECT * FROM edges").fetchall()]
        return {"nodes": nodes, "edges": edges}

    def get_sentiment(self, entity_id: str) -> dict:
        db = self._db_path(entity_id)
        if not db.exists():
            return {"current_score": 0.0, "history": [], "by_source": {}}
        with sqlite3.connect(str(db)) as conn:
            row = conn.execute(
                "SELECT score, updated_at FROM entity_sentiment WHERE entity_id=?",
                (entity_id,),
            ).fetchone()
        if not row:
            return {"current_score": 0.0, "history": [], "by_source": {}}
        return {
            "current_score": row[0],
            "history": [{"score": row[0], "at": row[1]}],
            "by_source": {},
        }

    def get_ontology(self, entity_id: str) -> dict:
        db = self._db_path(entity_id)
        if not db.exists():
            return {"entity_types": [], "relation_types": []}
        with sqlite3.connect(str(db)) as conn:
            entity_types = [
                r[0] for r in conn.execute(
                    "SELECT DISTINCT type FROM nodes ORDER BY type"
                ).fetchall()
            ]
            relation_types = [
                r[0] for r in conn.execute(
                    "SELECT DISTINCT relation FROM edges ORDER BY relation"
                ).fetchall()
            ]
        return {"entity_types": entity_types, "relation_types": relation_types}

    # ------------------------------------------------------------------
    # Queue reader
    # ------------------------------------------------------------------

    def _read_all_queue_records(self, entity_id: str) -> list[dict]:
        """Read all PostRecord JSONL files for an entity."""
        ingestion_dir = Path(self.config.ENTITIES_DIR) / entity_id / "ingestion"
        if not ingestion_dir.exists():
            return []
        records = []
        for jsonl_file in sorted(ingestion_dir.glob("posts_*.jsonl")):
            with jsonl_file.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        try:
                            records.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        return records


# Module-level singleton
graph_builder_service = GraphBuilderService(Config)

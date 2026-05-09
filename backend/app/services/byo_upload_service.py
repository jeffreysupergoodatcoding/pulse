"""
BYOUploadService — Bring-your-own-data ingestion path.

Lets users upload a JSONL or CSV file of social posts instead of paying for API
ingestion. Once uploaded, the data is indistinguishable from API-ingested data
downstream — graph build, persona generation, simulation, audience discovery,
briefs all work identically.

Schema (PostRecord JSON, one per line in JSONL OR one per row in CSV):
  Required: id, content, created_at
  Recommended: platform, author_id (will be SHA-256 anonymized if provided)
  Optional: author_metadata, parent_id, engagement, url, raw

CSV column mapping is supplied by the caller — keys = PostRecord fields,
values = CSV header names.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from app.config import Config
from app.utils.logger import get_logger

logger = get_logger("byo_upload_service")


REQUIRED_FIELDS = ("id", "content", "created_at")


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _normalize_timestamp(value) -> str | None:
    """Best-effort ISO-8601 normalizer."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    s = str(value).strip()
    for fmt in (None, "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%m/%d/%Y", "%m/%d/%Y %H:%M"):
        try:
            if fmt is None:
                return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc).isoformat()
        except (ValueError, TypeError):
            continue
    return None


def _normalize_record(raw: dict, default_platform: str = "uploaded") -> dict | None:
    """Coerce a row into a valid PostRecord-shaped dict; return None if invalid."""
    rid = raw.get("id")
    content = raw.get("content")
    if not rid or not content:
        return None

    ts = _normalize_timestamp(raw.get("created_at"))
    if not ts:
        return None

    author_id = raw.get("author_id") or ""
    if author_id:
        is_hash = len(author_id) == 64 and all(c in "0123456789abcdef" for c in author_id.lower())
        author_id = author_id if is_hash else _sha256(author_id)

    eng = raw.get("engagement") or {}
    if isinstance(eng, str):
        try:
            eng = json.loads(eng)
        except json.JSONDecodeError:
            eng = {}

    am = raw.get("author_metadata") or {}
    if isinstance(am, str):
        try:
            am = json.loads(am)
        except json.JSONDecodeError:
            am = {}

    return {
        "id": str(rid),
        "platform": raw.get("platform") or default_platform,
        "entity_id": raw.get("entity_id", ""),
        "author_id": author_id,
        "author_metadata": am,
        "content": str(content).strip(),
        "parent_id": raw.get("parent_id"),
        "created_at": ts,
        "engagement": {
            "likes": int(eng.get("likes") or 0),
            "shares": int(eng.get("shares") or 0),
            "replies": int(eng.get("replies") or 0),
            "views": int(eng.get("views") or 0),
        },
        "url": raw.get("url") or "",
        "raw": raw.get("raw") or {},
    }


def _iter_jsonl(path: Path) -> Iterable[dict]:
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                logger.warning(f"skipping bad JSONL line: {exc}")


def _iter_csv(path: Path, column_mapping: dict[str, str] | None) -> Iterable[dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if column_mapping:
                mapped = {field: row.get(src) for field, src in column_mapping.items()}
                for k, v in row.items():
                    if k not in column_mapping.values():
                        mapped.setdefault(k, v)
                yield mapped
            else:
                yield row


class BYOUploadService:
    def __init__(self, config: type[Config] = Config):
        self.config = config

    def ingest_uploaded_file(
        self,
        entity_id: str,
        file_path: str,
        file_format: str,
        column_mapping: dict[str, str] | None = None,
        default_platform: str = "uploaded",
    ) -> dict:
        path = Path(file_path)
        if not path.exists():
            return {"records_added": 0, "records_skipped": 0, "errors": [f"file not found: {file_path}"]}

        ent_dir = Path(self.config.ENTITIES_DIR) / entity_id
        ing_dir = ent_dir / "ingestion"
        ing_dir.mkdir(parents=True, exist_ok=True)

        dedup_path = ing_dir / "pulled_ids.db"
        dedup = sqlite3.connect(str(dedup_path))
        dedup.execute("CREATE TABLE IF NOT EXISTS seen (id TEXT PRIMARY KEY)")

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        out_path = ing_dir / f"posts_{today}_uploaded.jsonl"

        added = 0
        skipped = 0
        errors: list[str] = []

        if file_format == "jsonl":
            iterator = _iter_jsonl(path)
        elif file_format == "csv":
            iterator = _iter_csv(path, column_mapping)
        else:
            return {"records_added": 0, "records_skipped": 0,
                    "errors": [f"unsupported file_format: {file_format!r}"]}

        with out_path.open("a", encoding="utf-8") as out_fh:
            for raw in iterator:
                rec = _normalize_record(raw, default_platform=default_platform)
                if rec is None:
                    skipped += 1
                    if len(errors) < 20:
                        missing = [f for f in REQUIRED_FIELDS if not raw.get(f)]
                        errors.append(f"missing required fields {missing} or unparseable timestamp")
                    continue
                rec["entity_id"] = entity_id
                cur = dedup.execute("SELECT 1 FROM seen WHERE id=?", (rec["id"],))
                if cur.fetchone():
                    skipped += 1
                    continue
                out_fh.write(json.dumps(rec) + "\n")
                dedup.execute("INSERT INTO seen (id) VALUES (?)", (rec["id"],))
                added += 1

        dedup.commit()
        dedup.close()
        logger.info(f"BYO upload {entity_id}: added={added} skipped={skipped} errors={len(errors)}")
        return {
            "records_added": added,
            "records_skipped": skipped,
            "errors": errors,
            "output_path": str(out_path),
        }


byo_upload_service = BYOUploadService(Config)

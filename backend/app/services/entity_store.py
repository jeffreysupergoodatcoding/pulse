"""
Entity Store — simple JSON file persistence for TrackedEntity objects.

Each entity is stored as:
  backend/data/entities/{entity_id}/config.json
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.config import Config
from app.models import TrackedEntity, SourceConfig
from app.utils.logger import get_logger

logger = get_logger("entity_store")


class EntityStore:
    def __init__(self, config: type[Config] = Config):
        self.entities_dir = Path(config.ENTITIES_DIR)
        self.entities_dir.mkdir(parents=True, exist_ok=True)

    def _entity_dir(self, entity_id: str) -> Path:
        return self.entities_dir / entity_id

    def _config_path(self, entity_id: str) -> Path:
        return self._entity_dir(entity_id) / "config.json"

    # ------------------------------------------------------------------

    def create(self, name: str, entity_type: str, **kwargs) -> TrackedEntity:
        entity = TrackedEntity(
            id=str(uuid.uuid4()),
            name=name,
            entity_type=entity_type,
            **kwargs,
        )
        self._entity_dir(entity.id).mkdir(parents=True, exist_ok=True)
        self._write(entity)
        logger.info(f"Created entity {entity.id} ({name})")
        return entity

    def get(self, entity_id: str) -> TrackedEntity | None:
        path = self._config_path(entity_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        return TrackedEntity.model_validate(data)

    def update(self, entity: TrackedEntity) -> TrackedEntity:
        self._write(entity)
        return entity

    def list_all(self) -> list[TrackedEntity]:
        results = []
        for config_path in self.entities_dir.glob("*/config.json"):
            try:
                data = json.loads(config_path.read_text())
                results.append(TrackedEntity.model_validate(data))
            except Exception as exc:
                logger.warning(f"Failed to load entity at {config_path}: {exc}")
        return results

    def delete(self, entity_id: str) -> bool:
        path = self._config_path(entity_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def _write(self, entity: TrackedEntity):
        path = self._config_path(entity.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(entity.model_dump_json(indent=2))


# Module-level singleton
entity_store = EntityStore(Config)

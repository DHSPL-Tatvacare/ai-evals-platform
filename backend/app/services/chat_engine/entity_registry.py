"""Per-app entity registry for Sherlock entity recognition."""
from __future__ import annotations

from typing import Any

from app.services.chat_engine.data_surfaces import get_chat_config, get_entity_resolvers
from app.services.chat_engine.sql_agent import _normalize_dimensions


def load_entity_registry(
    app_id: str,
    *,
    app_config: dict[str, Any] | None,
    semantic_model: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    del app_id

    registry: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in _seeded_entity_types(app_config):
        name = str(item.get('name', '')).strip()
        if not name:
            continue
        lowered = name.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        registry.append({
            'name': name,
            'description': str(item.get('description', '')).strip(),
            'examples': [str(example) for example in item.get('examples', []) if str(example).strip()],
        })

    for resolver in get_entity_resolvers(app_config):
        name = str(resolver.get('entity_type', '')).strip()
        if not name:
            continue
        lowered = name.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        registry.append({
            'name': name,
            'description': str(resolver.get('description', '')).strip() or f'Resolved value for {name}.',
            'examples': [],
        })

    for dimension in _normalize_dimensions(semantic_model or {}):
        name = str(dimension.get('name', '')).strip()
        if not name:
            continue
        lowered = name.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        registry.append({
            'name': name,
            'description': str(dimension.get('description', '')).strip() or f'Semantic dimension {name}.',
            'examples': [],
        })

    return registry


def _seeded_entity_types(app_config: dict[str, Any] | None) -> list[dict[str, Any]]:
    raw_entity_types = get_chat_config(app_config).get('entityTypes')
    if raw_entity_types is None:
        raw_entity_types = get_chat_config(app_config).get('entity_types')
    if not isinstance(raw_entity_types, list):
        return []
    return [item for item in raw_entity_types if isinstance(item, dict)]

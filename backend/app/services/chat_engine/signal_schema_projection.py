"""Project ``analytics.signal_definition`` rows into the Sherlock manifest.

Phase 11A of docs/plans/2026-05-12-analytics-facts-canonical-manifest-thinning.md.

The Sherlock manifest is composed from two sources, one per concern
(invariant 21, §7.4):

* ``fact_lead_signal``'s **structural columns** stay in the YAML manifest —
  stable, engineering-owned.
* ``fact_lead_signal``'s **per-``signal_type`` ``attribute_schemas``** are
  *projected from ``analytics.signal_definition``* — dynamic, tenant-specific.

This module overlays the DB-sourced ``attribute_schemas`` onto the
YAML-loaded manifest. It runs at boot (after seeding) and is the cache
invalidation hook the signal-definition admin screen (Phase 11C) calls on
every write — re-running is idempotent: it always rebuilds from the
pristine YAML plus current DB state, so a deleted definition correctly
drops its ``signal_type``s.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics_signal_definition import SignalDefinition
from app.services.analytics.signal_derivation.registry import get_strategy
from app.services.chat_engine.manifest import (
    AttributeKeySchema,
    invalidate_manifest_cache,
    load_all_manifests,
    replace_cached_manifest,
)

_log = logging.getLogger(__name__)

_SIGNAL_TABLE = "fact_lead_signal"


async def project_signal_definitions(db: AsyncSession) -> dict[str, Any]:
    """Rebuild every manifest's ``fact_lead_signal.attribute_schemas`` from
    the current ``analytics.signal_definition`` rows.

    Always starts from the pristine YAML manifest (cache is invalidated and
    reloaded first), so the result is a pure function of DB state.
    Returns a small summary for logging.
    """
    # Start from pristine YAML — never re-project onto an already-projected
    # manifest, or a deleted definition's signal_types would linger.
    invalidate_manifest_cache()
    manifests = load_all_manifests()

    rows = (
        await db.execute(
            select(SignalDefinition).where(SignalDefinition.enabled.is_(True))
        )
    ).scalars().all()
    by_app: dict[str, list[SignalDefinition]] = defaultdict(list)
    for row in rows:
        by_app[row.app_id].append(row)

    projected_apps: list[str] = []
    for app_id, manifest in list(manifests.items()):
        table = manifest.catalog_tables.get(_SIGNAL_TABLE)
        if table is None:
            continue

        # Start from the YAML-declared schemas (preserves ``_default``,
        # which covers the eval-run-coupled rows) and overlay the
        # per-``signal_type`` schemas every enabled definition declares.
        merged: dict[str, dict[str, AttributeKeySchema]] = {
            disc: dict(keys) for disc, keys in table.attribute_schemas.items()
        }
        for definition in by_app.get(app_id, []):
            strategy = get_strategy(definition.strategy)
            for signal_type, keys in strategy.attribute_schemas(
                definition.definition
            ).items():
                merged[signal_type] = {
                    key: AttributeKeySchema.model_validate(spec)
                    for key, spec in keys.items()
                }

        new_table = table.model_copy(update={"attribute_schemas": merged})
        new_manifest = manifest.model_copy(
            update={
                "catalog_tables": {
                    **manifest.catalog_tables,
                    _SIGNAL_TABLE: new_table,
                }
            }
        )
        replace_cached_manifest(app_id, new_manifest)
        projected_apps.append(app_id)

    summary = {
        "projected_apps": projected_apps,
        "enabled_definitions": len(rows),
    }
    _log.info(
        "signal_schema_projection.applied apps=%s definitions=%d",
        projected_apps,
        len(rows),
    )
    return summary

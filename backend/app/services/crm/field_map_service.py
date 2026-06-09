"""Publish a per-connection field map: closed-list validated, lead-link guarded, versioned.

Publish is the only server-persisted mapping action (the in-progress draft is client-only).
It enforces the invariants the resolved contract depends on: every target is a real column or
slot (never invented), and a non-lead grain MUST bind the lead-link or its rows can't resolve a
lead. Each publish replaces the connection's bindings for that grain and bumps the version.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm import CrmFieldMap
from app.services.crm.field_map_validation import validate_binding, validate_semantic_key

_LEAD_LINK_TARGET = "lead_id"  # the activity→lead join anchor


@dataclass(frozen=True)
class BindingInput:
    slot: str
    semantic_key: str
    source_field: str
    data_type: str = "text"
    value_map: Optional[dict[str, Any]] = None
    description: Optional[str] = None


async def publish_field_map(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    app_id: str,
    connection_id: uuid.UUID,
    record_type: str,
    bindings: list[BindingInput],
) -> int:
    """Validate + replace + version the bindings for one grain. Returns the new version."""
    for b in bindings:
        validate_binding(record_type, b.slot)  # raises ValueError outside the closed list
        validate_semantic_key(b.semantic_key)  # alias lands in matview DDL — must be a safe identifier

    if record_type == "activity" and not any(b.slot == _LEAD_LINK_TARGET for b in bindings):
        raise ValueError("activity mapping requires a lead-link binding (a source field → lead_id)")

    prior = (await db.execute(
        select(func.max(CrmFieldMap.version)).where(
            CrmFieldMap.tenant_id == tenant_id,
            CrmFieldMap.app_id == app_id,
            CrmFieldMap.connection_id == connection_id,
            CrmFieldMap.record_type == record_type,
        )
    )).scalar_one_or_none()
    version = (prior or 0) + 1

    await db.execute(
        delete(CrmFieldMap).where(
            CrmFieldMap.tenant_id == tenant_id,
            CrmFieldMap.app_id == app_id,
            CrmFieldMap.connection_id == connection_id,
            CrmFieldMap.record_type == record_type,
        )
    )
    for b in bindings:
        db.add(CrmFieldMap(
            id=uuid.uuid4(), tenant_id=tenant_id, app_id=app_id, connection_id=connection_id,
            record_type=record_type, slot=b.slot, semantic_key=b.semantic_key,
            source_field=b.source_field, data_type=b.data_type, value_map=b.value_map,
            description=b.description, version=version,
        ))
    await db.flush()
    return version


__all__ = ["BindingInput", "publish_field_map"]

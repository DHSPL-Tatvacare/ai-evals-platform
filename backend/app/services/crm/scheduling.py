"""Launch-source resolver for the source-bound ``sync-crm-source`` workload.

A scheduled CRM sync is bound to a single dataset (a connection + record type).
The create-schedule payload carries a ``source_id`` of ``{connection_id}:{record_type}``
and the backend re-resolves the canonical sync params from it here — the source is
the single authority, client-sent params are ignored.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.provider_connection import ProviderConnection
from app.services.scheduler.launch_sources import (
    LaunchSpec,
    register_launch_source_resolver,
)

SYNC_JOB_TYPE = "sync-crm-source"
RECORD_TYPES = ("lead", "activity")


def parse_source_id(source_id: str) -> tuple[uuid.UUID, str]:
    """Split a ``{connection_id}:{record_type}`` source id; ValueError on bad shape."""
    connection_str, _, record_type = source_id.partition(":")
    if not record_type:
        raise ValueError(f"Invalid source id {source_id!r}: expected '{{connection_id}}:{{record_type}}'")
    try:
        connection_id = uuid.UUID(connection_str)
    except ValueError as exc:
        raise ValueError(f"Invalid connection id in source {source_id!r}") from exc
    if record_type not in RECORD_TYPES:
        raise ValueError(f"Unknown record type {record_type!r} (expected one of {RECORD_TYPES})")
    return connection_id, record_type


def source_object_for(provider: str, record_type: str) -> str:
    """Provider-truth source object for a record type, derived statically (no live call)."""
    from app.services.crm.adapters import resolve_crm_adapter
    from app.services.orchestration.adapters import AdapterNotRegisteredError

    try:
        adapter_cls = type(resolve_crm_adapter(vendor=provider))
    except AdapterNotRegisteredError as exc:
        raise ValueError(f"provider {provider!r} has no CRM source adapter") from exc
    return adapter_cls.source_object_for(record_type)


async def resolve_crm_sync_source(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    app_id: str,  # noqa: ARG001 — connection scope is tenant-wide; app is informational here
    source_id: str,
) -> LaunchSpec:
    """Resolve canonical ``sync-crm-source`` params from a ``{connection_id}:{record_type}`` id."""
    connection_id, record_type = parse_source_id(source_id)
    conn = await db.scalar(
        select(ProviderConnection).where(
            ProviderConnection.id == connection_id,
            ProviderConnection.tenant_id == tenant_id,
        )
    )
    if conn is None:
        raise ValueError(f"connection {connection_id} not found for this tenant")
    source_object = source_object_for(conn.provider, record_type)
    return LaunchSpec(
        params={"connection_id": str(connection_id), "source_objects": [source_object]},
        schedule_key=source_id,
        name=f"{conn.name} · {record_type.capitalize()} sync",
    )


def register() -> None:
    """Register the CRM sync launch-source resolver. Idempotent."""
    register_launch_source_resolver(SYNC_JOB_TYPE, resolve_crm_sync_source)


register()

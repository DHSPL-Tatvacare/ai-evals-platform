"""CRM source sync — adapter fetch → verbatim landing on ``crm_source_record`` (the replay tape).

The land job is provider-agnostic: it resolves the connection's adapter from the registry,
sweeps each discovered object, and UPSERTs raw records by natural key. It never shapes a
serving row (that is the unpacker's sole job) and carries no provider branch.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm import CrmSourceRecord
from app.models.source_records import LogCrmSourceSync
from app.services.crm.adapters.protocol import SourceRecordDraft

_PAGE_CAP_DEFAULT = 50


def _hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


async def land_records(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    app_id: str,
    connection_id: uuid.UUID,
    drafts: list[SourceRecordDraft],
) -> int:
    """Idempotent UPSERT of landing drafts by natural key. Returns the count processed."""
    now = datetime.now(timezone.utc)
    landed = 0
    for d in drafts:
        if not d.source_record_id:
            continue
        stmt = pg_insert(CrmSourceRecord).values(
            id=uuid.uuid4(), tenant_id=tenant_id, app_id=app_id, connection_id=connection_id,
            source_object=d.source_object, record_type=d.record_type, source_record_id=d.source_record_id,
            raw_payload=d.raw_payload, source_record_hash=_hash(d.raw_payload),
            first_synced_at=now, last_synced_at=now, last_seen_in_source_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_crm_source_record_natural_key",
            set_={
                "raw_payload": stmt.excluded.raw_payload,
                "source_record_hash": stmt.excluded.source_record_hash,
                "last_synced_at": stmt.excluded.last_synced_at,
                "last_seen_in_source_at": stmt.excluded.last_seen_in_source_at,
            },
        )
        await db.execute(stmt)
        landed += 1
    await db.flush()
    return landed


async def _latest_watermark(
    db: AsyncSession, *, tenant_id: uuid.UUID, app_id: str, source_key: str
) -> str | None:
    return (await db.execute(
        select(LogCrmSourceSync.watermark_to)
        .where(
            LogCrmSourceSync.tenant_id == tenant_id,
            LogCrmSourceSync.app_id == app_id,
            LogCrmSourceSync.targeted_source_id == source_key,
            LogCrmSourceSync.status == "completed",
        )
        .order_by(LogCrmSourceSync.completed_at.desc())
        .limit(1)
    )).scalar_one_or_none()


async def run_crm_source_sync(job_id, params: dict, *, tenant_id: uuid.UUID, user_id: uuid.UUID) -> dict:
    """Land new/updated records for a connection. tenant + connection scoped via params."""
    from app.database import async_session
    from app.services.crm.adapters import resolve_crm_adapter
    from app.services.orchestration.connections.resolver import ConnectionResolver

    app_id = str(params.get("app_id") or "").strip()
    connection_id = uuid.UUID(str(params["connection_id"]))
    page_cap = int(params.get("page_cap") or _PAGE_CAP_DEFAULT)
    is_scheduled = bool(params.get("is_scheduled_run", False))

    landed_total = 0
    async with async_session() as db:
        resolver = ConnectionResolver(db, tenant_id=tenant_id, app_id=app_id)
        creds = await resolver.get_config(connection_id)
        provider = creds.pop("__provider__", "")
        adapter = resolve_crm_adapter(vendor=provider)

        source_objects = params.get("source_objects") or [
            o.source_object for o in await adapter.discover_objects(creds=creds)
        ]

        for obj in source_objects:
            source_key = f"{connection_id}:{obj}"
            watermark = await _latest_watermark(db, tenant_id=tenant_id, app_id=app_id, source_key=source_key)
            started = datetime.now(timezone.utc)
            page, scanned, new_watermark = 1, 0, watermark
            capped = False
            while True:
                fetched = await adapter.fetch_records(
                    creds=creds, source_object=obj, watermark=watermark, page=page
                )
                scanned += len(fetched.records)
                landed_total += await land_records(
                    db, tenant_id=tenant_id, app_id=app_id, connection_id=connection_id, drafts=fetched.records
                )
                new_watermark = max(
                    [w for w in (new_watermark, fetched.next_watermark) if w], default=new_watermark
                )
                if not fetched.has_more:
                    break
                page += 1
                if page > page_cap:
                    capped = True
                    break

            db.add(LogCrmSourceSync(
                id=uuid.uuid4(), tenant_id=tenant_id, app_id=app_id, source_system=provider,
                source_family=obj[:20], sync_mode="land", status="completed",
                targeted_source_id=source_key[:120], watermark_from=watermark, watermark_to=new_watermark,
                records_scanned=scanned, records_upserted=scanned, started_at=started,
                completed_at=datetime.now(timezone.utc), requested_by_user_id=user_id,
                is_scheduled_run=is_scheduled, details={"page_cap_reached": capped},
            ))
        await db.commit()
    return {"landed": landed_total}


__all__ = ["land_records", "run_crm_source_sync"]

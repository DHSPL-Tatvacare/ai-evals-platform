"""The single source-agnostic CRM unpacker: landed raw + field-map → core + typed slots.

The ONLY writer of CRM-derived core/slot rows. Adapters land + discover; this populator
shapes the serving core. Behaviour comes entirely from ``crm_field_map`` — there is no
provider branch here (a new CRM is a new mapping, not new code). Idempotent UPSERT by
natural key; replayable from the landed tape on a mapping edit (no re-sync). An activity
whose required lead-link cannot resolve a lead is skipped (orphan-guard, never fanned out).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crm import (
    CrmActivity,
    CrmActivityExt,
    CrmLead,
    CrmLeadExt,
    CrmFieldMap,
    CrmSourceRecord,
)
from app.models.source_records import LogCrmSourceSync
from app.utils.phone import normalise_phone_e164


@dataclass
class UnpackResult:
    scanned: int = 0
    upserted: int = 0
    skipped: int = 0
    failed: int = 0


@dataclass(frozen=True)
class _Grain:
    record_type: str
    core: type
    ext: type
    core_conflict: str
    ext_conflict: str
    ext_fk: str
    natural_key: str          # core column that, with tenant+app, is the upsert target
    required: tuple[str, ...]  # core columns that MUST resolve or the row is skipped


_GRAINS = (
    _Grain("lead", CrmLead, CrmLeadExt, "uq_crm_lead_business_key",
           "uq_crm_lead_ext_one_to_one", "crm_lead_id", "lead_id", ("lead_id",)),
    _Grain("activity", CrmActivity, CrmActivityExt, "uq_crm_activity_natural_key",
           "uq_crm_activity_ext_one_to_one", "crm_activity_id", "source_activity_id",
           ("source_activity_id", "lead_id")),
)

_PLUMBING = frozenset({"id", "tenant_id", "app_id", "crm_lead_id", "crm_activity_id"})


def _columns(model: type) -> set[str]:
    return {c for c in model.__table__.columns.keys() if c not in _PLUMBING}


def _to_int(raw: Any) -> int | None:
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return None


def _to_decimal(raw: Any) -> Decimal | None:
    try:
        return Decimal(str(raw).strip())
    except (InvalidOperation, TypeError, ValueError):
        return None


def _to_bool(raw: Any) -> bool | None:
    if isinstance(raw, bool):
        return raw
    s = str(raw).strip().lower()
    if s in ("true", "1", "yes", "y"):
        return True
    if s in ("false", "0", "no", "n"):
        return False
    return None


def _to_datetime(raw: Any) -> datetime | None:
    if isinstance(raw, datetime):
        return raw
    s = str(raw).strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _coerce(raw: Any, data_type: str) -> Any:
    dt = (data_type or "text").lower()
    if dt in ("int", "integer", "bigint"):
        return _to_int(raw)
    if dt in ("num", "numeric", "number", "decimal", "float"):
        return _to_decimal(raw)
    if dt in ("dt", "datetime", "date", "timestamp"):
        return _to_datetime(raw)
    if dt in ("bool", "boolean"):
        return _to_bool(raw)
    if dt in ("json", "jsonb"):
        return raw
    return str(raw)


def _resolve(raw: dict[str, Any], bindings: list[CrmFieldMap], targets: set[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for b in bindings:
        if b.slot not in targets:
            continue
        raw_val = raw.get(b.source_field)
        if raw_val is None:
            continue
        if b.value_map and str(raw_val) in b.value_map:
            out[b.slot] = b.value_map[str(raw_val)]
        else:
            out[b.slot] = _coerce(raw_val, b.data_type)
    return out


async def _bindings_for(
    db: AsyncSession, *, tenant_id: uuid.UUID, app_id: str, connection_id: uuid.UUID, record_type: str
) -> list[CrmFieldMap]:
    rows = await db.execute(
        select(CrmFieldMap).where(
            CrmFieldMap.tenant_id == tenant_id,
            CrmFieldMap.app_id == app_id,
            CrmFieldMap.connection_id == connection_id,
            CrmFieldMap.record_type == record_type,
        )
    )
    return list(rows.scalars().all())


async def _upsert(
    db: AsyncSession, model: type, *, conflict: str, values: dict[str, Any], mutable: Iterable[str]
) -> uuid.UUID:
    stmt = pg_insert(model).values(id=uuid.uuid4(), **values)
    set_ = {col: stmt.excluded[col] for col in mutable if col in values}
    stmt = stmt.on_conflict_do_update(constraint=conflict, set_=set_).returning(model.id)
    return (await db.execute(stmt)).scalar_one()


async def unpack(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    app_id: str,
    connection_id: uuid.UUID,
    source_system: str,
    record_ids: list[uuid.UUID] | None = None,
) -> UnpackResult:
    """Unpack landed raw into core + slots for one connection. Provider-agnostic; map-driven."""
    result = UnpackResult()
    started = datetime.now(timezone.utc)

    for grain in _GRAINS:
        bindings = await _bindings_for(
            db, tenant_id=tenant_id, app_id=app_id, connection_id=connection_id, record_type=grain.record_type
        )
        if not bindings:
            continue
        core_targets = _columns(grain.core)
        ext_targets = _columns(grain.ext)

        q = select(CrmSourceRecord).where(
            CrmSourceRecord.tenant_id == tenant_id,
            CrmSourceRecord.app_id == app_id,
            CrmSourceRecord.connection_id == connection_id,
            CrmSourceRecord.record_type == grain.record_type,
        )
        if record_ids is not None:
            q = q.where(CrmSourceRecord.id.in_(record_ids))
        records = list((await db.execute(q)).scalars().all())
        result.scanned += len(records)

        for rec in records:
            raw = rec.raw_payload or {}
            core_vals = _resolve(raw, bindings, core_targets)
            ext_vals = _resolve(raw, bindings, ext_targets)

            if any(not core_vals.get(req) for req in grain.required):
                result.skipped += 1
                continue

            if core_vals.get("phone_number"):
                core_vals["phone_number_norm"] = normalise_phone_e164(core_vals["phone_number"])

            core_id = await _upsert(
                db, grain.core, conflict=grain.core_conflict,
                values={"tenant_id": tenant_id, "app_id": app_id, **core_vals},
                mutable=core_targets,
            )
            if ext_vals:
                await _upsert(
                    db, grain.ext, conflict=grain.ext_conflict,
                    values={"tenant_id": tenant_id, "app_id": app_id, grain.ext_fk: core_id, **ext_vals},
                    mutable=ext_targets,
                )
            result.upserted += 1

    db.add(
        LogCrmSourceSync(
            id=uuid.uuid4(), tenant_id=tenant_id, app_id=app_id, source_system=source_system,
            source_family="crm", sync_mode="unpack", status="completed",
            targeted_source_id=str(connection_id)[:120],
            records_scanned=result.scanned, records_upserted=result.upserted,
            records_failed=result.failed, started_at=started, completed_at=datetime.now(timezone.utc),
            details={"skipped": result.skipped},
        )
    )
    await db.flush()
    return result


async def run_crm_source_unpack(job_id, params: dict, *, tenant_id: uuid.UUID, user_id: uuid.UUID) -> dict:
    """Unpack-job entry: open a session, resolve the connection, populate from the landed tape."""
    from app.database import async_session
    from app.services.orchestration.connections.resolver import ConnectionResolver

    app_id = str(params.get("app_id") or "").strip()
    connection_id = uuid.UUID(str(params["connection_id"]))
    raw_ids = params.get("record_ids")
    record_ids = [uuid.UUID(str(x)) for x in raw_ids] if raw_ids else None

    async with async_session() as db:
        resolver = ConnectionResolver(db, tenant_id=tenant_id, app_id=app_id)
        creds = await resolver.get_config(connection_id)
        provider = str(creds.get("__provider__") or "crm")
        result = await unpack(
            db, tenant_id=tenant_id, app_id=app_id, connection_id=connection_id,
            source_system=provider, record_ids=record_ids,
        )
        # Refresh the resolved surfaces so the matview reflects the freshly unpacked rows.
        from app.services.crm.crm_resolved_populator import refresh_resolved_matviews
        await refresh_resolved_matviews(db, tenant_id=tenant_id, app_id=app_id, connection_id=connection_id)

        # Analytics tail of the chain: rebuild the deterministic lead facts for this app.
        if app_id:
            from app.services.crm.crm_chain import build_analytics_populate_job

            db.add(build_analytics_populate_job(tenant_id=tenant_id, user_id=user_id, app_id=app_id))
        await db.commit()
    return {
        "scanned": result.scanned, "upserted": result.upserted,
        "skipped": result.skipped, "failed": result.failed,
    }


__all__ = ["UnpackResult", "unpack", "run_crm_source_unpack"]

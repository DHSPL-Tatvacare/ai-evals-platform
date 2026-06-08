"""CRM ingestion routes — discover · field maps · sync/unpack · sync activity.

The CRM data surface is coupled to the connections it ingests: every route is gated on
``orchestration:manage`` (the same permission as the connection) and app-gated against the
connection's ``app_id``. Connection cred CRUD stays on the orchestration connections router;
this router owns mapping + ingestion only. Discovery, sync, and unpack are provider-agnostic —
they resolve the connection's adapter from the registry.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthContext
from app.auth.app_scope import ensure_registered_app_access
from app.auth.permissions import require_permission
from app.database import get_db
from app.models.crm import CrmFieldMap
from app.models.job import BackgroundJob
from app.models.provider_connection import ProviderConnection
from app.models.source_records import LogCrmSourceSync
from app.schemas.crm import (
    DiscoverResponse,
    DiscoveredObjectOut,
    FieldBindingOut,
    FieldMapPublishRequest,
    FieldMapPublishResponse,
    FieldMapResponse,
    FieldValuesResponse,
    GrainSchemaOut,
    GrainsResponse,
    JobSubmittedResponse,
    SyncActivityOut,
    SyncActivityResponse,
    SyncRequest,
)
from app.services.crm.adapters import resolve_crm_adapter
from app.services.crm.field_map_service import BindingInput, publish_field_map
from app.services.crm.field_values import distinct_field_values
from app.services.crm.grain_schema import all_grain_schemas
from app.services.job_worker import get_job_submission_metadata
from app.services.orchestration.adapters import AdapterNotRegisteredError
from app.services.orchestration.connections.resolver import ConnectionResolver

router = APIRouter(prefix="/api/crm", tags=["crm"])

_RECORD_TYPES = ("lead", "activity")


async def _load_connection(
    db: AsyncSession, auth: AuthContext, connection_id: uuid.UUID
) -> ProviderConnection:
    row = await db.scalar(
        select(ProviderConnection).where(
            ProviderConnection.id == connection_id,
            ProviderConnection.tenant_id == auth.tenant_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="connection not found")
    await ensure_registered_app_access(db, auth, row.app_id)
    return row


async def _submit_job(
    db: AsyncSession, auth: AuthContext, job_type: str, params: dict, message: str
) -> BackgroundJob:
    full = {**params, "tenant_id": str(auth.tenant_id), "user_id": str(auth.user_id)}
    meta = get_job_submission_metadata(job_type, full)
    job = BackgroundJob(
        app_id=str(meta["app_id"]), job_type=job_type, status="queued",
        priority=int(meta["priority"]), queue_class=str(meta["queue_class"]),
        max_attempts=int(meta["max_attempts"]),
        progress={"current": 0, "total": 0, "message": message},
        params={**full, "app_id": str(meta["app_id"])},
        tenant_id=auth.tenant_id, user_id=auth.user_id,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


@router.get(
    "/grains",
    response_model=GrainsResponse,
    summary="The closed list of bind targets per grain (standard columns + slot pool)",
)
async def get_grains(
    auth: AuthContext = require_permission("orchestration:manage"),  # noqa: ARG001
):
    return GrainsResponse(grains=[GrainSchemaOut(**g) for g in all_grain_schemas()])


@router.get(
    "/connections/{connection_id}/field-values",
    response_model=FieldValuesResponse,
    summary="Distinct observed values of a source field (for exhaustive value maps)",
)
async def get_field_values(
    connection_id: uuid.UUID,
    field: str = Query(..., description="The CRM source field name"),
    record_type: str = Query(..., alias="recordType", description="lead | activity"),
    auth: AuthContext = require_permission("orchestration:manage"),
    db: AsyncSession = Depends(get_db),
):
    if record_type not in _RECORD_TYPES:
        raise HTTPException(status_code=400, detail="record_type must be lead | activity")
    row = await _load_connection(db, auth, connection_id)
    values = await distinct_field_values(
        db, tenant_id=auth.tenant_id, app_id=row.app_id, connection_id=connection_id,
        record_type=record_type, field=field,
    )
    return FieldValuesResponse(field=field, values=values)


@router.get(
    "/connections/{connection_id}/objects",
    response_model=DiscoverResponse,
    summary="Discover a CRM connection's mappable objects and their fields",
)
async def discover_objects(
    connection_id: uuid.UUID,
    auth: AuthContext = require_permission("orchestration:manage"),
    db: AsyncSession = Depends(get_db),
):
    row = await _load_connection(db, auth, connection_id)
    resolver = ConnectionResolver(db, tenant_id=auth.tenant_id, app_id=row.app_id)
    creds = await resolver.get_config(connection_id)
    provider = str(creds.pop("__provider__", None) or row.provider)
    try:
        adapter = resolve_crm_adapter(vendor=provider)
    except AdapterNotRegisteredError:
        raise HTTPException(status_code=400, detail=f"provider {provider!r} has no CRM source adapter")
    try:
        objects = await adapter.discover_objects(creds=creds)
    except Exception as exc:  # noqa: BLE001 — surface the provider error, never 500
        raise HTTPException(status_code=502, detail=f"discovery failed: {exc}"[:200])
    return DiscoverResponse(objects=[
        DiscoveredObjectOut(source_object=o.source_object, record_type=o.record_type, fields=o.fields)
        for o in objects
    ])


@router.get(
    "/connections/{connection_id}/field-maps",
    response_model=FieldMapResponse,
    summary="Get the published field map for a grain",
)
async def get_field_map(
    connection_id: uuid.UUID,
    record_type: str = Query(..., alias="recordType", description="lead | activity"),
    auth: AuthContext = require_permission("orchestration:manage"),
    db: AsyncSession = Depends(get_db),
):
    if record_type not in _RECORD_TYPES:
        raise HTTPException(status_code=400, detail="record_type must be lead | activity")
    row = await _load_connection(db, auth, connection_id)
    rows = (await db.execute(
        select(CrmFieldMap).where(
            CrmFieldMap.tenant_id == auth.tenant_id,
            CrmFieldMap.app_id == row.app_id,
            CrmFieldMap.connection_id == connection_id,
            CrmFieldMap.record_type == record_type,
        ).order_by(CrmFieldMap.slot)
    )).scalars().all()
    version = max((r.version for r in rows), default=0)
    return FieldMapResponse(
        record_type=record_type, version=version,
        bindings=[
            FieldBindingOut(
                slot=r.slot, semantic_key=r.semantic_key, source_field=r.source_field,
                data_type=r.data_type, value_map=r.value_map, description=r.description, version=r.version,
            ) for r in rows
        ],
    )


@router.put(
    "/connections/{connection_id}/field-maps",
    response_model=FieldMapPublishResponse,
    summary="Publish a field map for a grain and re-unpack from landed raw",
)
async def publish_field_map_route(
    connection_id: uuid.UUID,
    body: FieldMapPublishRequest,
    auth: AuthContext = require_permission("orchestration:manage"),
    db: AsyncSession = Depends(get_db),
):
    row = await _load_connection(db, auth, connection_id)
    try:
        version = await publish_field_map(
            db, tenant_id=auth.tenant_id, app_id=row.app_id, connection_id=connection_id,
            record_type=body.record_type,
            bindings=[
                BindingInput(
                    slot=b.slot, semantic_key=b.semantic_key, source_field=b.source_field,
                    data_type=b.data_type, value_map=b.value_map,
                ) for b in body.bindings
            ],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    job = await _submit_job(
        db, auth, "unpack-crm-source",
        {"app_id": row.app_id, "connection_id": str(connection_id)},
        "Re-unpack after mapping publish",
    )
    return FieldMapPublishResponse(record_type=body.record_type, version=version, unpack_job_id=str(job.id))


@router.post(
    "/connections/{connection_id}/sync",
    response_model=JobSubmittedResponse,
    summary="Queue a sync (land) for this connection",
)
async def trigger_sync(
    connection_id: uuid.UUID,
    body: SyncRequest | None = None,
    auth: AuthContext = require_permission("orchestration:manage"),
    db: AsyncSession = Depends(get_db),
):
    row = await _load_connection(db, auth, connection_id)
    params: dict = {"app_id": row.app_id, "connection_id": str(connection_id)}
    if body and body.source_objects:
        params["source_objects"] = body.source_objects
    job = await _submit_job(db, auth, "sync-crm-source", params, "Sync queued")
    return JobSubmittedResponse(job_id=str(job.id), status=job.status)


@router.post(
    "/connections/{connection_id}/unpack",
    response_model=JobSubmittedResponse,
    summary="Queue an unpack (populate core + slots) from landed raw",
)
async def trigger_unpack(
    connection_id: uuid.UUID,
    auth: AuthContext = require_permission("orchestration:manage"),
    db: AsyncSession = Depends(get_db),
):
    row = await _load_connection(db, auth, connection_id)
    job = await _submit_job(
        db, auth, "unpack-crm-source",
        {"app_id": row.app_id, "connection_id": str(connection_id)}, "Unpack queued",
    )
    return JobSubmittedResponse(job_id=str(job.id), status=job.status)


@router.get(
    "/connections/{connection_id}/sync-activity",
    response_model=SyncActivityResponse,
    summary="Recent sync/unpack runs for this connection",
)
async def get_sync_activity(
    connection_id: uuid.UUID,
    auth: AuthContext = require_permission("orchestration:manage"),
    db: AsyncSession = Depends(get_db),
):
    row = await _load_connection(db, auth, connection_id)
    rows = (await db.execute(
        select(LogCrmSourceSync).where(
            LogCrmSourceSync.tenant_id == auth.tenant_id,
            LogCrmSourceSync.app_id == row.app_id,
            LogCrmSourceSync.targeted_source_id.like(f"{connection_id}%"),
        ).order_by(LogCrmSourceSync.created_at.desc()).limit(50)
    )).scalars().all()
    return SyncActivityResponse(runs=[
        SyncActivityOut(
            id=str(r.id), source_family=r.source_family, sync_mode=r.sync_mode, status=r.status,
            records_scanned=r.records_scanned, records_upserted=r.records_upserted,
            records_failed=r.records_failed, watermark_to=r.watermark_to,
            started_at=r.started_at, completed_at=r.completed_at,
        ) for r in rows
    ])

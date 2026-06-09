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
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthContext
from app.auth.app_scope import ensure_registered_app_access
from app.auth.permissions import require_permission
from app.database import get_db
from app.models.crm import CrmFieldMap, SourceDatasetDefinition
from app.models.job import BackgroundJob
from app.models.provider_connection import ProviderConnection
from app.models.scheduled_job import ScheduledJobDefinition
from app.models.source_records import LogCrmSourceSync
from app.schemas.scheduled_job import ScheduleSourceItem, ScheduleSourcesResponse
from app.schemas.crm import (
    ActivateRequest,
    ActivateResponse,
    ChainJobOut,
    DatasetJobsResponse,
    DatasetScheduleOut,
    DatasetSummary,
    DatasetsResponse,
    DiscoverResponse,
    DiscoveredObjectOut,
    DraftDefinitionRequest,
    DraftDefinitionResponse,
    FieldBindingOut,
    FilterCapabilityResponse,
    FilterableFieldOut,
    FieldMapPublishRequest,
    FieldMapPublishResponse,
    FieldMapResponse,
    FieldValuesResponse,
    GrainSchemaOut,
    GrainsResponse,
    JobSubmittedResponse,
    RawSampleRecordOut,
    RawSampleResponse,
    ResolvedPreviewResponse,
    SyncActivityOut,
    SyncActivityResponse,
    SyncRequest,
    UnpackedSampleResponse,
)
from app.services.crm.adapters import resolve_crm_adapter
from app.services.crm.crm_resolved_fragment import validate_resolved_contract
from app.services.crm.crm_resolved_populator import rebuild_resolved_surfaces, resolved_sample
from app.services.crm.crm_source_unpacker import _columns, _resolve, _GRAINS as _UNPACK_GRAINS
from app.services.crm.field_map_service import BindingInput, publish_field_map
from app.services.crm.field_values import distinct_field_values
from app.services.crm.grain_schema import all_grain_schemas, grain_schema, registered_record_types
from app.services.crm.scheduling import source_object_for
from app.services.job_worker import get_job_submission_metadata
from app.services.orchestration.adapters import AdapterNotRegisteredError
from app.services.orchestration.connections.provider_specs import get_spec
from app.services.orchestration.connections.resolver import ConnectionResolver
from app.services.orchestration.predicate_contract import PredicateError, parse as parse_predicate

router = APIRouter(prefix="/api/crm", tags=["crm"])

_RECORD_TYPES = registered_record_types("crm")


async def _resolve_adapter(
    db: AsyncSession, auth: AuthContext, conn: ProviderConnection
):
    """The connection's CRM adapter + decrypted creds (provider stripped). Tenant+app scoped."""
    resolver = ConnectionResolver(db, tenant_id=auth.tenant_id, app_id=conn.app_id)
    creds = await resolver.get_config(conn.id)
    provider = str(creds.pop("__provider__", None) or conn.provider)
    try:
        adapter = resolve_crm_adapter(vendor=provider)
    except AdapterNotRegisteredError:
        raise HTTPException(status_code=400, detail=f"provider {provider!r} has no CRM source adapter")
    return adapter, creds


async def _source_object_for(adapter, creds: dict, record_type: str) -> str:
    """Map a record_type to the provider's source object via discovery (provider-truth)."""
    try:
        discovered = await adapter.discover_objects(creds=creds)
    except Exception as exc:  # noqa: BLE001 — surface the provider error, never 500
        raise HTTPException(status_code=502, detail=f"discovery failed: {exc}"[:200])
    for o in discovered:
        if o.record_type == record_type:
            return o.source_object
    raise HTTPException(status_code=404, detail=f"connection exposes no {record_type} dataset")


def _require_record_type(record_type: str) -> None:
    if record_type not in _RECORD_TYPES:
        raise HTTPException(status_code=400, detail="record_type must be lead | activity")


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
    "/schedule-sources",
    response_model=ScheduleSourcesResponse,
    summary="Datasets this tenant can schedule a sync for (source list for the sync-crm-source workload)",
)
async def list_schedule_sources(
    app_id: str | None = Query(default=None, alias="appId"),
    auth: AuthContext = require_permission("orchestration:manage"),
    db: AsyncSession = Depends(get_db),
) -> ScheduleSourcesResponse:
    """One source item per (CRM connection, record type) the tenant can sync.

    Record types are derived statically from the grain registry + provider-truth
    source-object map — no live provider call. The create-schedule overlay reads
    this list; the backend re-resolves canonical params from the picked source_id.
    """
    stmt = select(ProviderConnection).where(
        ProviderConnection.tenant_id == auth.tenant_id,
        ProviderConnection.active.is_(True),
    )
    if app_id:
        stmt = stmt.where(ProviderConnection.app_id == app_id)
    stmt = stmt.order_by(ProviderConnection.name)
    connections = (await db.execute(stmt)).scalars().all()

    items: list[ScheduleSourceItem] = []
    for conn in connections:
        if get_spec(conn.provider).kind != "crm_source":
            continue
        for record_type in _RECORD_TYPES:
            try:
                source_object = source_object_for(conn.provider, record_type)
            except ValueError:
                continue
            items.append(
                ScheduleSourceItem(
                    id=f"{conn.id}:{record_type}",
                    label=f"{conn.name} · {record_type.capitalize()}",
                    sublabel=conn.name,
                    schedule_key=f"{conn.id}:{record_type}",
                    params={"connection_id": str(conn.id), "source_objects": [source_object]},
                )
            )
    return ScheduleSourcesResponse(items=items)


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
                    data_type=b.data_type, value_map=b.value_map, description=b.description,
                ) for b in body.bindings
            ],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Rebuild the resolved surfaces from the new map and gate publish on the contract: the matview
    # must match the projected fragment AND resolved-column SQL must pass the same enforcers Sherlock
    # runs. A map that can't be served is refused here, not at a turn. (Rolls back with the request.)
    await rebuild_resolved_surfaces(db, tenant_id=auth.tenant_id, app_id=row.app_id, connection_id=connection_id)
    try:
        await validate_resolved_contract(db, tenant_id=auth.tenant_id, app_id=row.app_id)
    except Exception as exc:  # noqa: BLE001 — surface a clean 400, never a 500
        raise HTTPException(status_code=400, detail=f"resolved-layer validation failed: {exc}"[:300])

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
    "/connections/{connection_id}/resolved-preview",
    response_model=ResolvedPreviewResponse,
    summary="Sample of the resolved layer for a grain (what Sherlock will see)",
)
async def get_resolved_preview(
    connection_id: uuid.UUID,
    record_type: str = Query(..., alias="recordType", description="lead | activity"),
    auth: AuthContext = require_permission("orchestration:manage"),
    db: AsyncSession = Depends(get_db),
):
    if record_type not in _RECORD_TYPES:
        raise HTTPException(status_code=400, detail="record_type must be lead | activity")
    row = await _load_connection(db, auth, connection_id)
    columns, rows = await resolved_sample(
        db, tenant_id=auth.tenant_id, app_id=row.app_id, grain=record_type,
    )
    return ResolvedPreviewResponse(record_type=record_type, columns=columns, rows=rows)


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


async def _definitions_by_record_type(
    db: AsyncSession, *, tenant_id, app_id: str, connection_id
) -> dict[str, SourceDatasetDefinition]:
    rows = (await db.execute(
        select(SourceDatasetDefinition).where(
            SourceDatasetDefinition.tenant_id == tenant_id,
            SourceDatasetDefinition.app_id == app_id,
            SourceDatasetDefinition.connection_id == connection_id,
        )
    )).scalars().all()
    return {d.record_type: d for d in rows}


@router.get(
    "/connections/{connection_id}/datasets",
    response_model=DatasetsResponse,
    summary="The datasets (record types) this connection exposes + each one's lifecycle state",
)
async def list_datasets(
    connection_id: uuid.UUID,
    auth: AuthContext = require_permission("orchestration:manage"),
    db: AsyncSession = Depends(get_db),
):
    row = await _load_connection(db, auth, connection_id)
    # Datasets (the grains this connection can ingest) are static — listing them must NOT hit the
    # provider. The adapter only maps a record type to its provider source object (no creds, no call);
    # live field discovery is a separate, user-initiated step.
    adapter, _creds = await _resolve_adapter(db, auth, row)
    defs = await _definitions_by_record_type(
        db, tenant_id=auth.tenant_id, app_id=row.app_id, connection_id=connection_id
    )
    last_sync = (await db.execute(
        select(LogCrmSourceSync.source_family, func.max(LogCrmSourceSync.completed_at))
        .where(
            LogCrmSourceSync.tenant_id == auth.tenant_id,
            LogCrmSourceSync.app_id == row.app_id,
            LogCrmSourceSync.targeted_source_id.like(f"{connection_id}%"),
            LogCrmSourceSync.status == "completed",
        ).group_by(LogCrmSourceSync.source_family)
    )).all()
    last_sync_by_family = {fam: ts for fam, ts in last_sync}
    datasets = []
    for grain in _UNPACK_GRAINS:
        rt = grain.record_type
        source_object = adapter.source_object_for(rt)
        d = defs.get(rt)
        datasets.append(DatasetSummary(
            record_type=rt, source_object=source_object,
            status=d.status if d else "draft", version=d.version if d else 0,
            has_schedule=bool(d and d.schedule_id is not None),
            last_sync_at=last_sync_by_family.get(source_object[:20]),
        ))
    return DatasetsResponse(datasets=datasets)


@router.get(
    "/connections/{connection_id}/datasets/{record_type}/raw-sample",
    response_model=RawSampleResponse,
    summary="Raw provider JSON sample for a dataset (read-only; the 'Raw JSON' toggle)",
)
async def get_raw_sample(
    connection_id: uuid.UUID,
    record_type: str,
    auth: AuthContext = require_permission("orchestration:manage"),
    db: AsyncSession = Depends(get_db),
):
    _require_record_type(record_type)
    row = await _load_connection(db, auth, connection_id)
    adapter, creds = await _resolve_adapter(db, auth, row)
    source_object = await _source_object_for(adapter, creds, record_type)
    try:
        sample = await adapter.sample_records(creds=creds, source_object=source_object)
    except Exception as exc:  # noqa: BLE001 — surface the provider error, never 500
        raise HTTPException(status_code=502, detail=f"sample failed: {exc}"[:200])
    return RawSampleResponse(
        record_type=record_type, source_object=source_object,
        records=[RawSampleRecordOut(source_record_id=r.source_record_id, raw_payload=r.raw_payload) for r in sample],
    )


@router.post(
    "/connections/{connection_id}/datasets/{record_type}/unpacked-sample",
    response_model=UnpackedSampleResponse,
    summary="A provider sample run through the DRAFT map without persisting (the 'Unpacked' toggle)",
)
async def get_unpacked_sample(
    connection_id: uuid.UUID,
    record_type: str,
    body: DraftDefinitionRequest,
    auth: AuthContext = require_permission("orchestration:manage"),
    db: AsyncSession = Depends(get_db),
):
    _require_record_type(record_type)
    row = await _load_connection(db, auth, connection_id)
    adapter, creds = await _resolve_adapter(db, auth, row)
    source_object = await _source_object_for(adapter, creds, record_type)
    try:
        sample = await adapter.sample_records(creds=creds, source_object=source_object)
    except Exception as exc:  # noqa: BLE001 — surface the provider error, never 500
        raise HTTPException(status_code=502, detail=f"sample failed: {exc}"[:200])

    grain = next(g for g in _UNPACK_GRAINS if g.record_type == record_type)
    targets = _columns(grain.core) | _columns(grain.ext)
    # Transient (unpersisted) bindings drive the same _resolve the unpacker uses.
    draft = [
        CrmFieldMap(
            slot=b.slot, semantic_key=b.semantic_key, source_field=b.source_field,
            data_type=b.data_type, value_map=b.value_map,
        ) for b in body.bindings
    ]
    slot_to_key = {b.slot: b.semantic_key for b in body.bindings}
    rows = []
    for rec in sample:
        resolved = _resolve(rec.raw_payload, draft, targets)
        rows.append({slot_to_key.get(k, k): (None if v is None else str(v)) for k, v in resolved.items()})
    columns = [b.semantic_key for b in body.bindings]
    return UnpackedSampleResponse(record_type=record_type, columns=columns, rows=rows)


@router.get(
    "/connections/{connection_id}/datasets/{record_type}/filter-capabilities",
    response_model=FilterCapabilityResponse,
    summary="The provider-declared filterable fields, operators, and pushdown flag for a dataset",
)
async def get_filter_capabilities(
    connection_id: uuid.UUID,
    record_type: str,
    auth: AuthContext = require_permission("orchestration:manage"),
    db: AsyncSession = Depends(get_db),
):
    _require_record_type(record_type)
    row = await _load_connection(db, auth, connection_id)
    adapter, creds = await _resolve_adapter(db, auth, row)
    source_object = await _source_object_for(adapter, creds, record_type)
    cap = adapter.filter_capabilities(source_object)
    return FilterCapabilityResponse(
        record_type=record_type, source_object=cap.source_object,
        fields=[FilterableFieldOut(field=f.field, operators=list(f.operators), pushable=f.pushable) for f in cap.fields],
    )


@router.get(
    "/connections/{connection_id}/datasets/{record_type}/field-values",
    response_model=FieldValuesResponse,
    summary="Sample-derived distinct values of a source field (read-only, capped; for filter pickers)",
)
async def get_dataset_field_values(
    connection_id: uuid.UUID,
    record_type: str,
    field: str = Query(..., description="The source field name"),
    auth: AuthContext = require_permission("orchestration:manage"),
    db: AsyncSession = Depends(get_db),
):
    _require_record_type(record_type)
    row = await _load_connection(db, auth, connection_id)
    adapter, creds = await _resolve_adapter(db, auth, row)
    source_object = await _source_object_for(adapter, creds, record_type)
    try:
        values = await adapter.field_values(creds=creds, source_object=source_object, field=field)
    except Exception as exc:  # noqa: BLE001 — surface the provider error, never 500
        raise HTTPException(status_code=502, detail=f"field-values failed: {exc}"[:200])
    return FieldValuesResponse(field=field, values=values)


def _validate_draft_predicate(predicate: dict, allowed_fields: set[str]) -> None:
    """Parse the predicate and verify every referenced field is a real resolved-projection field."""
    from app.services.orchestration.predicate_contract import required_fields
    try:
        parse_predicate(predicate)
        referenced = set(required_fields(predicate))
    except PredicateError as exc:
        raise HTTPException(status_code=400, detail=f"invalid filter predicate: {exc}"[:300])
    unknown = sorted(referenced - allowed_fields)
    if unknown:
        raise HTTPException(
            status_code=400, detail=f"filter predicate references unknown fields: {unknown}"[:300]
        )


async def _upsert_definition(
    db: AsyncSession, *, tenant_id, app_id: str, connection_id, record_type: str,
    filter_predicate: dict | None, status: str | None = None, bump_version: bool = False,
) -> SourceDatasetDefinition:
    defn = await db.scalar(
        select(SourceDatasetDefinition).where(
            SourceDatasetDefinition.tenant_id == tenant_id,
            SourceDatasetDefinition.app_id == app_id,
            SourceDatasetDefinition.connection_id == connection_id,
            SourceDatasetDefinition.record_type == record_type,
        )
    )
    if defn is None:
        defn = SourceDatasetDefinition(
            id=uuid.uuid4(), tenant_id=tenant_id, app_id=app_id, connection_id=connection_id,
            record_type=record_type, status="draft", version=0,
        )
        db.add(defn)
    defn.filter_predicate = filter_predicate
    if status is not None:
        defn.status = status
    if bump_version:
        defn.version = (defn.version or 0) + 1
    await db.flush()
    return defn


@router.put(
    "/connections/{connection_id}/datasets/{record_type}/draft",
    response_model=DraftDefinitionResponse,
    summary="Save the in-progress field map + filter for a dataset (status stays draft)",
)
async def save_dataset_draft(
    connection_id: uuid.UUID,
    record_type: str,
    body: DraftDefinitionRequest,
    auth: AuthContext = require_permission("orchestration:manage"),
    db: AsyncSession = Depends(get_db),
):
    _require_record_type(record_type)
    row = await _load_connection(db, auth, connection_id)

    if body.filter_predicate is not None:
        target = grain_schema(record_type)
        allowed = {sc["target"] for sc in target["standard_columns"]} | {b.semantic_key for b in body.bindings}
        _validate_draft_predicate(body.filter_predicate, allowed)

    try:
        await publish_field_map(
            db, tenant_id=auth.tenant_id, app_id=row.app_id, connection_id=connection_id,
            record_type=record_type,
            bindings=[
                BindingInput(
                    slot=b.slot, semantic_key=b.semantic_key, source_field=b.source_field,
                    data_type=b.data_type, value_map=b.value_map, description=b.description,
                ) for b in body.bindings
            ],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    defn = await _upsert_definition(
        db, tenant_id=auth.tenant_id, app_id=row.app_id, connection_id=connection_id,
        record_type=record_type, filter_predicate=body.filter_predicate, status="draft",
    )
    return DraftDefinitionResponse(record_type=record_type, status=defn.status, version=defn.version)


@router.post(
    "/connections/{connection_id}/datasets/{record_type}/activate",
    response_model=ActivateResponse,
    summary="Activate a dataset: publish the map + filter, rebuild the resolved view, bump version",
)
async def activate_dataset(
    connection_id: uuid.UUID,
    record_type: str,
    body: ActivateRequest,  # noqa: ARG001 — record_type is the path param; body keeps the FE contract symmetric
    auth: AuthContext = require_permission("orchestration:manage"),
    db: AsyncSession = Depends(get_db),
):
    _require_record_type(record_type)
    row = await _load_connection(db, auth, connection_id)

    bindings = (await db.execute(
        select(CrmFieldMap).where(
            CrmFieldMap.tenant_id == auth.tenant_id,
            CrmFieldMap.app_id == row.app_id,
            CrmFieldMap.connection_id == connection_id,
            CrmFieldMap.record_type == record_type,
        )
    )).scalars().all()
    if not bindings:
        raise HTTPException(status_code=400, detail="no draft field map to activate")
    if record_type == "activity" and not any(b.slot == "lead_id" for b in bindings):
        raise HTTPException(
            status_code=400, detail="activity mapping requires a lead-link binding (a source field → lead_id)"
        )

    defn = await _upsert_definition(
        db, tenant_id=auth.tenant_id, app_id=row.app_id, connection_id=connection_id,
        record_type=record_type, filter_predicate=await _existing_predicate(db, auth, row.app_id, connection_id, record_type),
        status="active", bump_version=True,
    )

    grains = await rebuild_resolved_surfaces(
        db, tenant_id=auth.tenant_id, app_id=row.app_id, connection_id=connection_id
    )
    try:
        await validate_resolved_contract(db, tenant_id=auth.tenant_id, app_id=row.app_id)
    except Exception as exc:  # noqa: BLE001 — refuse a map that can't be served, never 500
        await db.rollback()
        raise HTTPException(status_code=400, detail=f"resolved-layer validation failed: {exc}"[:300])

    return ActivateResponse(
        record_type=record_type, status=defn.status, version=defn.version, resolved_grains=grains,
    )


async def _existing_predicate(db, auth, app_id, connection_id, record_type):
    return await db.scalar(
        select(SourceDatasetDefinition.filter_predicate).where(
            SourceDatasetDefinition.tenant_id == auth.tenant_id,
            SourceDatasetDefinition.app_id == app_id,
            SourceDatasetDefinition.connection_id == connection_id,
            SourceDatasetDefinition.record_type == record_type,
        )
    )


@router.get(
    "/connections/{connection_id}/datasets/{record_type}/preview",
    response_model=ResolvedPreviewResponse,
    summary="Filtered resolved dry-run — exactly what an activated dataset lands (reuses resolved_sample)",
)
async def get_dataset_preview(
    connection_id: uuid.UUID,
    record_type: str,
    auth: AuthContext = require_permission("orchestration:manage"),
    db: AsyncSession = Depends(get_db),
):
    _require_record_type(record_type)
    row = await _load_connection(db, auth, connection_id)
    columns, rows = await resolved_sample(
        db, tenant_id=auth.tenant_id, app_id=row.app_id, grain=record_type,
    )
    return ResolvedPreviewResponse(record_type=record_type, columns=columns, rows=rows)


@router.get(
    "/connections/{connection_id}/datasets/{record_type}/jobs",
    response_model=DatasetJobsResponse,
    summary="The ingestion chain jobs (sync→unpack→resolved→analytics) + active schedule for a dataset",
)
async def get_dataset_jobs(
    connection_id: uuid.UUID,
    record_type: str,
    auth: AuthContext = require_permission("orchestration:manage"),
    db: AsyncSession = Depends(get_db),
):
    from app.services.crm.crm_chain import CHAIN_JOB_TYPES

    _require_record_type(record_type)
    row = await _load_connection(db, auth, connection_id)

    candidates = (await db.execute(
        select(BackgroundJob).where(
            BackgroundJob.tenant_id == auth.tenant_id,
            BackgroundJob.app_id == row.app_id,
            BackgroundJob.job_type.in_(CHAIN_JOB_TYPES),
        ).order_by(BackgroundJob.created_at.desc()).limit(100)
    )).scalars().all()

    # Connection-keyed steps (sync/unpack/resolved) carry connection_id in params; the analytics
    # tail is app-scoped (no connection_id) and belongs to every dataset on the app. Keep both.
    conn_str = str(connection_id)
    jobs = [
        j for j in candidates
        if (j.params or {}).get("connection_id") in (None, conn_str)
    ][:50]

    # The dataset's recurring sync schedule. Prefer the definition's explicit ``schedule_id`` link;
    # fall back to the schedule_key convention (``{connection_id}:{record_type}`` on the sync job_type)
    # so a schedule created before the link is backfilled still surfaces.
    schedule: DatasetScheduleOut | None = None
    defn = await db.scalar(
        select(SourceDatasetDefinition).where(
            SourceDatasetDefinition.tenant_id == auth.tenant_id,
            SourceDatasetDefinition.app_id == row.app_id,
            SourceDatasetDefinition.connection_id == connection_id,
            SourceDatasetDefinition.record_type == record_type,
        )
    )
    sched = None
    if defn is not None and defn.schedule_id is not None:
        sched = await db.scalar(
            select(ScheduledJobDefinition).where(
                ScheduledJobDefinition.id == defn.schedule_id,
                ScheduledJobDefinition.tenant_id == auth.tenant_id,
            )
        )
    if sched is None:
        sched = await db.scalar(
            select(ScheduledJobDefinition).where(
                ScheduledJobDefinition.tenant_id == auth.tenant_id,
                ScheduledJobDefinition.app_id == row.app_id,
                ScheduledJobDefinition.job_type == "sync-crm-source",
                ScheduledJobDefinition.schedule_key == f"{connection_id}:{record_type}",
            )
        )
    if sched is not None:
        schedule = DatasetScheduleOut(
            id=str(sched.id), name=sched.name, cron=sched.cron, enabled=sched.enabled,
            next_check_at=sched.next_check_at, last_fire_at=sched.last_fire_at,
        )

    return DatasetJobsResponse(
        record_type=record_type,
        jobs=[
            ChainJobOut(
                id=str(j.id), job_type=j.job_type, status=j.status,
                created_at=j.created_at, started_at=j.started_at, completed_at=j.completed_at,
            ) for j in jobs
        ],
        schedule=schedule,
    )

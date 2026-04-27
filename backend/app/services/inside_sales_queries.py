"""Postgres-backed query services for Inside Sales collection serving."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.source_records import SourceCallRecord, SourceLeadRecord, SourceSyncRun
from app.services.inside_sales_dataset_resolver import (
    CallDatasetScope,
    InsideSalesCallFilters,
    InsideSalesLeadFilters,
    ResolvedDatasetPage,
)
from app.services.inside_sales_eval_linkage import (
    extract_inside_sales_eval_score,
    fetch_latest_eval_overlays,
)
from app.services.lsq_client import extract_lead_plan_fields

INSIDE_SALES_STALE_AFTER = timedelta(minutes=30)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _format_response_datetime(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _format_optional_response_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _format_response_datetime(value)


def _to_float(value: Decimal | float | int | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _call_sort_expression():
    return func.coalesce(SourceCallRecord.call_started_at, SourceCallRecord.created_on)


def _normalize_text_values(values: tuple[str, ...]) -> tuple[str, ...]:
    """Strip + lowercase + collapse whitespace for case-insensitive equality.

    Mirrors what `func.lower(col)` produces on the Postgres side, so callers
    can do `func.lower(col).in_(_normalize_text_values(values))`.
    """
    out: list[str] = []
    for value in values:
        if not value:
            continue
        normalized = " ".join(value.strip().lower().split())
        if normalized:
            out.append(normalized)
    return tuple(out)


def _build_call_filter_clauses(
    *,
    tenant_id: uuid.UUID,
    app_id: str,
    filters: InsideSalesCallFilters,
) -> list[Any]:
    clauses: list[Any] = [
        SourceCallRecord.tenant_id == tenant_id,
        SourceCallRecord.app_id == app_id,
    ]

    agent_names = _normalize_text_values(filters.agents)
    if agent_names:
        clauses.append(func.lower(SourceCallRecord.agent_name).in_(agent_names))

    call_prospect_ids = tuple(pid.strip() for pid in filters.prospect_ids if pid.strip())
    if call_prospect_ids:
        clauses.append(
            or_(*(SourceCallRecord.prospect_id.ilike(f"%{pid}%") for pid in call_prospect_ids))
        )

    if filters.direction:
        clauses.append(SourceCallRecord.direction == filters.direction)

    if filters.status:
        clauses.append(func.lower(SourceCallRecord.status) == filters.status.strip().lower())

    if filters.duration_min is not None:
        clauses.append(SourceCallRecord.duration_seconds >= filters.duration_min)

    if filters.duration_max is not None:
        clauses.append(SourceCallRecord.duration_seconds <= filters.duration_max)

    if filters.has_recording is True:
        clauses.append(SourceCallRecord.has_recording.is_(True))

    if filters.event_codes:
        clauses.append(SourceCallRecord.event_code.in_(filters.event_codes))

    return clauses


def build_call_filtered_query(
    *,
    tenant_id: uuid.UUID,
    app_id: str,
    filters: InsideSalesCallFilters,
) -> Select:
    return select(SourceCallRecord).where(
        *_build_call_filter_clauses(tenant_id=tenant_id, app_id=app_id, filters=filters)
    )


def build_call_listing_query(
    *,
    tenant_id: uuid.UUID,
    app_id: str,
    filters: InsideSalesCallFilters,
    page: int,
    page_size: int,
    scope: CallDatasetScope,
) -> Select:
    stmt = build_call_filtered_query(tenant_id=tenant_id, app_id=app_id, filters=filters).order_by(
        _call_sort_expression().desc(),
        SourceCallRecord.activity_id.desc(),
    )
    if scope == "all":
        return stmt
    offset = max(page - 1, 0) * page_size
    return stmt.offset(offset).limit(page_size)


def build_call_count_query(
    *,
    tenant_id: uuid.UUID,
    app_id: str,
    filters: InsideSalesCallFilters,
) -> Select:
    return (
        select(func.count())
        .select_from(SourceCallRecord)
        .where(*_build_call_filter_clauses(tenant_id=tenant_id, app_id=app_id, filters=filters))
    )


def _build_lead_filter_clauses(
    *,
    tenant_id: uuid.UUID,
    app_id: str,
    filters: InsideSalesLeadFilters,
) -> list[Any]:
    clauses: list[Any] = [
        SourceLeadRecord.tenant_id == tenant_id,
        SourceLeadRecord.app_id == app_id,
    ]

    agent_names = _normalize_text_values(filters.agents)
    if agent_names:
        clauses.append(func.lower(SourceLeadRecord.agent_name).in_(agent_names))

    stages = _normalize_text_values(filters.stage)
    if stages:
        clauses.append(func.lower(SourceLeadRecord.prospect_stage).in_(stages))

    conditions = tuple(c.strip() for c in filters.condition if c.strip())
    if conditions:
        clauses.append(
            or_(*(SourceLeadRecord.condition.ilike(f"%{condition}%") for condition in conditions))
        )

    cities = tuple(c.strip() for c in filters.city if c.strip())
    if cities:
        clauses.append(
            or_(*(SourceLeadRecord.city.ilike(f"%{city}%") for city in cities))
        )

    prospect_ids = tuple(pid.strip() for pid in filters.prospect_ids if pid.strip())
    if prospect_ids:
        clauses.append(
            or_(*(SourceLeadRecord.prospect_id.ilike(f"%{pid}%") for pid in prospect_ids))
        )

    phones = tuple(p.strip() for p in filters.phones if p.strip())
    if phones:
        # Digits-only compare so UI input like "+91 98-xxx" matches a stored
        # "+919800000000". Keep raw ilike as fallback for non-digit chars.
        phone_clauses = []
        phone_col = func.regexp_replace(
            func.coalesce(SourceLeadRecord.phone, ""), r"\D", "", "g"
        )
        for value in phones:
            digits = "".join(ch for ch in value if ch.isdigit())
            if digits:
                phone_clauses.append(phone_col.ilike(f"%{digits}%"))
            else:
                phone_clauses.append(SourceLeadRecord.phone.ilike(f"%{value}%"))
        if phone_clauses:
            clauses.append(or_(*phone_clauses))

    plan_names = tuple(name.strip() for name in filters.plan_names if name.strip())
    if plan_names:
        clauses.append(
            or_(*(SourceLeadRecord.plan_name.ilike(f"%{name}%") for name in plan_names))
        )

    if filters.mql_min is not None:
        clauses.append(SourceLeadRecord.mql_score >= filters.mql_min)

    if filters.q:
        needle = filters.q.strip()
        if needle:
            clauses.append(
                func.concat(
                    func.coalesce(SourceLeadRecord.first_name, ""),
                    " ",
                    func.coalesce(SourceLeadRecord.last_name, ""),
                    " ",
                    func.coalesce(SourceLeadRecord.phone, ""),
                ).ilike(f"%{needle}%")
            )

    return clauses


def build_lead_filtered_query(
    *,
    tenant_id: uuid.UUID,
    app_id: str,
    filters: InsideSalesLeadFilters,
) -> Select:
    return select(SourceLeadRecord).where(
        *_build_lead_filter_clauses(tenant_id=tenant_id, app_id=app_id, filters=filters)
    )


def build_lead_listing_query(
    *,
    tenant_id: uuid.UUID,
    app_id: str,
    filters: InsideSalesLeadFilters,
    page: int,
    page_size: int,
) -> Select:
    offset = max(page - 1, 0) * page_size
    return (
        build_lead_filtered_query(tenant_id=tenant_id, app_id=app_id, filters=filters)
        .order_by(SourceLeadRecord.created_on.desc(), SourceLeadRecord.prospect_id.desc())
        .offset(offset)
        .limit(page_size)
    )


def build_lead_count_query(
    *,
    tenant_id: uuid.UUID,
    app_id: str,
    filters: InsideSalesLeadFilters,
) -> Select:
    return (
        select(func.count())
        .select_from(SourceLeadRecord)
        .where(*_build_lead_filter_clauses(tenant_id=tenant_id, app_id=app_id, filters=filters))
    )


def map_call_listing_row(
    call: SourceCallRecord,
    *,
    eval_count: int = 0,
    eval_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "activityId": call.activity_id,
        "prospectId": call.prospect_id,
        "agentName": call.agent_name or "",
        "agentEmail": call.agent_email or "",
        "eventCode": call.event_code,
        "direction": call.direction,
        "status": call.status or "",
        "callStartTime": _format_response_datetime(call.call_started_at or call.created_on),
        "durationSeconds": call.duration_seconds,
        "recordingUrl": call.recording_url or "",
        "phoneNumber": call.phone_number or "",
        "displayNumber": call.display_number or "",
        "callNotes": call.call_notes or "",
        "callSessionId": call.call_session_id or "",
        "createdOn": _format_response_datetime(call.created_on),
        "lastEvalScore": extract_inside_sales_eval_score(eval_result),
        "evalCount": int(eval_count or 0),
    }


def map_lead_call_history_entry(call: SourceCallRecord) -> dict[str, Any]:
    """Project a stored call row into the dict shape consumed by the lead
    drilldown response and ``compute_drilldown_metrics``.

    Returned shape mirrors what ``normalize_activity`` used to emit, so
    downstream consumers do not need to branch on data source.
    """
    return {
        "activityId": call.activity_id,
        "callTime": _format_response_datetime(call.call_started_at or call.created_on),
        "agentName": call.agent_name or None,
        "durationSeconds": call.duration_seconds,
        "status": call.status or "",
        "recordingUrl": call.recording_url or None,
        "evalScore": None,
        "isCounseling": call.duration_seconds >= 600,
    }


def map_lead_listing_row(lead: SourceLeadRecord) -> dict[str, Any]:
    return {
        "prospectId": lead.prospect_id,
        "firstName": lead.first_name,
        "lastName": lead.last_name,
        "phone": lead.phone,
        "prospectStage": lead.prospect_stage,
        "city": lead.city,
        "ageGroup": lead.age_group,
        "condition": lead.condition,
        "hba1cBand": lead.hba1c_band,
        "intentToPay": lead.intent_to_pay,
        "agentName": lead.agent_name,
        "rnrCount": lead.rnr_count,
        "answeredCount": lead.answered_count,
        "totalDials": lead.total_dials,
        "connectRate": _to_float(lead.connect_rate),
        "frtSeconds": lead.frt_seconds,
        "leadAgeDays": lead.lead_age_days,
        "daysSinceLastContact": lead.days_since_last_contact,
        "mqlScore": lead.mql_score,
        "mqlSignals": lead.mql_signals,
        "createdOn": _format_response_datetime(lead.created_on),
        "lastActivityOn": _format_optional_response_datetime(lead.last_activity_on),
        "source": lead.source,
        "sourceCampaign": lead.source_campaign,
        "planName": lead.plan_name,
        # Full plan-purchase surface. Read from ``raw_payload`` rather than
        # per-field columns — every plan attribute other than ``plan_name``
        # is derived at response time.
        "plan": extract_lead_plan_fields(lead.raw_payload),
    }


async def list_calls_from_source(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    app_id: str,
    filters: InsideSalesCallFilters,
    page: int,
    page_size: int,
    scope: CallDatasetScope,
) -> ResolvedDatasetPage:
    total = int(
        (await db.execute(build_call_count_query(tenant_id=tenant_id, app_id=app_id, filters=filters)))
        .scalar_one()
        or 0
    )
    result = await db.execute(
        build_call_listing_query(
            tenant_id=tenant_id,
            app_id=app_id,
            filters=filters,
            page=page,
            page_size=page_size,
            scope=scope,
        )
    )
    calls = list(result.scalars().all())

    activity_ids = [call.activity_id for call in calls if call.activity_id]
    eval_map = await fetch_latest_eval_overlays(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        app_id=app_id,
        thread_ids=activity_ids,
    )

    records = []
    for call in calls:
        overlay = eval_map.get(call.activity_id)
        records.append(
            map_call_listing_row(
                call,
                eval_count=overlay.eval_count if overlay else 0,
                eval_result=overlay.latest_result if overlay else None,
            )
        )
    resolved_page_size = total if scope == "all" and total > 0 else page_size
    return ResolvedDatasetPage(
        records=records,
        total=total,
        page=1 if scope == "all" else page,
        page_size=resolved_page_size,
    )


async def list_leads_from_source(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    app_id: str,
    filters: InsideSalesLeadFilters,
    page: int,
    page_size: int,
) -> ResolvedDatasetPage:
    total = int(
        (await db.execute(build_lead_count_query(tenant_id=tenant_id, app_id=app_id, filters=filters)))
        .scalar_one()
        or 0
    )
    result = await db.execute(
        build_lead_listing_query(
            tenant_id=tenant_id,
            app_id=app_id,
            filters=filters,
            page=page,
            page_size=page_size,
        )
    )
    leads = list(result.scalars().all())
    return ResolvedDatasetPage(
        records=[map_lead_listing_row(lead) for lead in leads],
        total=total,
        page=page,
        page_size=page_size,
    )


async def get_lead_record(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    app_id: str,
    prospect_id: str,
) -> SourceLeadRecord | None:
    """Fetch one lead row from the synced mirror, or ``None`` if absent."""
    stmt = select(SourceLeadRecord).where(
        SourceLeadRecord.tenant_id == tenant_id,
        SourceLeadRecord.app_id == app_id,
        SourceLeadRecord.prospect_id == prospect_id,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def list_call_history_for_prospect(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    app_id: str,
    prospect_id: str,
    limit: int,
) -> tuple[list[SourceCallRecord], bool]:
    """Return up to ``limit`` most-recent calls for the prospect.

    The boolean is ``True`` when the prospect has more than ``limit``
    matching rows. Implemented via ``LIMIT limit + 1`` so we avoid an
    extra ``COUNT`` round trip purely to set the flag.
    """
    stmt = (
        select(SourceCallRecord)
        .where(
            SourceCallRecord.tenant_id == tenant_id,
            SourceCallRecord.app_id == app_id,
            SourceCallRecord.prospect_id == prospect_id,
        )
        .order_by(_call_sort_expression())
        .limit(limit + 1)
    )
    rows = list((await db.execute(stmt)).scalars().all())
    if len(rows) > limit:
        return rows[:limit], True
    return rows, False


async def get_collection_sync_status(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    app_id: str,
    source_family: str,
) -> dict[str, Any]:
    """Durable freshness signal read straight from ``source_sync_runs``.

    Returns the most recent success, the most recent attempt, and whether a
    sync is in progress right now — three independent signals the UI needs
    to decide between "up-to-date", "refreshing", "last sync failed", and
    "never synced".
    """
    latest_successful = await db.scalar(
        select(SourceSyncRun)
        .where(
            SourceSyncRun.tenant_id == tenant_id,
            SourceSyncRun.app_id == app_id,
            SourceSyncRun.source_family == source_family,
            SourceSyncRun.status == "completed",
        )
        .order_by(SourceSyncRun.completed_at.desc(), SourceSyncRun.created_at.desc())
        .limit(1)
    )
    latest_attempt = await db.scalar(
        select(SourceSyncRun)
        .where(
            SourceSyncRun.tenant_id == tenant_id,
            SourceSyncRun.app_id == app_id,
            SourceSyncRun.source_family == source_family,
        )
        .order_by(SourceSyncRun.started_at.desc().nullslast(), SourceSyncRun.created_at.desc())
        .limit(1)
    )
    in_progress = await db.scalar(
        select(SourceSyncRun.id)
        .where(
            SourceSyncRun.tenant_id == tenant_id,
            SourceSyncRun.app_id == app_id,
            SourceSyncRun.source_family == source_family,
            SourceSyncRun.status == "running",
        )
        .limit(1)
    )
    return {
        "lastSuccessAt": latest_successful.completed_at if latest_successful else None,
        "lastAttemptAt": (
            (latest_attempt.started_at or latest_attempt.created_at)
            if latest_attempt
            else None
        ),
        "lastStatus": latest_attempt.status if latest_attempt else None,
        "lastError": latest_attempt.error_message if latest_attempt else None,
        "syncInProgress": in_progress is not None,
    }


async def get_collection_freshness(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    app_id: str,
    source_family: str,
) -> dict[str, Any]:
    latest_successful = await db.scalar(
        select(SourceSyncRun)
        .where(
            SourceSyncRun.tenant_id == tenant_id,
            SourceSyncRun.app_id == app_id,
            SourceSyncRun.source_family == source_family,
            SourceSyncRun.status == "completed",
        )
        .order_by(SourceSyncRun.completed_at.desc(), SourceSyncRun.created_at.desc())
        .limit(1)
    )
    sync_in_progress = await db.scalar(
        select(SourceSyncRun.id)
        .where(
            SourceSyncRun.tenant_id == tenant_id,
            SourceSyncRun.app_id == app_id,
            SourceSyncRun.source_family == source_family,
            SourceSyncRun.status == "running",
        )
        .limit(1)
    )
    last_synced_at = latest_successful.completed_at if latest_successful else None
    stale = last_synced_at is None or (_utc_now() - last_synced_at > INSIDE_SALES_STALE_AFTER)
    return {
        "lastSyncedAt": last_synced_at,
        "syncInProgress": sync_in_progress is not None,
        "stale": stale,
    }


_SUGGESTION_FIELDS: dict[tuple[str, str], Any] = {
    ("leads", "prospect_id"): SourceLeadRecord.prospect_id,
    ("leads", "phone"): SourceLeadRecord.phone,
    ("leads", "agent_name"): SourceLeadRecord.agent_name,
    ("leads", "city"): SourceLeadRecord.city,
    ("leads", "stage"): SourceLeadRecord.prospect_stage,
    ("leads", "plan_name"): SourceLeadRecord.plan_name,
    ("calls", "prospect_id"): SourceCallRecord.prospect_id,
    ("calls", "agent_name"): SourceCallRecord.agent_name,
}


def _suggestion_model_for(source_family: str) -> Any:
    if source_family == "leads":
        return SourceLeadRecord
    if source_family == "calls":
        return SourceCallRecord
    raise ValueError(f"unsupported source_family for suggestions: {source_family!r}")


async def list_collection_suggestions(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    app_id: str,
    source_family: str,
    field: str,
    query: str,
    limit: int,
) -> list[str]:
    """Distinct values of ``field`` for the collection, prefix-filtered by
    ``query``, tenant/app-scoped. Used to feed type-ahead filter dropdowns.

    ``field`` is validated against a fixed whitelist so this can never be
    steered into reading arbitrary columns. The same raw column the listing
    query matches against is read here, so what the user sees in the
    dropdown is exactly what filtering matches.
    """
    column = _SUGGESTION_FIELDS.get((source_family, field))
    if column is None:
        raise ValueError(
            f"unsupported suggestion field: source_family={source_family!r}, field={field!r}"
        )
    model = _suggestion_model_for(source_family)

    stmt = (
        select(column)
        .where(
            model.tenant_id == tenant_id,
            model.app_id == app_id,
            column.is_not(None),
            column != "",
        )
        .distinct()
        .order_by(column)
        .limit(limit)
    )

    needle = (query or "").strip()
    if needle:
        if field == "phone":
            digits = "".join(ch for ch in needle if ch.isdigit())
            if digits:
                stmt = stmt.where(
                    func.regexp_replace(column, r"\D", "", "g").ilike(f"%{digits}%")
                )
            else:
                stmt = stmt.where(column.ilike(f"%{needle}%"))
        else:
            stmt = stmt.where(column.ilike(f"%{needle}%"))

    result = await db.execute(stmt)
    return [value for value in result.scalars().all() if value]


async def prune_rows_older_than(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    app_id: str,
    source_family: str,
    cutoff: datetime,
) -> int:
    """Delete synced source rows with `created_on < cutoff`.

    STRICTLY scoped to (tenant_id, app_id, source_family) — this is a
    tenant-isolation guarantee, not an optimization. Called only by
    scheduled `sync-external-source` runs (§PR4); on-demand syncs never
    prune.

    Returns the number of rows deleted.
    """
    if source_family == "calls":
        model = SourceCallRecord
    elif source_family == "leads":
        model = SourceLeadRecord
    else:
        raise ValueError(f"unsupported source_family for prune: {source_family!r}")

    stmt = delete(model).where(
        model.tenant_id == tenant_id,
        model.app_id == app_id,
        model.created_on.is_not(None),
        model.created_on < cutoff,
    )
    result = await db.execute(stmt)
    return int(result.rowcount or 0)

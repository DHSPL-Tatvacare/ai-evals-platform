"""Admin endpoints for mirror->fact mapping operator-disable plumbing.

Phase 3 of docs/plans/2026-05-12-analytics-facts-canonical-manifest-thinning.md.
Mounted under ``/api/admin/analytics``. Gated on the ``analytics:admin``
permission (added in the same commit). Mutations write breadcrumb rows into
``analytics.log_fact_population_run`` so operator actions are auditable.

No new permission tier; ``analytics:admin`` lives in the existing ``cost``
permission group because mapping-state ops are analytics-pipeline admin work
adjacent to cost-rollup admin (closest existing precedent).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import AuthContext
from app.auth.permissions import require_permission
from app.database import get_db
from app.models.analytics_log import LogFactPopulationRun
from app.models.analytics_mapping_state import MappingState
from app.models.job import BackgroundJob
from app.schemas.base import CamelModel
from app.services.analytics import mirror_to_fact_sync
from app.services.analytics.backfill_facts_from_mirror_job import (
    DEFAULT_BATCH_SIZE,
    MAX_BATCH_SIZE,
    MIN_BATCH_SIZE,
    SUPPORTED_TARGET_FACT,
)
from app.services.analytics.backfill_lead_signals_job import (
    DEFAULT_BATCH_SIZE as LEAD_SIGNALS_DEFAULT_BATCH_SIZE,
    DEFAULT_COST_BUDGET_USD as LEAD_SIGNALS_DEFAULT_COST_BUDGET_USD,
    DEFAULT_MAX_LEADS as LEAD_SIGNALS_DEFAULT_MAX_LEADS,
    DEFAULT_PER_LEAD_COST_USD as LEAD_SIGNALS_DEFAULT_PER_LEAD_COST_USD,
    DEFAULT_PROMPT_TOKEN_ESTIMATE as LEAD_SIGNALS_DEFAULT_PROMPT_TOKEN_ESTIMATE,
    MAX_BATCH_SIZE as LEAD_SIGNALS_MAX_BATCH_SIZE,
    MAX_MAX_LEADS as LEAD_SIGNALS_MAX_MAX_LEADS,
    MIN_BATCH_SIZE as LEAD_SIGNALS_MIN_BATCH_SIZE,
    MIN_MAX_LEADS as LEAD_SIGNALS_MIN_MAX_LEADS,
    count_candidate_leads,
    estimate_cost,
    parse_request as parse_lead_signals_request,
)
from app.services.analytics.mirror_to_fact_mapper import MirrorToFactMapper


router = APIRouter(prefix="/api/admin/analytics", tags=["admin", "analytics"])


# ── schemas ─────────────────────────────────────────────────────────────


class MappingStateRow(CamelModel):
    id: uuid.UUID
    app_id: str
    source_table: str
    target_fact: str
    activity_type: str
    enabled: bool
    disabled_at: datetime | None = None
    disabled_by_user_id: uuid.UUID | None = None
    disabled_reason: str | None = None
    updated_at: datetime


class MappingStateListResponse(CamelModel):
    mappings: list[MappingStateRow]


class DisableMappingRequest(CamelModel):
    reason: str = Field(
        ...,
        min_length=3,
        description=(
            "Operator-visible reason for disabling. Surfaced in "
            "log_fact_population_run.metadata so the audit trail stays "
            "self-describing."
        ),
    )


class BackfillFactsRequest(CamelModel):
    """Request body for ``POST /api/admin/analytics/backfill-facts``.

    The mapping registry is the source of truth for allowed (app_id,
    source_table, activity_type) tuples — operators cannot point this at an
    arbitrary table. ``target_fact`` is gated to ``analytics.fact_lead_activity``
    in Phase 4; signal-fact (Phase 5) and stage-transition-fact (Phase 6)
    backfills will ship as their own job types, not as new targets for this
    endpoint.
    """

    app_id: str = Field(..., min_length=1, max_length=50)
    source_table: str = Field(..., min_length=1, max_length=120)
    activity_type: str = Field(..., min_length=1, max_length=64)
    started_after: datetime | None = None
    ended_before: datetime | None = None
    batch_size: int = Field(
        default=DEFAULT_BATCH_SIZE,
        ge=MIN_BATCH_SIZE,
        le=MAX_BATCH_SIZE,
        description=(
            f"Mirror rows per batch. Clamped to "
            f"[{MIN_BATCH_SIZE}, {MAX_BATCH_SIZE}] to bound per-batch DB cost."
        ),
    )

    @field_validator("ended_before")
    @classmethod
    def _ended_after_started(
        cls, value: datetime | None, info: Any  # noqa: ANN401
    ) -> datetime | None:
        started = info.data.get("started_after") if info is not None else None
        if value is not None and started is not None and value <= started:
            raise ValueError("ended_before must be strictly after started_after")
        return value


class BackfillFactsResponse(CamelModel):
    job_id: uuid.UUID
    mapping_id: uuid.UUID
    target_fact: str


class BackfillLeadSignalsRequest(CamelModel):
    """Request body for ``POST /api/admin/analytics/backfill-lead-signals``.

    Phase 5 of the analytics-facts-canonical-manifest-thinning plan.
    CRM-agnostic — the same endpoint serves inside-sales today and any
    future CRM-backed app by passing the new app_id.

    ``dry_run=true`` returns the lead count and estimated cost without
    enqueuing a job. ``cost_budget_usd`` is the hard ceiling — the live
    run refuses to start if the projected cost exceeds it; raise the budget
    or tighten the window to proceed.
    """

    app_id: str = Field(..., min_length=1, max_length=50)
    dry_run: bool = Field(
        default=False,
        description=(
            "When true, returns lead count + estimated cost and skips the "
            "job submission. No LLM calls, no fact rows written."
        ),
    )
    max_leads: int = Field(
        default=LEAD_SIGNALS_DEFAULT_MAX_LEADS,
        ge=LEAD_SIGNALS_MIN_MAX_LEADS,
        le=LEAD_SIGNALS_MAX_MAX_LEADS,
    )
    batch_size: int = Field(
        default=LEAD_SIGNALS_DEFAULT_BATCH_SIZE,
        ge=LEAD_SIGNALS_MIN_BATCH_SIZE,
        le=LEAD_SIGNALS_MAX_BATCH_SIZE,
    )
    cost_budget_usd: float = Field(
        default=LEAD_SIGNALS_DEFAULT_COST_BUDGET_USD,
        gt=0,
        description=(
            "Hard USD ceiling for projected cost. Live run refuses to start "
            "if estimate exceeds this value."
        ),
    )
    started_after: datetime | None = None
    ended_before: datetime | None = None

    @field_validator("ended_before")
    @classmethod
    def _ended_after_started_lead_signals(
        cls, value: datetime | None, info: Any  # noqa: ANN401
    ) -> datetime | None:
        started = info.data.get("started_after") if info is not None else None
        if value is not None and started is not None and value <= started:
            raise ValueError("ended_before must be strictly after started_after")
        return value


class BackfillLeadSignalsDryRunResponse(CamelModel):
    """Dry-run path response. No job is enqueued."""

    dry_run: bool = True
    app_id: str
    lead_count: int
    estimated_cost_usd: float
    per_lead_cost_usd: float
    cost_budget_usd: float
    prompt_token_estimate: int
    over_budget: bool


class BackfillLeadSignalsResponse(CamelModel):
    """Live-run path response — job enqueued at 202."""

    job_id: uuid.UUID
    estimated_cost_usd: float
    cost_budget_usd: float
    lead_count: int
    app_id: str


# ── helpers ─────────────────────────────────────────────────────────────


def _row_to_response(row: MappingState) -> MappingStateRow:
    return MappingStateRow(
        id=row.id,
        app_id=row.app_id,
        source_table=row.source_table,
        target_fact=row.target_fact,
        activity_type=row.activity_type,
        enabled=row.enabled,
        disabled_at=row.disabled_at,
        disabled_by_user_id=row.disabled_by_user_id,
        disabled_reason=row.disabled_reason,
        updated_at=row.updated_at,
    )


async def _write_log_row(
    db: AsyncSession,
    *,
    mapping: MappingState,
    status: str,
    user_id: uuid.UUID,
    reason: str | None,
) -> None:
    db.add(
        LogFactPopulationRun(
            tenant_id=_log_tenant_id(),
            app_id=mapping.app_id,
            job_type="mapping_admin",
            status=status,
            metadata_={
                "mapping_id": str(mapping.id),
                "mapping_key": [
                    mapping.app_id,
                    mapping.source_table,
                    mapping.target_fact,
                    mapping.activity_type,
                ],
                "user_id": str(user_id),
                "reason": reason,
            },
        )
    )


def _log_tenant_id() -> uuid.UUID:
    # ``log_fact_population_run.tenant_id`` is NOT NULL with an FK to
    # ``platform.tenants``. Mapping state is not tenant-scoped, so we tag
    # admin events against the platform-system tenant.
    from app.constants import SYSTEM_TENANT_ID
    return SYSTEM_TENANT_ID


# ── routes ──────────────────────────────────────────────────────────────


@router.get("/mappings", response_model=MappingStateListResponse)
async def list_mappings(
    auth: AuthContext = require_permission("analytics:admin"),
    db: AsyncSession = Depends(get_db),
) -> MappingStateListResponse:
    _ = auth
    rows = (
        (
            await db.execute(
                select(MappingState).order_by(
                    MappingState.app_id,
                    MappingState.source_table,
                    MappingState.activity_type,
                )
            )
        )
        .scalars()
        .all()
    )
    return MappingStateListResponse(
        mappings=[_row_to_response(r) for r in rows]
    )


@router.post("/mappings/{mapping_id}/disable", response_model=MappingStateRow)
async def disable_mapping(
    mapping_id: uuid.UUID,
    body: DisableMappingRequest,
    auth: AuthContext = require_permission("analytics:admin"),
    db: AsyncSession = Depends(get_db),
) -> MappingStateRow:
    row = await _load_or_404(db, mapping_id)
    if not row.enabled:
        # Idempotent — operator hitting disable twice shouldn't 409.
        return _row_to_response(row)
    row.enabled = False
    row.disabled_at = datetime.now(timezone.utc)
    row.disabled_by_user_id = auth.user_id
    row.disabled_reason = body.reason
    await _write_log_row(
        db,
        mapping=row,
        status="mapping_disabled",
        user_id=auth.user_id,
        reason=body.reason,
    )
    await db.commit()
    await db.refresh(row)
    # Operator intervention is the natural reset point for the in-memory
    # failure counter. Without this, a disable->investigate->re-enable cycle
    # leaves the counter at 3 and the next single projection failure
    # immediately writes another ``blocking_sync`` row. Reset on both
    # disable and enable.
    _reset_counter_for_row(row)
    return _row_to_response(row)


@router.post("/mappings/{mapping_id}/enable", response_model=MappingStateRow)
async def enable_mapping(
    mapping_id: uuid.UUID,
    auth: AuthContext = require_permission("analytics:admin"),
    db: AsyncSession = Depends(get_db),
) -> MappingStateRow:
    row = await _load_or_404(db, mapping_id)
    if row.enabled:
        return _row_to_response(row)
    row.enabled = True
    row.disabled_at = None
    row.disabled_by_user_id = None
    row.disabled_reason = None
    await _write_log_row(
        db,
        mapping=row,
        status="mapping_enabled",
        user_id=auth.user_id,
        reason=None,
    )
    await db.commit()
    await db.refresh(row)
    _reset_counter_for_row(row)
    return _row_to_response(row)


def _reset_counter_for_row(row: MappingState) -> None:
    """Reset the process-local failure counter for this mapping only.

    Looks the mapping up in the registry; if it's not registered (mapping
    file deleted, row stale) we silently no-op rather than fail an admin
    action. The next sync would refuse to load that mapping anyway.
    """
    try:
        mapping = MirrorToFactMapper.default().for_table(
            row.app_id, row.source_table, row.activity_type
        )
    except KeyError:
        return
    mirror_to_fact_sync.reset_failure_counter(mapping)


@router.post(
    "/backfill-facts",
    response_model=BackfillFactsResponse,
    status_code=202,
)
async def submit_backfill_facts(
    body: BackfillFactsRequest,
    auth: AuthContext = require_permission("analytics:admin"),
    db: AsyncSession = Depends(get_db),
) -> BackfillFactsResponse:
    """Submit a ``backfill-facts-from-mirror`` job for one mapping.

    Phase 4 only supports projection into ``analytics.fact_lead_activity``;
    signal and stage-transition backfills will land as their own job types
    in Phases 5/6. Validation refuses anything else with a stable 400 detail
    so future callers can branch on it.

    Idempotency: this endpoint does NOT use ``Idempotency-Key`` semantics
    because backfills are explicitly safe to replay (ON CONFLICT DO UPDATE
    re-projects from the current mirror state). Operators wanting to dedupe
    in-flight runs should check the existing ``mapping_id``'s open log row
    via the mappings list endpoint first.
    """
    # Mapper lookup is the allowlist. An unknown tuple = 400 with a stable
    # detail string. We don't fall through to the job runner's later
    # KeyError because that would only surface as a generic 500.
    try:
        mapping = MirrorToFactMapper.default().for_table(
            body.app_id, body.source_table, body.activity_type
        )
    except KeyError:
        raise HTTPException(
            status_code=400,
            detail=(
                f"no mirror->fact mapping registered for "
                f"app_id={body.app_id!r}, source_table={body.source_table!r}, "
                f"activity_type={body.activity_type!r}"
            ),
        )

    if mapping.target_fact != SUPPORTED_TARGET_FACT:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Phase 4 backfill only supports target_fact="
                f"{SUPPORTED_TARGET_FACT!r}; mapping {mapping.key!r} targets "
                f"{mapping.target_fact!r}"
            ),
        )

    # The mapping_state row is the cross-reference operators see in the
    # mappings list — we surface its id in the response so the UI can link
    # the new job to the row that controls disable/enable.
    state_row = await db.scalar(
        select(MappingState).where(
            MappingState.app_id == mapping.app_id,
            MappingState.source_table == mapping.source_table,
            MappingState.target_fact == mapping.target_fact,
            MappingState.activity_type == mapping.activity_type,
        )
    )
    if state_row is None:
        # A registered mapping without a state row means the Phase 2 seed
        # migration was skipped — refuse rather than crash inside the job.
        raise HTTPException(
            status_code=500,
            detail=(
                f"mapping_state row missing for {mapping.key!r}; "
                "seed migration 0039 must run before backfill"
            ),
        )

    # NOTE: we do NOT reject when ``enabled=False``. A disabled mapping
    # means same-tx sync runs mirror-only; backfill is exactly the recovery
    # path the operator needs to close the resulting gap. The plan
    # (§5.2 "Backfill replay safety") makes this explicit.

    params: dict[str, Any] = {
        "app_id": body.app_id,
        "source_table": body.source_table,
        "activity_type": body.activity_type,
        "started_after": (
            body.started_after.isoformat() if body.started_after else None
        ),
        "ended_before": (
            body.ended_before.isoformat() if body.ended_before else None
        ),
        "batch_size": body.batch_size,
        # Carry submitter info into params for parity with the existing
        # job-submission pattern (jobs.py:submit_job injects tenant/user
        # automatically; admin endpoints write the row directly so we
        # mirror the fields the worker reads).
        "tenant_id": str(auth.tenant_id),
        "user_id": str(auth.user_id),
    }

    # Pre-allocate the job id so the response carries it without depending
    # on flush()-time default population. The ORM ``default=uuid.uuid4`` only
    # fires inside the SQLAlchemy flush path; pre-allocating makes the id
    # available immediately and also lets the worker reference itself in
    # downstream log rows before flush.
    job_id = uuid.uuid4()
    job = BackgroundJob(
        id=job_id,
        job_type="backfill-facts-from-mirror",
        app_id=body.app_id,
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        # ``bulk`` queue: this can scan tens of thousands of rows and
        # shouldn't compete with interactive analytics requests.
        priority=520,
        queue_class="bulk",
        # The handler is idempotent and the worker retries transient failures
        # via ``retry_safe=True``; 3 attempts matches populate-analytics.
        max_attempts=3,
        params=params,
    )
    db.add(job)
    await db.flush()
    await db.commit()

    return BackfillFactsResponse(
        job_id=job_id,
        mapping_id=state_row.id,
        target_fact=mapping.target_fact,
    )


@router.post(
    "/backfill-lead-signals",
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        200: {"description": "Dry-run result (no job enqueued)"},
        202: {"description": "Job enqueued"},
    },
)
async def submit_backfill_lead_signals(
    body: BackfillLeadSignalsRequest,
    response: Response,
    auth: AuthContext = require_permission("analytics:admin"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Submit a ``backfill-lead-signals`` job for one ``(tenant, app_id)``.

    Dry-run (``dry_run=true``) returns a 200 with ``BackfillLeadSignalsDryRunResponse``
    containing the count of candidate leads and the estimated USD cost; no
    job is enqueued. Live run (``dry_run=false``) returns a 202 with
    ``BackfillLeadSignalsResponse`` and enqueues the job. The live run
    refuses to start (HTTP 400) if the projected cost exceeds
    ``cost_budget_usd``.

    Rollback: ``DELETE FROM analytics.fact_lead_signal WHERE sync_run_id = '<id>'``.
    The job writes a ``LogCrmSourceSync`` row whose id is the ``sync_run_id``;
    the response surfaces the job id, and the resulting BackgroundJob row
    persists the sync_run_id once the worker starts running.
    """
    # Validate via the same parser the worker uses so the admin endpoint and
    # the job loader can never drift on bounds / required fields.
    params: dict[str, Any] = {
        "app_id": body.app_id,
        "dry_run": body.dry_run,
        "max_leads": body.max_leads,
        "batch_size": body.batch_size,
        "cost_budget_usd": body.cost_budget_usd,
        "started_after": (
            body.started_after.isoformat() if body.started_after else None
        ),
        "ended_before": (
            body.ended_before.isoformat() if body.ended_before else None
        ),
    }
    try:
        parsed = parse_lead_signals_request(params)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Dry-run is in-line — no job, no LLM, no rows. The worker also supports
    # a dry-run path so scheduled callers can probe without a roundtrip; the
    # endpoint version short-circuits to avoid the BackgroundJob row entirely
    # for the most common operator workflow.
    if parsed.dry_run:
        # Dry-run is informational, not a job submission. Override the
        # route-level 202 default so the status code matches semantics
        # (200 = here is the answer; 202 = work accepted for async).
        response.status_code = status.HTTP_200_OK
        lead_count = await count_candidate_leads(
            db, tenant_id=auth.tenant_id, request=parsed
        )
        estimated = estimate_cost(lead_count)
        return BackfillLeadSignalsDryRunResponse(
            app_id=parsed.app_id,
            lead_count=lead_count,
            estimated_cost_usd=estimated,
            per_lead_cost_usd=LEAD_SIGNALS_DEFAULT_PER_LEAD_COST_USD,
            cost_budget_usd=parsed.cost_budget_usd,
            prompt_token_estimate=LEAD_SIGNALS_DEFAULT_PROMPT_TOKEN_ESTIMATE,
            over_budget=estimated > parsed.cost_budget_usd,
        )

    # Pre-flight budget gate so a rejected run leaves no audit clutter.
    lead_count = await count_candidate_leads(
        db, tenant_id=auth.tenant_id, request=parsed
    )
    estimated = estimate_cost(lead_count)
    if estimated > parsed.cost_budget_usd:
        raise HTTPException(
            status_code=400,
            detail=(
                f"estimated cost ${estimated:.2f} exceeds cost_budget_usd "
                f"${parsed.cost_budget_usd:.2f}; raise the budget or tighten "
                f"the window"
            ),
        )

    job_id = uuid.uuid4()
    job = BackgroundJob(
        id=job_id,
        job_type="backfill-lead-signals",
        app_id=body.app_id,
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        priority=520,
        queue_class="bulk",
        max_attempts=3,
        params={**params, "tenant_id": str(auth.tenant_id), "user_id": str(auth.user_id)},
    )
    db.add(job)
    await db.flush()
    await db.commit()

    return BackfillLeadSignalsResponse(
        job_id=job_id,
        estimated_cost_usd=estimated,
        cost_budget_usd=parsed.cost_budget_usd,
        lead_count=lead_count,
        app_id=parsed.app_id,
    )


async def _load_or_404(db: AsyncSession, mapping_id: uuid.UUID) -> MappingState:
    row = (
        (
            await db.execute(
                select(MappingState).where(MappingState.id == mapping_id)
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Mapping not found")
    return row



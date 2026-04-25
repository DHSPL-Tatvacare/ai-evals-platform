"""Jobs API - submit, list, check status, cancel background jobs."""
from uuid import UUID
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy import select, desc, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone

from app.auth.app_scope import ensure_registered_app_access
from app.auth.context import AuthContext, get_auth_context
from app.auth.permissions import require_permission
from app.database import get_db
from app.models.job import Job
from app.models.eval_run import EvalRun
from app.schemas.job import JobCreate, JobResponse

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

# Idempotency keys are opaque client tokens. Cap the length at the column
# width and reject obvious garbage so the unique-index path is the only
# place we ever care about collision semantics.
_IDEMPOTENCY_KEY_MAX_LEN = 120


def _normalize_idempotency_key(raw: str | None) -> str | None:
    if raw is None:
        return None
    key = raw.strip()
    if not key:
        return None
    if len(key) > _IDEMPOTENCY_KEY_MAX_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"Idempotency-Key must be <= {_IDEMPOTENCY_KEY_MAX_LEN} chars",
        )
    return key


async def _maybe_chain_boundary_sync(
    db: AsyncSession,
    *,
    auth: AuthContext,
    job_params: dict,
) -> UUID | None:
    """For evaluate-inside-sales: if the requested date range is outside the
    mirrored source coverage, enqueue (or dedup) a date_range sync first.

    Returns None when the selected range is already mirrored, when the eval
    uses specific call IDs (date filters are bypassed there), and for payloads
    that do not carry a usable date range.
    """
    from app.services.inside_sales_boundary import (
        find_or_enqueue_ondemand_sync,
        get_mirrored_coverage_window,
    )

    call_selection = job_params.get("call_selection") or {}
    date_from = str(call_selection.get("date_from") or "").strip()
    date_to = str(call_selection.get("date_to") or "").strip()
    selection_mode = str(call_selection.get("selection_mode") or "all").strip().lower()
    source_family = str(call_selection.get("source_family") or "calls").strip() or "calls"
    if selection_mode == "specific" or not date_from or not date_to:
        return None

    coverage_window = await get_mirrored_coverage_window(
        db,
        tenant_id=auth.tenant_id,
        app_id="inside-sales",
        source_family=source_family,
        date_from=date_from,
        date_to=date_to,
    )
    if not coverage_window.requires_sync:
        return None

    event_codes = call_selection.get("event_codes")
    event_codes_str = event_codes if isinstance(event_codes, str) else None
    sync_job = await find_or_enqueue_ondemand_sync(
        db,
        tenant_id=auth.tenant_id,
        app_id="inside-sales",
        source_family=source_family,
        date_from=date_from,
        date_to=date_to,
        user_id=auth.user_id,
        event_codes=event_codes_str,
    )
    return sync_job.id


@router.post("", response_model=JobResponse, status_code=201)
async def submit_job(
    body: JobCreate,
    response: Response,
    auth: AuthContext = require_permission('evaluation:run'),
    db: AsyncSession = Depends(get_db),
    idempotency_key_header: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Submit a new background job.

    Injects auth context into params for downstream runners. Two pre-write
    guards run before any DB work:

    1. ``job_type`` must have a registered handler. Submitting an unknown
       type used to succeed and then fail at the worker; now it 422s at the
       boundary where the client can see it.
    2. If ``Idempotency-Key`` is supplied, a prior ``(tenant_id, user_id, key)``
       match is returned verbatim with status 200 instead of inserting a
       duplicate. A race between two concurrent replays is handled by
       catching the partial-unique-index violation and re-selecting.
       Scope is per-user (not per-tenant) because ``GET /api/jobs/{id}``
       is user-filtered — returning another user's job here would be a
       cross-user read and also unusable (404 on next fetch).
    """
    from app.services.job_worker import JOB_HANDLERS, get_job_submission_metadata

    if body.job_type not in JOB_HANDLERS:
        # 422 because the payload is semantically invalid (unknown type),
        # not malformed. Stable detail string so clients can branch on it.
        raise HTTPException(
            status_code=422,
            detail=f"Unknown job_type: {body.job_type!r}",
        )

    idempotency_key = _normalize_idempotency_key(idempotency_key_header)
    if idempotency_key is not None:
        existing = await db.scalar(
            select(Job).where(
                Job.tenant_id == auth.tenant_id,
                Job.user_id == auth.user_id,
                Job.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            # Replay: mirror the original submission. 200 (not 201) so the
            # client can distinguish "already here" from "just created".
            response.status_code = 200
            return existing

    job_data = body.model_dump()
    job_params = dict(job_data.get("params") or {})

    try:
        metadata = get_job_submission_metadata(job_data["job_type"], job_params)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    await ensure_registered_app_access(
        db,
        auth,
        metadata["app_id"],
        required=True,
        param_name="app_id",
    )

    # Inject auth context into params — runners read this
    job_params["tenant_id"] = str(auth.tenant_id)
    job_params["user_id"] = str(auth.user_id)
    if metadata["app_id"]:
        job_params["app_id"] = metadata["app_id"]
    job_data["params"] = job_params

    # § PR5 boundary chaining for evaluate-inside-sales: if the filter window
    # falls outside mirrored source coverage, enqueue a scoped on-demand sync
    # first and chain this eval job to it via `depends_on_job_id`. Dedup
    # against any queued/running sync that already covers the same window.
    depends_on_job_id = None
    if job_data["job_type"] == "evaluate-inside-sales":
        depends_on_job_id = await _maybe_chain_boundary_sync(
            db, auth=auth, job_params=job_params
        )

    job = Job(
        **job_data,
        app_id=metadata["app_id"],
        priority=metadata["priority"],
        queue_class=metadata["queue_class"],
        max_attempts=metadata["max_attempts"],
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        depends_on_job_id=depends_on_job_id,
        idempotency_key=idempotency_key,
    )
    db.add(job)
    try:
        await db.commit()
    except IntegrityError:
        # Concurrent submission with the same Idempotency-Key won the race.
        # Roll back and return the row that landed first. Per-user scope
        # matches the uq_jobs_user_idempotency_key index.
        await db.rollback()
        if idempotency_key is not None:
            existing = await db.scalar(
                select(Job).where(
                    Job.tenant_id == auth.tenant_id,
                    Job.user_id == auth.user_id,
                    Job.idempotency_key == idempotency_key,
                )
            )
            if existing is not None:
                response.status_code = 200
                return existing
        raise HTTPException(status_code=409, detail="Job submission conflict")
    await db.refresh(job)

    # Placeholder EvalRun so queued work is visible in the Runs list before
    # the worker claims the job. Runners reuse params["eval_run_id"] so the
    # placeholder id is promoted in place instead of duplicated.
    from app.services.evaluators.runner_utils import create_pending_eval_run_for_job
    eval_run_id = await create_pending_eval_run_for_job(job, job_params)
    if eval_run_id is not None:
        job_params["eval_run_id"] = str(eval_run_id)
        job.params = job_params
        await db.commit()
        await db.refresh(job)

    return job


@router.get("", response_model=list[JobResponse])
async def list_jobs(
    status: Optional[str] = Query(None),
    job_type: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """List jobs for the current user."""
    query = (
        select(Job)
        .where(
            Job.tenant_id == auth.tenant_id,
            Job.user_id == auth.user_id,
        )
        .order_by(desc(Job.created_at))
        .limit(limit)
        .offset(offset)
    )
    if status:
        query = query.where(Job.status == status)
    if job_type:
        query = query.where(Job.job_type == job_type)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """Get job status and progress."""
    job = await db.scalar(
        select(Job).where(
            Job.id == job_id,
            Job.tenant_id == auth.tenant_id,
            Job.user_id == auth.user_id,
        )
    )
    if not job:
        raise HTTPException(404, "Job not found")
    await ensure_registered_app_access(
        db,
        auth,
        job.app_id,
        required=False,
        param_name="app_id",
    )

    # Compute queue position for queued jobs
    if job.status in ("queued", "retryable_failed"):
        from app.services.job_worker import get_queue_position
        job.queue_position = await get_queue_position(str(job_id))

    return job


@router.post("/{job_id}/cancel")
async def cancel_job(
    job_id: UUID,
    auth: AuthContext = require_permission('evaluation:cancel'),
    db: AsyncSession = Depends(get_db),
):
    """Cancel a queued or running job."""
    job = await db.scalar(
        select(Job).where(
            Job.id == job_id,
            Job.tenant_id == auth.tenant_id,
            Job.user_id == auth.user_id,
        )
    )
    if not job:
        raise HTTPException(404, "Job not found")
    await ensure_registered_app_access(
        db,
        auth,
        job.app_id,
        required=False,
        param_name="app_id",
    )
    if job.status in ("completed", "failed"):
        raise HTTPException(400, f"Cannot cancel job in '{job.status}' state")
    if job.status == "cancelled":
        # Still fix any orphaned eval_run (idempotent)
        await db.execute(
            update(EvalRun)
            .where(EvalRun.job_id == job_id, EvalRun.status.in_(("pending", "running")))
            .values(status="cancelled", completed_at=datetime.now(timezone.utc))
        )
        await db.commit()
        from app.services.job_worker import mark_job_cancelled
        mark_job_cancelled(job_id)
        return {"id": str(job_id), "status": "cancelled"}
    now = datetime.now(timezone.utc)
    job.status = "cancelled"
    job.completed_at = now
    job.lease_owner = None
    job.lease_expires_at = None
    job.heartbeat_at = now
    job.next_retry_at = None
    # Also cancel any associated eval_run so RunDetail reflects it immediately
    await db.execute(
        update(EvalRun)
        .where(EvalRun.job_id == job_id, EvalRun.status.in_(("pending", "running")))
        .values(status="cancelled", completed_at=now)
    )
    await db.commit()
    from app.services.job_worker import mark_job_cancelled
    mark_job_cancelled(job_id)
    return {"id": str(job_id), "status": "cancelled"}

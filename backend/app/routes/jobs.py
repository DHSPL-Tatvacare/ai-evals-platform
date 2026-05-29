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
from app.auth.permissions import ensure_any_permission
from app.database import get_db
from app.models.job import BackgroundJob
from app.models.eval_run import EvaluationRun
from app.openapi_examples import err, ok
from app.schemas.job import JobCreate, JobResponse

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

_JOB_EXAMPLE = {
    "id": "b7d3f0a1-2c4e-4a6b-8d0f-1a2b3c4d5e6f",
    "appId": "support-assistant",
    "jobType": "evaluate-batch",
    "status": "queued",
    "priority": 100,
    "queueClass": "standard",
    "attemptCount": 0,
    "maxAttempts": 1,
    "params": {"listingIds": ["7c9e6679-7425-40de-944b-e07fc1f90ae7"]},
    "submissionContext": None,
    "result": None,
    "progress": {"current": 0, "total": 12, "message": "queued"},
    "errorMessage": None,
    "createdAt": "2026-05-20T09:20:00Z",
    "startedAt": None,
    "completedAt": None,
    "queuePosition": 3,
    "idempotencyKey": "batch-2026-05-20-001",
}

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


@router.post(
    "",
    response_model=JobResponse,
    status_code=201,
    summary="Submit a job",
    description=(
        "Queue a long-running operation — an evaluation, report, or backfill — and get "
        "back a job to poll. Set `jobType` to a registered type and pass its `params`; "
        "tenant, user, and app context are injected for you. Send an `Idempotency-Key` "
        "header to make retries safe: a repeat with the same key returns the original job "
        "(HTTP 200) instead of starting a duplicate.\n\n"
        "**Authentication:** Bearer token holding the permission(s) the chosen `jobType` "
        "requires (e.g. `evaluation:run` for evaluation jobs)."
    ),
    responses={
        201: ok("The job was queued.", _JOB_EXAMPLE),
        200: ok("Idempotent replay — the job with this Idempotency-Key already existed and is returned unchanged.", _JOB_EXAMPLE),
        400: err("Invalid params for this job type, or the Idempotency-Key is too long.", "Idempotency-Key must be <= 120 chars"),
        409: err("A concurrent submission with the same Idempotency-Key won the race.", "BackgroundJob submission conflict"),
        422: err("The job_type has no registered handler.", "Unknown job_type: 'evaluate-foo'"),
    },
)
async def submit_job(
    body: JobCreate,
    response: Response,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
    idempotency_key_header: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        description="Optional opaque token (≤120 chars). Resubmitting with the same key returns the original job instead of starting a new one.",
    ),
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
    from app.services.job_worker import JOB_HANDLERS, get_job_submission_metadata, required_permissions_for_job

    if body.job_type not in JOB_HANDLERS:
        # 422 because the payload is semantically invalid (unknown type),
        # not malformed. Stable detail string so clients can branch on it.
        raise HTTPException(
            status_code=422,
            detail=f"Unknown job_type: {body.job_type!r}",
        )

    # Permission gate fires before any DB access.
    ensure_any_permission(auth, *required_permissions_for_job(body.job_type))

    idempotency_key = _normalize_idempotency_key(idempotency_key_header)
    if idempotency_key is not None:
        existing = await db.scalar(
            select(BackgroundJob).where(
                BackgroundJob.tenant_id == auth.tenant_id,
                BackgroundJob.user_id == auth.user_id,
                BackgroundJob.idempotency_key == idempotency_key,
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

    # Pre-allocate the placeholder EvaluationRun id and stamp it into params
    # BEFORE the BackgroundJob is committed. This must be atomic with the job
    # INSERT — if the worker claims the job before params['eval_run_id'] is
    # visible, the runner mints a fresh UUID via uuid.uuid4() and the
    # placeholder is orphaned at status='pending' forever (see commit history
    # for the 302a54c4 incident).
    from app.services.evaluators.runner_utils import (
        add_pending_eval_run_to_session,
        derive_pending_eval_run_id,
    )
    eval_run_id = derive_pending_eval_run_id(job_data["job_type"])
    if eval_run_id is not None:
        job_params["eval_run_id"] = str(eval_run_id)
    job_data["params"] = job_params

    job = BackgroundJob(
        **job_data,
        app_id=metadata["app_id"],
        priority=metadata["priority"],
        queue_class=metadata["queue_class"],
        max_attempts=metadata["max_attempts"],
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        idempotency_key=idempotency_key,
    )
    db.add(job)
    try:
        if eval_run_id is not None:
            # flush() materialises job.id so the EvaluationRun.job_id FK
            # resolves inside this transaction. The unique index on
            # idempotency_key fires here (not on commit) so the flush
            # MUST be inside this try/except — otherwise a concurrent
            # replay raises IntegrityError before the handler below
            # gets a chance to convert it to a 200/409.
            await db.flush()
            add_pending_eval_run_to_session(
                db, eval_run_id=eval_run_id, job=job, params=job_params,
            )
        await db.commit()
    except IntegrityError:
        # Concurrent submission with the same Idempotency-Key won the race.
        # Roll back and return the row that landed first. Per-user scope
        # matches the uq_jobs_user_idempotency_key index.
        await db.rollback()
        if idempotency_key is not None:
            existing = await db.scalar(
                select(BackgroundJob).where(
                    BackgroundJob.tenant_id == auth.tenant_id,
                    BackgroundJob.user_id == auth.user_id,
                    BackgroundJob.idempotency_key == idempotency_key,
                )
            )
            if existing is not None:
                response.status_code = 200
                return existing
        raise HTTPException(status_code=409, detail="BackgroundJob submission conflict")
    await db.refresh(job)

    return job


@router.get(
    "",
    response_model=list[JobResponse],
    summary="List jobs",
    description=(
        "Return your jobs, newest first, optionally filtered by status or job type and "
        "paginated with `limit`/`offset`. Scoped to your tenant and user.\n\n"
        "**Authentication:** Bearer token."
    ),
    responses={200: ok("Your jobs, newest first.", [_JOB_EXAMPLE])},
)
async def list_jobs(
    status: Optional[str] = Query(None, description="Filter by status, e.g. `queued`, `running`, `completed`, `failed`, `cancelled`."),
    job_type: Optional[str] = Query(None, description="Filter by job type, e.g. `evaluate-batch`."),
    limit: int = Query(20, ge=1, le=100, description="Page size (1–100)."),
    offset: int = Query(0, ge=0, description="Number of jobs to skip."),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """List jobs for the current user."""
    query = (
        select(BackgroundJob)
        .where(
            BackgroundJob.tenant_id == auth.tenant_id,
            BackgroundJob.user_id == auth.user_id,
        )
        .order_by(desc(BackgroundJob.created_at))
        .limit(limit)
        .offset(offset)
    )
    if status:
        query = query.where(BackgroundJob.status == status)
    if job_type:
        query = query.where(BackgroundJob.job_type == job_type)
    result = await db.execute(query)
    return result.scalars().all()


@router.get(
    "/{job_id}",
    response_model=JobResponse,
    summary="Get job status",
    description=(
        "Poll a job's status, progress, result, and — while it's waiting — its position "
        "in the queue. This is the endpoint you call on a timer after submitting, until "
        "`status` reaches `completed`, `failed`, or `cancelled`.\n\n"
        "**Authentication:** Bearer token. Only your own jobs are visible."
    ),
    responses={
        200: ok("The job's current state.", _JOB_EXAMPLE),
        404: err("No such job for your tenant and user.", "BackgroundJob not found"),
    },
)
async def get_job(
    job_id: UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """Get job status and progress."""
    job = await db.scalar(
        select(BackgroundJob).where(
            BackgroundJob.id == job_id,
            BackgroundJob.tenant_id == auth.tenant_id,
            BackgroundJob.user_id == auth.user_id,
        )
    )
    if not job:
        raise HTTPException(404, "BackgroundJob not found")
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


@router.post(
    "/{job_id}/cancel",
    summary="Cancel a job",
    description=(
        "Request cancellation of a queued or running job. Any evaluation run the job "
        "created is also marked cancelled so downstream views update immediately. Jobs "
        "already `completed` or `failed` cannot be cancelled; calling on an already-"
        "cancelled job is a safe no-op.\n\n"
        "**Authentication:** Bearer token holding the permission(s) the job's type requires."
    ),
    responses={
        200: ok("The job is cancelled.", {"id": "b7d3f0a1-2c4e-4a6b-8d0f-1a2b3c4d5e6f", "status": "cancelled"}),
        400: err("The job is in a terminal state and cannot be cancelled.", "Cannot cancel job in 'completed' state"),
        404: err("No such job for your tenant and user.", "BackgroundJob not found"),
    },
)
async def cancel_job(
    job_id: UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """Cancel a queued or running job."""
    from app.services.job_worker import required_permissions_for_job
    job = await db.scalar(
        select(BackgroundJob).where(
            BackgroundJob.id == job_id,
            BackgroundJob.tenant_id == auth.tenant_id,
            BackgroundJob.user_id == auth.user_id,
        )
    )
    if not job:
        raise HTTPException(404, "BackgroundJob not found")
    ensure_any_permission(auth, *required_permissions_for_job(job.job_type))
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
            update(EvaluationRun)
            .where(EvaluationRun.job_id == job_id, EvaluationRun.status.in_(("pending", "running")))
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
        update(EvaluationRun)
        .where(EvaluationRun.job_id == job_id, EvaluationRun.status.in_(("pending", "running")))
        .values(status="cancelled", completed_at=now)
    )
    await db.commit()
    from app.services.job_worker import mark_job_cancelled
    mark_job_cancelled(job_id)
    return {"id": str(job_id), "status": "cancelled"}

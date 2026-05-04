"""Run lifecycle: manual fire, list, detail, recipients, actions, cancel, override."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import BackgroundJob
from app.models.orchestration import (
    Workflow,
    WorkflowRun,
    WorkflowRunNodeStep,
    WorkflowRunRecipientAction,
    WorkflowRunRecipientOverride,
    WorkflowRunRecipientState,
)


class RunFireError(ValueError):
    pass


async def fire_manual_run(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    workflow_id: uuid.UUID,
    user_id: uuid.UUID,
    params: dict[str, Any],
) -> Optional[WorkflowRun]:
    wf = (await db.execute(
        select(Workflow).where(Workflow.id == workflow_id, Workflow.tenant_id == tenant_id)
    )).scalar_one_or_none()
    if wf is None:
        return None
    if wf.current_published_version_id is None:
        raise RunFireError("workflow has no published version")

    run = WorkflowRun(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        app_id=wf.app_id,
        workflow_id=wf.id,
        workflow_version_id=wf.current_published_version_id,
        triggered_by="manual",
        triggered_by_user_id=user_id,
        status="pending",
        params=params,
    )
    db.add(run)
    await db.flush()

    job = BackgroundJob(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        app_id=wf.app_id,
        user_id=user_id,
        job_type="run-workflow",
        queue_class="standard",
        priority=5,
        # ``process_job`` reads tenant_id / user_id straight off ``params``
        # before forwarding to the handler — every job submission has to
        # echo them here even though the BackgroundJob row already carries
        # them. Other run-workflow submission paths (resume_poller,
        # generic_event webhook) need the same shape.
        params={
            "run_id": str(run.id),
            "tenant_id": str(tenant_id),
            "user_id": str(user_id),
        },
        status="queued",
    )
    db.add(job)
    await db.flush()
    run.job_id = job.id

    await db.commit()
    await db.refresh(run)
    return run


async def list_runs(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    workflow_id: Optional[uuid.UUID] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    app_ids: Optional[frozenset[str]] = None,
) -> tuple[list[WorkflowRun], int]:
    """List runs in a tenant. Pass ``app_ids`` to additionally restrict to a
    set of apps the caller has access to; pass None to disable that filter
    (callers using ``workflow_id`` typically gate via the workflow's app_id
    upstream and don't need to filter again here).

    Returns ``(items, total)`` — ``total`` is the unpaged count under the same
    filters so the UI can render server-side pagination identical to other
    list endpoints in this codebase (e.g. ``LeadListResponse``).
    """
    base = select(WorkflowRun).where(WorkflowRun.tenant_id == tenant_id)
    if workflow_id:
        base = base.where(WorkflowRun.workflow_id == workflow_id)
    if app_ids is not None:
        if not app_ids:
            return [], 0  # caller has no app access; cannot see any runs
        base = base.where(WorkflowRun.app_id.in_(app_ids))
    if status:
        base = base.where(WorkflowRun.status == status)

    total = (await db.execute(
        select(func.count()).select_from(base.subquery())
    )).scalar_one()

    page = base.order_by(WorkflowRun.created_at.desc()).limit(limit).offset(offset)
    items = list((await db.execute(page)).scalars().all())
    return items, int(total)


async def latest_runs_by_workflow_ids(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    workflow_ids: list[uuid.UUID],
) -> dict[uuid.UUID, tuple[uuid.UUID, Optional[Any], Optional[str]]]:
    """Return ``{workflow_id: (run_id, created_at, status)}`` for the latest run.

    One round-trip — uses ``DISTINCT ON (workflow_id)`` to pick the latest
    run per workflow; rides the existing
    ``ix_workflow_runs_tenant_app_workflow_started`` index. Workflows that
    have never been run are absent from the result.
    """
    if not workflow_ids:
        return {}
    stmt = (
        select(
            WorkflowRun.workflow_id,
            WorkflowRun.id,
            WorkflowRun.created_at,
            WorkflowRun.status,
        )
        .where(
            WorkflowRun.tenant_id == tenant_id,
            WorkflowRun.workflow_id.in_(workflow_ids),
        )
        .order_by(WorkflowRun.workflow_id, WorkflowRun.created_at.desc())
        .distinct(WorkflowRun.workflow_id)
    )
    rows = (await db.execute(stmt)).all()
    return {
        wf_id: (run_id, created_at, status)
        for wf_id, run_id, created_at, status in rows
    }


async def get_run(
    db: AsyncSession, *, tenant_id: uuid.UUID, run_id: uuid.UUID,
) -> Optional[WorkflowRun]:
    return (await db.execute(
        select(WorkflowRun).where(WorkflowRun.id == run_id, WorkflowRun.tenant_id == tenant_id)
    )).scalar_one_or_none()


async def list_latest_node_steps(
    db: AsyncSession, *, tenant_id: uuid.UUID, run_id: uuid.UUID,
) -> list[WorkflowRunNodeStep]:
    """Return the latest node-step row per node for one run.

    The run viewer needs a deterministic current-state snapshot to hydrate the
    canvas before live SSE events arrive (and after reconnect gaps). Multiple
    cohorts can execute the same node over time, so we collapse to the latest
    row per ``node_id`` rather than returning the full execution history.
    """
    stmt = (
        select(WorkflowRunNodeStep)
        .where(
            WorkflowRunNodeStep.run_id == run_id,
            WorkflowRunNodeStep.tenant_id == tenant_id,
        )
        .order_by(
            WorkflowRunNodeStep.node_id,
            WorkflowRunNodeStep.started_at.desc().nullslast(),
            WorkflowRunNodeStep.completed_at.desc().nullslast(),
            WorkflowRunNodeStep.id.desc(),
        )
        .distinct(WorkflowRunNodeStep.node_id)
    )
    return list((await db.execute(stmt)).scalars().all())


async def list_recipients(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    run_id: uuid.UUID,
    limit: int = 100,
    offset: int = 0,
) -> list[WorkflowRunRecipientState]:
    stmt = select(WorkflowRunRecipientState).where(
        WorkflowRunRecipientState.run_id == run_id,
        WorkflowRunRecipientState.tenant_id == tenant_id,
    ).order_by(WorkflowRunRecipientState.enrolled_at.desc()).limit(limit).offset(offset)
    return list((await db.execute(stmt)).scalars().all())


async def list_actions(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    run_id: uuid.UUID,
    channel: Optional[str] = None,
    action_type: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
) -> list[WorkflowRunRecipientAction]:
    stmt = select(WorkflowRunRecipientAction).where(
        WorkflowRunRecipientAction.run_id == run_id,
        WorkflowRunRecipientAction.tenant_id == tenant_id,
    )
    if channel:
        stmt = stmt.where(WorkflowRunRecipientAction.channel == channel)
    if action_type:
        stmt = stmt.where(WorkflowRunRecipientAction.action_type == action_type)
    stmt = stmt.order_by(WorkflowRunRecipientAction.created_at.desc()).limit(limit).offset(offset)
    return list((await db.execute(stmt)).scalars().all())


async def cancel_run(
    db: AsyncSession, *, tenant_id: uuid.UUID, run_id: uuid.UUID,
) -> bool:
    run = await get_run(db, tenant_id=tenant_id, run_id=run_id)
    if run is None:
        return False
    if run.status in ("completed", "failed", "cancelled"):
        return True
    from app.services.job_worker import mark_job_cancelled
    if run.job_id:
        mark_job_cancelled(str(run.job_id))
    run.status = "cancelled"
    run.completed_at = datetime.now(timezone.utc)
    await db.commit()
    return True


async def apply_override(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    run_id: uuid.UUID,
    recipient_id: str,
    action: str,
    target_node_id: Optional[str],
    reason: Optional[str],
    applied_by: uuid.UUID,
) -> Optional[WorkflowRunRecipientOverride]:
    run = await get_run(db, tenant_id=tenant_id, run_id=run_id)
    if run is None:
        return None
    ov = WorkflowRunRecipientOverride(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        app_id=run.app_id,
        workflow_id=run.workflow_id,
        workflow_version_id=run.workflow_version_id,
        run_id=run_id,
        recipient_id=recipient_id,
        action=action,
        target_node_id=target_node_id,
        reason=reason,
        applied_by=applied_by,
        applied_at=datetime.now(timezone.utc),
    )
    db.add(ov)
    await db.commit()
    await db.refresh(ov)
    return ov

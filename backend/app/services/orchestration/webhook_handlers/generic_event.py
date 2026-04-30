"""Match an inbound event against workflow_triggers and submit run-workflow jobs.

Used by:
  - /webhooks/event/<name>/<secret> directly
  - /webhooks/lsq/<secret> (after the LSQ handler translates the payload to 'lsq.lead.updated')

For each active matching trigger, creates one workflow_runs row + one
background_jobs row of type 'run-workflow'. The run-workflow handler is
already registered (Phase 1) and will execute the source nodes.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import SYSTEM_USER_ID
from app.models.job import BackgroundJob
from app.models.orchestration import Workflow, WorkflowRun, WorkflowTrigger


async def fire_event(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    app_id: Optional[str],
    event_name: str,
    event_payload: dict[str, Any],
    triggered_by_user_id: Optional[uuid.UUID] = None,
) -> list[uuid.UUID]:
    """Find matching active triggers, create one workflow_run + one BackgroundJob per trigger.

    Returns the list of workflow_run.id values created.
    """
    stmt = select(WorkflowTrigger).where(
        WorkflowTrigger.tenant_id == tenant_id,
        WorkflowTrigger.event_name == event_name,
        WorkflowTrigger.kind == "event",
        WorkflowTrigger.active.is_(True),
    )
    if app_id is not None:
        stmt = stmt.where(WorkflowTrigger.app_id == app_id)
    triggers = (await db.execute(stmt)).scalars().all()

    created: list[uuid.UUID] = []
    for trigger in triggers:
        wf = (
            await db.execute(select(Workflow).where(Workflow.id == trigger.workflow_id))
        ).scalar_one()
        if wf.current_published_version_id is None:
            continue

        run = WorkflowRun(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            app_id=trigger.app_id,
            workflow_id=wf.id,
            workflow_version_id=wf.current_published_version_id,
            trigger_id=trigger.id,
            triggered_by="event",
            triggered_by_user_id=triggered_by_user_id,
            status="pending",
            params={"event_payload": event_payload},
        )
        db.add(run)
        await db.flush()  # ensure run.id is materialized for FK on job

        job = BackgroundJob(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            app_id=trigger.app_id,
            user_id=triggered_by_user_id or trigger.created_by or SYSTEM_USER_ID,
            job_type="run-workflow",
            queue_class="standard",
            priority=5,
            params={"run_id": str(run.id)},
            status="queued",
        )
        db.add(job)
        await db.flush()
        run.job_id = job.id
        created.append(run.id)

    await db.flush()
    return created

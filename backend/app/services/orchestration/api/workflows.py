"""Workflow lineage CRUD."""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import SYSTEM_TENANT_ID
from app.models.orchestration import Workflow, WorkflowTrigger
from app.models.scheduled_job import ScheduledJobDefinition


class WorkflowConflict(ValueError):
    pass


async def create_workflow(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    app_id: str,
    workflow_type: str,
    slug: str,
    name: str,
    description: Optional[str],
    created_by: uuid.UUID,
) -> Workflow:
    wf = Workflow(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        app_id=app_id,
        workflow_type=workflow_type,
        slug=slug,
        name=name,
        description=description,
        created_by=created_by,
    )
    db.add(wf)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise WorkflowConflict(
            f"workflow with slug={slug!r} already exists for this tenant + app"
        )
    await db.refresh(wf)
    return wf


async def list_workflows(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    app_id: Optional[str] = None,
    workflow_type: Optional[str] = None,
    app_ids: Optional[frozenset[str]] = None,
) -> list[Workflow]:
    """List workflows in a tenant. Pass ``app_ids`` to additionally restrict
    output to apps the caller has access to (used when the caller didn't
    specify an explicit ``app_id`` filter)."""
    stmt = select(Workflow).where(
        Workflow.tenant_id == tenant_id,
        Workflow.active.is_(True),
    )
    if app_id:
        stmt = stmt.where(Workflow.app_id == app_id)
    elif app_ids is not None:
        if not app_ids:
            return []
        stmt = stmt.where(Workflow.app_id.in_(app_ids))
    if workflow_type:
        stmt = stmt.where(Workflow.workflow_type == workflow_type)
    stmt = stmt.order_by(Workflow.created_at.desc())
    return list((await db.execute(stmt)).scalars().all())


async def list_system_workflows(
    db: AsyncSession,
    *,
    app_id: Optional[str] = None,
    workflow_type: Optional[str] = None,
    app_ids: Optional[frozenset[str]] = None,
) -> list[Workflow]:
    """List published system-seeded workflows available for tenant cloning."""
    stmt = select(Workflow).where(
        Workflow.tenant_id == SYSTEM_TENANT_ID,
        Workflow.active.is_(True),
        Workflow.current_published_version_id.is_not(None),
    )
    if app_id:
        stmt = stmt.where(Workflow.app_id == app_id)
    elif app_ids is not None:
        if not app_ids:
            return []
        stmt = stmt.where(Workflow.app_id.in_(app_ids))
    if workflow_type:
        stmt = stmt.where(Workflow.workflow_type == workflow_type)
    stmt = stmt.order_by(Workflow.created_at.desc())
    return list((await db.execute(stmt)).scalars().all())


async def get_workflow(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    workflow_id: uuid.UUID,
    active_only: bool = False,
) -> Optional[Workflow]:
    stmt = select(Workflow).where(Workflow.id == workflow_id, Workflow.tenant_id == tenant_id)
    if active_only:
        stmt = stmt.where(Workflow.active.is_(True))
    return (await db.execute(stmt)).scalar_one_or_none()


async def update_workflow(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    workflow_id: uuid.UUID,
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> Optional[Workflow]:
    wf = await get_workflow(
        db, tenant_id=tenant_id, workflow_id=workflow_id, active_only=True,
    )
    if wf is None:
        return None
    if name is not None:
        wf.name = name
    if description is not None:
        wf.description = description
    await db.commit()
    await db.refresh(wf)
    return wf


async def archive_workflow(
    db: AsyncSession, *, tenant_id: uuid.UUID, workflow_id: uuid.UUID,
) -> bool:
    """Soft-archive a workflow.

    Runtime rows (`workflow_runs`, node steps, actions, recipient state) keep
    their FK back to the workflow lineage, so archive must preserve the row and
    simply mark it inactive. Inactive workflows disappear from listings and can
    no longer be mutated or manually run. Existing triggers are deactivated; any
    linked scheduled jobs are disabled in the same transaction.
    """
    wf = await get_workflow(
        db, tenant_id=tenant_id, workflow_id=workflow_id, active_only=True,
    )
    if wf is None:
        return False
    wf.active = False

    triggers = list((await db.execute(
        select(WorkflowTrigger).where(
            WorkflowTrigger.workflow_id == workflow_id,
            WorkflowTrigger.tenant_id == tenant_id,
        )
    )).scalars().all())
    scheduled_job_ids = [
        trig.scheduled_job_id for trig in triggers if trig.scheduled_job_id is not None
    ]
    for trig in triggers:
        trig.active = False

    if scheduled_job_ids:
        schedules = list((await db.execute(
            select(ScheduledJobDefinition).where(
                ScheduledJobDefinition.id.in_(scheduled_job_ids)
            )
        )).scalars().all())
        for schedule in schedules:
            schedule.enabled = False

    await db.commit()
    return True

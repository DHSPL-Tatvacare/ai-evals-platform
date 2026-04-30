"""Action template list + tenant-override upsert.

System defaults (tenant_id IS NULL) are read-only via the API; tenants only
edit their own override row keyed on (tenant_id, app_id, channel, slug).
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orchestration import WorkflowActionTemplate


async def list_templates(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    app_id: Optional[str] = None,
    channel: Optional[str] = None,
) -> list[WorkflowActionTemplate]:
    """Returns tenant overrides + system defaults (tenant_id IS NULL)."""
    stmt = select(WorkflowActionTemplate).where(
        (WorkflowActionTemplate.tenant_id == tenant_id)
        | (WorkflowActionTemplate.tenant_id.is_(None))
    )
    if app_id:
        stmt = stmt.where(
            (WorkflowActionTemplate.app_id == app_id)
            | (WorkflowActionTemplate.app_id.is_(None))
        )
    if channel:
        stmt = stmt.where(WorkflowActionTemplate.channel == channel)
    return list((await db.execute(
        stmt.order_by(WorkflowActionTemplate.channel, WorkflowActionTemplate.slug)
    )).scalars().all())


async def upsert_tenant_template(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    app_id: str,
    channel: str,
    slug: str,
    name: str,
    payload_schema: dict[str, Any],
    active: bool,
) -> WorkflowActionTemplate:
    existing = (await db.execute(
        select(WorkflowActionTemplate).where(
            WorkflowActionTemplate.tenant_id == tenant_id,
            WorkflowActionTemplate.app_id == app_id,
            WorkflowActionTemplate.channel == channel,
            WorkflowActionTemplate.slug == slug,
        )
    )).scalar_one_or_none()
    if existing is not None:
        existing.name = name
        existing.payload_schema = payload_schema
        existing.active = active
    else:
        existing = WorkflowActionTemplate(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            app_id=app_id,
            channel=channel,
            slug=slug,
            name=name,
            payload_schema=payload_schema,
            active=active,
        )
        db.add(existing)
    await db.commit()
    await db.refresh(existing)
    return existing

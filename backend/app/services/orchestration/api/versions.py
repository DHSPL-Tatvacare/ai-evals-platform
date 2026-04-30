"""Workflow version create / list / publish.

Publish validates ``definition.nodes[*].type`` against the node registry and
checks each node's config against ``handler.config_schema``. Only a successful
validation flips status to 'published' and points the workflow at the version.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orchestration import Workflow, WorkflowVersion
from app.services.orchestration.node_registry import NodeRegistryError, resolve_handler


class VersionPublishError(ValueError):
    pass


async def create_draft_version(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    workflow_id: uuid.UUID,
    definition: dict[str, Any],
) -> Optional[WorkflowVersion]:
    wf = (await db.execute(
        select(Workflow).where(Workflow.id == workflow_id, Workflow.tenant_id == tenant_id)
    )).scalar_one_or_none()
    if wf is None:
        return None
    next_version = (await db.execute(
        select(func.coalesce(func.max(WorkflowVersion.version), 0))
        .where(WorkflowVersion.workflow_id == workflow_id)
    )).scalar_one() + 1
    v = WorkflowVersion(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        app_id=wf.app_id,
        workflow_id=workflow_id,
        version=next_version,
        definition=definition,
        status="draft",
    )
    db.add(v)
    await db.commit()
    await db.refresh(v)
    return v


async def list_versions(
    db: AsyncSession, *, tenant_id: uuid.UUID, workflow_id: uuid.UUID,
) -> list[WorkflowVersion]:
    return list((await db.execute(
        select(WorkflowVersion).where(
            WorkflowVersion.workflow_id == workflow_id,
            WorkflowVersion.tenant_id == tenant_id,
        ).order_by(WorkflowVersion.version.desc())
    )).scalars().all())


async def get_version(
    db: AsyncSession, *, tenant_id: uuid.UUID, version_id: uuid.UUID,
) -> Optional[WorkflowVersion]:
    return (await db.execute(
        select(WorkflowVersion).where(
            WorkflowVersion.id == version_id,
            WorkflowVersion.tenant_id == tenant_id,
        )
    )).scalar_one_or_none()


async def publish_version(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    workflow_id: uuid.UUID,
    version_id: uuid.UUID,
    published_by: uuid.UUID,
) -> Optional[WorkflowVersion]:
    v = await get_version(db, tenant_id=tenant_id, version_id=version_id)
    if v is None or v.workflow_id != workflow_id:
        return None
    wf = (await db.execute(
        select(Workflow).where(Workflow.id == workflow_id, Workflow.tenant_id == tenant_id)
    )).scalar_one_or_none()
    if wf is None:
        return None

    _validate_definition(v.definition, workflow_type=wf.workflow_type)

    v.status = "published"
    v.published_by = published_by
    v.published_at = datetime.now(timezone.utc)
    wf.current_published_version_id = v.id
    await db.commit()
    await db.refresh(v)
    return v


def _validate_definition(definition: dict[str, Any], *, workflow_type: str) -> None:
    """Walk every node's type through the registry; raise VersionPublishError on miss."""
    for n in definition.get("nodes", []):
        node_type = n.get("type")
        if not node_type:
            raise VersionPublishError(f"node {n.get('id')!r} missing 'type'")
        try:
            handler = resolve_handler(workflow_type=workflow_type, node_type=node_type)
        except NodeRegistryError as exc:
            raise VersionPublishError(
                f"unknown node type {node_type!r} for workflow_type={workflow_type!r}: {exc}"
            )
        try:
            handler.config_schema(**(n.get("config") or {}))
        except Exception as exc:
            raise VersionPublishError(f"node {n.get('id')!r} config invalid: {exc}")

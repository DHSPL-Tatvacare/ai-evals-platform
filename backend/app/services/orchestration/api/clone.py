"""Clone a system-owned workflow into the requesting tenant.

Tenants opt into seeded workflows ("Default MQL Concierge", "DM2 Adherence
Watch") by cloning. Cloning creates a fresh Workflow lineage in the tenant's
namespace, seeding the mutable draft from the system workflow's definition.
When nothing needs rebinding it also mints a v1 published version and points
live at it. Tenants edit the cloned workflow visually without affecting the
system seed.

The system seed is identified by ``tenant_id == SYSTEM_TENANT_ID``; any
non-system workflow rejected here.

Phase 10 commit 1 adds **clone sanitization**: any node ``connection_id`` in
the cloned definition that does not point at a connection visible to
``(target_tenant_id, target_app_id)`` is cleared, so tenant clones never
inherit system-owned credential bindings. If anything was cleared, the
cloned workflow lands draft-only (``current_published_version_id=NULL``, no
version row) and the builder requires operator rebind before publish/run.
"""
from __future__ import annotations

import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import SYSTEM_TENANT_ID
from app.models.mixins.shareable import Visibility
from app.models.orchestration import Workflow, WorkflowVersion
from app.models.provider_connection import ProviderConnection
from app.services.orchestration.connections.scope import (
    connection_app_scope_clause,
)


class CloneError(ValueError):
    """Raised when the source workflow cannot be cloned (no published version,
    target slug already taken, etc.)."""


async def _allowed_connection_ids(
    db: AsyncSession, *, tenant_id: uuid.UUID, app_id: str,
) -> set[uuid.UUID]:
    """Connection ids the cloned workflow may legally reference.

    ``connection_id`` is a tenant-local pointer. Cloning a system workflow
    into tenant T may keep an id only if the row is reachable by
    (T, target_app_id) — its home app, an app_scope, or tenant-wide.
    Otherwise the id is stripped.
    """
    rows = await db.scalars(
        select(ProviderConnection.id).where(
            ProviderConnection.tenant_id == tenant_id,
            connection_app_scope_clause(app_id),
        )
    )
    return set(rows.all())


def _strip_foreign_connection_ids(
    definition: dict[str, Any], allowed_ids: set[uuid.UUID],
) -> tuple[dict[str, Any], int]:
    """Return (sanitized_definition, cleared_count). Walks every node's
    ``config.connection_id`` and removes the key when the id isn't in
    ``allowed_ids`` (which for fresh tenants is empty)."""
    cleaned = deepcopy(definition)
    cleared = 0
    for node in cleaned.get("nodes", []):
        config = node.get("config")
        if not isinstance(config, dict):
            continue
        raw = config.get("connection_id")
        if raw is None:
            continue
        try:
            cid = uuid.UUID(str(raw))
        except (TypeError, ValueError):
            # Malformed value — treat as foreign and clear.
            del config["connection_id"]
            cleared += 1
            continue
        if cid not in allowed_ids:
            del config["connection_id"]
            cleared += 1
    return cleaned, cleared


async def clone_system_workflow(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    source_workflow_id: uuid.UUID,
    new_slug: str,
    new_name: str,
    target_app_id: str,
    created_by: uuid.UUID,
) -> Optional[Workflow]:
    """Clone a system workflow. Returns ``None`` if the source is missing or
    not system-owned. Raises ``CloneError`` if the source has no published
    version or the target slug collides.
    """
    src = await db.scalar(
        select(Workflow).where(
            Workflow.id == source_workflow_id,
            Workflow.tenant_id == SYSTEM_TENANT_ID,
            Workflow.active == True,
        )
    )
    if src is None:
        return None
    if src.current_published_version_id is None:
        raise CloneError("source workflow has no published version")

    src_version = await db.scalar(
        select(WorkflowVersion).where(
            WorkflowVersion.id == src.current_published_version_id
        )
    )
    if src_version is None:
        raise CloneError("source workflow's current_published_version_id is dangling")

    allowed = await _allowed_connection_ids(
        db, tenant_id=tenant_id, app_id=target_app_id,
    )
    sanitized_definition, cleared = _strip_foreign_connection_ids(
        src_version.definition, allowed,
    )
    rebind_required = cleared > 0

    # Seed the single mutable draft from the sanitized definition either way.
    # When nothing needed rebinding we also mint v1 published and point live
    # at it; otherwise the operator rebinds in the builder and publishes.
    cloned_wf = Workflow(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        app_id=target_app_id,
        workflow_type=src.workflow_type,
        slug=new_slug,
        name=new_name,
        description=f"Cloned from system workflow {src.slug}",
        created_by=created_by,
        visibility=Visibility.PRIVATE,
        draft_definition=sanitized_definition,
        draft_updated_at=datetime.now(timezone.utc),
    )
    db.add(cloned_wf)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise CloneError(
            f"workflow with slug={new_slug!r} already exists for this tenant + app"
        )

    if not rebind_required:
        cloned_v = WorkflowVersion(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            app_id=target_app_id,
            workflow_id=cloned_wf.id,
            version=1,
            definition=sanitized_definition,
            status="published",
            published_by=created_by,
            published_at=datetime.now(timezone.utc),
        )
        db.add(cloned_v)
        await db.flush()
        cloned_wf.current_published_version_id = cloned_v.id
    await db.commit()
    await db.refresh(cloned_wf)
    return cloned_wf

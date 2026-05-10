"""Tenant-ownership guard for the authoring pack.

Single shared helper — used by the route gate (R1) AND every per-tool
re-check (R3). Pinning both call sites on the same helper closes the
"R3 evolves and R1 doesn't" drift risk called out in the permission-rules
decision (§Risks still open).
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orchestration import Workflow


async def assert_workflow_owned(
    db: AsyncSession,
    *,
    workflow_id: uuid.UUID | str,
    auth: Any,
) -> Workflow:
    """Fetch the workflow scoped by tenant; raise 404 on mismatch.

    Returns the loaded `Workflow` row. Caller verifies `app_id` separately
    (per the permission-rules R1 step 3) — this helper enforces tenant
    ownership only so it can be reused at every call depth without
    re-deciding the app-access policy.

    Raises HTTP 404 (not 403) on tenant mismatch — never leak existence.
    """
    if not isinstance(workflow_id, uuid.UUID):
        try:
            workflow_id = uuid.UUID(str(workflow_id))
        except (TypeError, ValueError) as exc:
            raise HTTPException(404, 'workflow not found') from exc

    row = await db.scalar(
        select(Workflow).where(
            Workflow.id == workflow_id,
            Workflow.tenant_id == auth.tenant_id,
        )
    )
    if row is None:
        raise HTTPException(404, 'workflow not found')
    return row


__all__ = ['assert_workflow_owned']

"""Read-only run-start preview: count over-cap manifest rows for operator display.

The cut is the dispatch enforcer alone — this never flips a recipient state.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orchestration import WorkflowRun, WorkflowRunRecipient
from app.services.orchestration.comm_cap.policy_resolver import (
    count_recent_comms,
    get_active_policy,
)


async def run_cap_preview(db: AsyncSession, *, run: WorkflowRun) -> int:
    """Return how many manifest rows are currently over the active cap.

    Display-only: no recipient state is mutated. Rows with no best-effort
    phone are not counted (the dispatch enforcer counts on the resolved phone).
    """
    policy = await get_active_policy(db, tenant_id=run.tenant_id, app_id=run.app_id)
    if policy is None:
        return 0

    manifest_rows = (
        await db.execute(
            select(WorkflowRunRecipient).where(WorkflowRunRecipient.run_id == run.id)
        )
    ).scalars().all()

    capped = 0
    for recipient in manifest_rows:
        if not recipient.phone_e164:
            continue
        used = await count_recent_comms(
            db,
            tenant_id=recipient.tenant_id,
            app_id=recipient.app_id,
            phone_e164=recipient.phone_e164,
            window_seconds=policy.window_seconds,
        )
        if used >= policy.max_count:
            capped += 1
    return capped

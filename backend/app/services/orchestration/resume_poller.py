"""resume-waiting-cohorts — wakes due / ready recipient states and dispatches resume jobs.

Polls workflow_run_recipient_states with status in ('waiting','ready'). For each
recipient picked, advances current_node_id along the wakeup edge (for logic.wait
nodes) or the success edge (for action nodes whose state was flipped via webhook).
Groups by run_id and submits one BackgroundJob('run-workflow') per run with
params.resume_recipient_ids = [...]. The run-workflow handler's resume mode
takes over from there.

Registered as a schedulable job with cron '* * * * *' (1 / minute) by
seed_orchestration_defaults.
"""
from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import SYSTEM_USER_ID
from app.models.job import BackgroundJob
from app.models.orchestration import (
    WorkflowRun,
    WorkflowRunRecipientState,
    WorkflowVersion,
)


_log = logging.getLogger(__name__)


async def poll_and_resume(db: AsyncSession, *, batch_limit: int = 1000) -> int:
    """Returns number of recipients resumed. Called once per scheduler tick."""
    stmt = (
        select(WorkflowRunRecipientState)
        .where(WorkflowRunRecipientState.status.in_(("waiting", "ready")))
        .order_by(
            WorkflowRunRecipientState.tenant_id,
            WorkflowRunRecipientState.run_id,
        )
        .limit(batch_limit)
        .with_for_update(skip_locked=True)
    )
    rows = (await db.execute(stmt)).scalars().all()
    now = datetime.now(timezone.utc)
    due = [
        r for r in rows
        if r.status == "ready" or (r.wakeup_at is not None and r.wakeup_at <= now)
    ]
    if not due:
        return 0

    version_ids = {r.workflow_version_id for r in due}
    versions = (
        await db.execute(select(WorkflowVersion).where(WorkflowVersion.id.in_(version_ids)))
    ).scalars().all()
    versions_by_id = {v.id: v for v in versions}

    by_run: dict[uuid.UUID, list[str]] = defaultdict(list)
    advanced = 0
    for r in due:
        version = versions_by_id.get(r.workflow_version_id)
        if version is None:
            continue
        # Wake reason lives in the recipient state already: an inbound event
        # (webhook / reconciler) flips status→'ready' and clears wakeup_at;
        # a timer elapse leaves status='waiting' with wakeup_at<=now. No
        # parallel reason field — the state itself distinguishes the two.
        woke_by = "event" if r.status == "ready" else "timeout"
        target = _wakeup_edge_target(version.definition, r.current_node_id or "", woke_by=woke_by)
        new_node = target if target else r.current_node_id
        await db.execute(
            update(WorkflowRunRecipientState)
            .where(WorkflowRunRecipientState.id == r.id)
            .values(status="ready", wakeup_at=None, current_node_id=new_node)
        )
        by_run[r.run_id].append(r.recipient_id)
        advanced += 1

    runs = (
        await db.execute(select(WorkflowRun).where(WorkflowRun.id.in_(by_run.keys())))
    ).scalars().all()
    runs_by_id = {r.id: r for r in runs}

    for run_id, recipient_ids in by_run.items():
        run = runs_by_id[run_id]
        job_user_id = run.triggered_by_user_id or SYSTEM_USER_ID
        job = BackgroundJob(
            id=uuid.uuid4(),
            tenant_id=run.tenant_id,
            app_id=run.app_id,
            user_id=job_user_id,
            job_type="run-workflow",
            queue_class="standard",
            priority=5,
            # ``process_job`` reads tenant_id / user_id off ``params``;
            # every run-workflow submission has to echo them.
            params={
                "run_id": str(run_id),
                "resume_recipient_ids": recipient_ids,
                "tenant_id": str(run.tenant_id),
                "user_id": str(job_user_id),
            },
            status="queued",
        )
        db.add(job)

    await db.flush()
    return advanced


def _wakeup_edge_target(
    definition: dict[str, Any],
    current_node_id: str,
    *,
    woke_by: str = "timeout",
) -> Optional[str]:
    """Return the resume-edge target from ``current_node_id`` for the given wake reason.

    Matches outgoing edges by canonical ``output_id`` (the shape the FE
    persists), with legacy ``label`` as a fallback. The output_id literals
    mirror what ``logic.wait`` declares per mode:

      duration / until_datetime  -> 'wakeup'   (single timer edge)
      event_or_timeout           -> 'event' (inbound) / 'timeout' (timer)

    ``woke_by`` is 'event' when an inbound event flipped the recipient to
    'ready', 'timeout' when the wakeup timer elapsed. For non-wait nodes
    (action rows resumed via webhook reconcile) the success edge is taken.
    """
    if not current_node_id:
        return None
    edges = definition.get("edges", [])
    nodes = definition.get("nodes", [])
    cur_node_type = next((n.get("type") for n in nodes if n.get("id") == current_node_id), None)

    # edge_index[output_id] -> target (mirror traversal's edge-index pattern).
    edge_index: dict[str, str] = {}
    first_target: Optional[str] = None
    for e in edges:
        if e.get("source") != current_node_id:
            continue
        if first_target is None:
            first_target = e.get("target")
        output_id = e.get("output_id") or e.get("label")
        if output_id and output_id not in edge_index:
            edge_index[output_id] = e.get("target")

    if cur_node_type == "logic.wait":
        # event reason → 'event'; timer reason → 'timeout', then 'wakeup'
        # (single-timer modes only ever wire 'wakeup').
        preferred = ["event"] if woke_by == "event" else ["timeout", "wakeup"]
    else:
        preferred = ["success"]

    for output_id in preferred:
        if output_id in edge_index:
            return edge_index[output_id]
    return first_target

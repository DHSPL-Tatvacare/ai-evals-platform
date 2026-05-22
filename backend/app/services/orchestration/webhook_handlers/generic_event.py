"""Fire a single token-resolved event trigger: one canonical batch → one workflow run.

The inbound route resolves the trigger by its webhook_token, the vendor adapter
normalizes the native payload into a CanonicalEventBatch, and this module
creates exactly one workflow_runs row + one run-workflow job for THAT trigger.
Replay dedupe keys on (trigger_id, batch.ingest_id): a CRM retry returns the
prior run instead of creating a second one.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import SYSTEM_USER_ID
from app.models.job import BackgroundJob
from app.models.orchestration import (
    EventIngestLog,
    Workflow,
    WorkflowRun,
    WorkflowTrigger,
)
from app.services.orchestration.adapters.canonical import CanonicalEventBatch

_log = logging.getLogger(__name__)


class EventPayloadContractError(ValueError):
    """Raised when an inbound event references no recipient(s)."""


class EventTriggerConfigurationError(ValueError):
    """Raised when a matching trigger points at an invalid workflow state."""


@dataclass(frozen=True)
class EventFireResult:
    run_ids: list[uuid.UUID] = field(default_factory=list)
    deduped: bool = False


def _recipients_payload(batch: CanonicalEventBatch) -> dict[str, Any]:
    return {
        "recipients": [
            {"recipient_id": r.recipient_id, "payload": dict(r.payload)}
            for r in batch.recipients
        ],
        "event_name": batch.event_name,
    }


async def fire_event(
    db: AsyncSession,
    *,
    trigger: WorkflowTrigger,
    batch: CanonicalEventBatch,
    triggered_by_user_id: uuid.UUID | None = None,
) -> EventFireResult:
    """Create one workflow_run + one run-workflow job for ``trigger``.

    Idempotent on ``(trigger.id, batch.ingest_id)`` — a duplicate inbound event
    returns the prior run ids without creating a second run. No-op (empty
    result) when the trigger is inactive."""
    if not trigger.active:
        return EventFireResult(run_ids=[], deduped=False)
    if not batch.recipients:
        raise EventPayloadContractError(
            "event payload must reference at least one recipient"
        )

    tenant_id = trigger.tenant_id
    app_id = trigger.app_id

    if batch.ingest_id:
        ingest_key = batch.ingest_id
        prior = (await db.execute(
            select(EventIngestLog).where(
                EventIngestLog.trigger_id == trigger.id,
                EventIngestLog.ingest_key == ingest_key,
                EventIngestLog.tenant_id == tenant_id,
            )
        )).scalar_one_or_none()
        if prior is not None:
            return EventFireResult(
                run_ids=[uuid.UUID(r) for r in (prior.run_ids or [])], deduped=True,
            )

    wf = (await db.execute(
        select(Workflow).where(
            Workflow.id == trigger.workflow_id,
            Workflow.tenant_id == tenant_id,
        )
    )).scalar_one_or_none()
    if wf is None or not wf.active or wf.current_published_version_id is None:
        raise EventTriggerConfigurationError(
            "event trigger references a workflow without a published version"
        )

    run = WorkflowRun(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        app_id=app_id,
        workflow_id=wf.id,
        workflow_version_id=wf.current_published_version_id,
        trigger_id=trigger.id,
        triggered_by="event",
        triggered_by_user_id=triggered_by_user_id,
        status="pending",
        params={"event_payload": _recipients_payload(batch)},
    )
    db.add(run)
    await db.flush()

    job_user_id = triggered_by_user_id or trigger.created_by or SYSTEM_USER_ID
    job = BackgroundJob(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        app_id=app_id,
        user_id=job_user_id,
        job_type="run-workflow",
        queue_class="standard",
        priority=5,
        params={
            "run_id": str(run.id),
            "tenant_id": str(tenant_id),
            "user_id": str(job_user_id),
        },
        status="queued",
    )
    db.add(job)
    await db.flush()
    run.job_id = job.id

    if batch.ingest_id:
        db.add(EventIngestLog(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            app_id=app_id,
            trigger_id=trigger.id,
            ingest_key=batch.ingest_id,
            run_ids=[str(run.id)],
        ))
        try:
            await db.flush()
        except IntegrityError:
            # Concurrent duplicate inbound event raced us to the unique index;
            # roll back to the prior savepoint and resolve the winner's run.
            await db.rollback()
            prior = (await db.execute(
                select(EventIngestLog).where(
                    EventIngestLog.trigger_id == trigger.id,
                    EventIngestLog.ingest_key == batch.ingest_id,
                )
            )).scalar_one_or_none()
            if prior is not None:
                return EventFireResult(
                    run_ids=[uuid.UUID(r) for r in (prior.run_ids or [])], deduped=True,
                )
            raise

    return EventFireResult(run_ids=[run.id], deduped=False)


__all__ = [
    "EventFireResult",
    "EventPayloadContractError",
    "EventTriggerConfigurationError",
    "fire_event",
]

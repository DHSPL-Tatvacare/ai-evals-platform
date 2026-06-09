"""Builders for the CRM ingestion job chain: sync → unpack → resolved refresh → analytics populate.

A sync lands raw records; the unpack populates the serving core + refreshes the resolved matviews
(dim_lead / fact_lead_activity); the analytics populate rebuilds the deterministic lead facts. Each
step enqueues the next as a ``BackgroundJob`` (mirroring the workflow-engagement post-run hook) so a
scheduled sync runs the whole chain. Every step is idempotent, so the chain is safe to re-run.

Note: the LLM-extracted ``backfill-lead-signals`` populator is intentionally NOT auto-chained (it
incurs generation cost); it stays an explicit, operator-triggered job. The deterministic
``backfill-stage-transitions`` populator is the analytics tail of the automatic chain.
"""
from __future__ import annotations

import uuid

from app.models.job import BackgroundJob

CHAIN_JOB_TYPES = (
    "sync-crm-source",
    "unpack-crm-source",
    "populate-crm-resolved",
    "backfill-stage-transitions",
)

_ANALYTICS_POPULATE_JOB = "backfill-stage-transitions"


def build_unpack_job(
    *, tenant_id: uuid.UUID, user_id: uuid.UUID, app_id: str, connection_id: str
) -> BackgroundJob:
    """The follow-on ``unpack-crm-source`` job a sync enqueues once records land."""
    return BackgroundJob(
        id=uuid.uuid4(), tenant_id=tenant_id, user_id=user_id, app_id=app_id,
        job_type="unpack-crm-source", queue_class="standard", priority=120, max_attempts=1,
        status="queued",
        progress={"current": 0, "total": 0, "message": "Unpack queued (chained after sync)"},
        params={
            "app_id": app_id, "connection_id": connection_id,
            "tenant_id": str(tenant_id), "user_id": str(user_id),
        },
    )


def build_analytics_populate_job(
    *, tenant_id: uuid.UUID, user_id: uuid.UUID, app_id: str
) -> BackgroundJob:
    """The analytics tail the unpack enqueues: rebuild the deterministic lead facts for this app."""
    return BackgroundJob(
        id=uuid.uuid4(), tenant_id=tenant_id, user_id=user_id, app_id=app_id,
        job_type=_ANALYTICS_POPULATE_JOB, queue_class="bulk", priority=520, max_attempts=1,
        status="queued",
        progress={"current": 0, "total": 0, "message": "Analytics populate queued (chained after unpack)"},
        params={"app_id": app_id, "tenant_id": str(tenant_id), "user_id": str(user_id)},
    )


__all__ = [
    "CHAIN_JOB_TYPES",
    "build_unpack_job",
    "build_analytics_populate_job",
]

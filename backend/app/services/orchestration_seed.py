"""Seed loader for orchestration.* — system action templates + seed workflows + scheduled poller.

Phase 0 shipped empty scaffolding. Phase 4 adds the singleton resume-waiting-cohorts
scheduled job. Phase 8 (concierge cutover) will add system action templates +
the 'Default MQL Concierge' seeded crm workflow here.

Loader runs idempotently from app startup (lifespan hook). Each insert uses
the model's natural-key uniqueness so reseed is a no-op.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import SYSTEM_TENANT_ID, SYSTEM_USER_ID
from app.models.scheduled_job import ScheduledJobDefinition
from app.models.tenant import Tenant
from app.models.user import User


_log = logging.getLogger(__name__)


RESUME_POLLER_APP_ID = ""
RESUME_POLLER_JOB_TYPE = "resume-waiting-cohorts"
RESUME_POLLER_SCHEDULE_KEY = "platform:orchestration:resume-waiting-cohorts"
# 1/min. Cheap query backed by a partial index on (status, wakeup_at);
# matches the temporal/airflow default poll cadence.
RESUME_POLLER_CRON = "* * * * *"


async def seed_orchestration_defaults(db: AsyncSession) -> None:
    """Insert orchestration system defaults. Idempotent."""
    await _ensure_resume_poller_scheduled(db)


async def _ensure_resume_poller_scheduled(
    db: AsyncSession, *, now: datetime | None = None
) -> bool:
    """Insert the singleton resume-waiting-cohorts schedule row if absent."""
    current = now or datetime.now(timezone.utc)

    existing = await db.scalar(
        select(ScheduledJobDefinition).where(
            ScheduledJobDefinition.tenant_id == SYSTEM_TENANT_ID,
            ScheduledJobDefinition.app_id == RESUME_POLLER_APP_ID,
            ScheduledJobDefinition.job_type == RESUME_POLLER_JOB_TYPE,
            ScheduledJobDefinition.schedule_key == RESUME_POLLER_SCHEDULE_KEY,
        )
    )
    if existing is not None:
        return False

    tenant = await db.get(Tenant, SYSTEM_TENANT_ID)
    if tenant is None:
        _log.warning(
            "orchestration.resume_poller.seed.missing_system_tenant tenant_id=%s — skipping",
            SYSTEM_TENANT_ID,
        )
        return False

    system_user = await db.get(User, SYSTEM_USER_ID)
    created_by = SYSTEM_USER_ID if system_user is not None else None

    from app.services.scheduler.engine import next_cron_tick

    schedule = ScheduledJobDefinition(
        id=uuid.uuid4(),
        tenant_id=SYSTEM_TENANT_ID,
        app_id=RESUME_POLLER_APP_ID,
        job_type=RESUME_POLLER_JOB_TYPE,
        schedule_key=RESUME_POLLER_SCHEDULE_KEY,
        name="Platform · Orchestration resume poller",
        description=(
            "Polls orchestration.workflow_run_recipient_states for due/ready rows "
            "every minute, advances them along the appropriate edge, and dispatches "
            "run-workflow jobs grouped by run_id."
        ),
        cron=RESUME_POLLER_CRON,
        params={},
        override={},
        enabled=True,
        next_check_at=next_cron_tick(RESUME_POLLER_CRON, current),
        current_cycle_attempts=0,
        created_by=created_by,
        created_at=current,
        updated_at=current,
    )
    db.add(schedule)
    await db.flush()
    _log.info(
        "orchestration.resume_poller.seed.inserted schedule_id=%s cron=%r",
        schedule.id,
        RESUME_POLLER_CRON,
    )
    return True

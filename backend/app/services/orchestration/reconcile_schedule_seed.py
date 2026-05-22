"""Seed the platform-wide voice-dispatch reconciliation poller under the system tenant (app_id="")."""
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

RECONCILE_VOICE_APP_ID = ""
RECONCILE_VOICE_JOB_TYPE = "reconcile-voice-dispatch"
RECONCILE_VOICE_SCHEDULE_KEY = "platform:orchestration:reconcile-voice-dispatch"

# Every minute — polling only matters for the short active window of a call.
RECONCILE_VOICE_CRON = "* * * * *"


async def seed_reconcile_voice_schedule(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> bool:
    """Insert the voice reconciliation poller schedule if absent. No-op otherwise."""
    current = now or datetime.now(timezone.utc)

    existing = await session.scalar(
        select(ScheduledJobDefinition).where(
            ScheduledJobDefinition.tenant_id == SYSTEM_TENANT_ID,
            ScheduledJobDefinition.app_id == RECONCILE_VOICE_APP_ID,
            ScheduledJobDefinition.job_type == RECONCILE_VOICE_JOB_TYPE,
            ScheduledJobDefinition.schedule_key == RECONCILE_VOICE_SCHEDULE_KEY,
        )
    )
    if existing is not None:
        return False

    tenant = await session.get(Tenant, SYSTEM_TENANT_ID)
    if tenant is None:
        _log.warning(
            "reconcile_voice.schedule_seed.missing_system_tenant tenant_id=%s "
            "— skipping seed (seed_all_defaults order?)",
            SYSTEM_TENANT_ID,
        )
        return False

    system_user = await session.get(User, SYSTEM_USER_ID)
    created_by = SYSTEM_USER_ID if system_user is not None else None

    from app.services.scheduler.engine import next_cron_tick

    schedule = ScheduledJobDefinition(
        id=uuid.uuid4(),
        tenant_id=SYSTEM_TENANT_ID,
        app_id=RECONCILE_VOICE_APP_ID,
        job_type=RECONCILE_VOICE_JOB_TYPE,
        schedule_key=RECONCILE_VOICE_SCHEDULE_KEY,
        name="Voice dispatch reconciliation",
        description=(
            "Polls the provider for terminal status of open voice dispatch actions "
            "and reconciles them, across all tenants. Runs every minute."
        ),
        cron=RECONCILE_VOICE_CRON,
        params={},
        override={},
        enabled=True,
        next_check_at=next_cron_tick(RECONCILE_VOICE_CRON, current),
        current_cycle_attempts=0,
        created_by=created_by,
        created_at=current,
        updated_at=current,
    )
    session.add(schedule)
    await session.flush()
    _log.info(
        "reconcile_voice.schedule_seed.inserted schedule_id=%s cron=%r",
        schedule.id,
        RECONCILE_VOICE_CRON,
    )
    return True

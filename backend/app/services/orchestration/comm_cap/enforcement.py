"""The single Reach-Limit enforcer: count the resolved contact's prior sends."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.orchestration.comm_cap.policy_resolver import is_capped


@dataclass(frozen=True)
class EnforcementResult:
    proceed: bool
    reason: str | None = None


async def enforce_comm_cap_or_skip(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    app_id: str,
    contact: str,
    channel: str,
    stage: str = "cap_runtime",
) -> EnforcementResult:
    """Decide whether dispatch may proceed for ``contact`` on ``channel``.

    Counts prior sends for this resolved contact (the action ledger's
    ``contact_phone_e164`` = ``payload.contact``), per channel, over the active
    policy's rolling window. Over the cap ⇒ ``proceed=False`` (caller skips the
    recipient as ``skipped_capped``); under ⇒ ``proceed=True``. Read-only — it
    flips no state and writes no ledger row; the dispatch handler reacts.
    """
    capped = await is_capped(
        db,
        tenant_id=tenant_id,
        app_id=app_id,
        phone_e164=contact,
        channel=channel,
    )
    if capped:
        return EnforcementResult(proceed=False, reason=stage)
    return EnforcementResult(proceed=True)

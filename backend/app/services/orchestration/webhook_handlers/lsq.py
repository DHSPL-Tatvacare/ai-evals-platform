"""LSQ inbound webhook → translate to a 'lsq.lead.updated' event.

LSQ webhook payloads are passed verbatim as event_payload to fire_event so
matching triggers can read whatever fields they care about.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.orchestration.webhook_handlers.generic_event import fire_event


async def handle_lsq_event(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    app_id: str,
    payload: dict[str, Any],
) -> list[uuid.UUID]:
    return await fire_event(
        db,
        tenant_id=tenant_id,
        app_id=app_id,
        event_name="lsq.lead.updated",
        event_payload=payload,
    )

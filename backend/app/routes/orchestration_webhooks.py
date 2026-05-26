"""Inbound orchestration webhooks — PUBLIC routes."""
from __future__ import annotations

import logging
import uuid
from dataclasses import replace
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.orchestration import WorkflowTrigger
from app.models.provider_connection import ProviderConnection
from app.services.orchestration.adapters import (
    AdapterNotRegisteredError,
    resolve_adapter,
)

_log = logging.getLogger(__name__)

# Public ingest is an abuse/cost surface — cap the body and recipient fan-in.
_MAX_EVENT_BODY_BYTES = 1_000_000
_MAX_EVENT_RECIPIENTS = 5_000

router = APIRouter(prefix="/api/orchestration/webhooks", tags=["orchestration-webhooks"])


async def _resolve_connection_by_token(
    db: AsyncSession, *, vendor: str, token: str,
) -> tuple[uuid.UUID, str]:
    """Look up an active connection by ``(provider, webhook_token)``.

    Returns ``(tenant_id, app_id)``. Raises 404 when token is missing,
    unknown, mapped to a different vendor, or the connection is inactive.
    """
    if not token:
        raise HTTPException(status_code=404, detail="not found")
    row = await db.scalar(
        select(ProviderConnection).where(
            ProviderConnection.webhook_token == token,
            ProviderConnection.active.is_(True),
        )
    )
    if row is None or row.provider != vendor:
        raise HTTPException(status_code=404, detail="not found")
    return row.tenant_id, row.app_id


async def _dispatch_to_adapter(
    db: AsyncSession,
    *,
    capability: str,
    vendor: str,
    token: str,
    payload: dict[str, Any],
) -> dict[str, str]:
    try:
        adapter = resolve_adapter(capability=capability, vendor=vendor)
    except AdapterNotRegisteredError:
        raise HTTPException(status_code=404, detail="not found")
    tenant_id, app_id = await _resolve_connection_by_token(db, vendor=vendor, token=token)
    await adapter.handle_webhook(
        db, tenant_id=tenant_id, app_id=app_id, payload=payload,
    )
    await db.commit()
    return {"status": "ok"}


@router.post("/messaging/{vendor}/{token}", status_code=200)
async def messaging_webhook(
    vendor: str = Path(...),
    token: str = Path(...),
    payload: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    return await _dispatch_to_adapter(
        db, capability="messaging", vendor=vendor, token=token, payload=payload,
    )


@router.post("/voice/{vendor}/{token}", status_code=200)
async def voice_webhook(
    vendor: str = Path(...),
    token: str = Path(...),
    payload: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    return await _dispatch_to_adapter(
        db, capability="voice", vendor=vendor, token=token, payload=payload,
    )


async def _resolve_trigger_by_token(
    db: AsyncSession, *, vendor: str, token: str,
) -> WorkflowTrigger:
    """Resolve exactly one active event trigger by its webhook_token.

    Returns the trigger (carrying tenant_id + app_id). Raises 404 when the
    token is missing, unknown, inactive, or bound to a different vendor —
    never revealing which condition failed."""
    if not token:
        raise HTTPException(status_code=404, detail="not found")
    trig = await db.scalar(
        select(WorkflowTrigger).where(
            WorkflowTrigger.webhook_token == token,
            WorkflowTrigger.kind == "event",
            WorkflowTrigger.active.is_(True),
        )
    )
    if trig is None or trig.vendor != vendor:
        raise HTTPException(status_code=404, detail="not found")
    return trig


@router.post("/event/{vendor}/{token}", status_code=200)
async def event_ingest_webhook(
    request: Request,
    vendor: str = Path(...),
    token: str = Path(...),
    payload: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Token-resolved event ingest. One token → one trigger → one workflow + tenant."""
    raw_body = await request.body()
    if len(raw_body) > _MAX_EVENT_BODY_BYTES:
        raise HTTPException(status_code=413, detail="event payload too large")

    try:
        adapter = resolve_adapter(capability="event_source", vendor=vendor)
    except AdapterNotRegisteredError:
        raise HTTPException(status_code=404, detail="not found")

    trigger = await _resolve_trigger_by_token(db, vendor=vendor, token=token)

    if not adapter.verify_signature(raw_body, dict(request.headers)):
        raise HTTPException(status_code=404, detail="not found")

    headers = dict(request.headers)
    canonical_name = adapter.map_event_name(payload, headers=headers)
    if vendor == "webhook" and not canonical_name:
        # Identity passthrough carries no native fields — the trigger's own
        # event_name (NOT-NULL for kind='event') makes its sample runnable.
        canonical_name = trigger.event_name
    if not canonical_name:
        # Native event has no canonical mapping — acknowledge so the CRM stops
        # retrying, but create nothing.
        _log.info(
            "event_ingest.unmapped vendor=%s trigger_id=%s", vendor, trigger.id,
        )
        return {"status": "ok", "runsCreated": 0, "deduped": False, "runIds": []}

    batch = adapter.normalize_event(payload, headers=headers)
    if vendor == "webhook" and not batch.event_name:
        batch = replace(batch, event_name=canonical_name)
    if len(batch.recipients) > _MAX_EVENT_RECIPIENTS:
        raise HTTPException(status_code=413, detail="too many recipients in one event")

    from app.services.orchestration.webhook_handlers.generic_event import (
        EventPayloadContractError,
        EventTriggerConfigurationError,
        fire_event,
    )
    try:
        result = await fire_event(db, trigger=trigger, batch=batch)
    except EventPayloadContractError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EventTriggerConfigurationError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    await db.commit()
    _log.info(
        "event_ingest.fired vendor=%s trigger_id=%s event=%s runs=%d deduped=%s",
        vendor, trigger.id, canonical_name, len(result.run_ids), result.deduped,
    )
    return {
        "status": "ok",
        "runsCreated": len(result.run_ids),
        "deduped": result.deduped,
        "runIds": [str(r) for r in result.run_ids],
    }

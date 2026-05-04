"""Phase 13 / E.3 — sweeper for open Bolna dispatch actions.

Webhooks are the primary status signal. The poller is the safety net
for tenants whose Bolna account doesn't have webhook delivery enabled,
and for the post-call data Bolna emits *after* the initial webhook
(transcript, recording url, cost breakdown).

The poller is dumb:

  1. Pick up every open Bolna action (``provider_terminal=FALSE``).
  2. Group them: ``bolna_execution_id`` → fetch each via
     ``GET /executions/{id}``; ``bolna_batch_id`` → fetch the batch's
     paginated executions list.
  3. For each terminal upstream event, hand it to
     ``bolna_reconciler.apply_event`` — same persistence path the
     webhook uses, idempotent on ``provider_terminal``.

Anything still pending after the sweep is ignored — we'll see it again
on the next tick. Stale actions older than (TBD) get cleaned up later
by a separate sweep; that lives outside Phase E.
"""
from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orchestration import WorkflowRunRecipientAction
from app.models.provider_connection import ProviderConnection
from app.services.orchestration.connections.crypto import decrypt
from app.services.orchestration.dispatch import bolna_reconciler


_log = logging.getLogger(__name__)


# Cap each tick. The default tracks the plan's 200 — small enough to
# keep the run-once latency under the 30s scheduling interval, large
# enough to clear a typical day's backlog over a few ticks.
_DEFAULT_LIMIT = 200


@dataclass(frozen=True)
class PollerStats:
    """One-tick summary returned to the job-handler caller."""
    actions_scanned: int
    singles_polled: int
    batches_polled: int
    events_reconciled: int
    errors: list[str]


async def _fetch_open_actions(
    db: AsyncSession, *, limit: int,
) -> list[WorkflowRunRecipientAction]:
    """Open Bolna actions = parent ``bolna_queued`` rows that haven't
    been reconciled yet. The partial index added in 0024 keeps this
    fast regardless of total table size."""
    stmt = (
        select(WorkflowRunRecipientAction)
        .where(
            WorkflowRunRecipientAction.channel == "bolna",
            WorkflowRunRecipientAction.action_type == "bolna_queued",
            WorkflowRunRecipientAction.provider_terminal.is_(False),
            (
                (WorkflowRunRecipientAction.bolna_execution_id.isnot(None))
                | (WorkflowRunRecipientAction.bolna_batch_id.isnot(None))
            ),
        )
        .order_by(WorkflowRunRecipientAction.created_at)
        .limit(limit)
    )
    return list((await db.execute(stmt)).scalars().all())


async def _connection_config(
    db: AsyncSession, *, action: WorkflowRunRecipientAction,
) -> tuple[uuid.UUID | None, dict[str, Any] | None]:
    """Look up the Bolna connection that owns this action.

    The connection_id isn't stored on the action row directly — we
    reach it via tenant + app + provider scoping, which is unique under
    the system seed. When tenants run >1 Bolna connection per app the
    runtime stores ``connection_id`` in the action's ``payload`` (set by
    the dispatch node). We fall back to that when present.
    """
    payload_cid = (action.payload or {}).get("connection_id")
    if payload_cid:
        try:
            cid = uuid.UUID(str(payload_cid))
        except (TypeError, ValueError):
            cid = None
        if cid is not None:
            row = await db.scalar(
                select(ProviderConnection).where(ProviderConnection.id == cid)
            )
            if row is not None and row.provider == "bolna":
                return cid, decrypt(row.config_encrypted)

    # Fallback: pick the active Bolna connection in this tenant + app.
    row = await db.scalar(
        select(ProviderConnection).where(
            ProviderConnection.tenant_id == action.tenant_id,
            ProviderConnection.app_id == action.app_id,
            ProviderConnection.provider == "bolna",
            ProviderConnection.active.is_(True),
        ).limit(1)
    )
    if row is None:
        return None, None
    return row.id, decrypt(row.config_encrypted)


def _index_executions(
    executions: Iterable[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Index batch executions by recipient_id (preferred) or execution_id."""
    out: dict[str, dict[str, Any]] = {}
    for exec_row in executions:
        if not isinstance(exec_row, dict):
            continue
        ctx = exec_row.get("context_details") or {}
        user_data = (ctx.get("recipient_data") or {}) if isinstance(ctx, dict) else {}
        if not isinstance(user_data, dict):
            user_data = exec_row.get("user_data") or {}
        recipient_id = (
            user_data.get("recipient_id")
            if isinstance(user_data, dict)
            else None
        )
        execution_id = exec_row.get("execution_id") or exec_row.get("id")
        if recipient_id:
            out[f"recipient:{recipient_id}"] = exec_row
        if execution_id:
            out[f"execution:{execution_id}"] = exec_row
    return out


async def run_once(
    db: AsyncSession, *, limit: int = _DEFAULT_LIMIT,
) -> PollerStats:
    """Single sweep — called once per scheduler tick."""
    open_actions = await _fetch_open_actions(db, limit=limit)
    if not open_actions:
        return PollerStats(0, 0, 0, 0, [])

    singles = [a for a in open_actions if a.bolna_execution_id]
    batch_actions: dict[str, list[WorkflowRunRecipientAction]] = defaultdict(list)
    for a in open_actions:
        if a.bolna_batch_id and not a.bolna_execution_id:
            batch_actions[a.bolna_batch_id].append(a)

    # Lazy-import the service classes so the module doesn't pull httpx
    # at scheduler boot when there's nothing to do.
    from app.services.orchestration.integrations.bolna import (
        BolnaService,
        BolnaServiceError,
    )
    from app.services.orchestration.integrations.bolna_batch import (
        BolnaBatchService,
    )

    services: dict[uuid.UUID, BolnaService] = {}
    batch_services: dict[uuid.UUID, BolnaBatchService] = {}
    errors: list[str] = []

    async def _bolna_for(action: WorkflowRunRecipientAction) -> BolnaService | None:
        cid, config = await _connection_config(db, action=action)
        if cid is None or config is None:
            return None
        if cid in services:
            return services[cid]
        try:
            svc = BolnaService(
                base_url=str(config.get("base_url") or ""),
                api_key=str(config.get("api_key") or ""),
                connection_id=cid,
            )
        except ValueError as exc:
            errors.append(f"connection {cid}: {exc}")
            return None
        services[cid] = svc
        return svc

    async def _batch_for(
        action: WorkflowRunRecipientAction,
    ) -> BolnaBatchService | None:
        cid, config = await _connection_config(db, action=action)
        if cid is None or config is None:
            return None
        if cid in batch_services:
            return batch_services[cid]
        try:
            svc = BolnaBatchService(
                base_url=str(config.get("base_url") or ""),
                api_key=str(config.get("api_key") or ""),
                connection_id=cid,
            )
        except ValueError as exc:
            errors.append(f"connection {cid} (batch): {exc}")
            return None
        batch_services[cid] = svc
        return svc

    events_reconciled = 0
    singles_polled = 0
    batches_polled = 0

    # ─── Single-call rows ─────────────────────────────────────────────
    for action in singles:
        bolna = await _bolna_for(action)
        if bolna is None:
            continue
        try:
            event = await bolna.get_execution(
                execution_id=str(action.bolna_execution_id),
            )
        except BolnaServiceError as exc:
            errors.append(f"action {action.id}: {exc}")
            continue
        except Exception as exc:  # noqa: BLE001 — keep the sweep alive
            errors.append(f"action {action.id}: {exc.__class__.__name__}")
            continue
        singles_polled += 1
        if not bolna_reconciler.is_terminal(event.get("status")):
            continue
        applied = await bolna_reconciler.apply_event(db, action=action, event=event)
        if applied:
            events_reconciled += 1

    # ─── Batch rows — one fetch per batch covers every open recipient ─
    for batch_id, actions in batch_actions.items():
        batch_svc = await _batch_for(actions[0])
        if batch_svc is None:
            continue
        executions: list[dict[str, Any]] = []
        page = 1
        try:
            while True:
                payload = await batch_svc.list_batch_executions(
                    batch_id, page=page, page_size=100,
                )
                page_rows = payload.get("executions") or []
                if not isinstance(page_rows, list):
                    break
                executions.extend(page_rows)
                total = payload.get("total")
                if not isinstance(total, int):
                    break
                if len(executions) >= total or not page_rows:
                    break
                page += 1
        except BolnaServiceError as exc:
            errors.append(f"batch {batch_id}: {exc}")
            continue
        except Exception as exc:  # noqa: BLE001 — keep the sweep alive
            errors.append(f"batch {batch_id}: {exc.__class__.__name__}")
            continue
        batches_polled += 1

        index = _index_executions(executions)
        for action in actions:
            event = (
                index.get(f"recipient:{action.recipient_id}")
                or (index.get(f"execution:{action.bolna_execution_id}") if action.bolna_execution_id else None)
            )
            if not event:
                continue
            if not bolna_reconciler.is_terminal(event.get("status")):
                continue
            applied = await bolna_reconciler.apply_event(db, action=action, event=event)
            if applied:
                events_reconciled += 1

    return PollerStats(
        actions_scanned=len(open_actions),
        singles_polled=singles_polled,
        batches_polled=batches_polled,
        events_reconciled=events_reconciled,
        errors=errors,
    )

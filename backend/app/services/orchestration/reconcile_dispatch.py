"""Generic capability poller — PRIMARY dispatch reconciliation across pollable providers."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orchestration import (
    WorkflowRun,
    WorkflowRunNodeStep,
    WorkflowRunRecipientAction,
    WorkflowVersion,
)
from app.services.orchestration.adapters import (
    AdapterNotRegisteredError,
    resolve_adapter,
)
from app.services.orchestration.connections.resolver import (
    ConnectionNotFound,
    ConnectionResolver,
)

_log = logging.getLogger(__name__)


async def reconcile_dispatch(
    db: AsyncSession,
    *,
    capability: str,
    poll_window_seconds: int = 7200,
    limit: int = 500,
) -> int:
    """Pull terminal status for open dispatch actions of one capability.

    Capability-parameterized: the body has no vendor/voice logic — vendor comes
    from the connection's ``__provider__`` and the adapter from
    ``resolve_adapter(capability, vendor)``. Both reconciliation paths converge on
    the adapter's shared ``reconcile_execution`` (idempotent on ``provider_terminal``
    + the per-execution outcome key). Sweeps only within ``poll_window_seconds`` of
    dispatch; ``skip_locked`` + ``limit`` keep it multi-worker safe.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=poll_window_seconds)
    actions = (await db.execute(
        select(WorkflowRunRecipientAction)
        .where(
            WorkflowRunRecipientAction.channel == capability,
            WorkflowRunRecipientAction.provider_terminal.is_(False),
            WorkflowRunRecipientAction.provider_correlation_id.isnot(None),
            WorkflowRunRecipientAction.created_at >= cutoff,
        )
        .order_by(
            WorkflowRunRecipientAction.tenant_id,
            WorkflowRunRecipientAction.run_id,
        )
        .limit(limit)
        .with_for_update(skip_locked=True)
    )).scalars().all()
    if not actions:
        return 0

    run_ids = {a.run_id for a in actions}

    node_by_step = {
        step_id: node_id
        for step_id, node_id in (await db.execute(
            select(WorkflowRunNodeStep.id, WorkflowRunNodeStep.node_id)
            .where(WorkflowRunNodeStep.run_id.in_(run_ids))
        )).all()
    }

    conn_by_node_per_run = await _connection_ids_by_node(db, run_ids)

    # Group by (tenant, app, connection) so each connection resolves config + adapter once.
    grouped: dict[tuple[uuid.UUID, str, uuid.UUID], list[WorkflowRunRecipientAction]] = {}
    action_node: dict[uuid.UUID, str] = {}
    for action in actions:
        node_id = node_by_step.get(action.node_step_id)
        if node_id is None:
            continue
        conn_id = conn_by_node_per_run.get(action.run_id, {}).get(node_id)
        if conn_id is None:
            continue
        action_node[action.id] = node_id
        grouped.setdefault((action.tenant_id, action.app_id, conn_id), []).append(action)

    reconciled = 0
    resolvers: dict[tuple[uuid.UUID, str], ConnectionResolver] = {}
    for (tenant_id, app_id, conn_id), conn_actions in grouped.items():
        resolver = resolvers.get((tenant_id, app_id))
        if resolver is None:
            resolver = ConnectionResolver(db, tenant_id=tenant_id, app_id=app_id)
            resolvers[(tenant_id, app_id)] = resolver
        try:
            config = await resolver.get_config(conn_id)
        except ConnectionNotFound:
            _log.warning("reconcile_dispatch.connection_missing connection_id=%s", conn_id)
            continue
        vendor = config.get("__provider__", "")
        try:
            adapter = resolve_adapter(capability=capability, vendor=vendor)
        except AdapterNotRegisteredError:
            continue
        # Webhook-only providers (no status API) expose no poll method — skip.
        if not hasattr(adapter, "fetch_execution"):
            continue
        single = [a for a in conn_actions if (a.payload or {}).get("mode") != "batch"]
        batch = [a for a in conn_actions if (a.payload or {}).get("mode") == "batch"]

        for action in single:
            execution = await adapter.fetch_execution(
                connection=config, execution_id=action.provider_correlation_id,
            )
            if not execution:
                continue
            if await adapter.reconcile_execution(
                db, action=action, node_id=action_node[action.id], execution=execution,
            ):
                reconciled += 1

        batch_by_id: dict[str, list[WorkflowRunRecipientAction]] = {}
        for action in batch:
            batch_by_id.setdefault(str(action.provider_correlation_id), []).append(action)
        for batch_id, batch_actions in batch_by_id.items():
            reconciled += await _reconcile_batch(
                db, adapter=adapter, config=config, batch_id=batch_id,
                actions=batch_actions, action_node=action_node,
            )

    await db.commit()
    return reconciled


def _phone_key(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


async def _reconcile_batch(
    db: AsyncSession,
    *,
    adapter: Any,
    config: dict[str, Any],
    batch_id: str,
    actions: list[WorkflowRunRecipientAction],
    action_node: dict[uuid.UUID, str],
) -> int:
    """Summary-gated batch reconcile: skip the list until calls have completed, then page + match."""
    # Batch listing is optional on the adapter — webhook covers batch where it's absent.
    if not hasattr(adapter, "fetch_batch_executions"):
        return 0

    # GATE — one cheap summary call; skip the (paged) list while the whole batch is still in-flight.
    summary = await adapter.fetch_batch_summary(connection=config, batch_id=batch_id)
    if summary is None:
        _log.warning("reconcile_dispatch.batch_summary_missing batch_id=%s", batch_id)
        return 0
    status_counts = summary.get("execution_status") or {}
    terminal_ready = sum(
        int(n or 0) for status, n in status_counts.items() if adapter.is_terminal(status)
    )
    if terminal_ready <= 0:
        return 0

    # Match rows to still-open actions by recipient_id, then by phone; reconcile_execution's
    # own terminality guard decides each row, so a still-ringing row stays pending.
    by_recipient = {a.recipient_id: a for a in actions}
    by_phone = {_phone_key((a.payload or {}).get("contact")): a for a in actions}
    pending: set[uuid.UUID] = {a.id for a in actions}

    reconciled = 0
    page_number = 1
    while pending:
        page = await adapter.fetch_batch_executions(
            connection=config, batch_id=batch_id, page_number=page_number,
        )
        for row in (page.get("data") or []):
            ctx = row.get("context_details")
            ctx = ctx if isinstance(ctx, dict) else {}
            rdata = ctx.get("recipient_data")
            rdata = rdata if isinstance(rdata, dict) else {}
            tele = row.get("telephony_data")
            tele = tele if isinstance(tele, dict) else {}
            rid = rdata.get("recipient_id")
            action = (by_recipient.get(rid) if rid else None) or by_phone.get(
                _phone_key(tele.get("to_number"))
            )
            if action is None or action.id not in pending:
                continue
            if await adapter.reconcile_execution(
                db, action=action, node_id=action_node[action.id], execution=row,
            ):
                reconciled += 1
                pending.discard(action.id)
        if not page.get("has_more"):
            break
        page_number += 1
    return reconciled


async def _connection_ids_by_node(
    db: AsyncSession, run_ids: set[uuid.UUID],
) -> dict[uuid.UUID, dict[str, uuid.UUID]]:
    """run_id -> {node_id: connection_id}, read from each run's version definition."""
    run_rows = (await db.execute(
        select(WorkflowRun).where(WorkflowRun.id.in_(run_ids))
    )).scalars().all()
    version_ids = {r.workflow_version_id for r in run_rows}
    versions = {
        v.id: v
        for v in (await db.execute(
            select(WorkflowVersion).where(WorkflowVersion.id.in_(version_ids))
        )).scalars().all()
    }
    out: dict[uuid.UUID, dict[str, uuid.UUID]] = {}
    for run in run_rows:
        version = versions.get(run.workflow_version_id)
        mapping: dict[str, uuid.UUID] = {}
        for node in ((version.definition if version else {}) or {}).get("nodes", []):
            raw = (node.get("config") or {}).get("connection_id")
            if not raw:
                continue
            try:
                mapping[node["id"]] = uuid.UUID(str(raw))
            except (ValueError, KeyError):
                continue
        out[run.id] = mapping
    return out

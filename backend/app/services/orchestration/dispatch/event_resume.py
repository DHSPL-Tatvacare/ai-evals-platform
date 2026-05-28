"""Shared event-resume core — resumes a parked recipient only when the event it actually awaits arrives."""
from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any, Collection

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orchestration import WorkflowRunRecipientState, WorkflowVersion
from app.services.orchestration.definition_normalizer import normalize_definition
from app.services.orchestration.dispatch.bag import bag_write
from app.services.orchestration.nodes import logic_wait
from app.services.orchestration.predicate_contract import MissingFieldError, evaluate

if TYPE_CHECKING:
    from app.services.orchestration.adapters.canonical import CanonicalEventBatch

_log = logging.getLogger(__name__)


def _ttl_gate():
    """A sealed (aborted / lapsed) recipient never resumes."""
    return or_(
        WorkflowRunRecipientState.ignore_webhooks_after.is_(None),
        WorkflowRunRecipientState.ignore_webhooks_after > func.now(),
    )


async def _resume_state(
    db: AsyncSession,
    *,
    state: WorkflowRunRecipientState,
    event_names: Collection[str],
    payload: dict[str, Any],
    reason: str,
    match_correlation: bool = False,
) -> bool:
    """Shared core: gate the wait config, optionally correlation-match, flip->ready, bag_write, enqueue."""
    current_node_id = state.current_node_id
    if not current_node_id:
        return False

    # Resolve the wait node from the run's own version definition — provider truth never decides the node.
    version = await db.scalar(
        select(WorkflowVersion).where(WorkflowVersion.id == state.workflow_version_id)
    )
    if version is None:
        return False
    canonical = normalize_definition(version.definition or {})
    node = next(
        (n for n in canonical.get("nodes", []) if n.get("id") == current_node_id),
        None,
    )
    if node is None or node.get("type") != "logic.wait":
        return False

    config = logic_wait._Config(**(node.get("config") or {}))

    # Bug E core: only an event-mode wait whose event_name is satisfied may resume.
    if config.mode not in {"event", "event_or_timeout"}:
        return False
    if config.event_name not in event_names:
        return False

    # Path B: the inbound row must name THIS parked recipient via the wait's correlation key.
    if match_correlation:
        if config.correlation is None:
            return False
        key = payload.get(config.correlation.recipient_id_field)
        if str(key) != state.recipient_id:
            return False

    if config.event_match is not None:
        try:
            if not evaluate(config.event_match, payload):
                return False
        except MissingFieldError:
            return False

    ttl_gate = _ttl_gate()
    flip_result = await db.execute(
        update(WorkflowRunRecipientState)
        .where(
            WorkflowRunRecipientState.run_id == state.run_id,
            WorkflowRunRecipientState.recipient_id == state.recipient_id,
            WorkflowRunRecipientState.status == "waiting",
            ttl_gate,
        )
        .values(status="ready", wakeup_at=None)
    )
    if not bool(getattr(flip_result, "rowcount", 0)):
        return False

    # Record the event payload under the wait node so downstream nodes can branch on it.
    namespaced = bag_write(node_id=current_node_id, fields=payload)
    if namespaced:
        await db.execute(
            update(WorkflowRunRecipientState)
            .where(
                WorkflowRunRecipientState.run_id == state.run_id,
                WorkflowRunRecipientState.recipient_id == state.recipient_id,
                ttl_gate,
            )
            .values(payload=WorkflowRunRecipientState.payload.op("||")(namespaced))
        )

    from app.services.orchestration.dispatch.resume_enqueue import (
        enqueue_resume_for_recipient,
    )
    await enqueue_resume_for_recipient(
        db, run_id=state.run_id, recipient_id=state.recipient_id,
        available_at=None, reason=reason,
    )
    return True


async def resume_waiting_on_event(
    db: AsyncSession,
    *,
    run_id: uuid.UUID,
    recipient_id: str,
    event_names: Collection[str],
    payload: dict[str, Any],
    reason: str,
) -> bool:
    """Resume the parked recipient iff it waits at a logic.wait whose event the inbound event satisfies."""
    state = await db.scalar(
        select(WorkflowRunRecipientState).where(
            WorkflowRunRecipientState.run_id == run_id,
            WorkflowRunRecipientState.recipient_id == recipient_id,
            WorkflowRunRecipientState.status == "waiting",
            _ttl_gate(),
        )
    )
    if state is None:
        return False
    return await _resume_state(
        db, state=state, event_names=event_names, payload=payload,
        reason=reason, match_correlation=False,
    )


async def resume_waiting_on_inbound_event(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    app_id: str,
    workflow_id: uuid.UUID,
    batch: "CanonicalEventBatch",
    reason_prefix: str,
) -> int:
    """Resume waiting recipients of this workflow that await this inbound event (correlation-matched)."""
    candidates = (await db.execute(
        select(WorkflowRunRecipientState).where(
            WorkflowRunRecipientState.tenant_id == tenant_id,
            WorkflowRunRecipientState.app_id == app_id,
            WorkflowRunRecipientState.workflow_id == workflow_id,
            WorkflowRunRecipientState.status == "waiting",
            _ttl_gate(),
        )
    )).scalars().all()

    resumed = 0
    for recipient in batch.recipients:
        for state in candidates:
            reason = f"{reason_prefix}:{batch.event_name}:{state.recipient_id}"
            try:
                if await _resume_state(
                    db, state=state, event_names={batch.event_name},
                    payload=recipient.payload, reason=reason, match_correlation=True,
                ):
                    resumed += 1
            except Exception:  # one bad recipient must never break the trigger path or other resumes
                _log.exception(
                    "event_resume.path_b.failed run_id=%s recipient_id=%s",
                    state.run_id, state.recipient_id,
                )
    return resumed

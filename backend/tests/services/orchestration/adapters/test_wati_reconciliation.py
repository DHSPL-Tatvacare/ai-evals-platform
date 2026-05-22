"""I2: WATI round-trip reconciliation over the generic correlation contract.

Status events match on the provider_correlation_id COLUMN (localMessageId);
the outbound WAMID (whatsappMessageId) is captured into provider_reply_ref when
it first appears; inbound replies match replyContextId on provider_reply_ref —
never a response JSONB path. Exercised via handle_webhook against a real session.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.orchestration import (
    WorkflowRunRecipientAction,
    WorkflowRunRecipientState,
)
from app.services.orchestration.adapters.wati import WatiAdapter


# Verbatim WATI v2 webhook shapes (support.wati.io). Status events carry the
# outbound localMessageId AND whatsappMessageId (the outbound WAMID). The reply
# quotes that WAMID via replyContextId.
_OUTBOUND_WAMID = "gBEGkXmJQZVJAgkRHwjjZsITS6M"


def _delivered_event(local_msg_id: str) -> dict:
    return {
        "eventType": "sentMessageDELIVERED_v2",
        "statusString": "Delivered",
        "localMessageId": local_msg_id,
        "whatsappMessageId": _OUTBOUND_WAMID,
        "timestamp": "1678544854",
        "waId": "919999999999",
    }


def _reply_event() -> dict:
    return {
        "eventType": "messageReceived",
        "statusString": "Received",
        "localMessageId": "inbound-lm-1",
        "whatsappMessageId": "wamid.INBOUND_OWN_ID",
        "replyContextId": _OUTBOUND_WAMID,
        "waId": "919999999999",
        "text": "Yes please",
    }


async def _seed_dispatch(db, *, run, version, workflow, node_step, tenant_id, app_id,
                         local_msg_id: str, recipient_id: str = "L-recon"):
    db.add(WorkflowRunRecipientState(
        id=uuid.uuid4(), tenant_id=tenant_id, app_id=app_id,
        workflow_id=workflow.id, workflow_version_id=version.id,
        run_id=run.id, recipient_id=recipient_id, current_node_id="n1",
        status="waiting", wakeup_at=datetime.now(timezone.utc) + timedelta(days=1),
        payload={},
    ))
    action = WorkflowRunRecipientAction(
        id=uuid.uuid4(), tenant_id=tenant_id, app_id=app_id,
        workflow_id=workflow.id, workflow_version_id=version.id,
        run_id=run.id, node_step_id=node_step.id, recipient_id=recipient_id,
        channel="whatsapp", action_type="wa_dispatched", status="success",
        idempotency_key=f"k-{uuid.uuid4().hex[:8]}",
        payload={"contact": "+919999999999"},
        response={"raw": {}, "provider_correlation_id": local_msg_id},
        provider_correlation_id=local_msg_id,
    )
    db.add(action)
    await db.flush()
    return action


@pytest.mark.asyncio
async def test_status_event_matches_on_correlation_column_and_captures_reply_ref(
    db_session, seed_full_run,
):
    run, version, workflow, node_step, tenant_id, app_id = seed_full_run
    local_msg_id = f"lm-{uuid.uuid4().hex[:8]}"
    parent = await _seed_dispatch(
        db_session, run=run, version=version, workflow=workflow,
        node_step=node_step, tenant_id=tenant_id, app_id=app_id,
        local_msg_id=local_msg_id,
    )

    await WatiAdapter().handle_webhook(
        db_session, tenant_id=tenant_id, app_id=app_id,
        payload=_delivered_event(local_msg_id),
    )

    # A child wa_delivered row was created (matched on the correlation column).
    types = (await db_session.execute(
        select(WorkflowRunRecipientAction.action_type).where(
            WorkflowRunRecipientAction.run_id == run.id,
            WorkflowRunRecipientAction.recipient_id == "L-recon",
        )
    )).scalars().all()
    assert "wa_delivered" in types

    # The outbound WAMID was captured into the parent's provider_reply_ref column.
    await db_session.refresh(parent)
    assert parent.provider_reply_ref == _OUTBOUND_WAMID


@pytest.mark.asyncio
async def test_reply_matches_on_provider_reply_ref_column(db_session, seed_full_run):
    run, version, workflow, node_step, tenant_id, app_id = seed_full_run
    local_msg_id = f"lm-{uuid.uuid4().hex[:8]}"
    parent = await _seed_dispatch(
        db_session, run=run, version=version, workflow=workflow,
        node_step=node_step, tenant_id=tenant_id, app_id=app_id,
        local_msg_id=local_msg_id,
    )
    # The outbound WAMID is already on the parent (captured at delivered/sent).
    parent.provider_reply_ref = _OUTBOUND_WAMID
    await db_session.flush()

    await WatiAdapter().handle_webhook(
        db_session, tenant_id=tenant_id, app_id=app_id, payload=_reply_event(),
    )

    # The reply matched on provider_reply_ref (not a response JSONB path) and a
    # wa_replied child was routed.
    types = (await db_session.execute(
        select(WorkflowRunRecipientAction.action_type).where(
            WorkflowRunRecipientAction.run_id == run.id,
            WorkflowRunRecipientAction.recipient_id == "L-recon",
        )
    )).scalars().all()
    assert "wa_replied" in types

    # Recipient flipped waiting → ready by the resuming reply event.
    state = (await db_session.execute(
        select(WorkflowRunRecipientState).where(
            WorkflowRunRecipientState.run_id == run.id,
            WorkflowRunRecipientState.recipient_id == "L-recon",
        )
    )).scalar_one()
    assert state.status == "ready"


@pytest.mark.asyncio
async def test_reply_without_matching_reply_ref_does_not_route(db_session, seed_full_run):
    """A reply quoting an unknown WAMID matches nothing — no child, no flip."""
    run, version, workflow, node_step, tenant_id, app_id = seed_full_run
    local_msg_id = f"lm-{uuid.uuid4().hex[:8]}"
    await _seed_dispatch(
        db_session, run=run, version=version, workflow=workflow,
        node_step=node_step, tenant_id=tenant_id, app_id=app_id,
        local_msg_id=local_msg_id,
    )
    # provider_reply_ref left NULL — the reply's replyContextId can't match.

    await WatiAdapter().handle_webhook(
        db_session, tenant_id=tenant_id, app_id=app_id, payload=_reply_event(),
    )

    types = (await db_session.execute(
        select(WorkflowRunRecipientAction.action_type).where(
            WorkflowRunRecipientAction.run_id == run.id,
            WorkflowRunRecipientAction.recipient_id == "L-recon",
        )
    )).scalars().all()
    assert "wa_replied" not in types

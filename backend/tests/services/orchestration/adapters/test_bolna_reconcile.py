"""Two-path voice reconciliation — terminal statuses, shared core, webhook shape, idempotency.

No live Bolna calls — verbatim payload fixtures + a real db_session only.
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
from app.services.orchestration.adapters.bolna import (
    BolnaAdapter,
    _canonical_outcome,
    classify_outcome,
    is_terminal,
    voice_event_name,
)
from app.services.orchestration.dispatch.bag import bag_read


def test_call_disconnected_is_terminal():
    assert is_terminal("call-disconnected") is True


def test_call_disconnected_maps_to_no_answer():
    """A connect-then-drop is a no-reach outcome, not a failure — it must route
    down the same branch as RNR/busy so the recovery path fires."""
    assert classify_outcome("call-disconnected", None) == "bolna_rnr"
    assert _canonical_outcome("bolna_rnr") == "no_answer"


def test_outcome_buckets_unchanged_for_other_statuses():
    assert classify_outcome("completed", None) == "bolna_answered"
    assert classify_outcome("no-answer", None) == "bolna_rnr"
    assert classify_outcome("busy", None) == "bolna_rnr"
    assert classify_outcome("error", None) == "bolna_failed"
    assert classify_outcome("balance-low", None) == "bolna_failed"


def test_normalize_webhook_reads_nested_id_and_contact():
    event = BolnaAdapter().normalize_webhook({
        "id": "e1", "status": "completed",
        "telephony_data": {"to_number": "+91x"},
        "context_details": {"recipient_phone_number": "+91x"},
    })
    assert event.provider_correlation_id == "e1"
    assert event.contact == "+91x"


async def _seed_voice_action(
    db, *, run, version, workflow, node_step, tenant_id, app_id,
    correlation_id: str, recipient_id: str = "P-recon", mode: str = "single",
):
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
        channel="voice", action_type="voice_queued", status="success",
        idempotency_key=f"dispatch-{uuid.uuid4().hex[:8]}",
        payload={"contact": "+919505100019", "mode": mode},
        response={"raw": {}},
        provider_correlation_id=correlation_id,
        provider_terminal=False,
    )
    db.add(action)
    await db.flush()
    return action


@pytest.mark.asyncio
async def test_reconcile_execution_flips_action_and_creates_outcome_child(
    db_session, seed_full_run,
):
    run, version, workflow, node_step, tenant_id, app_id = seed_full_run
    action = await _seed_voice_action(
        db_session, run=run, version=version, workflow=workflow,
        node_step=node_step, tenant_id=tenant_id, app_id=app_id,
        correlation_id="ex-1",
    )
    action_id = action.id
    run_id = run.id

    applied = await BolnaAdapter().reconcile_execution(
        db_session, action=action, node_id="n1",
        execution={
            "id": "ex-1", "status": "completed", "conversation_duration": 6,
            "telephony_data": {"recording_url": "http://r"}, "transcript": "hi",
        },
    )
    assert applied is True
    await db_session.commit()

    # Re-read past the identity map to prove the write survived the commit.
    db_session.expire_all()
    parent = await db_session.get(WorkflowRunRecipientAction, action_id)
    assert parent.provider_terminal is True

    child = (await db_session.execute(
        select(WorkflowRunRecipientAction).where(
            WorkflowRunRecipientAction.run_id == run_id,
            WorkflowRunRecipientAction.action_type == "bolna_answered",
        )
    )).scalar_one()
    assert child.idempotency_key == "voice-outcome|ex-1|bolna_answered"


@pytest.mark.asyncio
async def test_reconcile_execution_is_idempotent_across_repeat_delivery(
    db_session, seed_full_run,
):
    run, version, workflow, node_step, tenant_id, app_id = seed_full_run
    action = await _seed_voice_action(
        db_session, run=run, version=version, workflow=workflow,
        node_step=node_step, tenant_id=tenant_id, app_id=app_id,
        correlation_id="ex-2",
    )
    run_id = run.id
    execution = {
        "id": "ex-2", "status": "completed", "conversation_duration": 6,
        "telephony_data": {"recording_url": "http://r"}, "transcript": "hi",
    }

    first = await BolnaAdapter().reconcile_execution(
        db_session, action=action, node_id="n1", execution=execution,
    )
    await db_session.commit()
    # Each path re-fetches the parent fresh; the second delivery sees provider_terminal=True.
    await db_session.refresh(action)
    second = await BolnaAdapter().reconcile_execution(
        db_session, action=action, node_id="n1", execution=execution,
    )
    await db_session.commit()

    assert first is True
    assert second is False

    children = (await db_session.execute(
        select(WorkflowRunRecipientAction).where(
            WorkflowRunRecipientAction.run_id == run_id,
            WorkflowRunRecipientAction.action_type == "bolna_answered",
        )
    )).scalars().all()
    assert len(children) == 1


# Verbatim shape of the real Bolna post-call webhook (captured via ngrok):
# the execution id is keyed under "id" and the recipient under
# context_details.recipient_data.recipient_id — NOT execution_id / user_data.
_WEBHOOK_PAYLOAD = {
    "id": "99828536", "batch_id": None, "status": "completed",
    "conversation_duration": 11,
    "telephony_data": {"to_number": "+919505100019", "recording_url": "http://r"},
    "transcript": "hello there",
    "context_details": {"recipient_data": {"recipient_id": "P-webhook"}},
}


@pytest.mark.asyncio
async def test_handle_webhook_reads_id_key_and_reconciles(db_session, seed_full_run):
    run, version, workflow, node_step, tenant_id, app_id = seed_full_run
    action = await _seed_voice_action(
        db_session, run=run, version=version, workflow=workflow,
        node_step=node_step, tenant_id=tenant_id, app_id=app_id,
        correlation_id="99828536", recipient_id="P-webhook",
    )
    action_id = action.id
    run_id = run.id

    await BolnaAdapter().handle_webhook(
        db_session, tenant_id=tenant_id, app_id=app_id, payload=_WEBHOOK_PAYLOAD,
    )
    await db_session.commit()

    db_session.expire_all()
    parent = await db_session.get(WorkflowRunRecipientAction, action_id)
    assert parent.provider_terminal is True

    child = (await db_session.execute(
        select(WorkflowRunRecipientAction).where(
            WorkflowRunRecipientAction.run_id == run_id,
            WorkflowRunRecipientAction.action_type == "bolna_answered",
        )
    )).scalar_one()
    assert child.idempotency_key == "voice-outcome|99828536|bolna_answered"


# ── Phase 1: canonical voice event name ───────────────────────────

@pytest.mark.parametrize("canonical,expected", [
    ("answered",  "voice.answered"),
    ("no_answer", "voice.no_answer"),
    ("failed",    "voice.failed"),
    ("weird",     "voice.failed"),   # unknown input defaults to voice.failed
])
def test_voice_event_name_pure_mapping(canonical, expected):
    assert voice_event_name(canonical) == expected


def test_voice_event_name_composes_with_canonical_outcome():
    # Composition test: outcome strings flow from classify_outcome through
    # _canonical_outcome into voice_event_name without a seam.
    assert voice_event_name(_canonical_outcome("bolna_answered")) == "voice.answered"
    assert voice_event_name(_canonical_outcome("bolna_rnr"))      == "voice.no_answer"
    assert voice_event_name(_canonical_outcome("bolna_failed"))   == "voice.failed"


@pytest.mark.asyncio
async def test_voice_outcome_namespace_and_event_name_round_trip(
    db_session, seed_full_run,
):
    """Regression guard: voice_outcome lands in steps.<node>.voice_outcome AND
    voice_event_name maps it to the correct event name — both ends of the
    outcome→event-name contract in one round trip."""
    run, version, workflow, node_step, tenant_id, app_id = seed_full_run
    action = await _seed_voice_action(
        db_session, run=run, version=version, workflow=workflow,
        node_step=node_step, tenant_id=tenant_id, app_id=app_id,
        correlation_id="ex-phase1",
    )
    run_id = run.id

    applied = await BolnaAdapter().reconcile_execution(
        db_session, action=action, node_id="n1",
        execution={
            "id": "ex-phase1", "status": "completed",
            "transcript": "hello", "conversation_duration": 5,
        },
    )
    assert applied is True
    await db_session.commit()

    db_session.expire_all()
    state = (await db_session.execute(
        select(WorkflowRunRecipientState).where(
            WorkflowRunRecipientState.run_id == run_id,
            WorkflowRunRecipientState.recipient_id == "P-recon",
        )
    )).scalar_one()

    # bag_write namespaces fields as flat dot-string keys: "steps.<node>.<key>"
    voice_outcome = bag_read(state.payload, node_id="n1", key="voice_outcome")
    assert voice_outcome == "answered"
    assert voice_event_name(voice_outcome) == "voice.answered"

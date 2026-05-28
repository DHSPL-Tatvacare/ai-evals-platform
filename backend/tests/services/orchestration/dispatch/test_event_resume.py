"""Shared event-resume core — gated wait resume (Bug E) + voice integration.

No live Bolna calls — verbatim payload fixtures + a real db_session only.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.job import BackgroundJob
from app.models.orchestration import (
    WorkflowRunRecipientAction,
    WorkflowRunRecipientState,
    WorkflowVersion,
)
from app.services.orchestration.adapters.bolna import (
    BolnaAdapter,
    voice_resume_event_names,
)
from app.services.orchestration.dispatch.bag import bag_read
from app.services.orchestration.dispatch.event_resume import resume_waiting_on_event


def _wait_definition(*, event_name: str, mode: str = "event_or_timeout",
                     event_match: dict | None = None) -> dict:
    config: dict = {
        "mode": mode,
        "event_name": event_name,
        "correlation": {"recipient_id_field": "recipient_id"},
    }
    if mode == "event_or_timeout":
        config["timeout_hours"] = 24
    if mode == "duration":
        config = {"mode": "duration", "duration_value": 1, "duration_unit": "hours"}
    if event_match is not None:
        config["event_match"] = event_match
    return {
        "nodes": [{"id": "wait1", "type": "logic.wait", "config": config}],
        "edges": [],
    }


async def _set_version_definition(db, version_id, definition):
    version = await db.get(WorkflowVersion, version_id)
    version.definition = definition
    await db.flush()


async def _seed_waiting(db, *, run, version, workflow, tenant_id, app_id,
                        recipient_id="R-wait", current_node_id="wait1",
                        ttl=None, payload=None):
    state = WorkflowRunRecipientState(
        id=uuid.uuid4(), tenant_id=tenant_id, app_id=app_id,
        workflow_id=workflow.id, workflow_version_id=version.id,
        run_id=run.id, recipient_id=recipient_id, current_node_id=current_node_id,
        status="waiting", wakeup_at=datetime.now(timezone.utc) + timedelta(days=1),
        ignore_webhooks_after=ttl, payload=payload or {},
    )
    db.add(state)
    await db.flush()
    return state


async def _read_state(db, *, run_id, recipient_id):
    return (await db.execute(
        select(WorkflowRunRecipientState)
        .where(
            WorkflowRunRecipientState.run_id == run_id,
            WorkflowRunRecipientState.recipient_id == recipient_id,
        )
        .execution_options(populate_existing=True)
    )).scalar_one()


async def _resume_job_count(db, *, run_id, recipient_id):
    rows = (await db.execute(
        select(BackgroundJob).where(
            BackgroundJob.job_type == "run-workflow",
            BackgroundJob.idempotency_key.like(f"run-resume:{run_id}:{recipient_id}:%"),
        )
    )).scalars().all()
    return len(rows)


# ── pure helper: voice satisfied event set ────────────────────────

@pytest.mark.parametrize("canonical,expected", [
    ("answered",  {"voice.answered", "voice.completed"}),
    ("no_answer", {"voice.no_answer", "voice.completed"}),
    ("failed",    {"voice.failed", "voice.completed"}),
])
def test_voice_resume_event_names(canonical, expected):
    assert voice_resume_event_names(canonical) == frozenset(expected)


# ── core: match resumes ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_match_resumes_and_enqueues(db_session, seed_full_run):
    run, version, workflow, node_step, tenant_id, app_id = seed_full_run
    await _set_version_definition(
        db_session, version.id, _wait_definition(event_name="voice.completed"),
    )
    await _seed_waiting(
        db_session, run=run, version=version, workflow=workflow,
        tenant_id=tenant_id, app_id=app_id,
    )

    resumed = await resume_waiting_on_event(
        db_session, run_id=run.id, recipient_id="R-wait",
        event_names=frozenset({"voice.answered", "voice.completed"}),
        payload={"voice_outcome": "answered"}, reason="r1",
    )
    assert resumed is True

    state = await _read_state(db_session, run_id=run.id, recipient_id="R-wait")
    assert state.status == "ready"
    assert state.wakeup_at is None
    assert bag_read(state.payload, node_id="wait1", key="voice_outcome") == "answered"
    assert await _resume_job_count(db_session, run_id=run.id, recipient_id="R-wait") == 1


# ── Bug E: event_name mismatch stays parked ───────────────────────

@pytest.mark.asyncio
async def test_event_name_mismatch_does_not_resume(db_session, seed_full_run):
    run, version, workflow, node_step, tenant_id, app_id = seed_full_run
    await _set_version_definition(
        db_session, version.id, _wait_definition(event_name="wa.replied"),
    )
    await _seed_waiting(
        db_session, run=run, version=version, workflow=workflow,
        tenant_id=tenant_id, app_id=app_id,
    )

    resumed = await resume_waiting_on_event(
        db_session, run_id=run.id, recipient_id="R-wait",
        event_names=frozenset({"voice.answered", "voice.completed"}),
        payload={"voice_outcome": "answered"}, reason="r1",
    )
    assert resumed is False
    state = await _read_state(db_session, run_id=run.id, recipient_id="R-wait")
    assert state.status == "waiting"


@pytest.mark.asyncio
async def test_non_event_mode_does_not_resume(db_session, seed_full_run):
    run, version, workflow, node_step, tenant_id, app_id = seed_full_run
    await _set_version_definition(
        db_session, version.id, _wait_definition(event_name="x", mode="duration"),
    )
    await _seed_waiting(
        db_session, run=run, version=version, workflow=workflow,
        tenant_id=tenant_id, app_id=app_id,
    )

    resumed = await resume_waiting_on_event(
        db_session, run_id=run.id, recipient_id="R-wait",
        event_names=frozenset({"voice.completed"}),
        payload={}, reason="r1",
    )
    assert resumed is False
    state = await _read_state(db_session, run_id=run.id, recipient_id="R-wait")
    assert state.status == "waiting"


# ── event_match gate ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_event_match_true_resumes(db_session, seed_full_run):
    run, version, workflow, node_step, tenant_id, app_id = seed_full_run
    await _set_version_definition(
        db_session, version.id,
        _wait_definition(event_name="voice.completed",
                         event_match={"field": "voice_outcome", "op": "eq", "value": "answered"}),
    )
    await _seed_waiting(
        db_session, run=run, version=version, workflow=workflow,
        tenant_id=tenant_id, app_id=app_id,
    )

    resumed = await resume_waiting_on_event(
        db_session, run_id=run.id, recipient_id="R-wait",
        event_names=frozenset({"voice.completed"}),
        payload={"voice_outcome": "answered"}, reason="r1",
    )
    assert resumed is True


@pytest.mark.asyncio
async def test_event_match_false_stays_parked(db_session, seed_full_run):
    run, version, workflow, node_step, tenant_id, app_id = seed_full_run
    await _set_version_definition(
        db_session, version.id,
        _wait_definition(event_name="voice.completed",
                         event_match={"field": "voice_outcome", "op": "eq", "value": "answered"}),
    )
    await _seed_waiting(
        db_session, run=run, version=version, workflow=workflow,
        tenant_id=tenant_id, app_id=app_id,
    )

    resumed = await resume_waiting_on_event(
        db_session, run_id=run.id, recipient_id="R-wait",
        event_names=frozenset({"voice.completed"}),
        payload={"voice_outcome": "no_answer"}, reason="r1",
    )
    assert resumed is False
    state = await _read_state(db_session, run_id=run.id, recipient_id="R-wait")
    assert state.status == "waiting"


@pytest.mark.asyncio
async def test_event_match_missing_field_stays_parked(db_session, seed_full_run):
    run, version, workflow, node_step, tenant_id, app_id = seed_full_run
    await _set_version_definition(
        db_session, version.id,
        _wait_definition(event_name="voice.completed",
                         event_match={"field": "voice_outcome", "op": "eq", "value": "answered"}),
    )
    await _seed_waiting(
        db_session, run=run, version=version, workflow=workflow,
        tenant_id=tenant_id, app_id=app_id,
    )

    resumed = await resume_waiting_on_event(
        db_session, run_id=run.id, recipient_id="R-wait",
        event_names=frozenset({"voice.completed"}),
        payload={"unrelated": 1}, reason="r1",
    )
    assert resumed is False
    state = await _read_state(db_session, run_id=run.id, recipient_id="R-wait")
    assert state.status == "waiting"


# ── TTL gate ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ttl_lapsed_does_not_resume(db_session, seed_full_run):
    run, version, workflow, node_step, tenant_id, app_id = seed_full_run
    await _set_version_definition(
        db_session, version.id, _wait_definition(event_name="voice.completed"),
    )
    await _seed_waiting(
        db_session, run=run, version=version, workflow=workflow,
        tenant_id=tenant_id, app_id=app_id,
        ttl=datetime.now(timezone.utc) - timedelta(seconds=60),
    )

    resumed = await resume_waiting_on_event(
        db_session, run_id=run.id, recipient_id="R-wait",
        event_names=frozenset({"voice.completed"}),
        payload={"voice_outcome": "answered"}, reason="r1",
    )
    assert resumed is False
    state = await _read_state(db_session, run_id=run.id, recipient_id="R-wait")
    assert state.status == "waiting"


# ── node is not logic.wait ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_non_wait_node_does_not_resume(db_session, seed_full_run):
    run, version, workflow, node_step, tenant_id, app_id = seed_full_run
    definition = {
        "nodes": [{"id": "wait1", "type": "voice.place_call", "config": {}}],
        "edges": [],
    }
    await _set_version_definition(db_session, version.id, definition)
    await _seed_waiting(
        db_session, run=run, version=version, workflow=workflow,
        tenant_id=tenant_id, app_id=app_id,
    )

    resumed = await resume_waiting_on_event(
        db_session, run_id=run.id, recipient_id="R-wait",
        event_names=frozenset({"voice.completed"}),
        payload={"voice_outcome": "answered"}, reason="r1",
    )
    assert resumed is False
    state = await _read_state(db_session, run_id=run.id, recipient_id="R-wait")
    assert state.status == "waiting"


# ── voice integration through reconcile_execution ─────────────────

async def _seed_voice_action(db, *, run, version, workflow, node_step,
                             tenant_id, app_id, correlation_id, recipient_id):
    action = WorkflowRunRecipientAction(
        id=uuid.uuid4(), tenant_id=tenant_id, app_id=app_id,
        workflow_id=workflow.id, workflow_version_id=version.id,
        run_id=run.id, node_step_id=node_step.id, recipient_id=recipient_id,
        channel="voice", action_type="voice_queued", status="success",
        idempotency_key=f"dispatch-{uuid.uuid4().hex[:8]}",
        payload={"contact": "+919505100019", "mode": "single"},
        response={"raw": {}}, provider_correlation_id=correlation_id,
        provider_terminal=False,
    )
    db.add(action)
    await db.flush()
    return action


@pytest.mark.asyncio
async def test_reconcile_resumes_coarse_completed_wait(db_session, seed_full_run):
    run, version, workflow, node_step, tenant_id, app_id = seed_full_run
    await _set_version_definition(
        db_session, version.id, _wait_definition(event_name="voice.completed"),
    )
    await _seed_waiting(
        db_session, run=run, version=version, workflow=workflow,
        tenant_id=tenant_id, app_id=app_id, recipient_id="P-voice",
        current_node_id="wait1",
    )
    action = await _seed_voice_action(
        db_session, run=run, version=version, workflow=workflow,
        node_step=node_step, tenant_id=tenant_id, app_id=app_id,
        correlation_id="ex-coarse", recipient_id="P-voice",
    )

    applied = await BolnaAdapter().reconcile_execution(
        db_session, action=action, node_id="wait1",
        execution={"id": "ex-coarse", "status": "completed",
                   "conversation_duration": 5, "transcript": "hi"},
    )
    assert applied is True

    state = await _read_state(db_session, run_id=run.id, recipient_id="P-voice")
    assert state.status == "ready"
    assert state.wakeup_at is None
    assert bag_read(state.payload, node_id="wait1", key="voice_outcome") == "answered"


@pytest.mark.asyncio
async def test_reconcile_does_not_resume_wa_wait_but_records_outcome(db_session, seed_full_run):
    run, version, workflow, node_step, tenant_id, app_id = seed_full_run
    await _set_version_definition(
        db_session, version.id, _wait_definition(event_name="wa.replied"),
    )
    await _seed_waiting(
        db_session, run=run, version=version, workflow=workflow,
        tenant_id=tenant_id, app_id=app_id, recipient_id="P-wa",
        current_node_id="wait1",
    )
    action = await _seed_voice_action(
        db_session, run=run, version=version, workflow=workflow,
        node_step=node_step, tenant_id=tenant_id, app_id=app_id,
        correlation_id="ex-wa", recipient_id="P-wa",
    )

    applied = await BolnaAdapter().reconcile_execution(
        db_session, action=action, node_id="wait1",
        execution={"id": "ex-wa", "status": "completed",
                   "conversation_duration": 5, "transcript": "hi"},
    )
    assert applied is True

    state = await _read_state(db_session, run_id=run.id, recipient_id="P-wa")
    # Bug E: a WhatsApp wait is NOT resumed by a voice reconcile.
    assert state.status == "waiting"
    # ...but the voice_outcome is STILL recorded at the voice node namespace.
    assert bag_read(state.payload, node_id="wait1", key="voice_outcome") == "answered"

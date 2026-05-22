"""Generic capability poller (primary path) — fetch_execution, sweep, idempotency, window.

httpx.MockTransport against /executions only — zero live Bolna calls.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.orchestration import (
    WorkflowRunRecipientAction,
    WorkflowRunRecipientState,
)
from app.models.provider_connection import ProviderConnection
from app.services.orchestration.adapters.bolna import BolnaAdapter, BolnaServiceError
from app.services.orchestration.connections.crypto import encrypt
from app.services.orchestration.reconcile_dispatch import reconcile_dispatch
from app.services.orchestration.reconcile_schedule_seed import (
    RECONCILE_VOICE_JOB_TYPE,
    RECONCILE_VOICE_SCHEDULE_KEY,
    seed_reconcile_voice_schedule,
)


def _patched(handler):
    transport = httpx.MockTransport(handler)
    return patch(
        "app.services.orchestration.adapters.bolna._make_client",
        return_value=httpx.AsyncClient(transport=transport),
    )


def _exec_handler(execution: dict):
    """MockTransport handler answering GET /executions/{id} with the given dict."""
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path.startswith("/executions/")
        return httpx.Response(200, json=execution)
    return handler


@pytest_asyncio.fixture
async def pollable_voice_run(db_session, seed_full_run, monkeypatch):
    """A run whose node n1 is bound to a bolna connection; returns a seeder.

    The seeder inserts a waiting state + a voice_queued action within scope and
    returns the action id. Caller controls correlation_id / created_at / recipient.
    """
    from cryptography.fernet import Fernet

    monkeypatch.setattr(
        "app.config.settings.ORCHESTRATION_CONNECTION_KEY",
        Fernet.generate_key().decode(),
    )
    run, version, workflow, node_step, tenant_id, app_id = seed_full_run

    conn = ProviderConnection(
        id=uuid.uuid4(), tenant_id=tenant_id, app_id=app_id, provider="bolna",
        name=f"bolna-{uuid.uuid4().hex[:8]}",
        config_encrypted=encrypt({"api_key": "tok", "base_url": "https://api.bolna.ai"}),
        active=True, created_by=run.triggered_by_user_id,
    )
    db_session.add(conn)
    version.definition = {
        "nodes": [{
            "id": node_step.node_id, "type": "voice.place_call",
            "config": {"connection_id": str(conn.id)},
        }],
        "edges": [],
    }
    await db_session.flush()

    async def _seed_action(
        *, correlation_id: str, recipient_id: str,
        created_at: datetime | None = None,
    ) -> uuid.UUID:
        db_session.add(WorkflowRunRecipientState(
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
            payload={"contact": "+919505100019", "mode": "single"},
            response={"raw": {}}, provider_correlation_id=correlation_id,
            provider_terminal=False,
        )
        if created_at is not None:
            action.created_at = created_at
        db_session.add(action)
        await db_session.flush()
        return action.id

    return run, tenant_id, _seed_action


@pytest.mark.asyncio
async def test_poller_reconciles_terminal_single_execution(db_session, pollable_voice_run):
    run, _tenant_id, seed_action = pollable_voice_run
    action_id = await seed_action(correlation_id="ex-9", recipient_id="P-poll")
    run_id = run.id

    with _patched(_exec_handler({
        "id": "ex-9", "status": "completed", "conversation_duration": 7,
        "telephony_data": {"recording_url": "http://r"}, "transcript": "hi",
    })):
        reconciled = await reconcile_dispatch(db_session, capability="voice")

    assert reconciled == 1

    db_session.expire_all()
    parent = await db_session.get(WorkflowRunRecipientAction, action_id)
    assert parent.provider_terminal is True

    child = (await db_session.execute(
        select(WorkflowRunRecipientAction).where(
            WorkflowRunRecipientAction.run_id == run_id,
            WorkflowRunRecipientAction.action_type == "bolna_answered",
        )
    )).scalar_one()
    assert child.idempotency_key == "voice-outcome|ex-9|bolna_answered"


@pytest.mark.asyncio
async def test_poller_leaves_non_terminal_open(db_session, pollable_voice_run):
    run, _tenant_id, seed_action = pollable_voice_run
    action_id = await seed_action(correlation_id="ex-ring", recipient_id="P-ring")
    run_id = run.id

    with _patched(_exec_handler({"id": "ex-ring", "status": "ringing"})):
        reconciled = await reconcile_dispatch(db_session, capability="voice")

    assert reconciled == 0

    db_session.expire_all()
    parent = await db_session.get(WorkflowRunRecipientAction, action_id)
    assert parent.provider_terminal is False

    children = (await db_session.execute(
        select(WorkflowRunRecipientAction).where(
            WorkflowRunRecipientAction.run_id == run_id,
            WorkflowRunRecipientAction.parent_action_id == action_id,
        )
    )).scalars().all()
    assert children == []


@pytest.mark.asyncio
async def test_poller_skips_out_of_window_action(db_session, pollable_voice_run):
    run, _tenant_id, seed_action = pollable_voice_run
    # Dispatched 3h ago — outside the default 2h poll window.
    old = datetime.now(timezone.utc) - timedelta(hours=3)
    action_id = await seed_action(
        correlation_id="ex-old", recipient_id="P-old", created_at=old,
    )

    with _patched(_exec_handler({"id": "ex-old", "status": "completed"})):
        reconciled = await reconcile_dispatch(db_session, capability="voice")

    assert reconciled == 0

    db_session.expire_all()
    parent = await db_session.get(WorkflowRunRecipientAction, action_id)
    assert parent.provider_terminal is False


@pytest.mark.asyncio
async def test_fetch_execution_hits_executions_endpoint_with_bearer():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/executions/ex-1"
        assert request.headers["Authorization"] == "Bearer k"
        return httpx.Response(200, json={"id": "ex-1", "status": "completed"})

    with _patched(handler):
        result = await BolnaAdapter().fetch_execution(
            connection={"api_key": "k", "base_url": "https://api.bolna.ai"},
            execution_id="ex-1",
        )
    assert result == {"id": "ex-1", "status": "completed"}


@pytest.mark.asyncio
async def test_fetch_execution_404_returns_none():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "not found"})

    with _patched(handler):
        result = await BolnaAdapter().fetch_execution(
            connection={"api_key": "k", "base_url": "https://api.bolna.ai"},
            execution_id="missing",
        )
    assert result is None


@pytest.mark.asyncio
async def test_fetch_execution_5xx_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"message": "boom"})

    with _patched(handler), pytest.raises(BolnaServiceError):
        await BolnaAdapter().fetch_execution(
            connection={"api_key": "k", "base_url": "https://api.bolna.ai"},
            execution_id="ex-1",
        )


def _outcome_children(run_id):
    return select(WorkflowRunRecipientAction).where(
        WorkflowRunRecipientAction.run_id == run_id,
        WorkflowRunRecipientAction.action_type == "bolna_answered",
    )


@pytest.mark.asyncio
async def test_webhook_then_poller_yields_one_child(db_session, pollable_voice_run):
    run, tenant_id, seed_action = pollable_voice_run
    await seed_action(correlation_id="ex-cross1", recipient_id="P-cross1")
    run_id = run.id

    # Real-time webhook reconciles first.
    await BolnaAdapter().handle_webhook(
        db_session, tenant_id=tenant_id, app_id=run.app_id,
        payload={"id": "ex-cross1", "status": "completed", "transcript": "hi"},
    )
    await db_session.commit()

    # The poller sweeps later — the terminal action is excluded; no second child.
    with _patched(_exec_handler({"id": "ex-cross1", "status": "completed"})):
        reconciled = await reconcile_dispatch(db_session, capability="voice")
    assert reconciled == 0

    children = (await db_session.execute(_outcome_children(run_id))).scalars().all()
    assert len(children) == 1


@pytest.mark.asyncio
async def test_seed_reconcile_voice_schedule_is_idempotent(db_session):
    from sqlalchemy import delete

    from app.constants import SYSTEM_TENANT_ID
    from app.models.scheduled_job import ScheduledJobDefinition

    # Establish the precondition (row absent) inside this rolled-back transaction;
    # seed_all_defaults already seeds it into the live DB on boot.
    await db_session.execute(
        delete(ScheduledJobDefinition).where(
            ScheduledJobDefinition.job_type == RECONCILE_VOICE_JOB_TYPE,
            ScheduledJobDefinition.schedule_key == RECONCILE_VOICE_SCHEDULE_KEY,
        )
    )
    await db_session.flush()

    first = await seed_reconcile_voice_schedule(db_session)
    second = await seed_reconcile_voice_schedule(db_session)
    assert first is True
    assert second is False

    rows = (await db_session.execute(
        select(ScheduledJobDefinition).where(
            ScheduledJobDefinition.tenant_id == SYSTEM_TENANT_ID,
            ScheduledJobDefinition.app_id == "",
            ScheduledJobDefinition.job_type == RECONCILE_VOICE_JOB_TYPE,
            ScheduledJobDefinition.schedule_key == RECONCILE_VOICE_SCHEDULE_KEY,
        )
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].cron == "* * * * *"
    assert rows[0].enabled is True


@pytest.mark.asyncio
async def test_poller_then_webhook_yields_one_child(db_session, pollable_voice_run):
    run, tenant_id, seed_action = pollable_voice_run
    await seed_action(correlation_id="ex-cross2", recipient_id="P-cross2")
    run_id = run.id

    # Poller reconciles first.
    with _patched(_exec_handler({"id": "ex-cross2", "status": "completed"})):
        reconciled = await reconcile_dispatch(db_session, capability="voice")
    assert reconciled == 1

    # A late webhook for the same execution is a no-op (provider_terminal guard).
    await BolnaAdapter().handle_webhook(
        db_session, tenant_id=tenant_id, app_id=run.app_id,
        payload={"id": "ex-cross2", "status": "completed", "transcript": "hi"},
    )
    await db_session.commit()

    children = (await db_session.execute(_outcome_children(run_id))).scalars().all()
    assert len(children) == 1

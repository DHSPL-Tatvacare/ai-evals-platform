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
    # side_effect (not return_value) so each _make_client() call gets a FRESH client —
    # the batch flow opens several (summary + paged list), mirroring production.
    transport = httpx.MockTransport(handler)
    return patch(
        "app.services.orchestration.adapters.bolna._make_client",
        side_effect=lambda *a, **k: httpx.AsyncClient(transport=transport),
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
        mode: str = "single", contact: str = "+919505100019",
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
            payload={"contact": contact, "mode": mode},
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


@pytest.mark.asyncio
async def test_fetch_batch_summary_returns_execution_status():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/batches/b-1"
        assert request.headers["Authorization"] == "Bearer k"
        return httpx.Response(200, json={
            "batch_id": "b-1", "status": "executed",
            "execution_status": {"completed": 2, "ringing": 1},
        })

    with _patched(handler):
        summary = await BolnaAdapter().fetch_batch_summary(
            connection={"api_key": "k", "base_url": "https://api.bolna.ai"},
            batch_id="b-1",
        )
    assert summary["execution_status"] == {"completed": 2, "ringing": 1}


@pytest.mark.asyncio
async def test_fetch_batch_summary_404_returns_none():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "no batch"})

    with _patched(handler):
        summary = await BolnaAdapter().fetch_batch_summary(
            connection={"api_key": "k", "base_url": "https://api.bolna.ai"},
            batch_id="missing",
        )
    assert summary is None


@pytest.mark.asyncio
async def test_fetch_batch_executions_paginates_with_bearer():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/batches/b-1/executions"
        assert request.url.params["page_number"] == "2"
        assert request.url.params["page_size"] == "50"
        assert request.headers["Authorization"] == "Bearer k"
        return httpx.Response(200, json={
            "data": [{"id": "ex-1", "status": "completed"}], "has_more": True,
        })

    with _patched(handler):
        page = await BolnaAdapter().fetch_batch_executions(
            connection={"api_key": "k", "base_url": "https://api.bolna.ai"},
            batch_id="b-1", page_number=2,
        )
    assert page["data"] == [{"id": "ex-1", "status": "completed"}]
    assert page["has_more"] is True


@pytest.mark.asyncio
async def test_fetch_batch_executions_404_returns_empty_page():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "no batch"})

    with _patched(handler):
        page = await BolnaAdapter().fetch_batch_executions(
            connection={"api_key": "k", "base_url": "https://api.bolna.ai"},
            batch_id="missing", page_number=1,
        )
    assert page == {"data": [], "has_more": False}


def _batch_handler(*, summary: dict, pages: dict[int, dict]):
    """MockTransport handler for /batches/{id} (summary) + /batches/{id}/executions (paged)."""
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/executions"):
            page = int(request.url.params.get("page_number", "1"))
            return httpx.Response(200, json=pages[page])
        return httpx.Response(200, json=summary)
    return handler


def _batch_row(*, exec_id, recipient_id=None, to_number=None, status="completed"):
    row: dict = {"id": exec_id, "status": status, "telephony_data": {"recording_url": "http://r"}}
    if to_number is not None:
        row["telephony_data"]["to_number"] = to_number
    row["context_details"] = {"recipient_data": {"recipient_id": recipient_id}} if recipient_id else {}
    return row


@pytest.mark.asyncio
async def test_poller_reconciles_batch_by_recipient_id(db_session, pollable_voice_run):
    run, _tenant_id, seed_action = pollable_voice_run
    a_id = await seed_action(correlation_id="b-9", recipient_id="P-a", mode="batch", contact="+91aaa")
    b_id = await seed_action(correlation_id="b-9", recipient_id="P-b", mode="batch", contact="+91bbb")
    run_id = run.id

    handler = _batch_handler(
        summary={"batch_id": "b-9", "execution_status": {"completed": 2}},
        pages={1: {"data": [
            _batch_row(exec_id="ex-a", recipient_id="P-a"),
            _batch_row(exec_id="ex-b", recipient_id="P-b"),
        ], "has_more": False}},
    )
    with _patched(handler):
        reconciled = await reconcile_dispatch(db_session, capability="voice")

    assert reconciled == 2
    db_session.expire_all()
    for aid in (a_id, b_id):
        assert (await db_session.get(WorkflowRunRecipientAction, aid)).provider_terminal is True

    children = (await db_session.execute(select(WorkflowRunRecipientAction.idempotency_key).where(
        WorkflowRunRecipientAction.run_id == run_id,
        WorkflowRunRecipientAction.action_type == "bolna_answered",
    ))).scalars().all()
    assert set(children) == {
        "voice-outcome|ex-a|bolna_answered", "voice-outcome|ex-b|bolna_answered",
    }


def _batch_children_keys(run_id):
    return select(WorkflowRunRecipientAction.idempotency_key).where(
        WorkflowRunRecipientAction.run_id == run_id,
        WorkflowRunRecipientAction.action_type == "bolna_answered",
    )


@pytest.mark.asyncio
async def test_batch_summary_gate_skips_list_when_nothing_terminal(db_session, pollable_voice_run):
    run, _t, seed_action = pollable_voice_run
    a_id = await seed_action(correlation_id="b-gate", recipient_id="P-g", mode="batch", contact="+91g")

    def handler(request: httpx.Request) -> httpx.Response:
        # The whole batch is still ringing — the executions list must NOT be paged.
        assert not request.url.path.endswith("/executions"), "list paged despite 0 terminal"
        return httpx.Response(200, json={"batch_id": "b-gate", "execution_status": {"ringing": 1}})

    with _patched(handler):
        reconciled = await reconcile_dispatch(db_session, capability="voice")

    assert reconciled == 0
    db_session.expire_all()
    assert (await db_session.get(WorkflowRunRecipientAction, a_id)).provider_terminal is False


@pytest.mark.asyncio
async def test_batch_matches_by_phone_when_recipient_id_absent(db_session, pollable_voice_run):
    run, _t, seed_action = pollable_voice_run
    a_id = await seed_action(
        correlation_id="b-ph", recipient_id="P-ph", mode="batch", contact="+919999000011",
    )
    run_id = run.id

    handler = _batch_handler(
        summary={"batch_id": "b-ph", "execution_status": {"completed": 1}},
        pages={1: {"data": [
            # context_details empty — only the phone number can match it back.
            _batch_row(exec_id="ex-ph", to_number="+919999000011"),
        ], "has_more": False}},
    )
    with _patched(handler):
        reconciled = await reconcile_dispatch(db_session, capability="voice")

    assert reconciled == 1
    db_session.expire_all()
    assert (await db_session.get(WorkflowRunRecipientAction, a_id)).provider_terminal is True
    keys = (await db_session.execute(_batch_children_keys(run_id))).scalars().all()
    assert keys == ["voice-outcome|ex-ph|bolna_answered"]


@pytest.mark.asyncio
async def test_batch_webhook_then_poller_one_child_each(db_session, pollable_voice_run):
    run, tenant_id, seed_action = pollable_voice_run
    await seed_action(correlation_id="b-x", recipient_id="P-a", mode="batch", contact="+91a")
    await seed_action(correlation_id="b-x", recipient_id="P-b", mode="batch", contact="+91b")
    run_id = run.id

    # Webhook closes recipient A first (batch_id + recipient_id match).
    await BolnaAdapter().handle_webhook(
        db_session, tenant_id=tenant_id, app_id=run.app_id,
        payload={"id": "ex-a", "batch_id": "b-x", "status": "completed",
                 "context_details": {"recipient_data": {"recipient_id": "P-a"}}},
    )
    await db_session.commit()

    # Poller lists the batch later — A is already terminal (excluded from the sweep), B reconciles.
    handler = _batch_handler(
        summary={"batch_id": "b-x", "execution_status": {"completed": 2}},
        pages={1: {"data": [
            _batch_row(exec_id="ex-a", recipient_id="P-a"),
            _batch_row(exec_id="ex-b", recipient_id="P-b"),
        ], "has_more": False}},
    )
    with _patched(handler):
        await reconcile_dispatch(db_session, capability="voice")

    keys = (await db_session.execute(_batch_children_keys(run_id))).scalars().all()
    assert sorted(keys) == [
        "voice-outcome|ex-a|bolna_answered", "voice-outcome|ex-b|bolna_answered",
    ]


@pytest.mark.asyncio
async def test_batch_pages_until_match_found(db_session, pollable_voice_run):
    run, _t, seed_action = pollable_voice_run
    await seed_action(correlation_id="b-pg", recipient_id="P-2", mode="batch", contact="+912")
    run_id = run.id

    handler = _batch_handler(
        summary={"batch_id": "b-pg", "execution_status": {"completed": 5}},
        pages={
            1: {"data": [_batch_row(exec_id="ex-other", recipient_id="P-other")], "has_more": True},
            2: {"data": [_batch_row(exec_id="ex-2", recipient_id="P-2")], "has_more": False},
        },
    )
    with _patched(handler):
        reconciled = await reconcile_dispatch(db_session, capability="voice")

    assert reconciled == 1
    keys = (await db_session.execute(_batch_children_keys(run_id))).scalars().all()
    assert keys == ["voice-outcome|ex-2|bolna_answered"]


@pytest.mark.asyncio
async def test_batch_stops_paging_once_all_reconciled(db_session, pollable_voice_run):
    run, _t, seed_action = pollable_voice_run
    await seed_action(correlation_id="b-ee", recipient_id="P-1", mode="batch", contact="+911")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/executions"):
            page = int(request.url.params.get("page_number", "1"))
            assert page == 1, "fetched page 2 after the only open action was reconciled"
            return httpx.Response(200, json={
                "data": [_batch_row(exec_id="ex-1", recipient_id="P-1")], "has_more": True,
            })
        return httpx.Response(200, json={"batch_id": "b-ee", "execution_status": {"completed": 1}})

    with _patched(handler):
        reconciled = await reconcile_dispatch(db_session, capability="voice")

    assert reconciled == 1


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

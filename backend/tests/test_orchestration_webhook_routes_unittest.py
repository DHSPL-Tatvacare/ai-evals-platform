"""End-to-end webhook route tests via FastAPI ASGITransport.

The router under test is public (no Bearer required). We use ASGITransport so
the request never crosses the network, then override ``get_db`` to share the
test's transactional session — its ``rollback()`` at teardown then cleans up
any data the route persisted. Route handlers call ``await db.commit()``; we
monkeypatch ``commit`` to ``flush`` on the test session so the outer rollback
still has something to undo.
"""
from __future__ import annotations

import uuid

import httpx
import pytest
from sqlalchemy import select

from app.constants import SYSTEM_USER_ID
from app.database import get_db
from app.main import app
from app.models.orchestration import (
    WorkflowRunRecipientAction,
)


@pytest.mark.asyncio
async def test_webhook_route_does_not_require_auth(db_session):
    """Hitting the webhook URL without a Bearer token must NOT 401.

    Phase 10 commit 2: wati / bolna paths look up the trailing segment as
    a per-connection ``webhook_token`` against
    ``orchestration.provider_connections``. Unknown tokens fail closed
    with 404 — never 401."""
    _override_db_with_session(db_session)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post("/api/orchestration/webhooks/wati/wrongtoken", json={})
        assert r.status_code != 401
        assert r.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)


def _override_db_with_session(db_session):
    """Make get_db yield our transactional test session and turn its commit into a flush
    so outer rollback at teardown still cleans up route-persisted rows."""
    async def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override
    db_session.commit = db_session.flush  # type: ignore[assignment]


@pytest.mark.asyncio
async def test_wati_webhook_with_per_connection_token_dispatches(
    db_session, seed_full_run, monkeypatch,
):
    """Phase 10 commit 2: WATI/Bolna webhooks now authenticate via the
    per-connection ``webhook_token``. Detailed coverage (revoked /
    unknown-token / cross-provider) lives in
    ``test_orchestration_webhook_per_connection_unittest.py``; this test
    verifies the route ends up persisting a wa_delivered row, exercising
    the full happy path."""
    import secrets as _secrets
    from cryptography.fernet import Fernet

    from app.models.provider_connection import ProviderConnection
    from app.services.orchestration.connections import crypto

    run, version, workflow, node_step, tenant_id, app_id = seed_full_run
    # Use monkeypatch so the key doesn't leak into subsequent tests.
    monkeypatch.setattr(
        "app.config.settings.ORCHESTRATION_CONNECTION_KEY",
        Fernet.generate_key().decode(),
    )

    token = _secrets.token_urlsafe(16)
    db_session.add(ProviderConnection(
        id=uuid.uuid4(), tenant_id=tenant_id, app_id=app_id,
        provider="wati", name=f"wati-route-{uuid.uuid4().hex[:8]}",
        config_encrypted=crypto.encrypt({
            "base_url": "https://w", "wati_tenant_id": "1", "api_token": "t",
        }),
        webhook_token=token, active=True,
        created_by=run.triggered_by_user_id or SYSTEM_USER_ID,
    ))

    local_msg_id = f"lm-{uuid.uuid4().hex[:8]}"
    db_session.add(WorkflowRunRecipientAction(
        id=uuid.uuid4(), tenant_id=tenant_id, app_id=app_id,
        workflow_id=workflow.id, workflow_version_id=version.id,
        run_id=run.id, node_step_id=node_step.id, recipient_id="L-route",
        channel="wati", action_type="wa_dispatched", status="success",
        idempotency_key=f"k-{uuid.uuid4().hex[:8]}",
        payload={}, response={"localMessageId": local_msg_id},
    ))
    await db_session.flush()

    _override_db_with_session(db_session)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(
                f"/api/orchestration/webhooks/wati/{token}",
                json={"eventType": "sentMessageDELIVERED_v2", "localMessageId": local_msg_id},
            )
        assert r.status_code == 200, r.text
    finally:
        app.dependency_overrides.pop(get_db, None)

    rows = await db_session.execute(
        select(WorkflowRunRecipientAction.action_type)
        .where(WorkflowRunRecipientAction.run_id == run.id,
               WorkflowRunRecipientAction.recipient_id == "L-route")
    )
    types = sorted(t[0] for t in rows.all())
    assert "wa_delivered" in types


async def _event_trigger(db_session, *, workflow, version, tenant_id, app_id, created_by):
    """Seed an active event trigger + publish the version so fire_event runs."""
    from app.models.orchestration import WorkflowTrigger
    workflow.current_published_version_id = version.id
    token = uuid.uuid4().hex
    trig = WorkflowTrigger(
        id=uuid.uuid4(), tenant_id=tenant_id, app_id=app_id,
        workflow_id=workflow.id, kind="event", event_name="crm.lead.replied",
        webhook_token=token, vendor="webhook", active=True, params={},
        created_by=created_by,
    )
    db_session.add(trig)
    await db_session.flush()
    return trig, token


@pytest.mark.asyncio
async def test_event_webhook_creates_run_and_resumes_waiting_recipient(
    db_session, seed_full_run,
):
    """Path B wiring: an inbound event BOTH fires a new run AND resumes a
    correlated waiting recipient parked at a logic.wait."""
    import uuid as _uuid
    from datetime import datetime, timedelta, timezone

    from app.models.orchestration import (
        WorkflowRun,
        WorkflowRunRecipientState,
    )

    run, version, workflow, _step, tenant_id, app_id = seed_full_run
    version.definition = {
        "nodes": [{
            "id": "wait1", "type": "logic.wait",
            "config": {
                "mode": "event_or_timeout", "event_name": "crm.lead.replied",
                "correlation": {"recipient_id_field": "lead_id"},
                "timeout_hours": 24,
            },
        }],
        "edges": [],
    }
    await db_session.flush()

    db_session.add(WorkflowRunRecipientState(
        id=_uuid.uuid4(), tenant_id=tenant_id, app_id=app_id,
        workflow_id=workflow.id, workflow_version_id=version.id,
        run_id=run.id, recipient_id="L-wired", current_node_id="wait1",
        status="waiting", wakeup_at=datetime.now(timezone.utc) + timedelta(days=1),
        payload={},
    ))
    trig, token = await _event_trigger(
        db_session, workflow=workflow, version=version,
        tenant_id=tenant_id, app_id=app_id, created_by=run.triggered_by_user_id,
    )

    _override_db_with_session(db_session)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(
                f"/api/orchestration/webhooks/event/webhook/{token}",
                json={
                    "event_name": "crm.lead.replied",
                    "recipient_id": "evt-NEW",
                    "lead_id": "L-wired",
                },
            )
        assert r.status_code == 200, r.text
        body = r.json()
        # Trigger path response shape is unchanged by Path B.
        assert body["runsCreated"] == 1
        assert "runIds" in body
    finally:
        app.dependency_overrides.pop(get_db, None)

    state = (await db_session.execute(
        select(WorkflowRunRecipientState)
        .where(WorkflowRunRecipientState.run_id == run.id,
               WorkflowRunRecipientState.recipient_id == "L-wired")
        .execution_options(populate_existing=True)
    )).scalar_one()
    assert state.status == "ready"

    runs = (await db_session.execute(
        select(WorkflowRun).where(WorkflowRun.trigger_id == trig.id)
    )).scalars().all()
    assert len(runs) == 1


@pytest.mark.asyncio
async def test_event_webhook_with_no_waiting_recipient_still_fires(
    db_session, seed_full_run,
):
    """Path B is fault-isolated and additive: with no waiting recipient the
    route still creates the run and returns the same response."""
    from app.models.orchestration import WorkflowRun

    run, version, workflow, _step, tenant_id, app_id = seed_full_run
    version.definition = {"nodes": [], "edges": []}
    await db_session.flush()
    trig, token = await _event_trigger(
        db_session, workflow=workflow, version=version,
        tenant_id=tenant_id, app_id=app_id, created_by=run.triggered_by_user_id,
    )

    _override_db_with_session(db_session)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(
                f"/api/orchestration/webhooks/event/webhook/{token}",
                json={
                    "event_name": "crm.lead.replied",
                    "recipient_id": "evt-NEW",
                    "lead_id": "L-none",
                },
            )
        assert r.status_code == 200, r.text
        assert r.json()["runsCreated"] == 1
    finally:
        app.dependency_overrides.pop(get_db, None)

    runs = (await db_session.execute(
        select(WorkflowRun).where(WorkflowRun.trigger_id == trig.id)
    )).scalars().all()
    assert len(runs) == 1


@pytest.mark.asyncio
async def test_bolna_webhook_404_on_unknown_token(db_session):
    """Phase 10 commit 2: per-connection lookup. Random token with no
    matching ``provider_connections`` row fails closed with 404."""
    _override_db_with_session(db_session)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post("/api/orchestration/webhooks/bolna/anything", json={})
        assert r.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)

"""POST /webhooks/event/{vendor}/{token} — token-resolved multi-tenant ingest."""
from __future__ import annotations

import uuid

import httpx
import pytest
from sqlalchemy import select

from app.constants import SYSTEM_USER_ID
from app.database import get_db
from app.main import app
from app.models.orchestration import (
    EventIngestLog,
    Workflow,
    WorkflowRun,
    WorkflowTrigger,
)

WEBHOOKS = "/api/orchestration/webhooks"


def _override_db_with_session(db_session):
    async def _override():
        yield db_session
    app.dependency_overrides[get_db] = _override
    db_session.commit = db_session.flush  # type: ignore[assignment]


async def _client_post(path, json, headers=None):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.post(path, json=json, headers=headers or {})


async def _make_event_trigger(db_session, seed_full_run, *, vendor="webhook", active=True):
    run, version, workflow, _step, tenant_id, app_id = seed_full_run
    workflow.current_published_version_id = version.id
    token = uuid.uuid4().hex
    trig = WorkflowTrigger(
        id=uuid.uuid4(), tenant_id=tenant_id, app_id=app_id,
        workflow_id=workflow.id, kind="event",
        event_name=f"e.{uuid.uuid4().hex[:6]}",
        webhook_token=token, vendor=vendor, active=active, params={},
        created_by=run.triggered_by_user_id or SYSTEM_USER_ID,
    )
    db_session.add(trig)
    await db_session.flush()
    return trig, token, tenant_id, app_id, workflow, version, run


@pytest.mark.asyncio
async def test_no_auth_required_unknown_token_404(db_session):
    _override_db_with_session(db_session)
    try:
        r = await _client_post(f"{WEBHOOKS}/webhook/nope", {"recipient_id": "x"})
        assert r.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_webhook_vendor_creates_run(db_session, seed_full_run):
    trig, token, *_ = await _make_event_trigger(db_session, seed_full_run, vendor="webhook")
    _override_db_with_session(db_session)
    try:
        r = await _client_post(
            f"{WEBHOOKS}/event/webhook/{token}",
            {"event_name": "crm.lead.created", "recipient_id": "evt-1", "foo": "bar"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "ok"
        assert body["runsCreated"] == 1
        assert body["deduped"] is False
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_webhook_canonical_sample_without_event_name_fires(db_session, seed_full_run):
    # Identity webhook: the inspector's canonical sample omits event_name; the
    # route falls back to the trigger's own event_name so the sample fires.
    trig, token, *_ = await _make_event_trigger(db_session, seed_full_run, vendor="webhook")
    _override_db_with_session(db_session)
    try:
        r = await _client_post(
            f"{WEBHOOKS}/event/webhook/{token}",
            {"recipient_id": "evt-1", "foo": "bar"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["runsCreated"] == 1
    finally:
        app.dependency_overrides.pop(get_db, None)

    run = (await db_session.execute(
        select(WorkflowRun).where(WorkflowRun.trigger_id == trig.id)
    )).scalar_one()
    assert run.params["event_payload"]["event_name"] == trig.event_name


@pytest.mark.asyncio
async def test_webhook_explicit_event_name_not_overwritten(db_session, seed_full_run):
    # An explicit body event_name wins over the trigger fallback.
    trig, token, *_ = await _make_event_trigger(db_session, seed_full_run, vendor="webhook")
    _override_db_with_session(db_session)
    try:
        r = await _client_post(
            f"{WEBHOOKS}/event/webhook/{token}",
            {"event_name": "crm.lead.created", "recipient_id": "evt-1"},
        )
        assert r.status_code == 200, r.text
    finally:
        app.dependency_overrides.pop(get_db, None)

    run = (await db_session.execute(
        select(WorkflowRun).where(WorkflowRun.trigger_id == trig.id)
    )).scalar_one()
    assert run.params["event_payload"]["event_name"] == "crm.lead.created"


@pytest.mark.asyncio
async def test_vendor_mismatch_404(db_session, seed_full_run):
    # Trigger is bound to frappe; hitting the same token under /webhook 404s.
    trig, token, *_ = await _make_event_trigger(db_session, seed_full_run, vendor="frappe")
    _override_db_with_session(db_session)
    try:
        r = await _client_post(
            f"{WEBHOOKS}/event/webhook/{token}", {"recipient_id": "x"},
        )
        assert r.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_inactive_trigger_404(db_session, seed_full_run):
    trig, token, *_ = await _make_event_trigger(db_session, seed_full_run, active=False)
    _override_db_with_session(db_session)
    try:
        r = await _client_post(
            f"{WEBHOOKS}/event/webhook/{token}", {"recipient_id": "x"},
        )
        assert r.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_payload_without_recipient_400(db_session, seed_full_run):
    trig, token, *_ = await _make_event_trigger(db_session, seed_full_run, vendor="webhook")
    _override_db_with_session(db_session)
    try:
        r = await _client_post(
            f"{WEBHOOKS}/event/webhook/{token}", {"event_name": "crm.lead.created"},
        )
        assert r.status_code == 400, r.text
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_replay_dedupe_single_run(db_session, seed_full_run):
    trig, token, *_ = await _make_event_trigger(db_session, seed_full_run, vendor="frappe")
    _override_db_with_session(db_session)
    try:
        body = {
            "doctype": "Lead", "name": "CRM-LEAD-1",
            "lead_name": "A", "_frappe_doc_event": "after_insert",
        }
        r1 = await _client_post(f"{WEBHOOKS}/event/frappe/{token}", body)
        assert r1.status_code == 200, r1.text
        assert r1.json()["runsCreated"] == 1
        assert r1.json()["deduped"] is False
        r2 = await _client_post(f"{WEBHOOKS}/event/frappe/{token}", body)
        assert r2.status_code == 200, r2.text
        assert r2.json()["deduped"] is True
    finally:
        app.dependency_overrides.pop(get_db, None)

    runs = (await db_session.execute(
        select(WorkflowRun).where(WorkflowRun.trigger_id == trig.id)
    )).scalars().all()
    assert len(runs) == 1


@pytest.mark.asyncio
async def test_frappe_event_in_header_creates_run(db_session, seed_full_run):
    # Real Frappe webhook: doc-event rides the X-Frappe-Event header, not the body.
    trig, token, *_ = await _make_event_trigger(db_session, seed_full_run, vendor="frappe")
    _override_db_with_session(db_session)
    try:
        r = await _client_post(
            f"{WEBHOOKS}/event/frappe/{token}",
            {"doctype": "Lead", "name": "CRM-LEAD-HDR-1", "lead_name": "Hdr"},
            headers={"X-Frappe-Event": "after_insert"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["runsCreated"] == 1, body
        assert body["deduped"] is False
    finally:
        app.dependency_overrides.pop(get_db, None)

    runs = (await db_session.execute(
        select(WorkflowRun).where(WorkflowRun.trigger_id == trig.id)
    )).scalars().all()
    assert len(runs) == 1


@pytest.mark.asyncio
async def test_body_over_max_bytes_413(db_session, seed_full_run):
    trig, token, *_ = await _make_event_trigger(db_session, seed_full_run, vendor="webhook")
    _override_db_with_session(db_session)
    try:
        oversized = {
            "event_name": "crm.lead.created",
            "recipient_id": "evt-1",
            "blob": "x" * 1_000_001,
        }
        r = await _client_post(f"{WEBHOOKS}/event/webhook/{token}", oversized)
        assert r.status_code == 413, r.text
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_unmapped_event_name_is_accepted_noop(db_session, seed_full_run):
    # Frappe doc with an unmapped doctype → adapter maps to None → no run, 200 ack.
    trig, token, *_ = await _make_event_trigger(db_session, seed_full_run, vendor="frappe")
    _override_db_with_session(db_session)
    try:
        r = await _client_post(
            f"{WEBHOOKS}/event/frappe/{token}",
            {"doctype": "Sales Invoice", "name": "SI-1", "_frappe_doc_event": "on_submit"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["runsCreated"] == 0
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_recipients_fan_in_cap_rejected(db_session, seed_full_run):
    trig, token, *_ = await _make_event_trigger(db_session, seed_full_run, vendor="webhook")
    _override_db_with_session(db_session)
    try:
        oversized = {
            "event_name": "crm.lead.created",
            "recipients": [
                {"recipient_id": f"r{i}", "payload": {}} for i in range(5001)
            ],
        }
        r = await _client_post(f"{WEBHOOKS}/event/webhook/{token}", oversized)
        assert r.status_code == 413, r.text
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_multi_tenant_isolation_token_scopes_to_owning_tenant(
    db_session, seed_full_run,
):
    """Tenant A's token only ever fires tenant A's trigger.

    A second trigger under a different workflow with its own token must not be
    reachable through tenant A's token. The route resolves exactly one trigger
    by token, so the run is created against that trigger's tenant + app only.
    """
    trigA, tokenA, tenant_id, app_id, workflow, version, run = await _make_event_trigger(
        db_session, seed_full_run, vendor="webhook",
    )
    # A distinct trigger with a distinct token on the same workflow.
    other_token = uuid.uuid4().hex
    trigB = WorkflowTrigger(
        id=uuid.uuid4(), tenant_id=tenant_id, app_id=app_id,
        workflow_id=workflow.id, kind="event",
        event_name=f"e.{uuid.uuid4().hex[:6]}",
        webhook_token=other_token, vendor="webhook", active=True, params={},
        created_by=run.triggered_by_user_id or SYSTEM_USER_ID,
    )
    db_session.add(trigB)
    await db_session.flush()

    _override_db_with_session(db_session)
    try:
        r = await _client_post(
            f"{WEBHOOKS}/event/webhook/{tokenA}",
            {"event_name": "crm.lead.created", "recipient_id": "x"},
        )
        assert r.status_code == 200, r.text
    finally:
        app.dependency_overrides.pop(get_db, None)

    # Exactly one run, bound to trigA (the token-resolved trigger), not trigB.
    runs = (await db_session.execute(
        select(WorkflowRun).where(WorkflowRun.workflow_id == workflow.id,
                                  WorkflowRun.triggered_by == "event")
    )).scalars().all()
    assert len(runs) == 1
    assert runs[0].trigger_id == trigA.id

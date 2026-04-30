"""Per-handler tests for the 5 CRM action nodes.

Same shape as test_orchestration_nodes_unittest.py — uses db_session fixture
and httpx.MockTransport for HTTP mocking (no respx dep).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import select

import app.services.orchestration.nodes  # noqa: F401 — registers handlers

from app.models.orchestration import (
    WorkflowActionTemplate,
    WorkflowRunNodeStep,
    WorkflowRunRecipientAction,
    WorkflowRunRecipientState,
)
from app.services.orchestration.cohort_stream import CohortStream
from app.services.orchestration.integrations.bolna import BolnaService
from app.services.orchestration.integrations.lsq import LsqWriter
from app.services.orchestration.integrations.wati import WatiService
from app.services.orchestration.node_context import NodeContext, ServiceRegistry


def _make_node_step(db_session, *, run, version, workflow, tenant_id, app_id, node_id, node_type) -> uuid.UUID:
    step_id = uuid.uuid4()
    db_session.add(WorkflowRunNodeStep(
        id=step_id, tenant_id=tenant_id, app_id=app_id,
        workflow_id=workflow.id, workflow_version_id=version.id,
        run_id=run.id, node_id=node_id, node_type=node_type,
        status="running", started_at=datetime.now(timezone.utc),
    ))
    return step_id


def _make_ctx(db_session, *, run, version, workflow, tenant_id, app_id, node_id, step_id, services=None) -> NodeContext:
    return NodeContext(
        db=db_session, tenant_id=tenant_id, app_id=app_id,
        workflow_id=workflow.id, workflow_version_id=version.id,
        run_id=run.id, node_step_id=step_id, current_node_id=node_id,
        services=services or ServiceRegistry(), job_id=None,
    )


def _patch_module_make_client(monkeypatch, mod, handler):
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        mod, "_make_client",
        lambda *a, **kw: httpx.AsyncClient(transport=transport, timeout=kw.get("timeout", 30.0) if kw else 30.0),
    )


# ─── crm.send_wati ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_crm_send_wati_per_recipient(db_session, seed_full_run, monkeypatch):
    from app.services.orchestration.integrations import wati as wati_mod
    from app.services.orchestration.nodes.crm_send_wati import _Config, _Handler

    run, version, workflow, _step, tenant_id, app_id = seed_full_run
    slug = f"welcome-{uuid.uuid4().hex[:8]}"
    db_session.add(WorkflowActionTemplate(
        id=uuid.uuid4(), tenant_id=None, app_id=None,
        channel="wati", slug=slug, name="Welcome",
        payload_schema={
            "template_name": "welcome_v1",
            "broadcast_name": "concierge_welcome",
            "parameter_map": [
                {"name": "patient_name", "source": "first_name"},
                {"name": "city", "source": "city"},
            ],
        },
    ))
    for rid, fname, phone in [("L-1", "Aarti", "919999990001"), ("L-2", "Bilal", "919999990002")]:
        db_session.add(WorkflowRunRecipientState(
            id=uuid.uuid4(), tenant_id=tenant_id, app_id=app_id,
            workflow_id=workflow.id, workflow_version_id=version.id,
            run_id=run.id, recipient_id=rid, current_node_id="wati",
            status="running", payload={"first_name": fname, "city": "Mumbai", "whatsapp_number": phone},
        ))
    step_id = _make_node_step(db_session, run=run, version=version, workflow=workflow,
                              tenant_id=tenant_id, app_id=app_id,
                              node_id="wati", node_type="crm.send_wati")
    await db_session.flush()

    captured: list[httpx.Request] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"localMessageId": "lm-A", "whatsappMessageId": "wm-A"})

    _patch_module_make_client(monkeypatch, wati_mod, _handler)

    services = ServiceRegistry()
    services.wati = WatiService(
        base_url="https://live-mt-server.wati.io",
        wati_tenant_id="12345",
        api_token="t",
    )

    cfg = _Config(template_slug=slug, phone_field="whatsapp_number")
    ctx = _make_ctx(db_session, run=run, version=version, workflow=workflow,
                    tenant_id=tenant_id, app_id=app_id, node_id="wati",
                    step_id=step_id, services=services)
    cohort = CohortStream([
        ("L-1", {"first_name": "Aarti", "city": "Mumbai", "whatsapp_number": "919999990001"}),
        ("L-2", {"first_name": "Bilal", "city": "Mumbai", "whatsapp_number": "919999990002"}),
    ])
    result = await _Handler().execute(cohort, cfg, ctx)
    assert sorted(o.recipient_id for o in result.by_edge_label["success"]) == ["L-1", "L-2"]
    assert result.by_edge_label["failed"] == []
    assert len(captured) == 2

    actions = await db_session.execute(
        select(
            WorkflowRunRecipientAction.recipient_id,
            WorkflowRunRecipientAction.action_type,
            WorkflowRunRecipientAction.status,
            WorkflowRunRecipientAction.response,
        )
        .where(WorkflowRunRecipientAction.run_id == run.id)
    )
    rows = list(actions.all())
    assert len(rows) == 2
    for _rid, atype, st, resp in rows:
        assert atype == "wa_dispatched"
        assert st == "success"
        assert resp.get("localMessageId") == "lm-A"


@pytest.mark.asyncio
async def test_crm_send_wati_failure_emits_failed_edge(db_session, seed_full_run, monkeypatch):
    from app.services.orchestration.integrations import wati as wati_mod
    from app.services.orchestration.nodes.crm_send_wati import _Config, _Handler

    run, version, workflow, _step, tenant_id, app_id = seed_full_run
    slug = f"t-{uuid.uuid4().hex[:8]}"
    db_session.add(WorkflowActionTemplate(
        id=uuid.uuid4(), tenant_id=None, app_id=None,
        channel="wati", slug=slug, name="t1",
        payload_schema={"template_name": "t1", "broadcast_name": "b", "parameter_map": []},
    ))
    db_session.add(WorkflowRunRecipientState(
        id=uuid.uuid4(), tenant_id=tenant_id, app_id=app_id,
        workflow_id=workflow.id, workflow_version_id=version.id,
        run_id=run.id, recipient_id="L-bad", current_node_id="wati",
        status="running", payload={"whatsapp_number": "0"},
    ))
    step_id = _make_node_step(db_session, run=run, version=version, workflow=workflow,
                              tenant_id=tenant_id, app_id=app_id,
                              node_id="wati", node_type="crm.send_wati")
    await db_session.flush()

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"info": "bad number"})

    _patch_module_make_client(monkeypatch, wati_mod, _handler)

    services = ServiceRegistry()
    services.wati = WatiService(
        base_url="https://live-mt-server.wati.io",
        wati_tenant_id="12345",
        api_token="t",
    )
    cfg = _Config(template_slug=slug, phone_field="whatsapp_number")
    ctx = _make_ctx(db_session, run=run, version=version, workflow=workflow,
                    tenant_id=tenant_id, app_id=app_id, node_id="wati",
                    step_id=step_id, services=services)
    result = await _Handler().execute(CohortStream([("L-bad", {"whatsapp_number": "0"})]), cfg, ctx)
    assert [o.recipient_id for o in result.by_edge_label["failed"]] == ["L-bad"]
    assert result.by_edge_label["success"] == []


@pytest.mark.asyncio
async def test_crm_send_wati_missing_phone_field(db_session, seed_full_run):
    from app.services.orchestration.nodes.crm_send_wati import _Config, _Handler

    run, version, workflow, _step, tenant_id, app_id = seed_full_run
    slug = f"t2-{uuid.uuid4().hex[:8]}"
    db_session.add(WorkflowActionTemplate(
        id=uuid.uuid4(), tenant_id=None, app_id=None,
        channel="wati", slug=slug, name="t2",
        payload_schema={"template_name": "t2", "broadcast_name": "b", "parameter_map": []},
    ))
    step_id = _make_node_step(db_session, run=run, version=version, workflow=workflow,
                              tenant_id=tenant_id, app_id=app_id,
                              node_id="wati", node_type="crm.send_wati")
    await db_session.flush()
    services = ServiceRegistry()
    services.wati = WatiService(
        base_url="https://live-mt-server.wati.io",
        wati_tenant_id="12345",
        api_token="t",
    )
    cfg = _Config(template_slug=slug, phone_field="whatsapp_number")
    ctx = _make_ctx(db_session, run=run, version=version, workflow=workflow,
                    tenant_id=tenant_id, app_id=app_id, node_id="wati",
                    step_id=step_id, services=services)
    # Missing whatsapp_number → failed edge, no HTTP call
    result = await _Handler().execute(CohortStream([("L-x", {})]), cfg, ctx)
    assert [o.recipient_id for o in result.by_edge_label["failed"]] == ["L-x"]


# ─── crm.place_bolna_call ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_crm_place_bolna_call_per_recipient(db_session, seed_full_run, monkeypatch):
    from app.services.orchestration.integrations import bolna as bolna_mod
    from app.services.orchestration.nodes.crm_place_bolna_call import _Config, _Handler

    run, version, workflow, _step, tenant_id, app_id = seed_full_run
    slug = f"confirm-{uuid.uuid4().hex[:8]}"
    db_session.add(WorkflowActionTemplate(
        id=uuid.uuid4(), tenant_id=None, app_id=None,
        channel="bolna", slug=slug, name="Slot Confirmation",
        payload_schema={
            "agent_id": "agent-confirm-1",
            "user_data_map": [
                {"name": "first_name", "source": "first_name"},
                {"name": "slot", "source": "slot"},
            ],
            "retry_config": {
                "enabled": True, "max_retries": 2,
                "retry_on_statuses": ["no-answer", "busy"],
                "retry_intervals_minutes": [5, 15],
            },
        },
    ))
    db_session.add(WorkflowRunRecipientState(
        id=uuid.uuid4(), tenant_id=tenant_id, app_id=app_id,
        workflow_id=workflow.id, workflow_version_id=version.id,
        run_id=run.id, recipient_id="L-1", current_node_id="bn",
        status="running", payload={"phone": "+919999990001", "first_name": "Aarti", "slot": "5pm"},
    ))
    step_id = _make_node_step(db_session, run=run, version=version, workflow=workflow,
                              tenant_id=tenant_id, app_id=app_id,
                              node_id="bn", node_type="crm.place_bolna_call")
    await db_session.flush()

    captured: list[httpx.Request] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"message": "queued", "status": "queued", "execution_id": "ex-100"})

    _patch_module_make_client(monkeypatch, bolna_mod, _handler)
    services = ServiceRegistry()
    services.bolna = BolnaService(base_url="https://api.bolna.ai", api_key="k")
    cfg = _Config(template_slug=slug, phone_field="phone")
    ctx = _make_ctx(db_session, run=run, version=version, workflow=workflow,
                    tenant_id=tenant_id, app_id=app_id, node_id="bn",
                    step_id=step_id, services=services)
    cohort = CohortStream([("L-1", {"phone": "+919999990001", "first_name": "Aarti", "slot": "5pm"})])
    result = await _Handler().execute(cohort, cfg, ctx)
    assert [o.recipient_id for o in result.by_edge_label["success"]] == ["L-1"]
    assert len(captured) == 1
    body = captured[0].content.decode()
    assert "agent-confirm-1" in body
    assert "+919999990001" in body
    assert "Aarti" in body

    actions = await db_session.execute(
        select(
            WorkflowRunRecipientAction.action_type,
            WorkflowRunRecipientAction.status,
            WorkflowRunRecipientAction.response,
        )
        .where(WorkflowRunRecipientAction.run_id == run.id)
    )
    row = actions.first()
    assert row[0] == "bolna_queued" and row[1] == "success"
    assert row[2]["execution_id"] == "ex-100"


# ─── crm.send_sms ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_crm_send_sms_via_gupshup(db_session, seed_full_run, monkeypatch):
    from app.services.orchestration.nodes import crm_send_sms as sms_mod
    from app.services.orchestration.nodes.crm_send_sms import _Config, _Handler

    monkeypatch.setattr("app.services.orchestration.nodes.crm_send_sms.settings.SMS_PROVIDER", "gupshup")
    monkeypatch.setattr("app.services.orchestration.nodes.crm_send_sms.settings.SMS_API_KEY", "k")
    monkeypatch.setattr("app.services.orchestration.nodes.crm_send_sms.settings.SMS_BASE_URL", "TATVAOTP")

    run, version, workflow, _step, tenant_id, app_id = seed_full_run
    slug = f"otp-{uuid.uuid4().hex[:8]}"
    db_session.add(WorkflowActionTemplate(
        id=uuid.uuid4(), tenant_id=None, app_id=None,
        channel="sms", slug=slug, name="OTP",
        payload_schema={"body": "Hi {{first_name}}, code: {{code}}"},
    ))
    db_session.add(WorkflowRunRecipientState(
        id=uuid.uuid4(), tenant_id=tenant_id, app_id=app_id,
        workflow_id=workflow.id, workflow_version_id=version.id,
        run_id=run.id, recipient_id="L1", current_node_id="sms",
        status="running", payload={"phone": "+919999990001", "first_name": "Aarti", "code": "123"},
    ))
    step_id = _make_node_step(db_session, run=run, version=version, workflow=workflow,
                              tenant_id=tenant_id, app_id=app_id,
                              node_id="sms", node_type="crm.send_sms")
    await db_session.flush()

    captured: list[httpx.Request] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(202, json={"messageId": "g1"})

    _patch_module_make_client(monkeypatch, sms_mod, _handler)
    cfg = _Config(template_slug=slug, phone_field="phone")
    ctx = _make_ctx(db_session, run=run, version=version, workflow=workflow,
                    tenant_id=tenant_id, app_id=app_id, node_id="sms",
                    step_id=step_id, services=ServiceRegistry())
    cohort = CohortStream([("L1", {"phone": "+919999990001", "first_name": "Aarti", "code": "123"})])
    result = await _Handler().execute(cohort, cfg, ctx)
    assert [o.recipient_id for o in result.by_edge_label["success"]] == ["L1"]
    assert len(captured) == 1
    sent_body = captured[0].content.decode()
    # Form-encoded body — Aarti and 123 appear as key=value pairs.
    assert "Aarti" in sent_body
    assert "123" in sent_body


@pytest.mark.asyncio
async def test_crm_send_sms_provider_unset_raises(db_session, seed_full_run, monkeypatch):
    from app.services.orchestration.nodes.crm_send_sms import _Config, _Handler

    monkeypatch.setattr("app.services.orchestration.nodes.crm_send_sms.settings.SMS_PROVIDER", "")

    run, version, workflow, _step, tenant_id, app_id = seed_full_run
    step_id = _make_node_step(db_session, run=run, version=version, workflow=workflow,
                              tenant_id=tenant_id, app_id=app_id,
                              node_id="sms", node_type="crm.send_sms")
    await db_session.flush()
    cfg = _Config(template_slug="whatever", phone_field="phone")
    ctx = _make_ctx(db_session, run=run, version=version, workflow=workflow,
                    tenant_id=tenant_id, app_id=app_id, node_id="sms",
                    step_id=step_id)
    with pytest.raises(RuntimeError, match="SMS_PROVIDER"):
        await _Handler().execute(CohortStream([("L1", {})]), cfg, ctx)


# ─── crm.lsq_update_stage ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_crm_lsq_update_stage(db_session, seed_full_run, monkeypatch):
    from app.services import lsq_client as lsq_client_mod
    from app.services.orchestration.integrations import lsq as lsq_mod
    from app.services.orchestration.nodes.crm_lsq_update_stage import _Config, _Handler

    run, version, workflow, _step, tenant_id, app_id = seed_full_run
    db_session.add(WorkflowRunRecipientState(
        id=uuid.uuid4(), tenant_id=tenant_id, app_id=app_id,
        workflow_id=workflow.id, workflow_version_id=version.id,
        run_id=run.id, recipient_id="P-99", current_node_id="ls",
        status="running", payload={},
    ))
    step_id = _make_node_step(db_session, run=run, version=version, workflow=workflow,
                              tenant_id=tenant_id, app_id=app_id,
                              node_id="ls", node_type="crm.lsq_update_stage")
    await db_session.flush()

    monkeypatch.setattr(lsq_client_mod, "LSQ_BASE_URL", "https://api-in22.leadsquared.com/v2")
    monkeypatch.setattr(lsq_client_mod, "_auth_params", lambda: {"accessKey": "ak", "secretKey": "sk"})

    captured: list[httpx.Request] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"Status": "Success"})

    _patch_module_make_client(monkeypatch, lsq_mod, _handler)
    services = ServiceRegistry()
    services.lsq = LsqWriter()
    cfg = _Config(target_stage="Slot Confirmed")
    ctx = _make_ctx(db_session, run=run, version=version, workflow=workflow,
                    tenant_id=tenant_id, app_id=app_id, node_id="ls",
                    step_id=step_id, services=services)
    result = await _Handler().execute(CohortStream([("P-99", {})]), cfg, ctx)
    assert [o.recipient_id for o in result.by_edge_label["success"]] == ["P-99"]
    assert len(captured) == 1
    assert "Lead.Update" in str(captured[0].url)


# ─── crm.lsq_log_activity ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_crm_lsq_log_activity_with_template_note(db_session, seed_full_run, monkeypatch):
    from app.services import lsq_client as lsq_client_mod
    from app.services.orchestration.integrations import lsq as lsq_mod
    from app.services.orchestration.nodes.crm_lsq_log_activity import _Config, _Handler

    run, version, workflow, _step, tenant_id, app_id = seed_full_run
    db_session.add(WorkflowRunRecipientState(
        id=uuid.uuid4(), tenant_id=tenant_id, app_id=app_id,
        workflow_id=workflow.id, workflow_version_id=version.id,
        run_id=run.id, recipient_id="P-77", current_node_id="la",
        status="running", payload={"slot_time": "5pm"},
    ))
    step_id = _make_node_step(db_session, run=run, version=version, workflow=workflow,
                              tenant_id=tenant_id, app_id=app_id,
                              node_id="la", node_type="crm.lsq_log_activity")
    await db_session.flush()

    monkeypatch.setattr(lsq_client_mod, "LSQ_BASE_URL", "https://api-in22.leadsquared.com/v2")
    monkeypatch.setattr(lsq_client_mod, "_auth_params", lambda: {"accessKey": "ak", "secretKey": "sk"})

    captured: list[httpx.Request] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"Status": "Success"})

    _patch_module_make_client(monkeypatch, lsq_mod, _handler)
    services = ServiceRegistry()
    services.lsq = LsqWriter()
    cfg = _Config(activity_event_code=212, note="Confirmed at {{slot_time}}", fields=[])
    ctx = _make_ctx(db_session, run=run, version=version, workflow=workflow,
                    tenant_id=tenant_id, app_id=app_id, node_id="la",
                    step_id=step_id, services=services)
    result = await _Handler().execute(CohortStream([("P-77", {"slot_time": "5pm"})]), cfg, ctx)
    assert [o.recipient_id for o in result.by_edge_label["success"]] == ["P-77"]
    body = captured[0].content.decode()
    assert "Confirmed at 5pm" in body
    assert "212" in body

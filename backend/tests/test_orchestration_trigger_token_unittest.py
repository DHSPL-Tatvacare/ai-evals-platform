"""Event-trigger token: generated on create, masked on read, rotatable, audited."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.models.audit_log import AuditEventLog
from app.models.orchestration import WorkflowTrigger
from app.services.orchestration.api import triggers as trig_service


@pytest.mark.asyncio
async def test_create_event_trigger_generates_token_and_vendor(db_session, seed_full_run):
    run, version, workflow, _step, tenant_id, app_id = seed_full_run
    trig = await trig_service.create_trigger(
        db_session, tenant_id=tenant_id, workflow_id=workflow.id,
        kind="event", cron_expression=None, event_name="crm.lead.created",
        params={}, active=True, created_by=run.triggered_by_user_id, vendor="frappe",
    )
    assert trig is not None
    assert trig.webhook_token
    assert trig.vendor == "frappe"


@pytest.mark.asyncio
async def test_create_cron_trigger_has_no_token(db_session, seed_full_run):
    run, version, workflow, _step, tenant_id, app_id = seed_full_run
    trig = await trig_service.create_trigger(
        db_session, tenant_id=tenant_id, workflow_id=workflow.id,
        kind="cron", cron_expression="0 9 * * *", event_name=None,
        params={}, active=True, created_by=run.triggered_by_user_id, vendor="webhook",
    )
    assert trig is not None
    assert trig.webhook_token is None


@pytest.mark.asyncio
async def test_serialize_trigger_masks_token(db_session, seed_full_run):
    run, version, workflow, _step, tenant_id, app_id = seed_full_run
    trig = await trig_service.create_trigger(
        db_session, tenant_id=tenant_id, workflow_id=workflow.id,
        kind="event", cron_expression=None, event_name="crm.lead.created",
        params={}, active=True, created_by=run.triggered_by_user_id, vendor="webhook",
    )
    full = trig.webhook_token
    view = trig_service.serialize_trigger(trig, base_url="https://evals.example.com")
    # Masked, never the full token.
    assert view["webhook_token_masked"]
    assert view["webhook_token_masked"] != full
    assert full not in view["webhook_token_masked"]
    # Composed URL embeds the FULL token (returned once at create / on rotate view).
    assert view["vendor"] == "webhook"
    assert view["webhook_url"].endswith(f"/event/webhook/{full}")


@pytest.mark.asyncio
async def test_rotate_token_changes_value_and_audits(db_session, seed_full_run):
    run, version, workflow, _step, tenant_id, app_id = seed_full_run
    trig = await trig_service.create_trigger(
        db_session, tenant_id=tenant_id, workflow_id=workflow.id,
        kind="event", cron_expression=None, event_name="crm.lead.created",
        params={}, active=True, created_by=run.triggered_by_user_id, vendor="webhook",
    )
    old = trig.webhook_token
    result = await trig_service.rotate_trigger_token(
        db_session, tenant_id=tenant_id, trigger_id=trig.id,
        actor_id=run.triggered_by_user_id, base_url="https://evals.example.com",
    )
    refreshed = (await db_session.execute(
        select(WorkflowTrigger).where(WorkflowTrigger.id == trig.id)
    )).scalar_one()
    assert refreshed.webhook_token != old
    assert result["webhook_url"].endswith(f"/event/webhook/{refreshed.webhook_token}")

    audits = (await db_session.execute(
        select(AuditEventLog).where(
            AuditEventLog.entity_type == "workflow_trigger",
            AuditEventLog.entity_id == trig.id,
            AuditEventLog.action == "orchestration.trigger.rotate_token",
        )
    )).scalars().all()
    assert len(audits) == 1


@pytest.mark.asyncio
async def test_rotate_cron_trigger_rejected(db_session, seed_full_run):
    run, version, workflow, _step, tenant_id, app_id = seed_full_run
    trig = await trig_service.create_trigger(
        db_session, tenant_id=tenant_id, workflow_id=workflow.id,
        kind="cron", cron_expression="0 9 * * *", event_name=None,
        params={}, active=True, created_by=run.triggered_by_user_id, vendor="webhook",
    )
    with pytest.raises(ValueError):
        await trig_service.rotate_trigger_token(
            db_session, tenant_id=tenant_id, trigger_id=trig.id,
            actor_id=run.triggered_by_user_id, base_url="https://x",
        )

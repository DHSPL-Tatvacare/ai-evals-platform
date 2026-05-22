"""Token-resolved single-trigger event fire — one trigger, one run, replay-deduped."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.models.job import BackgroundJob
from app.models.orchestration import (
    EventIngestLog,
    WorkflowRun,
    WorkflowTrigger,
)
from app.services.orchestration.adapters.canonical import (
    CanonicalEventBatch,
    CanonicalEventRecipient,
)
from app.services.orchestration.webhook_handlers.generic_event import (
    EventPayloadContractError,
    EventTriggerConfigurationError,
    fire_event,
)


def _batch(recipient_id="evt-NEW", *, ingest_id=None, event_name="crm.lead.created"):
    return CanonicalEventBatch(
        event_name=event_name,
        recipients=[CanonicalEventRecipient(recipient_id=recipient_id, payload={"k": "v"})],
        ingest_id=ingest_id,
    )


async def _event_trigger(db, workflow, tenant_id, app_id, created_by, *, active=True):
    trig = WorkflowTrigger(
        id=uuid.uuid4(), tenant_id=tenant_id, app_id=app_id,
        workflow_id=workflow.id, kind="event",
        event_name=f"e.{uuid.uuid4().hex[:6]}",
        webhook_token=uuid.uuid4().hex, vendor="webhook",
        active=active, params={}, created_by=created_by,
    )
    db.add(trig)
    await db.flush()
    return trig


@pytest.mark.asyncio
async def test_fire_event_creates_one_run_for_the_trigger(db_session, seed_full_run):
    run, version, workflow, _step, tenant_id, app_id = seed_full_run
    workflow.current_published_version_id = version.id
    trig = await _event_trigger(db_session, workflow, tenant_id, app_id, run.triggered_by_user_id)

    result = await fire_event(db_session, trigger=trig, batch=_batch())
    assert result.deduped is False
    assert len(result.run_ids) == 1

    new_run = (await db_session.execute(
        select(WorkflowRun).where(WorkflowRun.id == result.run_ids[0])
    )).scalar_one()
    assert new_run.triggered_by == "event"
    assert new_run.trigger_id == trig.id
    assert new_run.workflow_version_id == version.id
    assert new_run.params["event_payload"]["recipients"][0]["recipient_id"] == "evt-NEW"

    jobs = (await db_session.execute(
        select(BackgroundJob).where(BackgroundJob.job_type == "run-workflow")
    )).scalars().all()
    matching = [j for j in jobs if (j.params or {}).get("run_id") == str(new_run.id)]
    assert len(matching) == 1
    assert new_run.job_id == matching[0].id


@pytest.mark.asyncio
async def test_inactive_trigger_creates_no_run(db_session, seed_full_run):
    run, version, workflow, _step, tenant_id, app_id = seed_full_run
    workflow.current_published_version_id = version.id
    trig = await _event_trigger(
        db_session, workflow, tenant_id, app_id, run.triggered_by_user_id, active=False,
    )
    result = await fire_event(db_session, trigger=trig, batch=_batch())
    assert result.run_ids == []


@pytest.mark.asyncio
async def test_unpublished_workflow_raises(db_session, seed_full_run):
    run, version, workflow, _step, tenant_id, app_id = seed_full_run
    workflow.current_published_version_id = None
    trig = await _event_trigger(db_session, workflow, tenant_id, app_id, run.triggered_by_user_id)
    with pytest.raises(EventTriggerConfigurationError, match="without a published version"):
        await fire_event(db_session, trigger=trig, batch=_batch())


@pytest.mark.asyncio
async def test_event_requires_recipients(db_session, seed_full_run):
    run, version, workflow, _step, tenant_id, app_id = seed_full_run
    workflow.current_published_version_id = version.id
    trig = await _event_trigger(db_session, workflow, tenant_id, app_id, run.triggered_by_user_id)
    empty = CanonicalEventBatch(event_name="crm.lead.created", recipients=[], ingest_id=None)
    with pytest.raises(EventPayloadContractError):
        await fire_event(db_session, trigger=trig, batch=empty)


@pytest.mark.asyncio
async def test_replay_dedupe_returns_prior_run(db_session, seed_full_run):
    run, version, workflow, _step, tenant_id, app_id = seed_full_run
    workflow.current_published_version_id = version.id
    trig = await _event_trigger(db_session, workflow, tenant_id, app_id, run.triggered_by_user_id)
    ingest_id = f"frappe|Lead|LEAD-1|after_insert"

    first = await fire_event(db_session, trigger=trig, batch=_batch(ingest_id=ingest_id))
    assert first.deduped is False
    assert len(first.run_ids) == 1

    second = await fire_event(db_session, trigger=trig, batch=_batch(ingest_id=ingest_id))
    assert second.deduped is True
    assert second.run_ids == first.run_ids

    # Exactly one run, one ingest-log row.
    runs = (await db_session.execute(
        select(WorkflowRun).where(WorkflowRun.trigger_id == trig.id)
    )).scalars().all()
    assert len(runs) == 1
    logs = (await db_session.execute(
        select(EventIngestLog).where(EventIngestLog.trigger_id == trig.id)
    )).scalars().all()
    assert len(logs) == 1


@pytest.mark.asyncio
async def test_no_ingest_id_skips_dedupe(db_session, seed_full_run):
    run, version, workflow, _step, tenant_id, app_id = seed_full_run
    workflow.current_published_version_id = version.id
    trig = await _event_trigger(db_session, workflow, tenant_id, app_id, run.triggered_by_user_id)

    first = await fire_event(db_session, trigger=trig, batch=_batch(ingest_id=None))
    second = await fire_event(db_session, trigger=trig, batch=_batch(ingest_id=None))
    assert first.deduped is False
    assert second.deduped is False
    runs = (await db_session.execute(
        select(WorkflowRun).where(WorkflowRun.trigger_id == trig.id)
    )).scalars().all()
    assert len(runs) == 2

"""Live-DB seed helpers for orchestration analytics read-service tests."""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime, timezone

import pytest_asyncio

from app.constants import SYSTEM_TENANT_ID, SYSTEM_USER_ID
from app.models.orchestration import (
    Workflow,
    WorkflowVersion,
    WorkflowRun,
    WorkflowRunNodeStep,
    WorkflowRunRecipientState,
    WorkflowRunRecipientAction,
)
from app.services.orchestration.analytics.workflow_engagement_populator import (
    populate_workflow_engagement,
)


@pytest_asyncio.fixture
async def seed_orchestration_run(db_session):
    """Factory: insert a workflow + version + completed run + recipients + actions.

    Each call returns a dict with the inserted ids so a test can assert
    overview/breakdown/runs aggregates against known buckets and channels.

    ``recipients`` is a list of dicts: {recipient_id, bucket, channel, cost,
    contact}. Each yields one recipient state + one recipient action row.

    Optional additive keys: ``attributes`` (dict merged into the recipient
    state payload — dataset passthrough), ``voice_duration_sec`` /
    ``voice_transcript`` (written onto the single action's response, mirroring
    the reconciler's ``duration_sec`` / ``transcript`` capture keys).

    A recipient dict may instead carry ``events``: a list of child-event dicts
    {action_type, bucket} which seed a parent dispatch row (parent_action_id
    NULL, outcome_bucket NULL) plus one child action per event (parent_action_id
    set, the lifecycle outcome_bucket). This mirrors the WhatsApp/WATI adapter
    that persists one child row per lifecycle event.
    """

    _UNSET = object()

    async def _make(
        *,
        tenant_id=SYSTEM_TENANT_ID,
        app_id="test-orchestration",
        recipients: list[dict],
        workflow_name: str | None = None,
        run_status: str = "completed",
        started_at: datetime | None = _UNSET,
        definition: dict | None = None,
    ) -> dict:
        now = datetime.now(timezone.utc)
        # _UNSET defaults to now; an explicit None seeds a NULL started_at (in-flight).
        started = now if started_at is _UNSET else started_at
        workflow = Workflow(
            id=_uuid.uuid4(), tenant_id=tenant_id, app_id=app_id,
            workflow_type="crm",
            slug=f"analytics-{_uuid.uuid4().hex[:8]}",
            name=workflow_name or "Analytics Run",
            created_by=SYSTEM_USER_ID,
        )
        db_session.add(workflow)
        await db_session.flush()

        version = WorkflowVersion(
            id=_uuid.uuid4(), tenant_id=tenant_id, app_id=app_id,
            workflow_id=workflow.id, version=1,
            definition=definition or {"nodes": [], "edges": []},
            status="published",
        )
        db_session.add(version)
        await db_session.flush()

        run = WorkflowRun(
            id=_uuid.uuid4(), tenant_id=tenant_id, app_id=app_id,
            workflow_id=workflow.id, workflow_version_id=version.id,
            triggered_by="manual", triggered_by_user_id=SYSTEM_USER_ID,
            status=run_status, cohort_size_at_entry=len(recipients),
            started_at=started, completed_at=now if run_status == "completed" else None,
        )
        db_session.add(run)
        await db_session.flush()

        node_step = WorkflowRunNodeStep(
            id=_uuid.uuid4(), tenant_id=tenant_id, app_id=app_id,
            workflow_id=workflow.id, workflow_version_id=version.id,
            run_id=run.id, node_id="dispatch1", node_type="voice.place_call",
            status="completed", started_at=started, completed_at=now,
        )
        db_session.add(node_step)
        await db_session.flush()

        action_ids: list[_uuid.UUID] = []
        for idx, rec in enumerate(recipients):
            recipient_id = rec.get("recipient_id", f"r{idx}")
            channel = rec.get("channel", "voice")
            contact = rec.get("contact", f"+1000000{idx:04d}")
            cost = rec.get("cost", "0.05")
            state_payload = {"contact": contact, **(rec.get("attributes") or {})}
            db_session.add(WorkflowRunRecipientState(
                id=_uuid.uuid4(), tenant_id=tenant_id, app_id=app_id,
                workflow_id=workflow.id, workflow_version_id=version.id,
                run_id=run.id, recipient_id=recipient_id,
                status="completed", payload=state_payload,
            ))
            if rec.get("events") is not None:
                # WhatsApp-style: one parent dispatch row (no outcome_bucket) +
                # one child action row per lifecycle event.
                parent = WorkflowRunRecipientAction(
                    id=_uuid.uuid4(), tenant_id=tenant_id, app_id=app_id,
                    workflow_id=workflow.id, workflow_version_id=version.id,
                    run_id=run.id, node_step_id=node_step.id,
                    recipient_id=recipient_id, channel=channel,
                    action_type=rec.get("dispatch_action_type", "wa-sent"),
                    status="success",
                    idempotency_key=f"idem-{run.id}-{recipient_id}-{idx}-parent",
                    payload={"contact": contact},
                    response={"total_cost": cost} if cost is not None else None,
                    parent_action_id=None,
                    outcome_bucket=None,
                )
                db_session.add(parent)
                await db_session.flush()
                action_ids.append(parent.id)
                for evt_idx, evt in enumerate(rec["events"]):
                    child = WorkflowRunRecipientAction(
                        id=_uuid.uuid4(), tenant_id=tenant_id, app_id=app_id,
                        workflow_id=workflow.id, workflow_version_id=version.id,
                        run_id=run.id, node_step_id=node_step.id,
                        recipient_id=recipient_id, channel=channel,
                        action_type=evt["action_type"], status="success",
                        idempotency_key=(
                            f"idem-{run.id}-{recipient_id}-{idx}-{evt['action_type']}"
                        ),
                        payload={"contact": contact},
                        response=None,
                        parent_action_id=parent.id,
                        outcome_bucket=evt["bucket"],
                    )
                    db_session.add(child)
                    action_ids.append(child.id)
                continue
            response: dict | None = {"total_cost": cost} if cost is not None else None
            # Mirror the reconciler's capture keys on the terminal action response.
            if rec.get("voice_duration_sec") is not None or rec.get("voice_transcript") is not None:
                response = dict(response or {})
                if rec.get("voice_duration_sec") is not None:
                    response["duration_sec"] = rec["voice_duration_sec"]
                if rec.get("voice_transcript") is not None:
                    response["transcript"] = rec["voice_transcript"]
            action = WorkflowRunRecipientAction(
                id=_uuid.uuid4(), tenant_id=tenant_id, app_id=app_id,
                workflow_id=workflow.id, workflow_version_id=version.id,
                run_id=run.id, node_step_id=node_step.id,
                recipient_id=recipient_id, channel=channel,
                action_type=rec.get("action_type", "voice_queued"), status="success",
                idempotency_key=f"idem-{run.id}-{recipient_id}-{idx}",
                payload={"contact": contact},
                response=response,
                parent_action_id=None,
                outcome_bucket=rec["bucket"],
            )
            db_session.add(action)
            action_ids.append(action.id)
        await db_session.flush()

        # Mirror prod (run completes → populate): build the engagement fact + refresh the matview
        # so the fact-based read_service sees this run. This is the parity bridge — assertions
        # authored against the old TXN read now re-validate the flat-fact read.
        await populate_workflow_engagement(db_session, run_ids=[run.id])

        return {
            "tenant_id": tenant_id,
            "app_id": app_id,
            "workflow_id": workflow.id,
            "workflow_version_id": version.id,
            "run_id": run.id,
            "node_step_id": node_step.id,
            "node_id": node_step.node_id,
            "action_ids": action_ids,
        }

    return _make

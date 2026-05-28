"""The terminal-event reconcile path stamps a channel-agnostic outcome_bucket on the child action."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.orchestration import (
    WorkflowRunRecipientAction,
    WorkflowRunRecipientState,
)
from app.services.orchestration.adapters.bolna import BolnaAdapter


@pytest.mark.asyncio
async def test_reconcile_stamps_outcome_bucket_on_child(db_session, seed_full_run):
    run, version, workflow, node_step, tenant_id, app_id = seed_full_run
    recipient_id = "P-bucket"

    db_session.add(WorkflowRunRecipientState(
        id=uuid.uuid4(), tenant_id=tenant_id, app_id=app_id,
        workflow_id=workflow.id, workflow_version_id=version.id,
        run_id=run.id, recipient_id=recipient_id, current_node_id="n1",
        status="waiting", wakeup_at=datetime.now(timezone.utc) + timedelta(days=1),
        payload={},
    ))
    parent = WorkflowRunRecipientAction(
        id=uuid.uuid4(), tenant_id=tenant_id, app_id=app_id,
        workflow_id=workflow.id, workflow_version_id=version.id,
        run_id=run.id, node_step_id=node_step.id, recipient_id=recipient_id,
        channel="voice", action_type="voice_queued", status="success",
        idempotency_key=f"dispatch-{uuid.uuid4().hex[:8]}",
        payload={"contact": "+919505100019", "mode": "single"},
        response={"raw": {}}, provider_correlation_id="ex-bucket",
        provider_terminal=False,
    )
    db_session.add(parent)
    await db_session.flush()
    parent_id = parent.id

    applied = await BolnaAdapter().reconcile_execution(
        db_session,
        action=parent,
        node_id=node_step.node_id,
        execution={"id": "ex-bucket", "status": "completed"},
    )
    assert applied is True

    db_session.expire_all()
    child = (await db_session.execute(
        select(WorkflowRunRecipientAction).where(
            WorkflowRunRecipientAction.parent_action_id == parent_id,
            WorkflowRunRecipientAction.action_type == "bolna_answered",
        )
    )).scalar_one()
    assert child.outcome_bucket == "positive"

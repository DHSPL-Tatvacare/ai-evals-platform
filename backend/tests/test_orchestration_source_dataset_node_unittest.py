"""source.dataset node — communication_key stamps ``contact`` onto recipients.

Drives the handler's ``execute()`` against the live DB so the comm-key UPDATE
and the register-recipients receipt are exercised end-to-end. Mirrors the
node-execution pattern in ``test_orchestration_nodes_unittest.py``.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

import app.services.orchestration.nodes  # noqa: F401 — register handlers
from app.models.orchestration import (
    Workflow,
    WorkflowRun,
    WorkflowRunNodeStep,
    WorkflowRunRecipientState,
    WorkflowVersion,
)
from app.services.orchestration.api.datasets import create_dataset, import_version
from app.services.orchestration.cohort_stream import CohortStream
from app.services.orchestration.datasets.csv_importer import parse_csv
from app.services.orchestration.node_context import NodeContext, ServiceRegistry
from app.services.orchestration.nodes.source_dataset import _Handler


CSV_WITH_PHONE = (
    "recipient_id,name,phone\n"
    "r1,alice,+919000000001\n"
    "r2,bob,+919000000002\n"
)


@pytest.fixture
def commit_as_flush(db_session):
    original = db_session.commit
    db_session.commit = db_session.flush  # type: ignore[assignment]
    try:
        yield db_session
    finally:
        db_session.commit = original  # type: ignore[assignment]


@pytest.mark.asyncio
async def test_source_dataset_stamps_contact_from_communication_key(
    commit_as_flush, seed_tenant_user_app,
):
    db_session = commit_as_flush
    tenant_id, user_id, app_id = seed_tenant_user_app

    ds = await create_dataset(
        db_session,
        tenant_id=tenant_id,
        app_id=app_id,
        name=f"node-commkey-{uuid.uuid4().hex[:6]}",
        description=None,
        created_by=user_id,
    )
    version = await import_version(
        db_session,
        tenant_id=tenant_id,
        dataset_id=ds["id"],
        imported=parse_csv(
            CSV_WITH_PHONE.encode("utf-8"),
            id_strategy="column", id_column="recipient_id",
        ),
        source_type="csv",
        source_filename="cohort.csv",
        source_byte_size=len(CSV_WITH_PHONE),
        id_strategy="column",
        id_column="recipient_id",
        communication_key="phone",
        imported_by=user_id,
    )

    workflow = Workflow(
        id=uuid.uuid4(), tenant_id=tenant_id, app_id=app_id,
        workflow_type="crm", slug=f"node-{uuid.uuid4().hex[:8]}",
        name="dataset node", created_by=user_id,
    )
    db_session.add(workflow)
    await db_session.flush()
    wf_version = WorkflowVersion(
        id=uuid.uuid4(), tenant_id=tenant_id, app_id=app_id,
        workflow_id=workflow.id, version=1,
        definition={"nodes": [], "edges": []}, status="published",
    )
    db_session.add(wf_version)
    await db_session.flush()
    run = WorkflowRun(
        id=uuid.uuid4(), tenant_id=tenant_id, app_id=app_id,
        workflow_id=workflow.id, workflow_version_id=wf_version.id,
        triggered_by="manual", triggered_by_user_id=user_id, status="running",
    )
    db_session.add(run)
    await db_session.flush()
    step = WorkflowRunNodeStep(
        id=uuid.uuid4(), tenant_id=tenant_id, app_id=app_id,
        workflow_id=workflow.id, workflow_version_id=wf_version.id,
        run_id=run.id, node_id="src", node_type="source.dataset",
        status="running",
    )
    db_session.add(step)
    await db_session.flush()

    ctx = NodeContext(
        db=db_session, tenant_id=tenant_id, app_id=app_id,
        workflow_id=workflow.id, workflow_version_id=wf_version.id,
        run_id=run.id, node_step_id=step.id, current_node_id="src",
        services=ServiceRegistry(), job_id=None,
        outgoing_targets={"default": ["done"]},
    )
    from app.services.orchestration.nodes.source_dataset import _Config

    cfg = _Config(dataset_version_id=uuid.UUID(str(version["id"])))
    result = await _Handler().execute(CohortStream([]), cfg, ctx)

    assert result.summary["cohort_size"] == 2
    assert result.summary["registered"] == 2

    states = (
        await db_session.execute(
            select(WorkflowRunRecipientState)
            .where(WorkflowRunRecipientState.run_id == run.id)
            .order_by(WorkflowRunRecipientState.recipient_id)
        )
    ).scalars().all()
    by_id = {s.recipient_id: s.payload for s in states}
    # contact stamped from the comm-key column.
    assert by_id["r1"]["contact"] == "+919000000001"
    assert by_id["r2"]["contact"] == "+919000000002"

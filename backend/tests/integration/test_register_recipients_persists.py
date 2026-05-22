"""Rule #7: register_run_recipients persists across a real session boundary.

A test that shares one transaction (or stubs commit=flush) cannot catch a
missing-commit bug. Here the writer runs inside a committing transaction on
one session; a *fresh* session then re-reads the choke table and must see the
membership rows. The test commits real rows, so it cleans them up explicitly
(it does not ride the rollback-on-teardown db_session fixture).
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from app.constants import SYSTEM_TENANT_ID, SYSTEM_USER_ID
from app.models.orchestration import (
    Workflow,
    WorkflowRun,
    WorkflowRunRecipient,
    WorkflowVersion,
)
from app.services.orchestration.recipient_freezer import register_run_recipients


APP_ID = "test-orchestration"


@pytest_asyncio.fixture
async def committed_run(db_engine):
    """Create + COMMIT a workflow/version/run on its own session, yield the run
    id, and tear it all down with a CASCADE-bearing delete after the test."""
    Session = async_sessionmaker(
        bind=db_engine, expire_on_commit=False, class_=AsyncSession
    )
    workflow_id = uuid.uuid4()
    version_id = uuid.uuid4()
    run_id = uuid.uuid4()
    async with Session() as setup:
        setup.add(
            Workflow(
                id=workflow_id, tenant_id=SYSTEM_TENANT_ID, app_id=APP_ID,
                workflow_type="crm", slug=f"persist-{uuid.uuid4().hex[:8]}",
                name="Persist", created_by=SYSTEM_USER_ID,
            )
        )
        await setup.flush()
        setup.add(
            WorkflowVersion(
                id=version_id, tenant_id=SYSTEM_TENANT_ID, app_id=APP_ID,
                workflow_id=workflow_id, version=1,
                definition={"nodes": [], "edges": []}, status="published",
            )
        )
        await setup.flush()
        setup.add(
            WorkflowRun(
                id=run_id, tenant_id=SYSTEM_TENANT_ID, app_id=APP_ID,
                workflow_id=workflow_id, workflow_version_id=version_id,
                triggered_by="manual", triggered_by_user_id=SYSTEM_USER_ID,
                status="running",
            )
        )
        await setup.commit()
    try:
        yield run_id, version_id, workflow_id
    finally:
        # Delete in FK order: run (CASCADEs the choke rows) → version → workflow.
        async with Session() as cleanup:
            await cleanup.execute(delete(WorkflowRun).where(WorkflowRun.id == run_id))
            await cleanup.execute(
                delete(WorkflowVersion).where(WorkflowVersion.id == version_id)
            )
            await cleanup.execute(delete(Workflow).where(Workflow.id == workflow_id))
            await cleanup.commit()


@pytest.mark.asyncio
async def test_membership_visible_in_fresh_session(db_engine, committed_run):
    run_id, _version_id, _workflow_id = committed_run
    Session = async_sessionmaker(
        bind=db_engine, expire_on_commit=False, class_=AsyncSession
    )

    # Writer runs inside a committing transaction on its own session.
    async with Session() as writer:
        run = (
            await writer.execute(select(WorkflowRun).where(WorkflowRun.id == run_id))
        ).scalar_one()
        receipt = await register_run_recipients(
            writer,
            run=run,
            ingress_kind="dataset",
            resolved_rows=[("D1", "9876543210"), ("D2", "not-a-phone")],
        )
        assert receipt.registered_count == 2
        await writer.commit()

    # A brand-new session must observe the committed membership rows.
    async with Session() as reader:
        rows = (
            await reader.execute(
                select(WorkflowRunRecipient).where(
                    WorkflowRunRecipient.run_id == run_id
                )
            )
        ).scalars().all()
    assert {r.recipient_id for r in rows} == {"D1", "D2"}
    assert all(r.ingress_kind == "dataset" for r in rows)
    assert {r.phone_e164 for r in rows} == {"+919876543210", None}

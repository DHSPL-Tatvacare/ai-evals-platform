"""register_run_recipients: the single writer of the choke table.

The choke table (orchestration.workflow_run_recipients) records membership
only — "is this recipient real for this run". Cohort, dataset, and event
ingress all register through this one writer. ``phone_e164`` is best-effort
provenance (NULL when unresolvable), NOT the dispatch destination and NOT the
reach-count key — so a recipient with no resolvable phone at T0 is still a
member and ``assert_recipient_in_manifest`` passes for it.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.orchestration import (
    CohortDefinition,
    CohortDefinitionVersion,
    WorkflowRun,
    WorkflowRunRecipient,
)
from app.services.orchestration.recipient_freezer import (
    RegisterReceipt,
    register_run_recipients,
)


@pytest_asyncio.fixture
async def cohort_version(db_session, seed_tenant_user_app):
    tenant_id, user_id, app_id = seed_tenant_user_app
    cohort = CohortDefinition(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        app_id=app_id,
        slug=f"reg-test-{uuid.uuid4().hex[:8]}",
        name="Register test",
        created_by=user_id,
    )
    db_session.add(cohort)
    await db_session.flush()
    version = CohortDefinitionVersion(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        app_id=app_id,
        cohort_definition_id=cohort.id,
        version=1,
        source_ref="platform.leads",
        filters=[],
        payload_fields=["phone"],
        status="published",
    )
    db_session.add(version)
    await db_session.flush()
    return version


@pytest.mark.asyncio
async def test_cohort_ingress_registers_membership(
    db_session, seed_full_run, cohort_version
):
    run, *_ = seed_full_run
    receipt: RegisterReceipt = await register_run_recipients(
        db_session,
        run=run,
        ingress_kind="cohort",
        resolved_rows=[("L1", "9876543210"), ("L2", "+91 98765 00000")],
        cohort_version=cohort_version,
    )
    assert receipt.registered_count == 2
    rows = (
        await db_session.execute(
            select(WorkflowRunRecipient).where(WorkflowRunRecipient.run_id == run.id)
        )
    ).scalars().all()
    assert {r.recipient_id for r in rows} == {"L1", "L2"}
    assert all(r.ingress_kind == "cohort" for r in rows)
    assert {r.phone_e164 for r in rows} == {"+919876543210", "+919876500000"}
    assert all(r.source_cohort_version_id == cohort_version.id for r in rows)


@pytest.mark.asyncio
async def test_dataset_ingress_registers_membership(db_session, seed_full_run):
    run, *_ = seed_full_run
    receipt = await register_run_recipients(
        db_session,
        run=run,
        ingress_kind="dataset",
        resolved_rows=[("D1", "9876543210"), ("D2", "9876500000")],
        provenance={"enrolled_dataset_version_id": str(uuid.uuid4())},
    )
    assert receipt.registered_count == 2
    rows = (
        await db_session.execute(
            select(WorkflowRunRecipient).where(WorkflowRunRecipient.run_id == run.id)
        )
    ).scalars().all()
    assert {r.recipient_id for r in rows} == {"D1", "D2"}
    assert all(r.ingress_kind == "dataset" for r in rows)
    assert all(r.source_cohort_version_id is None for r in rows)
    assert all("enrolled_dataset_version_id" in (r.provenance or {}) for r in rows)


@pytest.mark.asyncio
async def test_event_ingress_registers_membership(db_session, seed_full_run):
    run, *_ = seed_full_run
    receipt = await register_run_recipients(
        db_session,
        run=run,
        ingress_kind="event_trigger",
        resolved_rows=[("E1", "9876543210")],
    )
    assert receipt.registered_count == 1
    rows = (
        await db_session.execute(
            select(WorkflowRunRecipient).where(WorkflowRunRecipient.run_id == run.id)
        )
    ).scalars().all()
    assert {r.recipient_id for r in rows} == {"E1"}
    assert all(r.ingress_kind == "event_trigger" for r in rows)


@pytest.mark.asyncio
async def test_unresolvable_phone_still_a_member(db_session, seed_full_run):
    """Membership does not depend on a resolvable phone — phone_e164 is
    best-effort provenance, so the row is still written with NULL phone."""
    run, *_ = seed_full_run
    receipt = await register_run_recipients(
        db_session,
        run=run,
        ingress_kind="dataset",
        resolved_rows=[("D1", "9876543210"), ("D2", "not-a-phone"), ("D3", None)],
    )
    assert receipt.registered_count == 3
    assert receipt.unresolved_phone_count == 2
    rows = {
        r.recipient_id: r.phone_e164
        for r in (
            await db_session.execute(
                select(WorkflowRunRecipient).where(
                    WorkflowRunRecipient.run_id == run.id
                )
            )
        ).scalars().all()
    }
    assert set(rows) == {"D1", "D2", "D3"}
    assert rows["D1"] == "+919876543210"
    assert rows["D2"] is None
    assert rows["D3"] is None


@pytest.mark.asyncio
async def test_register_is_idempotent(db_session, seed_full_run):
    run, *_ = seed_full_run
    rows_in = [("L1", "9876543210"), ("L2", "9876500000")]
    await register_run_recipients(
        db_session, run=run, ingress_kind="cohort", resolved_rows=rows_in,
        inline_predicate={"source_ref": "platform.leads"},
    )
    await register_run_recipients(
        db_session, run=run, ingress_kind="cohort", resolved_rows=rows_in,
        inline_predicate={"source_ref": "platform.leads"},
    )
    rows = (
        await db_session.execute(
            select(WorkflowRunRecipient).where(WorkflowRunRecipient.run_id == run.id)
        )
    ).scalars().all()
    assert len(rows) == 2

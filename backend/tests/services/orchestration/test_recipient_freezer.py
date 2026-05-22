"""Tests for recipient_freezer: phone normalisation, register write, idempotency."""
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
    normalise_phone_e164,
    register_run_recipients,
)


# ── Phone normalisation: pure-function tests ───────────────────


def test_normalise_phone_accepts_indian_local():
    assert normalise_phone_e164("9876543210", default_region="IN") == "+919876543210"


def test_normalise_phone_accepts_e164():
    assert normalise_phone_e164("+91 98765 43210") == "+919876543210"


def test_normalise_phone_returns_none_on_garbage():
    assert normalise_phone_e164("not-a-phone") is None


def test_normalise_phone_returns_none_on_empty():
    assert normalise_phone_e164("") is None
    assert normalise_phone_e164(None) is None


def test_normalise_phone_returns_none_on_invalid_e164():
    # 10 digits with leading + is not parseable as a real number
    assert normalise_phone_e164("+1234") is None


# ── Cohort version fixture ─────────────────────────────────────


@pytest_asyncio.fixture
async def cohort_version(db_session, seed_tenant_user_app):
    tenant_id, user_id, app_id = seed_tenant_user_app
    cohort = CohortDefinition(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        app_id=app_id,
        slug=f"freeze-test-{uuid.uuid4().hex[:8]}",
        name="Freeze test",
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
        filters=[{"field": "phone", "op": "in", "value": ["+919876543210"]}],
        payload_fields=["phone"],
        status="published",
    )
    db_session.add(version)
    await db_session.flush()
    return version


@pytest_asyncio.fixture
async def sample_recipient_rows():
    return [
        ("L1", "9876543210"),
        ("L2", "+91 98765 00000"),
    ]


# ── register_run_recipients integration tests ──────────────────


@pytest.mark.asyncio
async def test_register_writes_manifest_rows(
    db_session, seed_full_run, cohort_version, sample_recipient_rows
):
    run, *_ = seed_full_run
    receipt: RegisterReceipt = await register_run_recipients(
        db_session,
        run=run,
        ingress_kind="cohort",
        cohort_version=cohort_version,
        resolved_rows=sample_recipient_rows,
    )
    assert receipt.registered_count == 2
    assert receipt.unresolved_phone_count == 0
    rows = (
        await db_session.execute(
            select(WorkflowRunRecipient).where(WorkflowRunRecipient.run_id == run.id)
        )
    ).scalars().all()
    assert {r.phone_e164 for r in rows} == {"+919876543210", "+919876500000"}
    assert {r.recipient_id for r in rows} == {"L1", "L2"}
    assert all(r.predicate_hash == receipt.predicate_hash for r in rows)
    assert all(r.tenant_id == run.tenant_id for r in rows)
    assert all(r.app_id == run.app_id for r in rows)
    assert all(r.ingress_kind == "cohort" for r in rows)
    assert all(r.source_cohort_version_id == cohort_version.id for r in rows)


@pytest.mark.asyncio
async def test_register_keeps_members_with_unresolvable_phone(
    db_session, seed_full_run, cohort_version
):
    """Membership does not depend on a resolvable phone — invalid/empty phones
    are still members, with phone_e164 left NULL (best-effort provenance)."""
    run, *_ = seed_full_run
    rows = [
        ("L1", "9876543210"),
        ("L2", "not-a-phone"),
        ("L3", None),
        ("L4", ""),
    ]
    receipt = await register_run_recipients(
        db_session,
        run=run,
        ingress_kind="cohort",
        cohort_version=cohort_version,
        resolved_rows=rows,
    )
    assert receipt.registered_count == 4
    assert receipt.unresolved_phone_count == 3
    manifest = {
        r.recipient_id: r.phone_e164
        for r in (
            await db_session.execute(
                select(WorkflowRunRecipient).where(
                    WorkflowRunRecipient.run_id == run.id
                )
            )
        ).scalars().all()
    }
    assert set(manifest) == {"L1", "L2", "L3", "L4"}
    assert manifest["L1"] == "+919876543210"
    assert manifest["L2"] is None
    assert manifest["L3"] is None
    assert manifest["L4"] is None


@pytest.mark.asyncio
async def test_register_is_idempotent(
    db_session, seed_full_run, cohort_version, sample_recipient_rows
):
    run, *_ = seed_full_run
    receipt1 = await register_run_recipients(
        db_session,
        run=run,
        ingress_kind="cohort",
        cohort_version=cohort_version,
        resolved_rows=sample_recipient_rows,
    )
    receipt2 = await register_run_recipients(
        db_session,
        run=run,
        ingress_kind="cohort",
        cohort_version=cohort_version,
        resolved_rows=sample_recipient_rows,
    )
    assert receipt1.predicate_hash == receipt2.predicate_hash
    rows = (
        await db_session.execute(
            select(WorkflowRunRecipient).where(WorkflowRunRecipient.run_id == run.id)
        )
    ).scalars().all()
    assert len(rows) == 2


# ── Inline-mode register tests (cohort_version=None) ───────────


@pytest.mark.asyncio
async def test_inline_register_hashes_predicate_and_leaves_version_null(
    db_session, seed_full_run, sample_recipient_rows
):
    run, *_ = seed_full_run
    predicate = {
        "source_ref": "platform.leads",
        "filters": [{"field": "stage", "op": "eq", "value": "new"}],
        "payload_fields": ["phone"],
    }
    receipt = await register_run_recipients(
        db_session,
        run=run,
        ingress_kind="cohort",
        cohort_version=None,
        resolved_rows=sample_recipient_rows,
        inline_predicate=predicate,
    )
    assert receipt.registered_count == 2
    assert receipt.predicate_hash
    rows = (
        await db_session.execute(
            select(WorkflowRunRecipient).where(WorkflowRunRecipient.run_id == run.id)
        )
    ).scalars().all()
    assert all(r.source_cohort_version_id is None for r in rows)
    assert all(r.predicate_hash == receipt.predicate_hash for r in rows)


@pytest.mark.asyncio
async def test_inline_register_hash_is_stable_and_predicate_sensitive(
    db_session, seed_full_run, seed_tenant_user_app, sample_recipient_rows
):
    run, *_ = seed_full_run
    tenant_id, user_id, app_id = seed_tenant_user_app
    predicate_a = {
        "source_ref": "platform.leads",
        "filters": [{"field": "stage", "op": "eq", "value": "new"}],
    }
    receipt1 = await register_run_recipients(
        db_session,
        run=run,
        ingress_kind="cohort",
        cohort_version=None,
        resolved_rows=sample_recipient_rows,
        inline_predicate=predicate_a,
    )
    receipt2 = await register_run_recipients(
        db_session,
        run=run,
        ingress_kind="cohort",
        cohort_version=None,
        resolved_rows=sample_recipient_rows,
        inline_predicate=predicate_a,
    )
    assert receipt1.predicate_hash == receipt2.predicate_hash

    other_run = WorkflowRun(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        app_id=app_id,
        workflow_id=run.workflow_id,
        workflow_version_id=run.workflow_version_id,
        triggered_by="manual",
        triggered_by_user_id=user_id,
        status="running",
    )
    db_session.add(other_run)
    await db_session.flush()
    predicate_b = {
        "source_ref": "platform.leads",
        "filters": [{"field": "stage", "op": "eq", "value": "won"}],
    }
    receipt3 = await register_run_recipients(
        db_session,
        run=other_run,
        ingress_kind="cohort",
        cohort_version=None,
        resolved_rows=sample_recipient_rows,
        inline_predicate=predicate_b,
    )
    assert receipt3.predicate_hash != receipt1.predicate_hash


@pytest.mark.asyncio
async def test_register_without_predicate_leaves_hash_null(
    db_session, seed_full_run, sample_recipient_rows
):
    """Dataset / event ingress carry no predicate — the hash stays NULL while
    membership is still written."""
    run, *_ = seed_full_run
    receipt = await register_run_recipients(
        db_session,
        run=run,
        ingress_kind="dataset",
        cohort_version=None,
        resolved_rows=sample_recipient_rows,
        inline_predicate=None,
    )
    assert receipt.registered_count == 2
    assert receipt.predicate_hash is None
    rows = (
        await db_session.execute(
            select(WorkflowRunRecipient).where(WorkflowRunRecipient.run_id == run.id)
        )
    ).scalars().all()
    assert all(r.predicate_hash is None for r in rows)

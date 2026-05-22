"""enforce_comm_cap_or_skip: count the resolved contact's prior sends, decide.

The single Reach-Limit enforcer. It counts prior sends for the resolved
contact (the action ledger's ``contact_phone_e164`` generated column =
``payload->>'contact'``), per channel, over the rolling window. Over the
cap ⇒ ``proceed=False``; under ⇒ ``proceed=True``. It is read-only — it
does NOT flip any recipient state row (the dispatch handler reacts to the
result). No second function name, no T0 pre-cut.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.comm_cap_policy import CommCapPolicy
from app.models.orchestration import (
    WorkflowRunRecipientAction,
    WorkflowRunRecipientState,
)
from app.services.orchestration.comm_cap.enforcement import (
    EnforcementResult,
    enforce_comm_cap_or_skip,
)


PHONE = "+919876543210"


@pytest_asyncio.fixture
async def seed_action(db_session, seed_full_run):
    run, _version, workflow, node_step, tenant_id, app_id = seed_full_run

    async def _seed(
        *, phone: str, channel: str = "whatsapp", offset_seconds: int = 0
    ) -> uuid.UUID:
        action_id = uuid.uuid4()
        action = WorkflowRunRecipientAction(
            id=action_id,
            tenant_id=tenant_id,
            app_id=app_id,
            workflow_id=workflow.id,
            workflow_version_id=run.workflow_version_id,
            run_id=run.id,
            node_step_id=node_step.id,
            recipient_id=f"R-{uuid.uuid4().hex[:8]}",
            channel=channel,
            action_type="messaging.send_whatsapp_template",
            status="success",
            idempotency_key=f"idem-{uuid.uuid4().hex[:8]}",
            payload={"contact": phone},
        )
        db_session.add(action)
        await db_session.flush()
        if offset_seconds:
            from sqlalchemy import text

            await db_session.execute(
                text(
                    "UPDATE orchestration.workflow_run_recipient_actions "
                    "SET created_at = now() + make_interval(secs => :offset) "
                    "WHERE id = :id"
                ),
                {"offset": offset_seconds, "id": action_id},
            )
            await db_session.flush()
        return action_id

    return _seed


@pytest.mark.asyncio
async def test_no_policy_proceeds(db_session, seed_full_run):
    run, *_ = seed_full_run
    result = await enforce_comm_cap_or_skip(
        db_session,
        tenant_id=run.tenant_id,
        app_id=run.app_id,
        contact=PHONE,
        channel="whatsapp",
    )
    assert isinstance(result, EnforcementResult)
    assert result.proceed is True
    assert result.reason is None


@pytest.mark.asyncio
async def test_under_cap_proceeds(db_session, seed_full_run, seed_action):
    run, *_ = seed_full_run
    db_session.add(
        CommCapPolicy(
            tenant_id=run.tenant_id,
            app_id=run.app_id,
            max_count=2,
            window_seconds=86400,
            is_active=True,
        )
    )
    await seed_action(phone=PHONE, offset_seconds=-60)
    await db_session.flush()

    result = await enforce_comm_cap_or_skip(
        db_session,
        tenant_id=run.tenant_id,
        app_id=run.app_id,
        contact=PHONE,
        channel="whatsapp",
    )
    assert result.proceed is True
    assert result.reason is None


@pytest.mark.asyncio
async def test_over_cap_does_not_proceed(db_session, seed_full_run, seed_action):
    run, *_ = seed_full_run
    db_session.add(
        CommCapPolicy(
            tenant_id=run.tenant_id,
            app_id=run.app_id,
            max_count=1,
            window_seconds=86400,
            is_active=True,
        )
    )
    await seed_action(phone=PHONE, offset_seconds=-60)
    await db_session.flush()

    result = await enforce_comm_cap_or_skip(
        db_session,
        tenant_id=run.tenant_id,
        app_id=run.app_id,
        contact=PHONE,
        channel="whatsapp",
        stage="cap_runtime",
    )
    assert result.proceed is False
    assert result.reason == "cap_runtime"


@pytest.mark.asyncio
async def test_count_is_per_channel(db_session, seed_full_run, seed_action):
    """A prior send on a different channel does not count toward this channel."""
    run, *_ = seed_full_run
    db_session.add(
        CommCapPolicy(
            tenant_id=run.tenant_id,
            app_id=run.app_id,
            max_count=1,
            window_seconds=86400,
            is_active=True,
        )
    )
    await seed_action(phone=PHONE, channel="voice", offset_seconds=-60)
    await db_session.flush()

    result = await enforce_comm_cap_or_skip(
        db_session,
        tenant_id=run.tenant_id,
        app_id=run.app_id,
        contact=PHONE,
        channel="whatsapp",
    )
    assert result.proceed is True


@pytest.mark.asyncio
async def test_count_is_per_resolved_phone_across_runs(
    db_session, seed_full_run, seed_action
):
    """The count keys on the resolved contact, not recipient_id — actions seeded
    under different recipient_ids but the same phone all count."""
    run, *_ = seed_full_run
    db_session.add(
        CommCapPolicy(
            tenant_id=run.tenant_id,
            app_id=run.app_id,
            max_count=2,
            window_seconds=86400,
            is_active=True,
        )
    )
    # Two prior sends to the same phone under distinct recipient_ids.
    await seed_action(phone=PHONE, offset_seconds=-120)
    await seed_action(phone=PHONE, offset_seconds=-60)
    await db_session.flush()

    result = await enforce_comm_cap_or_skip(
        db_session,
        tenant_id=run.tenant_id,
        app_id=run.app_id,
        contact=PHONE,
        channel="whatsapp",
    )
    assert result.proceed is False


@pytest.mark.asyncio
async def test_enforcer_does_not_mutate_state_or_actions(
    db_session, seed_full_run, seed_action
):
    """The enforcer is read-only: no state flip, no actions row written."""
    run, _version, workflow, _node_step, tenant_id, app_id = seed_full_run
    recipient_id = f"R-{uuid.uuid4().hex[:8]}"
    state = WorkflowRunRecipientState(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        app_id=app_id,
        workflow_id=workflow.id,
        workflow_version_id=run.workflow_version_id,
        run_id=run.id,
        recipient_id=recipient_id,
        status="pending",
        payload={"contact": PHONE},
    )
    db_session.add(state)
    db_session.add(
        CommCapPolicy(
            tenant_id=tenant_id,
            app_id=app_id,
            max_count=1,
            window_seconds=86400,
            is_active=True,
        )
    )
    await seed_action(phone=PHONE, offset_seconds=-60)
    await db_session.flush()

    actions_before = (
        await db_session.execute(
            select(WorkflowRunRecipientAction).where(
                WorkflowRunRecipientAction.run_id == run.id,
            )
        )
    ).scalars().all()

    result = await enforce_comm_cap_or_skip(
        db_session,
        tenant_id=tenant_id,
        app_id=app_id,
        contact=PHONE,
        channel="whatsapp",
    )
    assert result.proceed is False

    await db_session.refresh(state)
    assert state.status == "pending"

    actions_after = (
        await db_session.execute(
            select(WorkflowRunRecipientAction).where(
                WorkflowRunRecipientAction.run_id == run.id,
            )
        )
    ).scalars().all()
    assert len(actions_after) == len(actions_before)

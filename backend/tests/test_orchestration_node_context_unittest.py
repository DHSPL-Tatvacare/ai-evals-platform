"""NodeContext exposes db/run state/services/idempotency to handlers.

Verifies dispatch_actions writes rows + honours idempotency,
set_recipient_state mutates the pointer row.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models.orchestration import WorkflowRunRecipientAction, WorkflowRunRecipientState
from app.services.orchestration.node_context import NodeContext, ServiceRegistry
from app.services.orchestration.node_protocol import ActionDispatch


@pytest.mark.asyncio
async def test_dispatch_actions_writes_action_rows(db_session, seed_full_run):
    run, version, workflow, node_step, tenant_id, app_id = seed_full_run
    state = WorkflowRunRecipientState(
        id=uuid.uuid4(), tenant_id=tenant_id, app_id=app_id,
        workflow_id=workflow.id, workflow_version_id=version.id,
        run_id=run.id, recipient_id="recip-A", current_node_id="n1",
        status="running", payload={},
    )
    db_session.add(state)
    await db_session.flush()

    ctx = NodeContext(
        db=db_session,
        tenant_id=tenant_id, app_id=app_id,
        workflow_id=workflow.id, workflow_version_id=version.id,
        run_id=run.id, node_step_id=node_step.id, current_node_id="n1",
        services=ServiceRegistry(),
        job_id=None,
    )
    dispatches = [
        ActionDispatch(
            recipient_id="recip-A", channel="system", action_type="test_action",
            idempotency_key=f"idem-A-1-{uuid.uuid4().hex[:8]}", payload={"hello": "world"},
        )
    ]
    results = await ctx.dispatch_actions(dispatches)
    assert len(results) == 1
    assert results[0].status == "pending"

    rows = await db_session.execute(
        select(WorkflowRunRecipientAction).where(
            WorkflowRunRecipientAction.run_id == run.id
        )
    )
    actions = rows.scalars().all()
    assert len(actions) == 1
    assert actions[0].recipient_id == "recip-A"


@pytest.mark.asyncio
async def test_dispatch_actions_idempotent_on_duplicate_key(db_session, seed_full_run):
    """Second dispatch with same idempotency_key is a no-op (returns existing row)."""
    run, version, workflow, node_step, tenant_id, app_id = seed_full_run
    state = WorkflowRunRecipientState(
        id=uuid.uuid4(), tenant_id=tenant_id, app_id=app_id,
        workflow_id=workflow.id, workflow_version_id=version.id,
        run_id=run.id, recipient_id="recip-B", current_node_id="n1",
        status="running", payload={},
    )
    db_session.add(state)
    await db_session.flush()

    ctx = NodeContext(
        db=db_session, tenant_id=tenant_id, app_id=app_id,
        workflow_id=workflow.id, workflow_version_id=version.id,
        run_id=run.id, node_step_id=node_step.id, current_node_id="n1",
        services=ServiceRegistry(), job_id=None,
    )
    d = ActionDispatch(
        recipient_id="recip-B", channel="system", action_type="test_action",
        idempotency_key=f"idem-B-1-{uuid.uuid4().hex[:8]}", payload={"x": 1},
    )
    r1 = await ctx.dispatch_actions([d])
    r2 = await ctx.dispatch_actions([d])
    assert r1[0].action_id == r2[0].action_id

    rows = await db_session.execute(
        select(WorkflowRunRecipientAction).where(
            WorkflowRunRecipientAction.run_id == run.id
        )
    )
    assert len(rows.scalars().all()) == 1


@pytest.mark.asyncio
async def test_fresh_run_resends_same_run_retry_dedupes(db_session, seed_full_run):
    """Two runs of one version → two action rows (re-send). Same run, same
    key → one row (retry deduped). Exercises the run_id-scoped idempotency key
    against the real (tenant_id, recipient_id, idempotency_key) constraint.

    The first dispatch is settled to ``success`` before the second run dials,
    mirroring the handler (which calls update_action_result right after the
    provider call) — that clears the pending-only ``no_double_dispatch`` guard,
    which exists to block two simultaneously-open dispatches, not a re-run."""
    import uuid as _uuid
    from datetime import datetime as _dt, timezone as _tz

    from app.models.orchestration import WorkflowRun, WorkflowRunNodeStep

    run_a, version, workflow, step_a, tenant_id, app_id = seed_full_run

    # A second run of the SAME workflow + version (a second Run Now).
    run_b = WorkflowRun(
        id=_uuid.uuid4(), tenant_id=tenant_id, app_id=app_id,
        workflow_id=workflow.id, workflow_version_id=version.id,
        triggered_by="manual", status="running",
    )
    db_session.add(run_b)
    await db_session.flush()
    step_b = WorkflowRunNodeStep(
        id=_uuid.uuid4(), tenant_id=tenant_id, app_id=app_id,
        workflow_id=workflow.id, workflow_version_id=version.id,
        run_id=run_b.id, node_id="n1", node_type="source.event_trigger",
        status="completed", started_at=_dt.now(_tz.utc), completed_at=_dt.now(_tz.utc),
    )
    db_session.add(step_b)
    for run in (run_a, run_b):
        db_session.add(WorkflowRunRecipientState(
            id=_uuid.uuid4(), tenant_id=tenant_id, app_id=app_id,
            workflow_id=workflow.id, workflow_version_id=version.id,
            run_id=run.id, recipient_id="recip-RR", current_node_id="n1",
            status="running", payload={},
        ))
    await db_session.flush()

    def _ctx(run, step):
        return NodeContext(
            db=db_session, tenant_id=tenant_id, app_id=app_id,
            workflow_id=workflow.id, workflow_version_id=version.id,
            run_id=run.id, node_step_id=step.id, current_node_id="n1",
            services=ServiceRegistry(), job_id=None,
        )

    ctx_a, ctx_b = _ctx(run_a, step_a), _ctx(run_b, step_b)

    def _dispatch_for(ctx):
        return ActionDispatch(
            recipient_id="recip-RR", channel="whatsapp", action_type="wa_dispatched",
            idempotency_key=ctx.idempotency_key("recip-RR", "whatsapp_template", "welcome_v1"),
            payload={"contact": "+918888888888"},
        )

    res_a = await ctx_a.dispatch_actions([_dispatch_for(ctx_a)])
    # Same-run retry BEFORE settling: identical key, ON CONFLICT DO NOTHING → no new row.
    res_a_retry = await ctx_a.dispatch_actions([_dispatch_for(ctx_a)])
    assert res_a[0].action_id == res_a_retry[0].action_id
    # Settle the first dispatch, as the handler does post provider-call.
    await ctx_a.update_action_result(res_a[0].action_id, status="success")
    # Fresh run now re-sends: a new run_id → new key → a second row.
    await ctx_b.dispatch_actions([_dispatch_for(ctx_b)])

    rows = (await db_session.execute(
        select(WorkflowRunRecipientAction.run_id).where(
            WorkflowRunRecipientAction.recipient_id == "recip-RR",
            WorkflowRunRecipientAction.tenant_id == tenant_id,
        )
    )).scalars().all()
    assert sorted(map(str, rows)) == sorted([str(run_a.id), str(run_b.id)])


@pytest.mark.asyncio
async def test_set_recipient_state_updates_pointer(db_session, seed_full_run):
    run, version, workflow, node_step, tenant_id, app_id = seed_full_run
    state = WorkflowRunRecipientState(
        id=uuid.uuid4(), tenant_id=tenant_id, app_id=app_id,
        workflow_id=workflow.id, workflow_version_id=version.id,
        run_id=run.id, recipient_id="recip-C", current_node_id="n1",
        status="running", payload={},
    )
    db_session.add(state)
    await db_session.flush()

    wakeup = datetime.now(timezone.utc)
    ctx = NodeContext(
        db=db_session, tenant_id=tenant_id, app_id=app_id,
        workflow_id=workflow.id, workflow_version_id=version.id,
        run_id=run.id, node_step_id=node_step.id, current_node_id="n1",
        services=ServiceRegistry(), job_id=None,
    )
    await ctx.set_recipient_state("recip-C", status="waiting", wakeup_at=wakeup)
    await db_session.refresh(state)
    assert state.status == "waiting"
    assert state.wakeup_at is not None


def test_idempotency_key_deterministic():
    run = uuid.uuid4()
    ctx = NodeContext(
        db=None, tenant_id=uuid.uuid4(), app_id="x",  # type: ignore[arg-type]
        workflow_id=uuid.uuid4(), workflow_version_id=uuid.UUID(int=1),
        run_id=run, node_step_id=uuid.uuid4(), current_node_id="node-A",
        services=ServiceRegistry(), job_id=None,
    )
    k1 = ctx.idempotency_key("recip-X", "attempt-1")
    k2 = ctx.idempotency_key("recip-X", "attempt-1")
    assert k1 == k2
    k3 = ctx.idempotency_key("recip-X", "attempt-2")
    assert k1 != k3


def _ctx_for_run(run_id: uuid.UUID, version_id: uuid.UUID) -> NodeContext:
    return NodeContext(
        db=None, tenant_id=uuid.uuid4(), app_id="x",  # type: ignore[arg-type]
        workflow_id=uuid.uuid4(), workflow_version_id=version_id,
        run_id=run_id, node_step_id=uuid.uuid4(), current_node_id="node-A",
        services=ServiceRegistry(), job_id=None,
    )


def test_idempotency_key_scoped_to_run_not_version():
    # Two Run Nows of the SAME published version → two run ids → two keys, so
    # each run sends. A retry inside one run keeps the run id → same key → dedupe.
    version = uuid.UUID(int=7)
    run_a, run_b = uuid.uuid4(), uuid.uuid4()
    ctx_a = _ctx_for_run(run_a, version)
    ctx_b = _ctx_for_run(run_b, version)
    key_a = ctx_a.idempotency_key("recip-X", "whatsapp_template", "welcome_v1")
    key_b = ctx_b.idempotency_key("recip-X", "whatsapp_template", "welcome_v1")
    assert key_a != key_b
    # Same run id, same parts → identical (a retry does not re-send).
    assert key_a == _ctx_for_run(run_a, version).idempotency_key(
        "recip-X", "whatsapp_template", "welcome_v1"
    )
    # Two runs of two DIFFERENT versions of the same workflow also differ —
    # but that already held; the regression is same-version, different-run.
    key_a_v2 = _ctx_for_run(run_a, uuid.UUID(int=99)).idempotency_key(
        "recip-X", "whatsapp_template", "welcome_v1"
    )
    assert key_a == key_a_v2  # key no longer varies with version

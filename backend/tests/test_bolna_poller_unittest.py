"""Phase 13 / E.3 — bolna_poller.run_once happy paths + idempotency.

Mocks at the BolnaService / BolnaBatchService boundary so the test
doesn't have to spin up the upstream HTTP layer. Asserts:

- Open single-call actions → ``GET /executions/{id}`` once each;
  terminal events trigger the reconciler and flip ``provider_terminal``.
- Open batch actions → one batch fetch per ``batch_id`` covers every
  recipient; per-execution status is matched back to the right action
  via the ``recipient_id`` user_data column.
- A second sweep over already-reconciled rows does nothing.
- Non-terminal upstream events are skipped (the row stays open).
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.models.orchestration import WorkflowRunRecipientAction
from app.services.orchestration.dispatch import bolna_poller


# ─── Index helper (pure function) ──────────────────────────────────────


def test_index_executions_keys_by_recipient_and_execution():
    rows = [
        {
            "execution_id": "ex-A",
            "status": "completed",
            "context_details": {"recipient_data": {"recipient_id": "L-1"}},
        },
        {"execution_id": "ex-B", "status": "no-answer"},
    ]
    idx = bolna_poller._index_executions(rows)
    assert idx["recipient:L-1"]["execution_id"] == "ex-A"
    assert idx["execution:ex-A"]["execution_id"] == "ex-A"
    assert idx["execution:ex-B"]["status"] == "no-answer"


# ─── End-to-end with a fake Bolna service ──────────────────────────────


class _FakeBolna:
    def __init__(self, executions: dict[str, dict[str, Any]]) -> None:
        self._executions = executions
        self.calls: list[str] = []

    async def get_execution(self, *, execution_id: str) -> dict[str, Any]:
        self.calls.append(execution_id)
        return self._executions[execution_id]


class _FakeBolnaBatch:
    def __init__(self, *, batch_id: str, executions: list[dict[str, Any]]) -> None:
        self._batch_id = batch_id
        self._executions = executions
        self.calls: list[tuple[str, int]] = []

    async def list_batch_executions(
        self, batch_id: str, *, page: int = 1, page_size: int = 100,
    ) -> dict[str, Any]:
        self.calls.append((batch_id, page))
        if batch_id != self._batch_id:
            return {"executions": [], "page": page, "total": 0}
        return {
            "executions": self._executions,
            "page": page,
            "total": len(self._executions),
            "page_size": page_size,
        }


def _seed_open_action(
    db, *, run, version, workflow, node_step, tenant_id, app_id,
    recipient_id: str, execution_id: str | None = None,
    batch_id: str | None = None,
) -> WorkflowRunRecipientAction:
    action = WorkflowRunRecipientAction(
        id=uuid.uuid4(), tenant_id=tenant_id, app_id=app_id,
        workflow_id=workflow.id, workflow_version_id=version.id,
        run_id=run.id, node_step_id=node_step.id, recipient_id=recipient_id,
        channel="bolna", action_type="bolna_queued", status="success",
        idempotency_key=f"bk-{uuid.uuid4().hex[:8]}",
        payload={}, response={"execution_id": execution_id, "batch_id": batch_id},
        bolna_execution_id=execution_id,
        bolna_batch_id=batch_id,
        provider_terminal=False,
    )
    db.add(action)
    return action


@pytest.fixture
def _fake_connection(monkeypatch):
    """Skip the connection_config lookup so the poller stays a pure
    integration of the action table + service mocks."""
    async def _fake(_db, *, action):
        return uuid.uuid4(), {
            "base_url": "https://api.bolna.ai",
            "api_key": "k",
        }

    monkeypatch.setattr(bolna_poller, "_connection_config", _fake)


@pytest.mark.asyncio
async def test_run_once_reconciles_single_terminal_executions(
    db_session, seed_full_run, monkeypatch, _fake_connection,
):
    run, version, workflow, node_step, tenant_id, app_id = seed_full_run

    a = _seed_open_action(
        db_session, run=run, version=version, workflow=workflow, node_step=node_step,
        tenant_id=tenant_id, app_id=app_id,
        recipient_id="L-1", execution_id="ex-1",
    )
    b = _seed_open_action(
        db_session, run=run, version=version, workflow=workflow, node_step=node_step,
        tenant_id=tenant_id, app_id=app_id,
        recipient_id="L-2", execution_id="ex-2",
    )
    await db_session.flush()

    fake_service = _FakeBolna({
        "ex-1": {"execution_id": "ex-1", "status": "completed",
                  "status_reason": "answered"},
        "ex-2": {"execution_id": "ex-2", "status": "in-progress"},  # non-terminal → skip
    })

    def _factory(**_kwargs):
        return fake_service

    from app.services.orchestration.integrations import bolna as bolna_mod
    monkeypatch.setattr(bolna_mod, "BolnaService", _factory)

    stats = await bolna_poller.run_once(db_session)

    assert stats.singles_polled == 2
    assert stats.events_reconciled == 1
    assert sorted(fake_service.calls) == ["ex-1", "ex-2"]

    await db_session.refresh(a)
    await db_session.refresh(b)
    assert a.provider_terminal is True
    assert a.provider_status == "completed"
    assert b.provider_terminal is False  # in-progress kept open


@pytest.mark.asyncio
async def test_run_once_reconciles_batch_executions(
    db_session, seed_full_run, monkeypatch, _fake_connection,
):
    run, version, workflow, node_step, tenant_id, app_id = seed_full_run

    a = _seed_open_action(
        db_session, run=run, version=version, workflow=workflow, node_step=node_step,
        tenant_id=tenant_id, app_id=app_id,
        recipient_id="L-A", batch_id="b-1",
    )
    b = _seed_open_action(
        db_session, run=run, version=version, workflow=workflow, node_step=node_step,
        tenant_id=tenant_id, app_id=app_id,
        recipient_id="L-B", batch_id="b-1",
    )
    await db_session.flush()

    fake_batch = _FakeBolnaBatch(
        batch_id="b-1",
        executions=[
            {
                "execution_id": "ex-aa",
                "status": "completed",
                "status_reason": "answered",
                "context_details": {"recipient_data": {"recipient_id": "L-A"}},
            },
            {
                "execution_id": "ex-bb",
                "status": "no-answer",
                "context_details": {"recipient_data": {"recipient_id": "L-B"}},
            },
        ],
    )

    def _factory(**_kwargs):
        return fake_batch

    from app.services.orchestration.integrations import bolna_batch as bb_mod
    monkeypatch.setattr(bb_mod, "BolnaBatchService", _factory)

    stats = await bolna_poller.run_once(db_session)

    assert stats.batches_polled == 1
    assert stats.events_reconciled == 2
    # Single batch fetch covers both recipients.
    assert fake_batch.calls == [("b-1", 1)]

    await db_session.refresh(a)
    await db_session.refresh(b)
    assert a.provider_terminal is True
    assert a.provider_status == "completed"
    assert b.provider_terminal is True
    assert b.provider_status == "no-answer"


@pytest.mark.asyncio
async def test_run_once_idempotent_on_second_sweep(
    db_session, seed_full_run, monkeypatch, _fake_connection,
):
    """A second sweep over already-reconciled rows must not re-call the
    upstream — the open-rows query filters by provider_terminal=FALSE."""
    run, version, workflow, node_step, tenant_id, app_id = seed_full_run

    _seed_open_action(
        db_session, run=run, version=version, workflow=workflow, node_step=node_step,
        tenant_id=tenant_id, app_id=app_id,
        recipient_id="L-once", execution_id="ex-once",
    )
    await db_session.flush()

    fake_service = _FakeBolna({
        "ex-once": {"execution_id": "ex-once", "status": "completed",
                     "status_reason": "answered"},
    })

    def _factory(**_kwargs):
        return fake_service

    from app.services.orchestration.integrations import bolna as bolna_mod
    monkeypatch.setattr(bolna_mod, "BolnaService", _factory)

    first = await bolna_poller.run_once(db_session)
    assert first.events_reconciled == 1
    second = await bolna_poller.run_once(db_session)
    assert second.actions_scanned == 0
    assert second.events_reconciled == 0
    # Upstream was hit exactly once.
    assert fake_service.calls == ["ex-once"]

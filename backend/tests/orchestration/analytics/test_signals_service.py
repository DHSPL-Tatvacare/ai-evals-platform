"""Orchestration signals-service tests — LLM patched, never called live."""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.constants import SYSTEM_TENANT_ID
from app.models.orchestration_signal import OrchestrationSignalSnapshot
from app.services.orchestration.analytics import signals_service
from app.services.orchestration.analytics.outcomes import EngagementBucket


@pytest.mark.asyncio
async def test_build_orchestration_signal_input_aggregates(db_session, seed_orchestration_run):
    app_id = f"sig-input-{uuid.uuid4().hex[:8]}"
    await seed_orchestration_run(
        app_id=app_id,
        recipients=[
            {"recipient_id": "a", "bucket": EngagementBucket.positive.value, "cost": "0.10"},
            {"recipient_id": "b", "bucket": EngagementBucket.reached.value, "cost": "0.05"},
            {"recipient_id": "c", "bucket": EngagementBucket.failed.value, "cost": "0.00"},
        ],
    )
    payload = await signals_service.build_orchestration_signal_input(
        db_session, SYSTEM_TENANT_ID, app_id
    )
    assert payload["overview"]["recipients"] == 3
    assert payload["overview"]["positive"] == 1
    assert "channel" in payload["breakdowns"]


@pytest.mark.asyncio
async def test_generate_orchestration_signals_writes_one_row(
    db_session, seed_orchestration_run, monkeypatch
):
    app_id = f"sig-gen-{uuid.uuid4().hex[:8]}"
    await seed_orchestration_run(
        app_id=app_id,
        recipients=[
            {"recipient_id": "a", "bucket": EngagementBucket.positive.value, "cost": "0.10"},
            {"recipient_id": "b", "bucket": EngagementBucket.no_response.value, "cost": "0.05"},
        ],
    )

    fixture_result = {
        "signals": [
            {
                "severity": "warning",
                "title": "Low reach",
                "detail": "Half the cohort did not respond.",
                "metric": {"label": "No-response", "value": "1"},
            }
        ]
    }

    async def _fake_llm(db, tenant_id, app_id_, signal_input, job_id=None):
        return fixture_result, "fake-model"

    monkeypatch.setattr(signals_service, "_run_signal_llm", _fake_llm)

    snapshot = await signals_service.generate_orchestration_signals(
        db_session, SYSTEM_TENANT_ID, app_id, job_id=uuid.uuid4()
    )
    assert snapshot is not None
    await db_session.flush()

    rows = (
        await db_session.execute(
            select(OrchestrationSignalSnapshot).where(
                OrchestrationSignalSnapshot.tenant_id == SYSTEM_TENANT_ID,
                OrchestrationSignalSnapshot.app_id == app_id,
            )
        )
    ).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.model == "fake-model"
    assert len(row.signals) == 1
    assert row.signals[0]["severity"] == "warning"
    assert row.signals[0]["title"] == "Low reach"
    assert row.signals[0]["metric"] == {"label": "No-response", "value": "1"}


@pytest.mark.asyncio
async def test_generate_orchestration_signals_skips_empty_window(
    db_session, monkeypatch
):
    app_id = f"sig-empty-{uuid.uuid4().hex[:8]}"

    async def _fail_llm(*a, **k):
        raise AssertionError("LLM must not be called for an empty window")

    monkeypatch.setattr(signals_service, "_run_signal_llm", _fail_llm)

    snapshot = await signals_service.generate_orchestration_signals(
        db_session, SYSTEM_TENANT_ID, app_id, job_id=uuid.uuid4()
    )
    assert snapshot is None


def test_generate_orchestration_signals_job_registered():
    from app.services.job_worker import JOB_HANDLERS, required_permissions_for_job

    assert "generate-orchestration-signals" in JOB_HANDLERS
    assert required_permissions_for_job("generate-orchestration-signals") == (
        "orchestration:manage",
    )

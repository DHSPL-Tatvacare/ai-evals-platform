"""Live-DB tests for window inclusion, status-based in-flight, NULL-bucket recovery, and trend."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.orchestration.analytics import read_service
from app.services.orchestration.analytics.read_service import (
    WORKFLOW_TENANT_ALL,
    _action_type_to_bucket_map,
)


def test_registry_map_merges_vendor_action_types():
    # The map is assembled from the adapter registry — no vendor literals in read_service.
    mapping = _action_type_to_bucket_map()
    assert mapping["bolna_answered"] == "positive"
    assert mapping["wa_replied"] == "positive"
    assert mapping["wa_read"] == "reached"


@pytest.mark.asyncio
async def test_same_day_run_included_with_exclusive_next_midnight(
    db_session, seed_orchestration_run
):
    # A run started today must appear when date_to is the exclusive next-midnight bound.
    now = datetime.now(timezone.utc)
    seeded = await seed_orchestration_run(
        recipients=[{"recipient_id": "a", "bucket": "positive"}],
        started_at=now,
    )
    today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    result = await read_service.overview(
        db_session,
        tenant_id=seeded["tenant_id"],
        app_id=seeded["app_id"],
        scope_clause=WORKFLOW_TENANT_ALL(seeded["tenant_id"]),
        date_from=today_midnight - timedelta(days=1),
        date_to=today_midnight + timedelta(days=1),
    )
    assert result.runs == 1
    assert result.positive == 1


@pytest.mark.asyncio
async def test_in_flight_counts_run_with_null_started_at(
    db_session, seed_orchestration_run
):
    # A running run with started_at IS NULL is dropped by any windowed predicate;
    # the status-based in-flight count must still see it.
    seeded = await seed_orchestration_run(
        recipients=[{"recipient_id": "a", "bucket": "in_flight"}],
        run_status="running",
        started_at=None,
    )
    result = await read_service.overview(
        db_session,
        tenant_id=seeded["tenant_id"],
        app_id=seeded["app_id"],
        scope_clause=WORKFLOW_TENANT_ALL(seeded["tenant_id"]),
        date_from=datetime.now(timezone.utc) - timedelta(days=1),
        date_to=datetime.now(timezone.utc) + timedelta(days=1),
    )
    assert result.in_flight_runs == 1


@pytest.mark.asyncio
async def test_null_outcome_bucket_recovered_from_action_type(
    db_session, seed_orchestration_run
):
    # Child rows written before the outcome_bucket column have NULL buckets; the
    # action_type-derived bucket must recover them in the funnel.
    seeded = await seed_orchestration_run(
        recipients=[
            {
                "recipient_id": "wa1",
                "channel": "whatsapp",
                "events": [
                    {"action_type": "wa_delivered", "bucket": None},
                    {"action_type": "wa_replied", "bucket": None},
                ],
            },
        ],
    )
    result = await read_service.overview(
        db_session,
        tenant_id=seeded["tenant_id"],
        app_id=seeded["app_id"],
        scope_clause=WORKFLOW_TENANT_ALL(seeded["tenant_id"]),
        date_from=None,
        date_to=None,
    )
    assert result.recipients == 1
    # wa_replied derives positive, the most-advanced bucket.
    assert result.positive == 1
    assert result.reached == 0


@pytest.mark.asyncio
async def test_trend_groups_by_day(db_session, seed_orchestration_run):
    base = datetime(2026, 5, 20, 9, 0, tzinfo=timezone.utc)
    s1 = await seed_orchestration_run(
        recipients=[{"recipient_id": "a", "bucket": "positive"}],
        started_at=base,
    )
    await seed_orchestration_run(
        recipients=[{"recipient_id": "b", "bucket": "failed"}],
        started_at=base + timedelta(days=1),
        tenant_id=s1["tenant_id"], app_id=s1["app_id"],
    )
    points = await read_service.trend(
        db_session,
        tenant_id=s1["tenant_id"],
        app_id=s1["app_id"],
        scope_clause=WORKFLOW_TENANT_ALL(s1["tenant_id"]),
        date_from=base - timedelta(days=1),
        date_to=base + timedelta(days=3),
    )
    by_day = {p.date.date(): p for p in points}
    assert by_day[base.date()].positive == 1
    assert by_day[(base + timedelta(days=1)).date()].failed == 1


@pytest.mark.asyncio
async def test_overview_cohort_total_counts_full_cohort(
    db_session, seed_orchestration_run
):
    # cohort_total sums cohort_size_at_entry per run, independent of action rows.
    seeded = await seed_orchestration_run(
        recipients=[
            {"recipient_id": "a", "bucket": "positive"},
            {"recipient_id": "b", "bucket": "failed"},
        ],
    )
    result = await read_service.overview(
        db_session,
        tenant_id=seeded["tenant_id"],
        app_id=seeded["app_id"],
        scope_clause=WORKFLOW_TENANT_ALL(seeded["tenant_id"]),
        date_from=None,
        date_to=None,
    )
    assert result.cohort_total == 2

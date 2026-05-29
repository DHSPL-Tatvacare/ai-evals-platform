"""Breakdown / runs / run-detail read-query tests against live Postgres."""

import uuid

import pytest

from app.services.orchestration.analytics import read_service
from app.services.orchestration.analytics.read_service import WORKFLOW_TENANT_ALL


def _scope(seeded):
    return dict(
        tenant_id=seeded["tenant_id"],
        app_id=seeded["app_id"],
        scope_clause=WORKFLOW_TENANT_ALL(seeded["tenant_id"]),
        date_from=None,
        date_to=None,
    )


@pytest.mark.asyncio
async def test_channel_breakdown(db_session, seed_orchestration_run):
    seeded = await seed_orchestration_run(
        recipients=[
            {"recipient_id": "a", "bucket": "positive", "channel": "voice"},
            {"recipient_id": "b", "bucket": "failed", "channel": "voice"},
            {"recipient_id": "c", "bucket": "positive", "channel": "whatsapp"},
        ],
    )
    rows = await read_service.breakdown(db_session, dimension="channel", **_scope(seeded))
    by_label = {r.label: r for r in rows}
    assert set(by_label) == {"voice", "whatsapp"}
    assert by_label["voice"].positive == 1
    assert by_label["voice"].failed == 1
    assert by_label["whatsapp"].positive == 1


@pytest.mark.asyncio
async def test_channel_breakdown_collapses_whatsapp_lifecycle(
    db_session, seed_orchestration_run
):
    # One WhatsApp recipient with a parent dispatch + 3 event children. dispatched
    # must count the single parent dispatch row (1), not all 4 action rows; and the
    # recipient's most-advanced bucket (positive) is counted once.
    seeded = await seed_orchestration_run(
        recipients=[
            {
                "recipient_id": "wa1",
                "channel": "whatsapp",
                "events": [
                    {"action_type": "wa_delivered", "bucket": "reached"},
                    {"action_type": "wa_read", "bucket": "reached"},
                    {"action_type": "wa_replied", "bucket": "positive"},
                ],
            },
        ],
    )
    rows = await read_service.breakdown(db_session, dimension="channel", **_scope(seeded))
    by_label = {r.label: r for r in rows}
    wa = by_label["whatsapp"]
    assert wa.recipients == 1
    assert wa.dispatched == 1
    assert wa.positive == 1
    assert wa.reached == 0


@pytest.mark.asyncio
async def test_campaign_breakdown(db_session, seed_orchestration_run):
    seeded = await seed_orchestration_run(
        workflow_name="Campaign One",
        recipients=[
            {"recipient_id": "a", "bucket": "positive"},
            {"recipient_id": "b", "bucket": "no_response"},
        ],
    )
    rows = await read_service.breakdown(db_session, dimension="campaign", **_scope(seeded))
    labels = {r.label for r in rows}
    assert "Campaign One" in labels


@pytest.mark.asyncio
async def test_runs_list(db_session, seed_orchestration_run):
    seeded = await seed_orchestration_run(
        workflow_name="Runs WF",
        recipients=[
            {"recipient_id": "a", "bucket": "positive"},
            {"recipient_id": "b", "bucket": "reached"},
            {"recipient_id": "c", "bucket": "failed"},
        ],
    )
    result = await read_service.runs(db_session, page=1, page_size=20, **_scope(seeded))
    assert result.total >= 1
    run_row = next(r for r in result.rows if r.run_id == seeded["run_id"])
    assert run_row.workflow_name == "Runs WF"
    assert run_row.positive == 1
    # reached + positive both count as "reached" (engaged) in the run row.
    assert run_row.reached >= 1


@pytest.mark.asyncio
async def test_run_detail(db_session, seed_orchestration_run):
    seeded = await seed_orchestration_run(
        recipients=[
            {"recipient_id": "a", "bucket": "positive"},
            {"recipient_id": "b", "bucket": "failed"},
        ],
    )
    detail = await read_service.run_detail(
        db_session,
        run_id=seeded["run_id"],
        tenant_id=seeded["tenant_id"],
        scope_clause=WORKFLOW_TENANT_ALL(seeded["tenant_id"]),
        page=1,
        page_size=50,
    )
    assert detail.buckets.positive == 1
    assert detail.buckets.failed == 1
    assert any(n.node_id == seeded["node_id"] for n in detail.node_steps)
    assert len(detail.actions) == 2
    assert detail.actions_total == 2


@pytest.mark.asyncio
async def test_run_detail_unknown_run_returns_none(db_session, seed_orchestration_run):
    seeded = await seed_orchestration_run(
        recipients=[{"recipient_id": "a", "bucket": "positive"}],
    )
    detail = await read_service.run_detail(
        db_session,
        run_id=uuid.uuid4(),
        tenant_id=seeded["tenant_id"],
        scope_clause=WORKFLOW_TENANT_ALL(seeded["tenant_id"]),
        page=1,
        page_size=50,
    )
    assert detail is None

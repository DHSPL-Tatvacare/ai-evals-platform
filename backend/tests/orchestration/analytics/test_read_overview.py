"""Overview read-query aggregate tests against live Postgres."""

import pytest

from app.services.orchestration.analytics import read_service
from app.services.orchestration.analytics.read_service import WORKFLOW_TENANT_ALL


@pytest.mark.asyncio
async def test_overview_kpis(db_session, seed_orchestration_run):
    seeded = await seed_orchestration_run(
        recipients=[
            {"recipient_id": "a", "bucket": "positive"},
            {"recipient_id": "b", "bucket": "no_response"},
            {"recipient_id": "c", "bucket": "failed"},
        ],
    )

    result = read_service.overview(
        db_session,
        tenant_id=seeded["tenant_id"],
        app_id=seeded["app_id"],
        scope_clause=WORKFLOW_TENANT_ALL(seeded["tenant_id"]),
        date_from=None,
        date_to=None,
    )
    result = await result if hasattr(result, "__await__") else result

    assert result.runs == 1
    assert result.recipients == 3
    assert result.positive == 1
    assert result.failed == 1


@pytest.mark.asyncio
async def test_overview_collapses_whatsapp_lifecycle_to_one_bucket(
    db_session, seed_orchestration_run
):
    # One WhatsApp recipient progresses delivered -> read -> replied. The adapter
    # persists a parent dispatch row + three child event rows. The most-advanced
    # outcome is positive (replied), so the recipient must count as positive=1,
    # reached=0 — not reached=2, positive=1.
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

    result = await read_service.overview(
        db_session,
        tenant_id=seeded["tenant_id"],
        app_id=seeded["app_id"],
        scope_clause=WORKFLOW_TENANT_ALL(seeded["tenant_id"]),
        date_from=None,
        date_to=None,
    )

    assert result.recipients == 1
    assert result.positive == 1
    assert result.reached == 0
    # buckets partition recipients: sum of terminal buckets never exceeds recipients.
    assert (
        result.positive + result.reached + result.no_response + result.failed
        <= result.recipients
    )
    # Connected% = (reached + positive) / recipients must be <= 100%.
    connected = (result.reached + result.positive) / result.recipients
    assert connected == 1.0


@pytest.mark.asyncio
async def test_overview_mixed_whatsapp_and_voice_partition(
    db_session, seed_orchestration_run
):
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
            {"recipient_id": "v1", "channel": "voice", "bucket": "positive"},
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

    assert result.recipients == 2
    assert result.positive == 2
    assert result.reached == 0
    assert (
        result.positive + result.reached + result.no_response + result.failed
        <= result.recipients
    )

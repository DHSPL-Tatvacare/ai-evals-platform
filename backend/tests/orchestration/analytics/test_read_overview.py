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

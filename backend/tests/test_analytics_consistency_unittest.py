from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.services.analytics import submit_analytics_job
from app.services.analytics.consistency import (
    build_analytics_consistency_summary,
    enqueue_missing_analytics_jobs,
)


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _ScalarsResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return SimpleNamespace(all=lambda: self._items)


@pytest.mark.asyncio
async def test_submit_analytics_job_includes_identity_params():
    db = AsyncMock()
    db.add = Mock()
    run_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()

    await submit_analytics_job(
        db=db,
        run_id=run_id,
        app_id='kaira-bot',
        tenant_id=tenant_id,
        user_id=user_id,
    )

    job = db.add.call_args.args[0]
    assert job.params == {
        'run_id': str(run_id),
        'app_id': 'kaira-bot',
        'tenant_id': str(tenant_id),
        'user_id': str(user_id),
    }


@pytest.mark.asyncio
async def test_build_analytics_consistency_summary_formats_missing_runs():
    db = AsyncMock()
    db.scalar.side_effect = [5, 4]
    db.execute.side_effect = [
        _RowsResult([('cancelled', 2), ('completed', 3)]),
        _RowsResult([('cancelled', 1)]),
    ]
    missing_run = SimpleNamespace(
        id=uuid.uuid4(),
        app_id='kaira-bot',
        eval_type='custom',
        status='cancelled',
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        completed_at=datetime(2026, 1, 1, 0, 1, tzinfo=timezone.utc),
    )

    with patch(
        'app.services.analytics.consistency.list_runs_missing_analytics',
        new=AsyncMock(return_value=[missing_run]),
    ):
        payload = await build_analytics_consistency_summary(
            db,
            tenant_id=uuid.uuid4(),
            app_id='kaira-bot',
            limit=25,
        )

    assert payload['eligibleRunCount'] == 5
    assert payload['analyticsRunFactCount'] == 4
    assert payload['missingRunFactCount'] == 1
    assert payload['missingByStatus'] == {'cancelled': 1}
    assert payload['missingRuns'][0]['status'] == 'cancelled'


@pytest.mark.asyncio
async def test_enqueue_missing_analytics_jobs_skips_active_duplicates():
    db = AsyncMock()
    db.execute.return_value = _ScalarsResult([
        SimpleNamespace(params={'run_id': 'skip-me'}),
    ])
    run_to_queue = SimpleNamespace(
        id=uuid.uuid4(),
        app_id='kaira-bot',
        eval_type='custom',
        status='completed',
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
    )
    skipped_run = SimpleNamespace(
        id='skip-me',
        app_id='kaira-bot',
        eval_type='custom',
        status='cancelled',
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
    )

    with patch(
        'app.services.analytics.consistency.list_runs_missing_analytics',
        new=AsyncMock(return_value=[run_to_queue, skipped_run]),
    ), patch(
        'app.services.analytics.consistency.submit_analytics_job',
        new=AsyncMock(),
    ) as submit_mock:
        payload = await enqueue_missing_analytics_jobs(
            db,
            tenant_id=uuid.uuid4(),
            app_id='kaira-bot',
            limit=100,
        )

    assert payload['queuedCount'] == 1
    assert payload['skippedAlreadyQueuedCount'] == 1
    assert payload['queuedRuns'][0]['runId'] == str(run_to_queue.id)
    assert payload['skippedRunIds'] == ['skip-me']
    assert submit_mock.await_count == 1

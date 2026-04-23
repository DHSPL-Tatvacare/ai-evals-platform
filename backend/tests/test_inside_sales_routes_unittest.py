"""inside-sales route tests for refresh behavior.

The refresh endpoint is locked to the 7-day hot window. Any ``date_from`` /
``date_to`` sent by the client is ignored; older data is out of scope for the
mirror and is not fetched here. Tests pin this contract.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.auth import AuthContext
from app.models.job import Job
from app.routes import inside_sales as inside_sales_routes
from app.schemas.inside_sales import CollectionRefreshRequest


def _auth() -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email='test@example.com',
        role_id=uuid.uuid4(),
        is_owner=False,
        permissions=frozenset({'inside-sales:view'}),
        app_access=frozenset({'inside-sales'}),
    )


class _FakeSession:
    def __init__(self):
        self.added: list[Any] = []
        self.commits = 0
        self.refreshes: list[Any] = []

    def add(self, item: Any) -> None:
        self.added.append(item)

    async def commit(self) -> None:
        self.commits += 1

    async def refresh(self, item: Any) -> None:
        self.refreshes.append(item)


def _parse_dt(value: str) -> datetime:
    return datetime.strptime(value, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_refresh_collection_forces_seven_day_window_and_ignores_body_dates():
    """Regardless of body dates (even 30-day out-of-window), the job params
    must carry ``[now-7d, now]`` as a ``date_range`` sync. No incremental,
    no boundary helper."""
    auth = _auth()
    db = _FakeSession()
    body = CollectionRefreshRequest(
        date_from='2026-01-01 00:00:00',  # deliberately way out of window
        date_to='2026-02-01 00:00:00',
        event_codes='21,22',
    )

    response = await inside_sales_routes.refresh_collection(
        source_family='calls',
        body=body,
        auth=auth,
        db=db,
    )

    assert db.commits == 1
    assert len(db.added) == 1
    job = db.added[0]
    assert isinstance(job, Job)
    params = job.params or {}
    assert params['app_id'] == 'inside-sales'
    assert params['source_family'] == 'calls'
    assert params['sync_mode'] == 'date_range'
    assert params['is_scheduled_run'] is False
    assert params['event_codes'] == '21,22'

    date_from = _parse_dt(params['date_from'])
    date_to = _parse_dt(params['date_to'])
    now = datetime.now(timezone.utc)
    # Hot window = [now-7d, now], allow a minute of clock drift in the test.
    assert now - date_to <= timedelta(minutes=1)
    span = date_to - date_from
    assert timedelta(days=7) - timedelta(minutes=1) <= span <= timedelta(days=7) + timedelta(minutes=1)
    # Body dates should NOT have leaked through.
    assert params['date_from'] != '2026-01-01 00:00:00'
    assert params['date_to'] != '2026-02-01 00:00:00'

    assert response.source_family == 'calls'
    assert response.sync_mode == 'date_range'


@pytest.mark.asyncio
async def test_get_collection_status_returns_durable_freshness_signal():
    """The status route reads from ``source_sync_runs`` so the UI can render
    correctly after a page reload. Verify it wires the service output to the
    ``CollectionSyncStatus`` schema field-for-field."""
    auth = _auth()
    db = _FakeSession()
    completed_at = datetime(2026, 4, 23, 9, 0, 0, tzinfo=timezone.utc)
    started_at = datetime(2026, 4, 23, 9, 30, 0, tzinfo=timezone.utc)
    fake_status = {
        'lastSuccessAt': completed_at,
        'lastAttemptAt': started_at,
        'lastStatus': 'failed',
        'lastError': 'A transaction is already begun on this Session.',
        'syncInProgress': False,
    }

    with patch.object(
        inside_sales_routes,
        'get_collection_sync_status',
        new=AsyncMock(return_value=fake_status),
    ) as status_mock:
        resp = await inside_sales_routes.get_collection_status(
            source_family='leads',
            auth=auth,
            db=db,
        )

    status_mock.assert_awaited_once_with(
        db,
        tenant_id=auth.tenant_id,
        app_id='inside-sales',
        source_family='leads',
    )
    assert resp.last_success_at == completed_at
    assert resp.last_attempt_at == started_at
    assert resp.last_status == 'failed'
    assert resp.last_error == 'A transaction is already begun on this Session.'
    assert resp.sync_in_progress is False


@pytest.mark.asyncio
async def test_get_collection_status_rejects_unknown_family():
    auth = _auth()
    db = _FakeSession()
    import fastapi
    with pytest.raises(fastapi.HTTPException) as excinfo:
        await inside_sales_routes.get_collection_status(
            source_family='bogus',
            auth=auth,
            db=db,
        )
    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_refresh_collection_leads_family_omits_event_codes():
    auth = _auth()
    db = _FakeSession()
    body = CollectionRefreshRequest()

    response = await inside_sales_routes.refresh_collection(
        source_family='leads',
        body=body,
        auth=auth,
        db=db,
    )

    assert len(db.added) == 1
    job = db.added[0]
    params = job.params or {}
    assert params['source_family'] == 'leads'
    # Leads path never attaches event_codes.
    assert 'event_codes' not in params
    assert response.source_family == 'leads'

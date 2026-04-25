"""Jobs-route coverage checks for Inside Sales eval dependency chaining."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.auth import AuthContext
from app.routes.jobs import _maybe_chain_boundary_sync
from app.services.inside_sales_boundary import MirroredCoverageWindow


def _auth() -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email='eval@example.com',
        role_id=uuid.uuid4(),
        is_owner=False,
        permissions=frozenset({'evaluation:run'}),
        app_access=frozenset({'inside-sales'}),
    )


@pytest.mark.asyncio
async def test_specific_selection_skips_boundary_sync_lookup():
    auth = _auth()
    db = AsyncMock()

    with patch(
        'app.services.inside_sales_boundary.get_mirrored_coverage_window',
        new=AsyncMock(),
    ) as coverage_mock:
        result = await _maybe_chain_boundary_sync(
            db,
            auth=auth,
            job_params={
                'call_selection': {
                    'selection_mode': 'specific',
                    'date_from': '2026-04-01 00:00:00',
                    'date_to': '2026-04-05 23:59:59',
                }
            },
        )

    assert result is None
    coverage_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_eval_range_inside_coverage_does_not_chain_sync():
    auth = _auth()
    db = AsyncMock()
    mirrored = MirroredCoverageWindow(
        requested_from=datetime(2026, 4, 10, 0, 0, tzinfo=timezone.utc),
        requested_to=datetime(2026, 4, 12, 23, 59, 59, tzinfo=timezone.utc),
        available_from=datetime(2026, 4, 1, 0, 0, tzinfo=timezone.utc),
        available_to=datetime(2026, 4, 30, 23, 59, 59, tzinfo=timezone.utc),
        has_data=True,
        requires_sync=False,
    )

    with patch(
        'app.services.inside_sales_boundary.get_mirrored_coverage_window',
        new=AsyncMock(return_value=mirrored),
    ), patch(
        'app.services.inside_sales_boundary.find_or_enqueue_ondemand_sync',
        new=AsyncMock(),
    ) as enqueue_mock:
        result = await _maybe_chain_boundary_sync(
            db,
            auth=auth,
            job_params={
                'call_selection': {
                    'selection_mode': 'all',
                    'date_from': '2026-04-10 00:00:00',
                    'date_to': '2026-04-12 23:59:59',
                    'event_codes': '21,22',
                }
            },
        )

    assert result is None
    enqueue_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_eval_range_outside_coverage_chains_sync_job():
    auth = _auth()
    db = AsyncMock()
    mirrored = MirroredCoverageWindow(
        requested_from=datetime(2026, 4, 1, 0, 0, tzinfo=timezone.utc),
        requested_to=datetime(2026, 4, 5, 23, 59, 59, tzinfo=timezone.utc),
        available_from=datetime(2026, 4, 10, 0, 0, tzinfo=timezone.utc),
        available_to=datetime(2026, 4, 30, 23, 59, 59, tzinfo=timezone.utc),
        has_data=True,
        requires_sync=True,
    )
    queued_job = SimpleNamespace(id=uuid.uuid4())

    with patch(
        'app.services.inside_sales_boundary.get_mirrored_coverage_window',
        new=AsyncMock(return_value=mirrored),
    ), patch(
        'app.services.inside_sales_boundary.find_or_enqueue_ondemand_sync',
        new=AsyncMock(return_value=queued_job),
    ) as enqueue_mock:
        result = await _maybe_chain_boundary_sync(
            db,
            auth=auth,
            job_params={
                'call_selection': {
                    'selection_mode': 'all',
                    'date_from': '2026-04-01 00:00:00',
                    'date_to': '2026-04-05 23:59:59',
                    'source_family': 'calls',
                    'event_codes': '21,22',
                }
            },
        )

    assert result == queued_job.id
    enqueue_mock.assert_awaited_once()

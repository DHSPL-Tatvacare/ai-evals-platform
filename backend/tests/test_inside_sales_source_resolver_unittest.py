"""Tests for ``resolve_call_selection_from_source``.

Phase 4 LSQ ETL contract: when ``selection_mode="specific"``, the
resolver must bypass UI date / agent / status filters and match calls
by ``activity_id`` scoped to tenant + app. If any requested ID does
not resolve, the run fails loudly with
``SpecificCallSelectionMissingError`` instead of returning a shorter
list than the user asked for.
"""

from __future__ import annotations

import unittest
import uuid
from unittest.mock import AsyncMock, patch

from app.services.inside_sales_dataset_resolver import InsideSalesCallFilters
from app.services import inside_sales_source_resolver as resolver


class _FakeSession:
    async def execute(self, statement):  # pragma: no cover — patched
        raise AssertionError("execute() should be patched in each test")

    async def scalars(self, statement):  # pragma: no cover — patched
        raise AssertionError("scalars() should be patched in each test")


class SpecificSelectionBypassesDateWindowTests(unittest.IsolatedAsyncioTestCase):
    async def test_specific_mode_does_not_run_filtered_list_query(self):
        """When mode=specific, the resolver must skip the date-filtered
        listing query entirely and go straight to activity_id lookup."""
        fetch_mock = AsyncMock(return_value=[
            {"activityId": "A1", "durationSeconds": 30, "recordingUrl": "u1"},
            {"activityId": "A2", "durationSeconds": 30, "recordingUrl": "u2"},
        ])
        list_mock = AsyncMock()
        with patch.object(resolver, "_fetch_calls_by_activity_ids", new=fetch_mock), \
             patch.object(resolver, "list_calls_from_source", new=list_mock):
            result = await resolver.resolve_call_selection_from_source(
                InsideSalesCallFilters(
                    date_from="2026-04-24 00:00:00",
                    date_to="2026-04-24 23:59:59",
                ),
                selection_mode="specific",
                selected_call_ids=["A1", "A2"],
                sample_size=10,
                skip_evaluated=False,
                min_duration_seconds=None,
                tenant_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                db=_FakeSession(),  # type: ignore[arg-type]
            )
        list_mock.assert_not_awaited()
        fetch_mock.assert_awaited_once()
        self.assertEqual([r["activityId"] for r in result.records], ["A1", "A2"])

    async def test_specific_mode_raises_when_any_selected_id_missing(self):
        fetch_mock = AsyncMock(return_value=[
            {"activityId": "A1", "durationSeconds": 30, "recordingUrl": "u1"},
        ])
        with patch.object(resolver, "_fetch_calls_by_activity_ids", new=fetch_mock):
            with self.assertRaises(resolver.SpecificCallSelectionMissingError) as ctx:
                await resolver.resolve_call_selection_from_source(
                    InsideSalesCallFilters(
                        date_from="2026-04-24 00:00:00",
                        date_to="2026-04-24 23:59:59",
                    ),
                    selection_mode="specific",
                    selected_call_ids=["A1", "A2-MISSING"],
                    sample_size=10,
                    skip_evaluated=False,
                    min_duration_seconds=None,
                    tenant_id=uuid.uuid4(),
                    user_id=uuid.uuid4(),
                    db=_FakeSession(),  # type: ignore[arg-type]
                )
        self.assertIn("A2-MISSING", ctx.exception.missing_ids)

    async def test_specific_mode_resolves_call_from_day_before_ui_window(self):
        """Probe for the real-world bug: a call with CreatedOn on
        2026-04-23 must resolve even when the UI date window is
        2026-04-24. This was the root cause of run
        66e0d243-e2f1-4854-b388-28f3d8f0334d returning total:0."""
        yesterday_call = {
            "activityId": "ACT-2026-04-23",
            "durationSeconds": 180,
            "recordingUrl": "https://example.com/rec.mp3",
            "createdOn": "2026-04-23 18:00:00",
        }
        fetch_mock = AsyncMock(return_value=[yesterday_call])
        list_mock = AsyncMock()  # would return [] for the tight UI date window
        with patch.object(resolver, "_fetch_calls_by_activity_ids", new=fetch_mock), \
             patch.object(resolver, "list_calls_from_source", new=list_mock):
            result = await resolver.resolve_call_selection_from_source(
                InsideSalesCallFilters(
                    date_from="2026-04-24 00:00:00",
                    date_to="2026-04-24 23:59:59",
                ),
                selection_mode="specific",
                selected_call_ids=["ACT-2026-04-23"],
                sample_size=10,
                skip_evaluated=False,
                min_duration_seconds=None,
                tenant_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                db=_FakeSession(),  # type: ignore[arg-type]
            )
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0]["activityId"], "ACT-2026-04-23")


class NonSpecificModeStillUsesFilteredListTests(unittest.IsolatedAsyncioTestCase):
    async def test_sample_mode_uses_filtered_list_and_random_samples(self):
        from app.services.inside_sales_dataset_resolver import ResolvedDatasetPage
        list_mock = AsyncMock(return_value=ResolvedDatasetPage(
            records=[
                {"activityId": f"A{i}", "durationSeconds": 100, "recordingUrl": f"u{i}"}
                for i in range(50)
            ],
            total=50,
            page=1,
            page_size=50,
        ))
        fetch_by_ids_mock = AsyncMock()
        with patch.object(resolver, "list_calls_from_source", new=list_mock), \
             patch.object(resolver, "_fetch_calls_by_activity_ids", new=fetch_by_ids_mock):
            result = await resolver.resolve_call_selection_from_source(
                InsideSalesCallFilters(
                    date_from="2026-04-24 00:00:00",
                    date_to="2026-04-24 23:59:59",
                ),
                selection_mode="sample",
                selected_call_ids=[],
                sample_size=5,
                skip_evaluated=False,
                min_duration_seconds=None,
                tenant_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                db=_FakeSession(),  # type: ignore[arg-type]
            )
        list_mock.assert_awaited_once()
        fetch_by_ids_mock.assert_not_awaited()
        self.assertEqual(len(result.records), 5)


if __name__ == "__main__":
    unittest.main()

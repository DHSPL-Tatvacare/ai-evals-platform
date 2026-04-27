"""Tests for ``resolve_call_selection_from_source``.

Specific-selection contract: when ``selection_mode="specific"``, the
resolver must bypass UI agent / status filters and match calls by
``activity_id`` scoped to tenant + app. If any requested ID does not
resolve, the run fails loudly with
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


class SpecificSelectionBypassesListQueryTests(unittest.IsolatedAsyncioTestCase):
    async def test_specific_mode_does_not_run_filtered_list_query(self):
        """When mode=specific, the resolver must skip the filtered listing
        query entirely and go straight to activity_id lookup."""
        fetch_mock = AsyncMock(return_value=[
            {"activityId": "A1", "durationSeconds": 30, "recordingUrl": "u1"},
            {"activityId": "A2", "durationSeconds": 30, "recordingUrl": "u2"},
        ])
        list_mock = AsyncMock()
        with patch.object(resolver, "_fetch_calls_by_activity_ids", new=fetch_mock), \
             patch.object(resolver, "list_calls_from_source", new=list_mock):
            result = await resolver.resolve_call_selection_from_source(
                InsideSalesCallFilters(),
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
                    InsideSalesCallFilters(),
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

    async def test_specific_mode_resolves_call_independent_of_other_filters(self):
        """Specific selection must resolve activity_ids regardless of the
        agent/status filter state — those filters apply only to the
        list-driven modes (all/sample)."""
        target_call = {
            "activityId": "ACT-FROM-OTHER-DAY",
            "durationSeconds": 180,
            "recordingUrl": "https://example.com/rec.mp3",
        }
        fetch_mock = AsyncMock(return_value=[target_call])
        list_mock = AsyncMock()
        with patch.object(resolver, "_fetch_calls_by_activity_ids", new=fetch_mock), \
             patch.object(resolver, "list_calls_from_source", new=list_mock):
            result = await resolver.resolve_call_selection_from_source(
                InsideSalesCallFilters(agents=("Other Agent",)),
                selection_mode="specific",
                selected_call_ids=["ACT-FROM-OTHER-DAY"],
                sample_size=10,
                skip_evaluated=False,
                min_duration_seconds=None,
                tenant_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                db=_FakeSession(),  # type: ignore[arg-type]
            )
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0]["activityId"], "ACT-FROM-OTHER-DAY")


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
                InsideSalesCallFilters(),
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

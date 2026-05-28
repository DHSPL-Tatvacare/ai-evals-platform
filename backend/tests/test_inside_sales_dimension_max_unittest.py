"""Per-dimension max resolution tests for InsideSalesAggregator.

Each call's `output.reasoning[]` carries the authoritative per-dimension max
(e.g. {"dimension": "Call Opening", "score": 7, "max": 10}). The seeded
evaluators set NO `max` on schema fields, so without a reasoning fallback every
dimension wrongly defaults to /100. These tests pin the schema-first +
reasoning-fallback resolution and the downstream threshold/bucket correctness.
"""
from __future__ import annotations

import unittest

from app.services.reports.inside_sales_aggregator import (
    InsideSalesAggregator,
    _resolve_dimension_max,
)


def _thread(call_id: str, output: dict) -> dict:
    return {
        "thread_id": call_id,
        "success_status": True,
        "result": {
            "evaluations": [
                {"evaluator_id": "sal", "output": output},
            ],
            "call_metadata": {"rep_external_id": "rep-1", "rep_label": "Rep One"},
        },
    }


class ResolveDimensionMaxTests(unittest.TestCase):
    def test_schema_max_wins_over_reasoning(self):
        field = {"key": "probing_quality", "max": 12}
        reasoning_max_by_key = {"probing_quality": 99.0}
        self.assertEqual(_resolve_dimension_max(field, reasoning_max_by_key), 12.0)

    def test_reasoning_fallback_when_schema_omits_max(self):
        field = {"key": "call_opening"}
        reasoning_max_by_key = {"call_opening": 10.0}
        self.assertEqual(_resolve_dimension_max(field, reasoning_max_by_key), 10.0)

    def test_default_100_only_when_neither_provides_usable_max(self):
        field = {"key": "brand_positioning"}
        self.assertEqual(_resolve_dimension_max(field, {}), 100.0)

    def test_non_positive_schema_max_is_ignored(self):
        field = {"key": "call_opening", "max": 0}
        reasoning_max_by_key = {"call_opening": 10.0}
        self.assertEqual(_resolve_dimension_max(field, reasoning_max_by_key), 10.0)


# Mixed-scale schema with NO max on any field (mirrors seeded evaluators).
MIXED_SCHEMA = [
    {"key": "overall_score", "type": "number", "isMainMetric": True},
    {"key": "call_opening", "type": "number", "role": "detail"},
    {"key": "brand_positioning", "type": "number", "role": "detail"},
]


def _reasoning(call_opening_max: int, brand_max: int) -> list[dict]:
    return [
        {"dimension": "Call Opening", "score": 7, "max": call_opening_max},
        {"dimension": "Brand Positioning", "score": 12, "max": brand_max},
    ]


class DimensionBreakdownReasoningMaxTests(unittest.TestCase):
    def test_breakdown_uses_reasoning_max_for_denominator_and_thresholds(self):
        threads = [
            _thread("c1", {
                "overall_score": 70, "call_opening": 8, "brand_positioning": 12,
                "reasoning": _reasoning(10, 15),
            }),
            _thread("c2", {
                "overall_score": 60, "call_opening": 6, "brand_positioning": 9,
                "reasoning": _reasoning(10, 15),
            }),
        ]
        agg = InsideSalesAggregator(
            threads, MIXED_SCHEMA, {"rep-1": "Rep One"}, evaluator_id="sal",
        ).aggregate()
        bd = agg["dimensionBreakdown"]

        self.assertEqual(bd["call_opening"]["maxPossible"], 10.0)
        self.assertEqual(bd["brand_positioning"]["maxPossible"], 15.0)
        # Thresholds derive from the correct max, not /100.
        self.assertAlmostEqual(bd["call_opening"]["greenThreshold"], 8.0)
        self.assertAlmostEqual(bd["call_opening"]["yellowThreshold"], 5.0)
        self.assertAlmostEqual(bd["brand_positioning"]["greenThreshold"], 12.0)
        self.assertAlmostEqual(bd["brand_positioning"]["yellowThreshold"], 7.5)

    def test_breakdown_distribution_buckets_use_correct_max(self):
        # call_opening max=10 → bucket_size 2. Values 8 and 6 → buckets [3] and [3].
        threads = [
            _thread("c1", {"overall_score": 70, "call_opening": 8,
                           "reasoning": [{"dimension": "Call Opening", "score": 8, "max": 10}]}),
            _thread("c2", {"overall_score": 60, "call_opening": 6,
                           "reasoning": [{"dimension": "Call Opening", "score": 6, "max": 10}]}),
        ]
        schema = [
            {"key": "overall_score", "type": "number", "isMainMetric": True},
            {"key": "call_opening", "type": "number", "role": "detail"},
        ]
        agg = InsideSalesAggregator(
            threads, schema, {"rep-1": "Rep One"}, evaluator_id="sal",
        ).aggregate()
        dist = agg["dimensionBreakdown"]["call_opening"]["distribution"]
        # bucket_size=2 → 8/2=4 (capped at idx 4), 6/2=3 → buckets[3]=1, buckets[4]=1
        self.assertEqual(dist, [0, 0, 0, 1, 1])


class AgentSliceDimensionMaxTests(unittest.TestCase):
    def test_agent_dims_carry_resolved_max_and_thresholds(self):
        threads = [
            _thread("c1", {
                "overall_score": 70, "call_opening": 8, "brand_positioning": 12,
                "reasoning": _reasoning(10, 15),
            }),
        ]
        agg = InsideSalesAggregator(
            threads, MIXED_SCHEMA, {"rep-1": "Rep One"}, evaluator_id="sal",
        ).aggregate()
        dims = agg["agentSlices"]["rep-1"]["dimensions"]

        self.assertEqual(dims["call_opening"]["avg"], 8.0)
        self.assertEqual(dims["call_opening"]["maxPossible"], 10.0)
        self.assertAlmostEqual(dims["call_opening"]["greenThreshold"], 8.0)
        self.assertAlmostEqual(dims["call_opening"]["yellowThreshold"], 5.0)

        self.assertEqual(dims["brand_positioning"]["maxPossible"], 15.0)
        self.assertAlmostEqual(dims["brand_positioning"]["greenThreshold"], 12.0)
        self.assertAlmostEqual(dims["brand_positioning"]["yellowThreshold"], 7.5)


if __name__ == "__main__":
    unittest.main()

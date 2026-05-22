"""Pure-unit validation tests for EvaluationSelectionSpec.

The spec is a Pydantic model with `extra='forbid'`. Every active validation
rule must produce a clear error rather than silently coercing.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from pydantic import ValidationError

from app.services.evaluators.selection.spec import EvaluationSelectionSpec


class SpecValidationTests(unittest.TestCase):
    def test_default_spec_is_mode_all(self):
        spec = EvaluationSelectionSpec()
        self.assertEqual(spec.mode, "all")
        self.assertEqual(spec.has_recording, "any")
        self.assertFalse(spec.skip_evaluated)
        self.assertEqual(spec.predicate_summary(), {"mode": "all"})

    def test_extra_keys_are_rejected(self):
        with self.assertRaises(ValidationError) as cm:
            EvaluationSelectionSpec.model_validate(
                {"mode": "all", "min_duration": True}  # legacy alias must NOT be accepted
            )
        self.assertIn("min_duration", str(cm.exception))

    def test_specific_mode_requires_selected_ids(self):
        with self.assertRaises(ValidationError):
            EvaluationSelectionSpec(mode="specific")

    def test_sample_mode_requires_sample_size(self):
        with self.assertRaises(ValidationError):
            EvaluationSelectionSpec(mode="sample")
        with self.assertRaises(ValidationError):
            EvaluationSelectionSpec(mode="sample", sample_size=0)

    def test_sample_mode_with_sample_size_is_valid(self):
        spec = EvaluationSelectionSpec(mode="sample", sample_size=20)
        self.assertEqual(spec.sample_size, 20)

    def test_specific_mode_with_ids_is_valid(self):
        spec = EvaluationSelectionSpec(
            mode="specific", selected_ids=("A1", "A2")
        )
        self.assertEqual(spec.selected_ids, ("A1", "A2"))

    def test_duration_range_validation(self):
        with self.assertRaises(ValidationError):
            EvaluationSelectionSpec(duration_min_seconds=-1)
        with self.assertRaises(ValidationError):
            EvaluationSelectionSpec(
                duration_min_seconds=100, duration_max_seconds=50
            )

    def test_predicate_summary_omits_inactive_filters(self):
        spec = EvaluationSelectionSpec(
            agents=("Komal", "Tushar"),
            duration_min_seconds=10,
            has_recording="only",
            skip_evaluated=True,
            mode="sample",
            sample_size=20,
        )
        summary = spec.predicate_summary()
        self.assertEqual(summary["agents"], ["Komal", "Tushar"])
        self.assertEqual(summary["duration_min_seconds"], 10)
        self.assertEqual(summary["has_recording"], "only")
        self.assertEqual(summary["mode"], "sample")
        self.assertEqual(summary["sample_size"], 20)
        self.assertEqual(summary["skip_evaluated"], True)
        self.assertEqual(summary["skip_evaluated_scope"], "self")
        self.assertNotIn("status", summary)
        self.assertNotIn("direction", summary)

    def test_spec_is_frozen(self):
        spec = EvaluationSelectionSpec()
        with self.assertRaises(ValidationError):
            spec.mode = "sample"  # type: ignore[misc]

    def test_call_date_range_defaults_none_and_omitted_from_summary(self):
        spec = EvaluationSelectionSpec()
        self.assertIsNone(spec.call_date_from)
        self.assertIsNone(spec.call_date_to)
        self.assertNotIn("call_date_from", spec.predicate_summary())

    def test_call_date_range_flows_into_predicate_summary(self):
        spec = EvaluationSelectionSpec(
            call_date_from=datetime(2026, 4, 1, tzinfo=timezone.utc),
            call_date_to=datetime(2026, 4, 30, tzinfo=timezone.utc),
        )
        summary = spec.predicate_summary()
        self.assertEqual(summary["call_date_from"], "2026-04-01T00:00:00+00:00")
        self.assertEqual(summary["call_date_to"], "2026-04-30T00:00:00+00:00")


if __name__ == "__main__":
    unittest.main()

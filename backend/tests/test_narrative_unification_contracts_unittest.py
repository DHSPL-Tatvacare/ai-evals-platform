"""Contract-layer tests for the unified, fail-loud narrative section.

These pin the *shape* guarantees of the narrative contract (distinct from the
``narrative_executor`` behaviour covered in
``test_narrative_unification_unittest.py``):

* ``NarrativeSection.data`` is a discriminated union on the ``schema_key``
  literal, so a single-run vs cross-run narrative dict routes to the correct
  model and an unknown key fails loud (``ValidationError``) instead of being
  silently coerced.
* Already-persisted single-run AND cross-run narrative dicts (the 18+ cached
  report artifacts use these camelCase shapes) still validate and round-trip
  through ``NarrativeSection``.
* ``PlatformCrossRunMetadata`` now carries the same ``narrative_status`` /
  ``narrative_model`` / ``narrative_error`` fields as ``PlatformReportMetadata``
  via the shared ``NarrativeStatus`` type.
"""

from __future__ import annotations

import unittest

from pydantic import TypeAdapter, ValidationError

from app.services.reports.contracts.cross_run_narrative import (
    PlatformCrossRunNarrative,
)
from app.services.reports.contracts.cross_run_report import (
    PlatformCrossRunMetadata,
)
from app.services.reports.contracts.report_sections import (
    NarrativeSection,
    PlatformReportSection,
)
from app.services.reports.contracts.run_narrative import PlatformRunNarrative
from app.services.reports.contracts.run_report import PlatformReportMetadata


def _run_narrative_dict() -> dict:
    """camelCase shape persisted by single-run report artifacts."""
    return {
        "schemaVersion": "v1",
        "schemaKey": "platform_run_narrative_v1",
        "schemaOwner": "backend",
        "executiveSummary": "Quality is stable with minor compliance gaps.",
        "issues": [
            {
                "title": "Intent slips",
                "area": "Intent",
                "severity": "high",
                "summary": "Pricing questions miss the right route.",
            }
        ],
        "recommendations": [
            {
                "priority": "P1",
                "area": "Intent",
                "action": "Tighten routing examples",
                "rationale": "Reduce wrong-intent fallback.",
            }
        ],
        "exemplars": [],
        "promptGaps": [
            {
                "gapType": "UNDERSPEC",
                "promptSection": "Escalation",
                "evaluationRule": "rule-1",
                "suggestedFix": "Add escalation thresholds.",
            }
        ],
    }


def _cross_run_narrative_dict() -> dict:
    """camelCase shape persisted by cross-run report artifacts."""
    return {
        "schemaVersion": "v1",
        "schemaKey": "platform_cross_run_narrative_v1",
        "schemaOwner": "backend",
        "executiveSummary": "Across 5 runs tone quality regressed.",
        "trendAnalysis": "Scores declined after the prompt change.",
        "criticalPatterns": [
            {
                "title": "Tone drift",
                "summary": "The agent grew terse over time.",
                "affectedRuns": 3,
            }
        ],
        "strategicRecommendations": [
            {
                "priority": "P0",
                "action": "Tighten tone guidance.",
                "expectedImpact": "+10 points on tone.",
            }
        ],
    }


def _narrative_section(data: dict) -> dict:
    return {
        "id": "narrative",
        "type": "narrative",
        "title": "Narrative",
        "variant": "executive_summary",
        "data": data,
    }


class NarrativeSectionDiscriminatorTests(unittest.TestCase):
    def test_routes_single_run_narrative(self):
        section = NarrativeSection.model_validate(
            _narrative_section(_run_narrative_dict())
        )
        self.assertIsInstance(section.data, PlatformRunNarrative)
        self.assertEqual(
            section.data.executive_summary,
            "Quality is stable with minor compliance gaps.",
        )

    def test_routes_cross_run_narrative(self):
        section = NarrativeSection.model_validate(
            _narrative_section(_cross_run_narrative_dict())
        )
        self.assertIsInstance(section.data, PlatformCrossRunNarrative)
        self.assertEqual(
            section.data.executive_summary,
            "Across 5 runs tone quality regressed.",
        )

    def test_fails_loud_on_unknown_schema_key(self):
        bad = {**_run_narrative_dict(), "schemaKey": "not_a_real_schema_v1"}
        with self.assertRaises(ValidationError):
            NarrativeSection.model_validate(_narrative_section(bad))

    def test_section_union_routes_cross_run_narrative(self):
        adapter = TypeAdapter(PlatformReportSection)
        section = adapter.validate_python(
            _narrative_section(_cross_run_narrative_dict())
        )
        self.assertIsInstance(section, NarrativeSection)
        self.assertIsInstance(section.data, PlatformCrossRunNarrative)


class CachedNarrativeRoundTripTests(unittest.TestCase):
    def test_cached_single_run_narrative_round_trips(self):
        section = NarrativeSection.model_validate(
            _narrative_section(_run_narrative_dict())
        )
        dumped = section.model_dump(by_alias=True)
        reloaded = NarrativeSection.model_validate(dumped)
        self.assertIsInstance(reloaded.data, PlatformRunNarrative)
        self.assertEqual(
            dumped["data"]["schemaKey"], "platform_run_narrative_v1"
        )
        self.assertEqual(len(dumped["data"]["promptGaps"]), 1)

    def test_cached_cross_run_narrative_round_trips(self):
        section = NarrativeSection.model_validate(
            _narrative_section(_cross_run_narrative_dict())
        )
        dumped = section.model_dump(by_alias=True)
        reloaded = NarrativeSection.model_validate(dumped)
        self.assertIsInstance(reloaded.data, PlatformCrossRunNarrative)
        self.assertEqual(
            dumped["data"]["schemaKey"], "platform_cross_run_narrative_v1"
        )
        self.assertEqual(len(dumped["data"]["criticalPatterns"]), 1)


class CrossRunMetadataNarrativeStatusTests(unittest.TestCase):
    def test_narrative_status_fields_default_to_none(self):
        meta = PlatformCrossRunMetadata.model_validate(
            {
                "appId": "kaira-bot",
                "computedAt": "2026-05-29T00:00:00+00:00",
                "sourceRunCount": 2,
                "totalRunsAvailable": 5,
            }
        )
        self.assertIsNone(meta.narrative_status)
        self.assertIsNone(meta.narrative_model)
        self.assertIsNone(meta.narrative_error)

    def test_failed_narrative_serialises_like_single_run(self):
        common = {
            "narrativeStatus": "failed",
            "narrativeModel": "gpt-x",
            "narrativeError": "validation_failed: boom",
        }
        cross = PlatformCrossRunMetadata.model_validate(
            {
                "appId": "kaira-bot",
                "computedAt": "2026-05-29T00:00:00+00:00",
                "sourceRunCount": 1,
                "totalRunsAvailable": 1,
                **common,
            }
        ).model_dump(by_alias=True)
        single = PlatformReportMetadata.model_validate(
            {
                "appId": "kaira-bot",
                "runId": "run-1",
                "evalType": "batch_thread",
                "createdAt": "2026-05-29T00:00:00+00:00",
                "computedAt": "2026-05-29T00:00:00+00:00",
                **common,
            }
        ).model_dump(by_alias=True)

        for key in ("narrativeStatus", "narrativeModel", "narrativeError"):
            self.assertEqual(cross[key], single[key])


if __name__ == "__main__":
    unittest.main()

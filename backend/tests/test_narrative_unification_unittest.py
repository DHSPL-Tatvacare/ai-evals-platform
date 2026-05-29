"""Characterization tests for the reportId-driven narrative pipeline.

These tests pin the behaviour of
``app.services.reports.narrative_executor.execute_narrative_generation`` when
the LLM returns camelCase keys (which it does, because the JSON schema handed
to ``llm.generate_json`` is ``<Contract>.model_json_schema()`` and the contracts
inherit ``CamelModel``, whose ``alias_generator=to_camel`` emits camelCase
property names).

- ``test_single_run_narrative_camelcase_is_inserted`` is the GOLDEN test: it
  locks the currently-correct single-run mapping, which routes the LLM result
  through ``PlatformRunNarrative.model_validate`` (alias-aware).
- ``test_cross_run_narrative_camelcase_is_inserted`` is the INTENDED-RED test:
  it characterizes the cross-run bug where ``_cross_run_narrative_payload``
  reads snake_case keys (``result.get('critical_patterns')`` etc.) out of the
  camelCase dict the LLM returns, and therefore always produces an empty
  narrative. It is expected to FAIL today and to pass once the cross-run mapper
  is unified with the single-run alias-aware path.

The repo configures ``asyncio_mode = "auto"`` (root ``pyproject.toml``), so the
async test functions need no explicit marker.
"""

from __future__ import annotations

from typing import Any

from app.services.reports.contracts.cross_run_report import PlatformCrossRunMetadata
from app.services.reports.contracts.run_report import PlatformReportMetadata
from app.services.reports.narrative_executor import execute_narrative_generation


class FakeLLM:
    """Minimal stand-in for the platform LLM client.

    Returns a pre-canned dict from ``generate_json`` regardless of the prompt,
    mirroring the real keyword-only signature
    (``prompt``, ``system_prompt``, ``json_schema``) used at both call sites in
    ``execute_narrative_generation``.
    """

    def __init__(self, canned: dict[str, Any]) -> None:
        self.canned = canned
        self.calls: list[dict[str, Any]] = []

    async def generate_json(
        self,
        *,
        prompt: str,
        system_prompt: str | None,
        json_schema: dict[str, Any],
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "prompt": prompt,
                "system_prompt": system_prompt,
                "json_schema": json_schema,
            }
        )
        return self.canned


async def test_single_run_narrative_camelcase_is_inserted() -> None:
    """GOLDEN: a camelCase single-run narrative round-trips into the payload.

    Locks the current good behaviour: the executiveSummary survives and the
    issues / promptGaps arrays are populated rather than silently defaulted.
    """
    camel_single = {
        "executiveSummary": "Overall the run is strong with minor latency issues.",
        "issues": [
            {
                "title": "Slow responses",
                "area": "latency",
                "severity": "high",
                "summary": "p95 latency exceeds the target.",
            }
        ],
        "recommendations": [
            {
                "priority": "P1",
                "area": "latency",
                "action": "Add response caching.",
                "rationale": "Cuts repeated work.",
            }
        ],
        "exemplars": [],
        "promptGaps": [
            {
                "gapType": "missing_rule",
                "promptSection": "system",
                "evaluationRule": "tone-check",
                "suggestedFix": "Document the expected tone.",
            }
        ],
    }
    llm = FakeLLM(camel_single)
    # model_construct() builds a metadata instance the prompt builder can
    # ``model_dump(by_alias=True)`` without us hard-coding required fields.
    metadata = PlatformReportMetadata.model_construct()
    narrative_config = {
        "enabled": True,
        "outputInsertionPoints": [
            "run-narrative",
            "run-prompt-gap-analysis",
            "run-issues-recommendations",
        ],
    }

    inserted = await execute_narrative_generation(
        llm=llm,
        report_id="report-single-1",
        report_kind="single_run",
        metadata=metadata,
        sections=[],
        narrative_config=narrative_config,
    )

    narrative_payload = inserted["run-narrative"]
    assert narrative_payload["executiveSummary"] == (
        "Overall the run is strong with minor latency issues."
    )
    assert len(narrative_payload["issues"]) == 1
    assert len(inserted["run-prompt-gap-analysis"]) == 1


async def test_cross_run_narrative_camelcase_is_inserted() -> None:
    """INTENDED-RED: a camelCase cross-run narrative must round-trip too.

    This FAILS today: ``_cross_run_narrative_payload`` reads snake_case keys
    (``critical_patterns`` / ``executive_summary`` ...) out of the camelCase
    dict the LLM returns, so the inserted narrative ends up with an empty
    executiveSummary and zero criticalPatterns. It will pass once the cross-run
    mapper uses the same alias-aware validation as the single-run path.
    """
    camel_cross = {
        "executiveSummary": "Across 5 runs, tone quality regressed week over week.",
        "trendAnalysis": "Scores declined steadily after the prompt change.",
        "criticalPatterns": [
            {
                "title": "Tone drift",
                "summary": "The agent became increasingly terse.",
                "affectedRuns": 3,
            }
        ],
        "strategicRecommendations": [
            {
                "priority": "P0",
                "action": "Tighten the tone guidance in the system prompt.",
                "expectedImpact": "+10 points on tone scores.",
            }
        ],
    }
    llm = FakeLLM(camel_cross)
    metadata = PlatformCrossRunMetadata.model_construct()
    narrative_config = {
        "enabled": True,
        # Cross-run insertion points use the '*-cross-narrative' id convention.
        "outputInsertionPoints": ["xrun-cross-narrative"],
    }

    inserted = await execute_narrative_generation(
        llm=llm,
        report_id="report-cross-1",
        report_kind="cross_run",
        metadata=metadata,
        sections=[],
        narrative_config=narrative_config,
    )

    narrative_payload = inserted["xrun-cross-narrative"]
    assert narrative_payload["executiveSummary"] == (
        "Across 5 runs, tone quality regressed week over week."
    )
    assert len(narrative_payload["criticalPatterns"]) > 0

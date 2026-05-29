"""Invariant lock: single_run and cross_run must traverse the SAME pipeline.

These tests fail if anyone re-forks the unified report pipeline. They assert two
shared seams, parametrized over both scopes (``single_run`` / ``cross_run``):

1. **One narrative parse boundary.** ``execute_narrative_generation`` parses the
   LLM output via ``<contract>.model_validate`` for BOTH scopes
   (``PlatformRunNarrative`` for single-run, ``PlatformCrossRunNarrative`` for
   cross-run). A spy wrapped around each scope's contract ``model_validate``
   must be hit. This kills any reintroduction of the old divergent snake_case
   ``.get()`` cross-run mapper that bypassed alias-aware validation.

2. **One data-quality finalizer.** The shared ``compose_report_payload`` engine
   invokes ``finalize_data_quality`` for BOTH scopes. A spy on
   ``finalize_data_quality`` must be hit on each scope's drive. This kills any
   re-fork where one scope skips finalization.

No docker / no DB: single-run is driven through ``_compose_single_run_payload``
with a stub producer (mirroring ``test_report_generation_end_to_end_unittest``);
cross-run is driven through ``CROSS_RUN_SCOPE_SPEC`` with the voice-rx cross-run
aggregate as the base payload (mirroring ``test_narrative_unification_engine``).
"""

from __future__ import annotations

import unittest
import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

from app.schemas.app_analytics_config import AppAnalyticsConfig
from app.schemas.app_config import AppConfig
from app.services.reports.analytics_profiles.base import AnalyticsProfile
from app.services.reports.asset_resolver import ResolvedNarrativeAssets
from app.services.reports.contracts.cross_run_narrative import PlatformCrossRunNarrative
from app.services.reports.contracts.run_narrative import PlatformRunNarrative
from app.services.reports.contracts.run_report import (
    PlatformReportMetadata,
    PlatformRunReportPayload,
)
from app.services.seed_defaults import APP_SEEDS


_SCOPES = ["single_run", "cross_run"]

_EMPTY_ASSETS = ResolvedNarrativeAssets(
    prompt_references={}, system_prompt="sys", glossary=None,
)


# ----- Seeded config helpers --------------------------------------------

_SEEDED_APP_CONFIG_BY_SLUG: dict[str, dict] = {
    seed["slug"]: seed["config"] for seed in APP_SEEDS
}


def _voice_rx_analytics():
    return AppConfig.model_validate(_SEEDED_APP_CONFIG_BY_SLUG["voice-rx"]).analytics


# ----- LLM output fixtures (camelCase, as the SDK enforces the schema) ---

# Each scope's contract defines required fields; the LLM returns camelCase keys
# matching ``model_json_schema()``. ``model_validate`` (populate_by_name=True) is
# the alias-aware boundary that accepts them. These mirror the real shapes in
# test_report_narrative_executor / test_narrative_unification_contracts.
_NARRATIVE_LLM_OUTPUT: dict[str, dict[str, Any]] = {
    "single_run": {
        "executiveSummary": "Quality stable.",
        "issues": [],
        "recommendations": [],
        "exemplars": [],
        "promptGaps": [],
    },
    "cross_run": {
        "executiveSummary": "Trends improving.",
        "trendAnalysis": "Accuracy up across runs.",
        "criticalPatterns": [],
        "strategicRecommendations": [],
    },
}

_NARRATIVE_CONTRACT_BY_SCOPE: dict[str, type] = {
    "single_run": PlatformRunNarrative,
    "cross_run": PlatformCrossRunNarrative,
}


class _FakeLLM:
    """Returns a canned dict from generate_json, recording the call."""

    def __init__(self, response: dict[str, Any]):
        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def generate_json(self, *, prompt, system_prompt=None, json_schema=None, **kwargs):
        self.calls.append(
            {"prompt": prompt, "system_prompt": system_prompt, "json_schema": json_schema},
        )
        return self.response


def _narrative_metadata():
    # Shared metadata shape accepted by both narrative prompt builders.
    return PlatformReportMetadata(
        app_id="voice-rx",
        run_id="run-1",
        run_name="Run 1",
        eval_type="batch",
        created_at="2026-04-01T00:00:00Z",
        computed_at="2026-04-01T00:05:00Z",
    )


# ----- Cross-run base payload (aggregate of two cached single-run payloads) --

def _run_payload(run_name: str, accuracy: float) -> dict:
    return {
        "schemaVersion": "v1",
        "metadata": {
            "appId": "voice-rx",
            "runId": run_name,
            "runName": run_name,
            "evalType": "batch",
            "createdAt": "2026-04-01T00:00:00Z",
            "computedAt": "2026-04-01T00:05:00Z",
        },
        "sections": [
            {
                "id": "voice-rx-summary",
                "type": "summary_cards",
                "title": "Accuracy Summary",
                "data": [
                    {"key": "overall-accuracy", "label": "Overall Accuracy", "value": f"{accuracy:.1f}%", "tone": "positive"},
                    {"key": "total-items", "label": "Total Items", "value": "20", "tone": "neutral"},
                    {"key": "critical-errors", "label": "Critical Errors", "value": "1", "tone": "negative"},
                ],
            },
            {
                "id": "voice-rx-issues",
                "type": "issues_recommendations",
                "title": "Issues",
                "data": {
                    "issues": [
                        {"title": "Dosage transcription error", "area": "Accuracy", "priority": "P0", "summary": "Wrong dose."},
                    ],
                    "recommendations": [],
                },
            },
        ],
        "exportDocument": {
            "schemaVersion": "v1",
            "title": run_name,
            "theme": {
                "accent": "#0f766e", "accentMuted": "#99f6e4", "border": "#d1d5db",
                "textPrimary": "#0f172a", "textSecondary": "#475569", "background": "#ffffff",
            },
            "blocks": [{"id": "cover", "type": "cover", "title": run_name}],
        },
    }


def _cross_run_base_payload(analytics_config):
    from app.services.reports.voice_rx_cross_run import build_voice_rx_cross_run_payload

    runs = [
        ({"id": "run-1", "created_at": "2026-04-01T00:00:00Z"}, _run_payload("Run 1", 88.5)),
        ({"id": "run-2", "created_at": "2026-04-02T00:00:00Z"}, _run_payload("Run 2", 92.0)),
    ]
    return build_voice_rx_cross_run_payload(
        runs, analytics_config, app_id="voice-rx", total_runs_available=2,
    )


# ----- Single-run base payload (stub producer, mirrors e2e test) --------

def _payload_for_type(component_type: str) -> Any:
    if component_type == "summary_cards":
        return [{"key": "k", "label": "Label", "value": "v", "tone": "neutral"}]
    if component_type == "narrative":
        return PlatformRunNarrative(
            executive_summary="fixture", issues=[], recommendations=[], exemplars=[], prompt_gaps=[],
        ).model_dump(by_alias=True)
    if component_type == "metric_breakdown":
        return [{"key": "m", "label": "Metric", "value": 50.0, "maxValue": 100, "unit": "%", "tone": "neutral"}]
    if component_type == "distribution_chart":
        return [{"label": "series", "values": [1.0], "categories": ["a"]}]
    if component_type == "compliance_table":
        return {"data": [{"key": "r", "label": "Rule", "passed": 1, "failed": 0, "notEvaluated": 0, "rate": 1.0}], "coFailures": []}
    if component_type == "friction_analysis":
        return {"totalFrictionTurns": 0, "byCause": {}, "recoveryQuality": {}, "avgTurnsByVerdict": {}, "topPatterns": []}
    if component_type == "heatmap":
        return {"columns": ["c1"], "rows": [{"key": "r1", "label": "R1", "cells": [{"label": "x", "value": 0, "tone": "neutral"}]}]}
    if component_type == "entity_slices":
        return [{"entityId": "e1", "label": "E1", "summary": {"score": 0}, "details": {}}]
    if component_type == "flags":
        return [{"key": "f1", "label": "Flag", "relevant": 1, "present": 1}]
    if component_type == "issues_recommendations":
        return {"issues": [], "recommendations": []}
    if component_type == "exemplars":
        return [{"itemId": "i1", "label": "Item", "score": 1.0, "summary": "ex", "details": {}}]
    if component_type == "prompt_gap_analysis":
        return []
    if component_type == "callout":
        return {"message": "callout", "tone": "info"}
    raise ValueError(f"Unknown section component type: {component_type}")


class _FakeSession:
    def __init__(self, scalar_returns: list[Any]):
        self._scalar_returns = list(scalar_returns)

    async def scalar(self, _stmt):
        if not self._scalar_returns:
            return None
        return self._scalar_returns.pop(0)

    async def execute(self, _stmt):
        return SimpleNamespace(all=lambda: [], scalars=lambda: SimpleNamespace(all=lambda: []))


def _make_stub_producer_cls(app_slug: str):
    analytics_config = AppAnalyticsConfig.model_validate(
        _SEEDED_APP_CONFIG_BY_SLUG[app_slug]["analytics"]
    )
    section_configs = analytics_config.single_run.sections

    class _StubProducer:
        payload_model = PlatformRunReportPayload

        def __init__(self, db, tenant_id, user_id):
            self.db = db

        async def build_payload_for_composer(self, run_id, *, llm_provider=None, llm_model=None, include_narrative=False):
            from app.services.reports.document_composer import compose_document
            from app.services.reports.report_composer import compose_run_report

            payloads: dict[str, Any] = {sc.id: _payload_for_type(sc.type) for sc in section_configs}
            metadata = PlatformReportMetadata(
                app_id=app_slug,
                run_id=str(run_id),
                run_name="invariant-fixture",
                eval_type="batch",
                created_at="2026-05-18T00:00:00Z",
                computed_at="2026-05-18T00:00:00Z",
            )
            export_doc = compose_document(
                title="fixture", subtitle=None, metadata={}, sections=[],
                export_config=analytics_config.single_run.export,
            )
            return compose_run_report(
                metadata=metadata,
                section_configs=section_configs,
                section_payloads=payloads,
                export_document=export_doc,
            )

    return _StubProducer


def _make_application_row(app_slug: str) -> SimpleNamespace:
    return SimpleNamespace(slug=app_slug, is_active=True, config=_SEEDED_APP_CONFIG_BY_SLUG[app_slug])


def _single_run_report_config(app_slug: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        app_id=app_slug,
        report_id="default-single-run",
        name="Default Single Run",
        presentation_config={},
        export_config={},
        narrative_config={
            "enabled": True,
            "assetKeys": {},
            "inputSelection": {"sectionIds": []},
            "outputInsertionPoints": [],
        },
    )


def _cross_run_report_config() -> SimpleNamespace:
    return SimpleNamespace(
        report_id="default-cross-run",
        name="Default Cross Run",
        presentation_config={},
        export_config={},
        narrative_config={
            "enabled": True,
            "assetKeys": {},
            "inputSelection": {"sectionIds": []},
            "outputInsertionPoints": [],
        },
    )


# ----- Invariant 1: single narrative parse boundary ----------------------

class NarrativeParsePathIsSharedTests(unittest.IsolatedAsyncioTestCase):
    """Both scopes parse LLM output through ``<contract>.model_validate``."""

    async def _assert_parse_path(self, scope: str):
        from app.services.reports import narrative_executor as ne

        contract = _NARRATIVE_CONTRACT_BY_SCOPE[scope]
        llm = _FakeLLM(_NARRATIVE_LLM_OUTPUT[scope])

        # Wrap the scope's contract ``model_validate`` so we observe (not stub)
        # the real call. ``execute_narrative_generation`` reaches the contract
        # via NARRATIVE_KINDS[scope].contract, so patching the class method here
        # is exactly the boundary the engine uses for this scope.
        with patch.object(
            contract, "model_validate", side_effect=contract.model_validate, autospec=True,
        ) as spy:
            result = await ne.execute_narrative_generation(
                llm=llm,
                report_id="rid",
                report_kind=scope,
                metadata=_narrative_metadata(),
                sections=[],
                narrative_config={
                    "enabled": True,
                    "resolvedAssets": {"systemPrompt": "sys", "promptReferences": {}},
                    "inputSelection": {"sectionIds": []},
                    "outputInsertionPoints": ["x-narrative"],
                },
            )

        # The narrative parse boundary was traversed exactly once for this scope.
        self.assertEqual(spy.call_count, 1, f"[{scope}] model_validate not the parse path")
        # And the LLM schema handed out is this scope's contract schema (same
        # source as the parse), proving schema-out and parse-in are one contract.
        self.assertEqual(llm.calls[0]["json_schema"], contract.model_json_schema())
        # Narrative payload was inserted at the narrative insertion point.
        self.assertIn("x-narrative", result)

    async def test_both_scopes_parse_via_model_validate(self):
        for scope in _SCOPES:
            with self.subTest(scope=scope):
                await self._assert_parse_path(scope)


# ----- Invariant 2: single data-quality finalizer ------------------------

class FinalizeDataQualityIsSharedTests(unittest.IsolatedAsyncioTestCase):
    """The shared engine invokes ``finalize_data_quality`` for both scopes."""

    async def _drive_single_run(self, svc):
        app_slug = "voice-rx"
        db = _FakeSession([_make_application_row(app_slug)])
        stub_profile = AnalyticsProfile(
            key="voice_rx_v1",
            report_service_cls=_make_stub_producer_cls(app_slug),
            report_payload_model=PlatformRunReportPayload,
        )
        report_run = SimpleNamespace(id=uuid.uuid4(), llm_provider=None, llm_model=None, status="pending", completed_at=None)
        run = SimpleNamespace(id=uuid.uuid4(), app_id=app_slug, eval_type="batch", llm_provider=None, llm_model=None)

        with patch.object(svc, "get_analytics_profile", return_value=stub_profile), \
             patch.object(svc, "resolve_report_config_assets", AsyncMock(return_value=_EMPTY_ASSETS)), \
             patch.object(svc, "_create_logging_llm", AsyncMock(return_value=(None, None, None))), \
             patch.object(svc, "execute_narrative_generation", AsyncMock(side_effect=lambda **kw: {})):
            await svc._compose_single_run_payload(
                db,
                tenant_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                run=run,
                report_run=report_run,
                report_config=_single_run_report_config(app_slug),
                llm_provider=None,
                llm_model=None,
            )

    async def _drive_cross_run(self, svc):
        analytics_config = _voice_rx_analytics()
        base_payload = _cross_run_base_payload(analytics_config)
        report_run = SimpleNamespace(id=uuid.uuid4(), llm_provider=None, llm_model=None)

        with patch.object(svc, "resolve_report_config_assets", AsyncMock(return_value=_EMPTY_ASSETS)), \
             patch.object(svc, "_create_logging_llm", AsyncMock(return_value=(None, None, None))), \
             patch.object(svc, "execute_narrative_generation", AsyncMock(side_effect=lambda **kw: {})):
            await svc.compose_report_payload(
                svc.CROSS_RUN_SCOPE_SPEC,
                db=SimpleNamespace(),
                tenant_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                app_id="voice-rx",
                base_payload=base_payload,
                analytics_config=analytics_config,
                report_config=_cross_run_report_config(),
                report_run=report_run,
                llm_provider=None,
                llm_model=None,
                run_provider=None,
                run_model=None,
            )

    async def _assert_finalize_invoked(self, scope: str):
        from app.services.reports import report_generation_service as svc

        # Spy on finalize_data_quality (wrapping the real impl so the pipeline
        # still completes). It is invoked inside compose_report_payload — the
        # one engine both scopes route through.
        with patch.object(
            svc, "finalize_data_quality", side_effect=svc.finalize_data_quality,
        ) as mock_finalize:
            if scope == "single_run":
                await self._drive_single_run(svc)
            else:
                await self._drive_cross_run(svc)
        self.assertGreaterEqual(
            mock_finalize.call_count, 1, f"[{scope}] finalize_data_quality not invoked",
        )

    async def test_both_scopes_invoke_finalize_data_quality(self):
        for scope in _SCOPES:
            with self.subTest(scope=scope):
                await self._assert_finalize_invoked(scope)


if __name__ == "__main__":
    unittest.main()

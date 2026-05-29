"""Unified-engine tests: cross-run now inherits finalize_data_quality +
narrative_status stamping from the same ``compose_report_payload`` engine the
single-run path uses.

These drive the scope-agnostic engine directly (no docker/DB) via the cross-run
scope spec, with the voice-rx cross-run aggregate as the base payload. They lock
in the behaviour change called out in the unification task: cross-run artifacts
used to ship with NO data_quality and NO narrative_status; they now carry both.
"""

from __future__ import annotations

import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.schemas.app_config import AppConfig
from app.services.reports.asset_resolver import ResolvedNarrativeAssets
from app.services.seed_defaults import APP_SEEDS


def _voice_rx_config():
    for seed in APP_SEEDS:
        if seed["slug"] == "voice-rx":
            return AppConfig.model_validate(seed["config"]).analytics
    raise KeyError("voice-rx")


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
    """Aggregate two cached single-run payloads into the cross-run base payload,
    exactly like the production cross_run_adapter does."""
    from app.services.reports.voice_rx_cross_run import build_voice_rx_cross_run_payload

    runs = [
        ({"id": "run-1", "created_at": "2026-04-01T00:00:00Z"}, _run_payload("Run 1", 88.5)),
        ({"id": "run-2", "created_at": "2026-04-02T00:00:00Z"}, _run_payload("Run 2", 92.0)),
    ]
    return build_voice_rx_cross_run_payload(
        runs, analytics_config, app_id="voice-rx", total_runs_available=2,
    )


def _report_config(*, narrative_enabled: bool) -> SimpleNamespace:
    return SimpleNamespace(
        report_id="default-cross-run",
        name="Default Cross Run",
        presentation_config={},
        export_config={},
        narrative_config={
            "enabled": narrative_enabled,
            "assetKeys": {},
            "inputSelection": {"sectionIds": []},
            "outputInsertionPoints": [],
        },
    )


_EMPTY_ASSETS = ResolvedNarrativeAssets(prompt_references={}, system_prompt="sys", glossary=None)


class CrossRunInheritsFinalizeAndNarrativeStatusTests(unittest.IsolatedAsyncioTestCase):
    async def _drive(self, *, narrative_enabled: bool, llm_present: bool):
        from app.services.reports import report_generation_service as svc

        analytics_config = _voice_rx_config()
        base_payload = _cross_run_base_payload(analytics_config)
        report_config = _report_config(narrative_enabled=narrative_enabled)
        report_run = SimpleNamespace(id=uuid.uuid4(), llm_provider=None, llm_model=None)

        llm_return = (SimpleNamespace(), "openai", "gpt-test") if llm_present else (None, None, None)

        def _narrative_payloads(**_kw):
            return {}

        with patch.object(svc, "resolve_report_config_assets", AsyncMock(return_value=_EMPTY_ASSETS)), \
             patch.object(svc, "_create_logging_llm", AsyncMock(return_value=llm_return)), \
             patch.object(svc, "execute_narrative_generation", AsyncMock(side_effect=lambda **kw: _narrative_payloads(**kw))):
            return await svc.compose_report_payload(
                svc.CROSS_RUN_SCOPE_SPEC,
                db=SimpleNamespace(),
                tenant_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                app_id="voice-rx",
                base_payload=base_payload,
                analytics_config=analytics_config,
                report_config=report_config,
                report_run=report_run,
                llm_provider=None,
                llm_model=None,
                run_provider=None,
                run_model=None,
            )

    async def test_cross_run_stamps_data_quality(self):
        payload, _provider, _model, _status = await self._drive(
            narrative_enabled=False, llm_present=False,
        )
        # finalize_data_quality now runs on the cross-run path. The voice-rx
        # cross-run composition declares a narrative section that the aggregate
        # does not emit (and narrative is disabled here), so the finalizer flags
        # it 'empty' -> partial. Before unification, cross-run shipped no
        # data_quality at all and this signal was invisible.
        self.assertEqual(payload.data_quality.overall, "partial")
        self.assertEqual(payload.data_quality.missing_inputs, [])
        self.assertEqual(
            payload.data_quality.section_status.get("voice-rx-cross-narrative"),
            "empty",
        )

    async def test_cross_run_narrative_status_disabled(self):
        payload, _provider, _model, status = await self._drive(
            narrative_enabled=False, llm_present=False,
        )
        self.assertEqual(status, "disabled")
        self.assertEqual(payload.metadata.narrative_status, "disabled")
        self.assertIsNone(payload.metadata.narrative_model)

    async def test_cross_run_narrative_status_skipped_no_model(self):
        payload, _provider, _model, status = await self._drive(
            narrative_enabled=True, llm_present=False,
        )
        self.assertEqual(status, "skipped_no_model")
        self.assertEqual(payload.metadata.narrative_status, "skipped_no_model")

    async def test_cross_run_narrative_status_completed(self):
        payload, provider, model, status = await self._drive(
            narrative_enabled=True, llm_present=True,
        )
        self.assertEqual(status, "completed")
        self.assertEqual(payload.metadata.narrative_status, "completed")
        self.assertEqual(payload.metadata.narrative_model, "gpt-test")
        self.assertEqual(provider, "openai")
        self.assertEqual(model, "gpt-test")

    async def test_cross_run_payload_is_cross_run_contract(self):
        from app.services.reports.contracts.cross_run_report import PlatformCrossRunPayload

        payload, _provider, _model, _status = await self._drive(
            narrative_enabled=False, llm_present=False,
        )
        self.assertIsInstance(payload, PlatformCrossRunPayload)
        self.assertEqual(payload.metadata.report_kind, "cross_run")


if __name__ == "__main__":
    unittest.main()

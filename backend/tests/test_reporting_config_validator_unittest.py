"""Unit tests for the Phase 1 + Phase 4 reporting config validator.

See docs/plans/2026-05-18-reporting-genericize/phase-1-config-validator.md
+ docs/plans/2026-05-18-reporting-genericize/phase-4-narrative-assets-alembic.md.
"""

from __future__ import annotations

import copy
import unittest
from typing import Any
from unittest.mock import AsyncMock, patch

from app.schemas.app_config import AppConfig
from app.services.reports.config_validator import validate_reporting_config
from app.services.seed_defaults import APP_SEEDS, _build_narrative_config


# Default cascade behavior for Phase 4 check 8 — returns a non-empty prompt for
# any (tenant, user, app, key) lookup. Tests that want to exercise the
# missing-prompt failure mode patch this with side_effect=[None, ...] explicitly.
def _resolved_prompt(*_args: Any, **_kwargs: Any) -> dict[str, str]:
    return {"systemPrompt": "Seeded SYSTEM-shared prompt content."}


def _patch_cascade_resolved():
    """Convenience patch — every cascade lookup returns a populated prompt row."""
    return patch(
        "app.services.reports.config_validator._resolve_setting_value",
        new=AsyncMock(side_effect=_resolved_prompt),
    )


class _FakeResult:
    def __init__(self, rows: list[tuple[str, dict]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[str, dict]]:
        return self._rows


class _FakeDB:
    """Minimal async DB stub matching the call shape used by validate_all_app_pack_ids."""

    def __init__(self, rows: list[tuple[str, dict]]) -> None:
        self._rows = rows

    async def execute(self, *_args: Any, **_kwargs: Any) -> _FakeResult:
        return _FakeResult(self._rows)


def _seed_rows() -> list[tuple[str, dict]]:
    """All active seeded apps as (slug, config) tuples — deep-copied so tests can mutate."""
    return [(app["slug"], copy.deepcopy(app["config"])) for app in APP_SEEDS]


def _row_for(slug: str) -> tuple[str, dict]:
    for s, cfg in _seed_rows():
        if s == slug:
            return s, cfg
    raise KeyError(slug)


class ReportingConfigValidatorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        # Default cascade resolves to a populated SYSTEM-shared prompt — keeps
        # Phase 1 invariant tests focused on what they actually exercise without
        # tripping the Phase 4 check 8 narrative-prompt-resolves assertion.
        # Tests that want to exercise check 8 failure modes start their own patch.
        self._cascade_patch = _patch_cascade_resolved()
        self._cascade_patch.start()
        self.addCleanup(self._cascade_patch.stop)

    # --- positive case ---------------------------------------------------

    async def test_all_seeded_apps_pass(self):
        """Regression gate — every active seeded app must satisfy every invariant."""
        db = _FakeDB(_seed_rows())
        # Should not raise.
        await validate_reporting_config(db)

    # --- negative: profile (G4) ------------------------------------------

    async def test_unknown_profile_fails(self):
        slug, cfg = _row_for("voice-rx")
        cfg["analytics"]["profile"] = "bogus_v9"
        with self.assertRaises(RuntimeError) as ctx:
            await validate_reporting_config(_FakeDB([(slug, cfg)]))
        self.assertIn("voice-rx", str(ctx.exception))
        self.assertIn("bogus_v9", str(ctx.exception))

    async def test_empty_profile_fails_when_capability_on(self):
        slug, cfg = _row_for("voice-rx")
        cfg["analytics"]["profile"] = ""
        with self.assertRaises(RuntimeError) as ctx:
            await validate_reporting_config(_FakeDB([(slug, cfg)]))
        self.assertIn("profile", str(ctx.exception).lower())

    async def test_capability_off_skips_all_checks(self):
        """If singleRunReport=false the validator must not look at sections/export/etc."""
        slug, cfg = _row_for("voice-rx")
        cfg["analytics"]["profile"] = "totally-bogus"  # would fail check 1
        cfg["analytics"]["capabilities"]["singleRunReport"] = False
        await validate_reporting_config(_FakeDB([(slug, cfg)]))  # should not raise

    # --- negative: sections shape ----------------------------------------

    async def test_empty_sections_fails(self):
        slug, cfg = _row_for("voice-rx")
        cfg["analytics"]["singleRun"]["sections"] = []
        with self.assertRaises(RuntimeError) as ctx:
            await validate_reporting_config(_FakeDB([(slug, cfg)]))
        self.assertIn("sections", str(ctx.exception).lower())

    async def test_duplicate_section_ids_fail(self):
        slug, cfg = _row_for("voice-rx")
        sections = cfg["analytics"]["singleRun"]["sections"]
        # Duplicate the first section's id onto the second.
        sections[1]["id"] = sections[0]["id"]
        with self.assertRaises(RuntimeError) as ctx:
            await validate_reporting_config(_FakeDB([(slug, cfg)]))
        self.assertIn("duplicate", str(ctx.exception).lower())

    # --- negative: export subset (G3 export half) ------------------------

    async def test_export_section_id_not_in_sections_fails(self):
        slug, cfg = _row_for("voice-rx")
        cfg["analytics"]["singleRun"]["export"]["sectionIds"].append("ghost-section")
        with self.assertRaises(RuntimeError) as ctx:
            await validate_reporting_config(_FakeDB([(slug, cfg)]))
        self.assertIn("ghost-section", str(ctx.exception))
        self.assertIn("export", str(ctx.exception).lower())

    # --- negative: documentVariant (G3 palette) --------------------------

    async def test_unknown_document_variant_fails(self):
        slug, cfg = _row_for("voice-rx")
        cfg["analytics"]["singleRun"]["export"]["documentVariant"] = "not-a-real-variant"
        with self.assertRaises(RuntimeError) as ctx:
            await validate_reporting_config(_FakeDB([(slug, cfg)]))
        self.assertIn("not-a-real-variant", str(ctx.exception))

    # --- negative: aiSummary subset (G3 narrative half) ------------------

    async def test_ai_summary_section_id_not_in_sections_fails(self):
        slug, cfg = _row_for("kaira-bot")
        cfg["analytics"]["singleRun"]["aiSummary"]["sectionIds"].append("phantom-id")
        with self.assertRaises(RuntimeError) as ctx:
            await validate_reporting_config(_FakeDB([(slug, cfg)]))
        self.assertIn("phantom-id", str(ctx.exception))
        self.assertIn("aiSummary", str(ctx.exception))

    # --- negative: narrative insertion substring match (G3) --------------

    async def test_narrative_typed_section_with_bad_id_fails(self):
        """A section.type='narrative' whose id has no 'narrative' substring would
        be silently dropped by narrative_executor.py:201-213 — must fail at boot."""
        slug, cfg = _row_for("kaira-bot")
        for section in cfg["analytics"]["singleRun"]["sections"]:
            if section["type"] == "narrative":
                section["id"] = "kaira-summary-text"  # no 'narrative' substring
                break
        with self.assertRaises(RuntimeError) as ctx:
            await validate_reporting_config(_FakeDB([(slug, cfg)]))
        msg = str(ctx.exception)
        self.assertIn("kaira-summary-text", msg)
        self.assertIn("narrative", msg.lower())

    async def test_prompt_gap_typed_section_with_bad_id_fails(self):
        slug, cfg = _row_for("kaira-bot")
        for section in cfg["analytics"]["singleRun"]["sections"]:
            if section["type"] == "prompt_gap_analysis":
                section["id"] = "kaira-rubric-quality"
                break
        with self.assertRaises(RuntimeError) as ctx:
            await validate_reporting_config(_FakeDB([(slug, cfg)]))
        self.assertIn("kaira-rubric-quality", str(ctx.exception))

    async def test_callout_typed_section_with_bad_id_fails(self):
        slug, cfg = _row_for("voice-rx")
        for section in cfg["analytics"]["singleRun"]["sections"]:
            if section["type"] == "callout":
                section["id"] = "voice-rx-banner"  # no 'overview' or 'callout' substring
                break
        with self.assertRaises(RuntimeError) as ctx:
            await validate_reporting_config(_FakeDB([(slug, cfg)]))
        self.assertIn("voice-rx-banner", str(ctx.exception))

    async def test_issues_typed_section_with_bad_id_fails(self):
        slug, cfg = _row_for("kaira-bot")
        for section in cfg["analytics"]["singleRun"]["sections"]:
            if section["type"] == "issues_recommendations":
                section["id"] = "kaira-todo-list"
                break
        with self.assertRaises(RuntimeError) as ctx:
            await validate_reporting_config(_FakeDB([(slug, cfg)]))
        self.assertIn("kaira-todo-list", str(ctx.exception))

    # --- error aggregation -----------------------------------------------

    async def test_multiple_errors_collected_into_single_raise(self):
        slug, cfg = _row_for("voice-rx")
        cfg["analytics"]["profile"] = "bogus_v9"
        cfg["analytics"]["singleRun"]["export"]["documentVariant"] = "not-a-real-variant"
        with self.assertRaises(RuntimeError) as ctx:
            await validate_reporting_config(_FakeDB([(slug, cfg)]))
        msg = str(ctx.exception)
        self.assertIn("bogus_v9", msg)
        self.assertIn("not-a-real-variant", msg)
        # Single raise reports both — count newline bullets.
        self.assertGreaterEqual(msg.count("\n  - "), 2)

    async def test_corrupt_config_reports_but_does_not_crash(self):
        """An app whose AppConfig parse fails should be reported, not propagated."""
        db = _FakeDB([("broken-app", {"analytics": "not-a-dict"})])
        with self.assertRaises(RuntimeError) as ctx:
            await validate_reporting_config(db)
        self.assertIn("broken-app", str(ctx.exception))

    # --- Phase 4: narrative prompt resolves via cascade ------------------

    async def test_missing_narrative_prompt_in_cascade_fails(self):
        """An app whose narrativeTemplateKey does not resolve via the cascade
        must fail boot — the Phase 4 Alembic migration has not been applied or
        rows were deleted. Tests overrides setUp's cascade patch with empty."""
        self._cascade_patch.stop()
        with patch(
            "app.services.reports.config_validator._resolve_setting_value",
            new=AsyncMock(return_value=None),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                await validate_reporting_config(_FakeDB(_seed_rows()))
        msg = str(ctx.exception)
        # Error names the app slug + the missing key so the operator knows
        # which Alembic migration row is missing.
        self.assertIn("narrative", msg.lower())
        # At least one seeded app's slug must appear in the error.
        self.assertTrue(
            any(app["slug"] in msg for app in APP_SEEDS),
            f"Expected at least one app slug in error message:\n{msg}",
        )
        # Restart the cleanup-tracked patch so addCleanup tearDown still works.
        self._cascade_patch = _patch_cascade_resolved()
        self._cascade_patch.start()
        self.addCleanup(self._cascade_patch.stop)

    async def test_app_without_narrative_key_skips_cascade_check(self):
        """An app whose narrativeTemplateKey is unset must NOT require a
        cascade lookup. (The aiSummary.enabled flag is intentionally NOT a
        skip condition — see the test below.)"""
        # Mock returns None for everything — would normally fail check 8.
        self._cascade_patch.stop()

        slug, cfg = _row_for("voice-rx")
        cfg["analytics"]["assets"]["narrativeTemplateKey"] = None

        with patch(
            "app.services.reports.config_validator._resolve_setting_value",
            new=AsyncMock(return_value=None),
        ):
            await validate_reporting_config(_FakeDB([(slug, cfg)]))  # must not raise

        # Restart cleanup-tracked patch.
        self._cascade_patch = _patch_cascade_resolved()
        self._cascade_patch.start()
        self.addCleanup(self._cascade_patch.stop)

    async def test_ai_summary_disabled_does_NOT_skip_cascade_check(self):
        """Regression gate for the wrong-gate bug fixed 2026-05-18: validator
        used to gate on aiSummary.enabled, which would skip the cascade check
        when an app turned off aiSummary but kept a report_config with
        narrative.enabled=true. Runtime would then call the LLM with
        system_prompt=None and silently degrade. The cascade must be enforced
        whenever narrativeTemplateKey is set, regardless of aiSummary."""
        self._cascade_patch.stop()

        slug, cfg = _row_for("voice-rx")
        cfg["analytics"]["singleRun"]["aiSummary"]["enabled"] = False
        # narrativeTemplateKey stays set — operator's promise to provide a row.

        with patch(
            "app.services.reports.config_validator._resolve_setting_value",
            new=AsyncMock(return_value=None),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                await validate_reporting_config(_FakeDB([(slug, cfg)]))
        self.assertIn("narrativeTemplateKey", str(ctx.exception))
        self.assertIn("cascade", str(ctx.exception).lower())

        self._cascade_patch = _patch_cascade_resolved()
        self._cascade_patch.start()
        self.addCleanup(self._cascade_patch.stop)


class CrossRunNarrativeSectionTests(unittest.TestCase):
    """Each app's cross_run composition must have a dedicated narrative section
    so the narrative executor inserts the full PlatformCrossRunNarrative payload
    (not just the flattened issues table).  The section id must contain
    'narrative' (narrative_executor.py substring routing) and the id must
    appear in _build_narrative_config outputInsertionPoints."""

    _EXPECTED = {
        "voice-rx": "voice-rx-cross-narrative",
        "kaira-bot": "kaira-cross-narrative",
        "inside-sales": "inside-sales-cross-narrative",
    }

    def _cross_run_config(self, slug: str):
        for seed in APP_SEEDS:
            if seed["slug"] == slug:
                cfg = AppConfig.model_validate(seed["config"])
                return cfg.analytics.cross_run, cfg.analytics.assets
        raise KeyError(slug)

    def _assert_app(self, slug: str, expected_id: str) -> None:
        cross, assets = self._cross_run_config(slug)
        narrative_sections = [s for s in cross.sections if s.type == "narrative"]
        self.assertTrue(
            narrative_sections,
            f"{slug}: cross_run.sections has no type='narrative' entry",
        )
        ids = [s.id for s in narrative_sections]
        self.assertIn(
            expected_id,
            ids,
            f"{slug}: expected narrative section id '{expected_id}' not found in {ids}",
        )
        nc = _build_narrative_config("cross_run", cross, assets)
        self.assertIn(
            expected_id,
            nc["outputInsertionPoints"],
            f"{slug}: '{expected_id}' missing from outputInsertionPoints {nc['outputInsertionPoints']}",
        )

    def test_voice_rx_cross_run_has_narrative_section(self):
        self._assert_app("voice-rx", self._EXPECTED["voice-rx"])

    def test_kaira_bot_cross_run_has_narrative_section(self):
        self._assert_app("kaira-bot", self._EXPECTED["kaira-bot"])

    def test_inside_sales_cross_run_has_narrative_section(self):
        self._assert_app("inside-sales", self._EXPECTED["inside-sales"])

    def test_voice_rx_cross_run_uses_trend_chart_and_insight_panels(self):
        """voice-rx cross_run emits trend_chart + insight_panels, keeps the
        narrative, and drops the flat issues_recommendations section.
        outputInsertionPoints must resolve to the narrative only."""
        cross, assets = self._cross_run_config("voice-rx")
        types_by_id = {s.id: s.type for s in cross.sections}
        self.assertEqual(types_by_id.get("voice-rx-cross-metrics"), "trend_chart")
        self.assertEqual(types_by_id.get("voice-rx-cross-insights"), "insight_panels")
        self.assertIn("voice-rx-cross-narrative", types_by_id)
        self.assertNotIn("issues_recommendations", set(types_by_id.values()))
        self.assertNotIn("voice-rx-cross-issues", types_by_id)

        nc = _build_narrative_config("cross_run", cross, assets)
        self.assertEqual(nc["outputInsertionPoints"], ["voice-rx-cross-narrative"])

    def test_kaira_cross_run_uses_trend_chart_and_insight_panels(self):
        """Kaira cross_run emits the richer trend_chart + insight_panels sections,
        keeps the dedicated narrative, and drops the flat issues_recommendations.
        With the issues section removed, outputInsertionPoints is the narrative
        only — the full PlatformCrossRunNarrative renders there."""
        cross, assets = self._cross_run_config("kaira-bot")
        types_by_id = {s.id: s.type for s in cross.sections}
        self.assertEqual(types_by_id.get("kaira-cross-trend"), "trend_chart")
        self.assertEqual(types_by_id.get("kaira-cross-insights"), "insight_panels")
        self.assertIn("kaira-cross-narrative", types_by_id)
        self.assertNotIn("issues_recommendations", set(types_by_id.values()))
        self.assertNotIn("kaira-cross-issues", types_by_id)

        nc = _build_narrative_config("cross_run", cross, assets)
        self.assertEqual(nc["outputInsertionPoints"], ["kaira-cross-narrative"])

    def test_narrative_section_placed_after_summary_cards(self):
        """Narrative section must immediately follow the summary_cards entry."""
        for slug, narrative_id in self._EXPECTED.items():
            cross, _ = self._cross_run_config(slug)
            ids = [s.id for s in cross.sections]
            summary_idx = next(
                (i for i, s in enumerate(cross.sections) if s.type == "summary_cards"), None
            )
            self.assertIsNotNone(summary_idx, f"{slug}: no summary_cards section found")
            self.assertEqual(
                ids[summary_idx + 1],
                narrative_id,
                f"{slug}: narrative section must be at index {summary_idx + 1}, got {ids}",
            )


if __name__ == "__main__":
    unittest.main()

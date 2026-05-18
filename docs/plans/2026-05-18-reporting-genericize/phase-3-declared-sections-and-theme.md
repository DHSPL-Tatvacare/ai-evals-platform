# Reporting genericization — Phase 3 (declared section contracts + theme palette by config)

**Status:** done
**Branch:** `feat/llm-credentials-cleanup` (stacked on Phases 1+2)
**Design doc:** `/Users/dhspl/Programs/tc-work/tatvacare-obsidian/Projects/ai-evals-platform/Designs/reporting-pipeline-genericization.md`
**Closes:** G2 + producer half of G3

## Why

Two structural concerns remain after Phases 1+2:

1. **G3 producer half.** Phase 1 boot validator only proves that
   `export.sectionIds ⊆ sections[].id`. It does NOT prove that the producer
   (the `*ReportService` subclass + narrative executor + composer) actually
   knows how to emit each `sections[].id`. A config-only edit that adds
   `kaira-extra-rollup` to the seed silently produces a blank card forever —
   the composer drops it because no payload key matches.
2. **G2 theme palette.** `document_composer.py:39-88` hardcodes a per-variant
   `PrintThemeTokenSet` dict (`'kaira-run-v1'`, `'inside-sales-run-v1'`, …).
   The `export.documentVariant` string IS config-driven; the palette behind
   it is not. Renaming the variant in config without updating the composer
   silently falls back to the `_DEFAULT_THEME`.

## What ships

### Backend EDITED (8)

- `backend/app/schemas/app_analytics_config.py` — adds `PrintThemeTokens`
  (Pydantic mirror of `PrintThemeTokenSet`; defined here so the schema module
  stays free of `services/` imports) and `theme: PrintThemeTokens | None = None`
  on `AnalyticsCompositionConfig`. Defaulted None — every existing seeded
  config validates unchanged; document_composer fallback runs until a seed
  populates the field.
- `backend/app/services/reports/analytics_profiles/base.py` — adds
  `declared_single_run_section_ids: tuple[str, ...] = ()` to the
  `AnalyticsProfile` dataclass. Empty tuple is the opt-out sentinel — used by
  future cross-run-only profiles and in-development profiles.
- `backend/app/services/reports/analytics_profiles/kaira.py` — declares the
  9 ids the producer emits (6 from `adapt_kaira_run_report`, 3 inserted by
  `narrative_executor.execute_narrative_generation` when narrative runs).
- `backend/app/services/reports/analytics_profiles/inside_sales.py` —
  declares 7 ids (5 from adapter, 2 from narrative executor).
- `backend/app/services/reports/analytics_profiles/voice_rx.py` — declares
  6 ids (all from inline `_build_payload`; voice-rx does not use the narrative
  executor, see plan L2a).
- `backend/app/services/reports/config_validator.py` — new check 8:
  `declared_section_ids ⊇ configured_section_ids` when the profile declares a
  non-empty tuple. Hoisted `get_analytics_profile` to a module-level import
  so the empty-declared opt-out test can patch it.
- `backend/app/services/reports/document_composer.py` — `compose_document`
  accepts an additional `composition_theme: PrintThemeTokens | None = None`.
  Theme resolution: `composition_theme → variant-dict fallback → presentation
  theme_tokens overrides`. The variant dict stays — removal is a separate PR
  after every app's seed populates `theme`.
- `backend/app/services/reports/report_generation_service.py` — passes
  `analytics_config.single_run.theme` (and `cross_run.theme` on the cross-run
  path) to all three `compose_document` call sites.
- `backend/app/services/reports/voice_rx_report_service.py` — passes
  `analytics_config.single_run.theme` to both `compose_document` call sites.

### Tests EDITED (1)

- `backend/tests/test_reporting_config_validator_unittest.py` — adds 3 tests
  for the new check (positive: all seeded apps pass; negative: configured-not-
  in-declared fails; opt-out: empty-tuple profile skips the check).

### Out of scope (deferred per design doc)

- `APP_SEEDS` theme populate — kept fallback-driven for this commit; each
  app's seed migration becomes a separate PR with a visual-regression PDF
  check against `eval-report-aad2c6e3.pdf`.
- `_THEMES_BY_VARIANT` deletion — same follow-up.
- Voice-rx producer convergence (L2a, plan calls this explicitly out of scope).
- Cross-run `declared_section_ids` — Phase 3b follow-up per open question 2.
- Fixture-based "declaration is truthful at runtime" tests — Phase 5 G7.

## Verification

1. `pytest backend/tests/test_reporting_config_validator_unittest.py -v` → 18/18 green
2. Adjacent regression sweep `pytest backend/tests/test_report_*.py
   backend/tests/test_reporting_*.py` → 51 pass, 3 pre-existing failures in
   `test_reports_blueprint_save_unittest.py` (unrelated; verified on `75f7385`
   in Phase 1)
3. `python -c "import app.main"` → main imports cleanly with new validator check
4. **Manual smoke (user-driven):** boot the backend, confirm validator passes;
   try setting `analytics.profile.kaira_v1.declared_single_run_section_ids = ()`
   in a local clone of `kaira.py` to confirm the validator skips. Revert.

## Architecture note

After Phase 3 the seam between **what the config declares** and **what the
producer guarantees** is enforceable at boot. A future workflow:

1. Engineer adds a section to a profile's `declared_single_run_section_ids`
   AND teaches the producer to emit a payload for it.
2. PM/designer adds the section to `app.config.analytics.single_run.sections`
   via seed.
3. Boot validator confirms `(2) ⊆ (1)`.
4. Phase 5 fixture test confirms the producer actually emits the new id at
   runtime.

Step 1 without step 4 catches obvious typos; the runtime check catches the
"declared but never emitted" class — see Phase 5 plan.

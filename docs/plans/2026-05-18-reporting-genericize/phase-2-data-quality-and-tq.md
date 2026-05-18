# Reporting genericization — Phase 2 (data_quality + narrative_status + ReportTab TQ migration)

**Status:** done
**Branch:** `feat/llm-credentials-cleanup` (stacked on Phase 1 commit `75f7385`)
**Design doc:** `/Users/dhspl/Programs/tc-work/tatvacare-obsidian/Projects/ai-evals-platform/Designs/reporting-pipeline-genericization.md`
**Closes:** G5 + G6 + G8

## Why

Three holes the renderer can't see today:

1. **G5** — `inside_sales_report_service.py:147-149` returns `({}, {})` on a missing evaluator schema and the aggregator runs against an empty rubric → blank dimension / compliance cards. Kaira `summary.get("avg_intent_accuracy"/"correctness_verdicts"/"efficiency_verdicts")` defaults silently → blank health score. Voice-rx `summary.get('overall_accuracy'/...)` defaults to `0` → blank metric cards indistinguishable from a real zero.
2. **G6** — `_compose_single_run_payload` runs narrative through the generic `execute_narrative_generation`. Today: enabled → maybe runs → maybe completes. Artifact metadata carries no flag for `disabled` / `skipped_no_model` / `completed`, so downstream readers can't distinguish them.
3. **G8** — `ReportTab.tsx` declares 15 useStates including three pure server-data fields (`configs`, `reportRuns`, `report`) wired via three fetch `useEffect`s. Mount/unmount cycles refetch warm data; switching `reportId` produces a waterfall.

## What ships

### Backend (commit 1)

**New:**
- `backend/app/services/reports/contracts/data_quality.py` — `DataQualityReport { overall, missing_inputs, section_status }`
- `backend/app/services/reports/data_quality_finalizer.py` — `finalize_data_quality(...)` runs at the composition boundary; only place that sees configured + produced + composed + exported section-id sets together
- `backend/tests/test_reporting_data_quality_unittest.py` — 10 tests (finalizer truth-table + contract round-trip + legacy-fixture regression)

**Edited:**
- `backend/app/services/reports/contracts/run_report.py` — adds `data_quality: DataQualityReport = Field(default_factory=...)` AND `narrative_status` / `narrative_error` on `PlatformReportMetadata`. All defaulted — `cache_validation.py:16` would 409 every cached artifact otherwise.
- `backend/app/services/reports/report_generation_service.py` — populates `metadata.narrative_status` at the `_compose_single_run_payload` boundary (`disabled` when `narrative_config.enabled=False`, `skipped_no_model` when `_create_logging_llm` returns `(None, None, None)`, `completed` after a successful `execute_narrative_generation`); calls finalizer to fill `section_status`. `failed` is reserved — executor failures still surface as job failures today.
- `backend/app/services/reports/report_service.py` — kaira emits markers for missing `summary.avg_intent_accuracy / correctness_verdicts / efficiency_verdicts`
- `backend/app/services/reports/inside_sales_report_service.py` — emits markers when `_load_evaluator_schemas` falls through to empty (`evaluator_id` / `evaluator_id:invalid` / `evaluator_schema:db_load_failed`). Signature widened to return 3-tuple `(schemas, names, missing_inputs)`.
- `backend/app/services/reports/voice_rx_report_service.py` — emits markers for missing `summary.overall_accuracy / extraction_recall / extraction_precision / overall_score` and missing `run.result`

### Frontend (commit 2)

**New:**
- `src/features/reports/queries/reportsQueries.ts` — `useReportConfigs(appId, scope)` (60 s stale), `useReportRuns(filters)` (30 s stale, `refetchOnWindowFocus`), `useReportRunArtifact(reportRunId)` (immutable, `Infinity` stale); local `reportKeys` factory + imperative `invalidateReportConfigs` / `invalidateReportRuns` helpers. Pattern mirrors `src/features/orchestration/queries/referenceData.ts`.

**Edited:**
- `src/types/platformReports.ts` — adds `DataQualityReport` + `NarrativeStatus` types; `dataQuality?` on `PlatformRunReportPayload`; `narrativeStatus?` / `narrativeError?` on `PlatformReportMetadata`. Optional + normalized in renderer so older cached artifacts deserialize unchanged.
- `src/features/analytics/components/PlatformReportRenderer.tsx` — adds `<DataQualityBanner>` (uses existing `CalloutBox`) above `headerCard` in both render paths (`:1046`, `:1058`). Banner returns `null` when `dataQuality.overall === 'complete'` AND `narrativeStatus ∈ {undefined, 'completed'}`. In print mode the banner mounts a sibling `<div class="report-partial-watermark">PARTIAL</div>` picked up by the print CSS.
- `src/features/evalRuns/components/report/report-print.css` — `.report-partial-watermark` rule inside the `@media print` block: faint 22°-rotated "PARTIAL" overlay so a printed page survives the banner scrolling off.
- `src/features/evalRuns/components/report/ReportTab.tsx` — **deleted**: `configs` / `reportRuns` / `report` / `status` / `error` `useState`s; `loadConfigs` / `loadReportRuns` / `loadSelectedArtifact` / `syncModelSelectionFromReport` callbacks; the 3 fetch `useEffect`s (lines 335, 362, 386). **Added**: 3 TQ hook calls; small `useEffect`s that default `selectedReportId` / `selectedReportRunId` when the query data changes; `mutationStatus` / `mutationError` local state for the generate/poll lifecycle; derived `status` / `error` `useMemo`s from query + mutation state. **Kept imperative**: `submitAndPollJob`, PDF blob download, the job-progress trio (`progressMsg` / `queuePosition` / `jobPhase`). Mutation handlers invalidate `reportKeys.runs` on terminal success; `ManageBlueprintsSlideOver.onConfigsChanged` invalidates `reportKeys.configs`.

## Out of scope (per design doc)

- Cross-run `data_quality` (single-run only — mirrors Phase 1)
- Retry-once for narrative (open question 4)
- Catching executor failures to emit `narrative_status='failed'` — kept reserved
- Stored `report_configurations.narrative_config` row validation (Phase 1 SoC note)
- `PrintReportRun.tsx` TQ migration (one-shot route-param fetch; not worth migrating for G8)
- `ManageBlueprintsSlideOver.tsx` internal migration (its API stays `onConfigsChanged`; only the caller invalidates)

## Verification

1. `pytest backend/tests/test_reporting_data_quality_unittest.py -v` → 10/10 green
2. Adjacent regression sweep `pytest backend/tests/test_report_*.py backend/tests/test_reporting_*.py` → 72 pass, 3 pre-existing failures in `test_reports_blueprint_save_unittest.py` unrelated to Phase 2 (verified by re-running on the pre-Phase-2 commit `75f7385`)
3. `npx tsc -b --noEmit` → exit 0
4. **Manual browser smoke** (user-driven, not blocking commit): generate one inside-sales report end-to-end; confirm (a) runs list refreshes on completion without a page reload, (b) the banner appears when `data_quality.overall != 'complete'`, (c) PDF export still downloads, (d) switching the blueprint dropdown does not refetch warm data

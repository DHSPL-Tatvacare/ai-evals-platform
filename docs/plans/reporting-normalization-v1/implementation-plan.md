# Reporting Normalization v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the analytics/reporting layer into a config-driven, scalable backbone that supports single-run reports, cross-run analytics, AI summaries, and Playwright-backed PDF export without frontend app hardcoding.

**Architecture:** Treat reporting as a platform contract, not a collection of app-specific pages. Backend analytics profiles compute domain metrics, shared composers assemble canonical section/document payloads, app config declares composition and capabilities, frontend composers render shared section components, and one shared HTML renderer produces print documents for Playwright export.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL JSONB, Pydantic/CamelModel, React, TypeScript, Zustand, Playwright PDF generation, background jobs via `job_worker.py`

---

## Guardrails

- Keep long-running report generation job-backed. No component polling loops beyond existing job polling abstractions.
- Keep frontend as a thin client. Analytics computation, report assembly, asset resolution, and export HTML generation stay on the backend.
- Do not encode domain-specific analytics math in app config.
- Do not preserve app-specific frontend registries as a permanent compatibility layer.
- Do not introduce new raw HTML template functions per app.
- Preserve the current provider/model selector UX and metadata-sync behavior from `src/features/evalRuns/components/report/ReportTab.tsx`.
- Normalize and harden narrative prompt/schema contracts; prompt text alone is not the contract.
- Preserve current Kaira and Inside Sales report intent and coverage during migration.
- Bring Voice Rx onto the canonical backbone even if its first normalized report has fewer sections than Kaira and Inside Sales.
- Use app config for structure/capabilities and settings-backed assets for long-form report-side content.
- Prefer atomic cache invalidation/regeneration over long compatibility shims.

---

## Phase Map

1. Contract freeze and touchpoint inventory
2. App config analytics schema and backend profile registry
3. Canonical report and print document contracts
4. Backend shared composition pipeline and asset resolution
5. PDF/export normalization on shared HTML renderer
6. Frontend shared report composers and section library
7. Kaira + Inside Sales migration to canonical contracts
8. Voice Rx onboarding, cleanup, docs, and verification

---

## File Map

### Backend config / models / routes

- Modify: `backend/app/models/app.py`
- Modify: `backend/app/routes/apps.py`
- Modify: `backend/app/models/evaluation_analytics.py`
- Modify: `backend/app/routes/reports.py`
- Create: `backend/app/schemas/app_analytics_config.py`
- Create: `backend/app/services/reports/analytics_profiles/base.py`
- Create: `backend/app/services/reports/analytics_profiles/registry.py`
- Create: `backend/app/services/reports/analytics_profiles/kaira.py`
- Create: `backend/app/services/reports/analytics_profiles/inside_sales.py`
- Create: `backend/app/services/reports/analytics_profiles/voice_rx.py`

### Backend report composition / assets / export

- Create: `backend/app/services/reports/contracts/report_sections.py`
- Create: `backend/app/services/reports/contracts/run_report.py`
- Create: `backend/app/services/reports/contracts/cross_run_report.py`
- Create: `backend/app/services/reports/contracts/print_document.py`
- Create: `backend/app/services/reports/contracts/run_narrative.py`
- Create: `backend/app/services/reports/contracts/cross_run_narrative.py`
- Create: `backend/app/services/reports/report_composer.py`
- Create: `backend/app/services/reports/document_composer.py`
- Create: `backend/app/services/reports/asset_resolver.py`
- Create: `backend/app/services/reports/html_renderer.py`
- Create: `backend/app/services/reports/narrative_contracts/base.py`
- Create: `backend/app/services/reports/narrative_prompt_builders/__init__.py`
- Modify: `backend/app/services/reports/base_report_service.py`
- Modify: `backend/app/services/reports/report_service.py`
- Modify: `backend/app/services/reports/inside_sales_report_service.py`
- Modify: `backend/app/services/reports/narrator.py`
- Modify: `backend/app/services/reports/inside_sales_narrator.py`
- Modify: `backend/app/services/reports/cross_run_narrator.py`
- Modify: `backend/app/services/reports/cross_run_aggregator.py`
- Modify: `backend/app/services/reports/inside_sales_cross_run.py`
- Retire/replace: `backend/app/services/reports/registry.py`
- Retire/replace: `backend/app/services/reports/pdf_template.py`
- Retire/replace: `backend/app/services/reports/inside_sales_pdf_template.py`
- Retire/replace: `backend/app/services/reports/inside_sales_schemas.py`
- Modify: `backend/app/services/reports/prompts/production_prompts.py`

### Jobs / caching

- Modify: `backend/app/services/job_worker.py`
- Modify: `backend/app/models/evaluation_analytics.py`
- Modify: `backend/tests/test_analytics_registry_unittest.py`
- Modify: `backend/tests/test_cross_run_aggregators_unittest.py`
- Create: `backend/tests/test_report_contracts.py`
- Create: `backend/tests/test_report_composer.py`
- Create: `backend/tests/test_print_document_renderer.py`
- Create: `backend/tests/test_report_asset_resolver.py`
- Create: `backend/tests/test_reporting_routes.py`
- Create: `backend/tests/test_reporting_jobs.py`

### Frontend config / API / stores / types

- Modify: `src/types/app.types.ts`
- Modify: `src/services/api/appsApi.ts`
- Modify: `src/stores/appStore.ts`
- Modify: `src/services/api/reportsApi.ts`
- Modify: `src/stores/crossRunStore.ts`
- Create: `src/types/platformReports.ts`
- Retire/replace: `src/types/reports.ts`
- Retire/replace: `src/types/crossRunAnalytics.ts`
- Retire/replace: `src/types/insideSalesReport.ts`
- Retire/replace: `src/types/insideSalesCrossRun.ts`

### Frontend report composition / pages

- Create: `src/features/analytics/composers/RunReportComposer.tsx`
- Create: `src/features/analytics/composers/CrossRunComposer.tsx`
- Create: `src/features/analytics/components/ReportGenerationShell.tsx`
- Create: `src/features/analytics/sections/ReportSummaryCardsSection.tsx`
- Create: `src/features/analytics/sections/ReportNarrativeSection.tsx`
- Create: `src/features/analytics/sections/ReportMetricBreakdownSection.tsx`
- Create: `src/features/analytics/sections/ReportDistributionSection.tsx`
- Create: `src/features/analytics/sections/ReportComplianceSection.tsx`
- Create: `src/features/analytics/sections/ReportHeatmapSection.tsx`
- Create: `src/features/analytics/sections/ReportEntitySlicesSection.tsx`
- Create: `src/features/analytics/sections/ReportFlagsSection.tsx`
- Create: `src/features/analytics/sections/ReportIssuesSection.tsx`
- Create: `src/features/analytics/sections/ReportExemplarsSection.tsx`
- Create: `src/features/analytics/sections/ReportPromptGapSection.tsx`
- Modify: `src/features/analytics/AppReportTab.tsx`
- Modify: `src/features/analytics/AnalyticsDashboardPage.tsx`
- Retire/replace: `src/features/analytics/registry.tsx`
- Retire/replace: `src/features/analytics/KairaCrossRunDashboard.tsx`
- Retire/replace: `src/features/analytics/InsideSalesCrossRunDashboard.tsx`
- Retire/replace: `src/features/evalRuns/components/report/KairaReportView.tsx`
- Retire/replace: `src/features/insideSales/components/report/InsideSalesReportView.tsx`

### Shared widgets to preserve or fold into section library

- Modify/reuse: `src/components/report/DimensionBreakdownChart.tsx`
- Modify/reuse: `src/components/report/HeatmapTable.tsx`
- Modify/reuse: `src/components/report/FlagStatsPanel.tsx`
- Modify/reuse: `src/components/report/ComplianceGatesPanel.tsx`
- Modify/reuse: `src/features/evalRuns/components/crossRun/IssuesTab.tsx`
- Modify/reuse: `src/features/evalRuns/components/crossRun/StatCardsRow.tsx`
- Modify/reuse: `src/features/evalRuns/components/crossRun/HealthTrendsTab.tsx`
- Modify/reuse: `src/features/evalRuns/components/crossRun/ComplianceHeatmapTab.tsx`
- Modify/reuse: `src/features/evalRuns/components/crossRun/AdversarialHeatmapTab.tsx`

### Pages / docs / guides

- Modify: `src/features/evalRuns/pages/RunDetail.tsx`
- Modify: `src/features/insideSales/pages/InsideSalesRunDetail.tsx`
- Modify: `src/features/evalRuns/pages/Dashboard.tsx`
- Modify: `src/features/insideSales/pages/InsideSalesDashboard.tsx`
- Modify: `src/features/guide/pages/Pipelines.tsx`
- Modify: `docs/PROJECT 101.md`

---

## Phase 1: Contract Freeze and Touchpoint Inventory

**Objective:** Lock the current reporting semantics, collect fixtures, and make regressions measurable before changing contracts.

**Primary files:**

- Modify: `docs/plans/reporting-normalization-v1/design-spec.md`
- Create: `backend/tests/test_report_contracts.py`
- Create: `backend/tests/fixtures/reports/`
- Create: `src/features/analytics/__tests__/fixtures/`

**Implementation scheme:**

- Capture representative cached report payloads for Kaira and Inside Sales.
- Capture representative PDF HTML output for both current exporters.
- Define the canonical section inventory required to preserve current UX meaning.
- Freeze which current report concepts are product requirements versus implementation artifacts.

**Checklist:**

- [ ] Build a touchpoint matrix mapping every route, job, cache scope, frontend page, and export function involved in reporting.
- [ ] Save golden fixtures for at least:
  - Kaira standard run
  - Kaira adversarial run
  - Inside Sales run
  - Kaira cross-run analytics
  - Inside Sales cross-run analytics
- [ ] Record current PDF block coverage so the new shared renderer can be compared structurally.
- [ ] Enumerate all section concepts the new canonical contract must support.
- [ ] Record all known app-specific report assets and hardcoded prompt references.
- [ ] Record current `ReportTab` provider/model selector behavior, metadata sync behavior, and credential gating as migration invariants.
- [ ] Record current narrator prompt/schema entry points and where they diverge by app.

**Verification:**

- Run: `pytest backend/tests/test_analytics_registry_unittest.py backend/tests/test_cross_run_aggregators_unittest.py -v`

**Exit gate:**

- The current reporting behavior is documented well enough that migration regressions can be detected intentionally rather than discovered accidentally.

---

## Phase 2: App Config Analytics Schema and Backend Profile Registry

**Objective:** Make reporting capability and composition app-config-driven, while moving app-specific computation behind backend analytics profiles.

**Primary files:**

- Modify: `backend/app/models/app.py`
- Modify: `backend/app/routes/apps.py`
- Create: `backend/app/schemas/app_analytics_config.py`
- Create: `backend/app/services/reports/analytics_profiles/base.py`
- Create: `backend/app/services/reports/analytics_profiles/registry.py`
- Create: `backend/app/services/reports/analytics_profiles/kaira.py`
- Create: `backend/app/services/reports/analytics_profiles/inside_sales.py`
- Create: `backend/app/services/reports/analytics_profiles/voice_rx.py`
- Modify: `src/types/app.types.ts`
- Modify: `src/services/api/appsApi.ts`
- Modify: `src/stores/appStore.ts`

**Implementation scheme:**

- Extend app config with an `analytics` subtree.
- Introduce backend analytics profile registration keyed by profile name, not by frontend app ID logic.
- Seed analytics config for `voice-rx`, `kaira-bot`, and `inside-sales`.
- Extend analytics config with narrative/export capability wiring, without moving provider/model choice into app config.

**Checklist:**

- [ ] Define `AppAnalyticsConfig` backend and frontend schemas.
- [ ] Add `profile` and capability flags for all active apps.
- [ ] Add single-run, cross-run, and export composition arrays to app config.
- [ ] Add narrative asset keys and export config hooks to app analytics config.
- [ ] Seed Voice Rx with an explicit reporting config, even if some capabilities are initially disabled.
- [ ] Replace frontend analytics registry dependence with app config reads where possible.
- [ ] Keep backend profile registration internal; the frontend should only see config, never adapter class names.

**Verification:**

- Run: `pytest backend/tests/test_apps_routes.py -v`
- Run: `npm test -- appStore`

**Exit gate:**

- App config expresses analytics capabilities and composition, and all active apps expose an explicit analytics config contract.

---

## Phase 3: Canonical Report and Print Document Contracts

**Objective:** Define the payloads that become the new public analytics contract.

**Primary files:**

- Create: `backend/app/services/reports/contracts/report_sections.py`
- Create: `backend/app/services/reports/contracts/run_report.py`
- Create: `backend/app/services/reports/contracts/cross_run_report.py`
- Create: `backend/app/services/reports/contracts/print_document.py`
- Create: `src/types/platformReports.ts`
- Modify: `backend/app/models/evaluation_analytics.py`

**Implementation scheme:**

- Define canonical discriminated unions for sections and print document blocks.
- Add schema versioning and analytics kind metadata.
- Update `evaluation_analytics` conventions so cached payloads are clearly versioned and self-describing.
- Define explicit narrative output contracts alongside run/cross-run report contracts.

**Checklist:**

- [ ] Define canonical metadata models shared by single-run and cross-run payloads.
- [ ] Define section union types with explicit `type`, `variant`, `title`, and `data`.
- [ ] Define print document block union types for Playwright export.
- [ ] Define run-level and cross-run narrative contracts with explicit JSON schema ownership.
- [ ] Add cache schema version rules and invalidation strategy.
- [ ] Document which current app-specific fields map into which canonical sections.
- [ ] Decide which section data is screen-only, print-only, or dual-purpose.

**Verification:**

- Run: `pytest backend/tests/test_report_contracts.py -v`
- Run: `npx tsc -b`

**Exit gate:**

- The platform has one run-report contract family, one cross-run contract family, and one print document family.

---

## Phase 4: Backend Shared Composition Pipeline and Asset Resolution

**Objective:** Replace per-app payload assembly with backend adapters feeding shared composers.

**Primary files:**

- Create: `backend/app/services/reports/report_composer.py`
- Create: `backend/app/services/reports/document_composer.py`
- Create: `backend/app/services/reports/asset_resolver.py`
- Modify: `backend/app/services/reports/base_report_service.py`
- Modify: `backend/app/services/reports/report_service.py`
- Modify: `backend/app/services/reports/inside_sales_report_service.py`
- Modify: `backend/app/services/reports/cross_run_aggregator.py`
- Modify: `backend/app/services/reports/inside_sales_cross_run.py`
- Modify: `backend/app/services/reports/prompts/production_prompts.py`

**Implementation scheme:**

- Shared report services orchestrate loading, adapter execution, asset resolution, section composition, and cache write.
- Kaira and Inside Sales adapters emit canonical section input instead of app-specific payloads.
- Prompt references and similar report-side assets resolve through settings-backed keys rather than static module constants.
- Narrator services consume explicit prompt/schema contracts and resolved assets instead of ad hoc prompt modules.

**Checklist:**

- [ ] Create adapter interfaces for single-run and cross-run analytics.
- [ ] Migrate Kaira run analytics to canonical section input.
- [ ] Migrate Inside Sales run analytics to canonical section input.
- [ ] Migrate Kaira cross-run analytics to canonical section input.
- [ ] Migrate Inside Sales cross-run analytics to canonical section input.
- [ ] Implement shared asset resolution for prompt references and narrative-side assets.
- [ ] Move narrative prompt construction behind shared contract builders.
- [ ] Harden Inside Sales narrative generation with an explicit JSON schema contract matching the canonical narrative model.
- [ ] Ensure cross-run AI summary input is assembled server-side from canonical sections instead of trusting frontend-shaped payloads.
- [ ] Remove assumptions that a given app owns a top-level payload family.
- [ ] Keep existing domain math intact while changing assembly shape.

**Verification:**

- Run: `pytest backend/tests/test_report_composer.py backend/tests/test_report_asset_resolver.py backend/tests/test_cross_run_aggregators_unittest.py -v`
- Run: `pytest backend/tests/test_reporting_jobs.py -v`

**Exit gate:**

- Backend services generate canonical run and cross-run payloads for Kaira and Inside Sales without app-specific frontend contracts.

---

## Phase 5: PDF / Export Normalization on Shared HTML Renderer

**Objective:** Preserve Playwright export fidelity while removing app-specific HTML template duplication.

**Primary files:**

- Create: `backend/app/services/reports/html_renderer.py`
- Create: `backend/app/services/reports/print_tokens.py` if needed
- Modify: `backend/app/services/reports/document_composer.py`
- Modify: `backend/app/routes/reports.py`
- Retire/replace: `backend/app/services/reports/pdf_template.py`
- Retire/replace: `backend/app/services/reports/inside_sales_pdf_template.py`
- Modify: `backend/tests/test_print_document_renderer.py`

**Implementation scheme:**

- Convert canonical print documents into self-contained HTML using one renderer.
- Keep Playwright invocation in the route layer.
- Move page layout, section spacing, theme tokens, and page-break behavior into shared print rendering logic.

**Checklist:**

- [ ] Define shared print theme tokens and defaults.
- [ ] Implement block renderers for cover, prose, stat grid, table, heatmap, recommendation list, and entity table.
- [ ] Implement page-break controls at the document block level.
- [ ] Ensure exported HTML is self-contained with no network dependency.
- [ ] Compare structural coverage against current Kaira and Inside Sales exports.
- [ ] Remove per-app raw HTML renderer references from route config.

**Verification:**

- Run: `pytest backend/tests/test_print_document_renderer.py backend/tests/test_reporting_routes.py -v`

**Exit gate:**

- PDF export remains Playwright-backed but is now driven by shared print document contracts and a single HTML renderer.

---

## Phase 6: Frontend Shared Report Composers and Section Library

**Objective:** Replace app-specific analytics pages with shared composers rendering canonical sections.

**Primary files:**

- Create: `src/features/analytics/composers/RunReportComposer.tsx`
- Create: `src/features/analytics/composers/CrossRunComposer.tsx`
- Create: `src/features/analytics/sections/*.tsx`
- Modify: `src/features/analytics/AppReportTab.tsx`
- Modify: `src/features/analytics/AnalyticsDashboardPage.tsx`
- Retire/replace: `src/features/analytics/registry.tsx`
- Modify: `src/services/api/reportsApi.ts`
- Modify: `src/stores/crossRunStore.ts`
- Create: `src/features/analytics/__tests__/RunReportComposer.test.tsx`
- Create: `src/features/analytics/__tests__/CrossRunComposer.test.tsx`
- Create: `src/features/analytics/__tests__/ReportGenerationShell.test.tsx`

**Implementation scheme:**

- Fetch canonical payloads.
- Render sections through one composer per scope.
- Reuse existing low-level report widgets where appropriate, but make section components the real public abstraction.
- Preserve provider/model selection as a shared report-generation shell concern.

**Checklist:**

- [ ] Create section renderer lookup by canonical section type.
- [ ] Move loading/error/empty states into shared shells that read app config analytics capabilities.
- [ ] Adapt `ReportTab` to render canonical payloads instead of app-specific payload generics.
- [ ] Preserve the current provider/model selection UX and metadata sync behavior from `ReportTab`.
- [ ] Keep credential gating behavior and notification flow intact during canonicalization.
- [ ] Update cross-run store and API typing to use canonical payloads.
- [ ] Reuse existing issue/recommendation, heatmap, compliance, and chart widgets under new section wrappers.
- [ ] Keep action controls such as refresh/export in shared shells, not in app-specific pages.

**Verification:**

- Run: `npx tsc -b`
- Run: `npm test -- RunReportComposer CrossRunComposer`

**Exit gate:**

- The frontend no longer needs app-specific analytics registries or app-specific run/cross-run pages to render normalized reporting.

---

## Phase 7: Kaira and Inside Sales Migration

**Objective:** Preserve current UX spirit while cutting Kaira and Inside Sales onto the new backbone.

**Primary files:**

- Modify: `src/features/evalRuns/pages/RunDetail.tsx`
- Modify: `src/features/insideSales/pages/InsideSalesRunDetail.tsx`
- Modify: `src/features/evalRuns/pages/Dashboard.tsx`
- Modify: `src/features/insideSales/pages/InsideSalesDashboard.tsx`
- Retire/replace: `src/features/evalRuns/components/report/KairaReportView.tsx`
- Retire/replace: `src/features/insideSales/components/report/InsideSalesReportView.tsx`
- Retire/replace: `src/features/analytics/KairaCrossRunDashboard.tsx`
- Retire/replace: `src/features/analytics/InsideSalesCrossRunDashboard.tsx`

**Implementation scheme:**

- Match current section coverage and meaning through canonical sections and configured composition.
- Preserve app-specific visual emphasis through section variants and theme tokens, not through separate page implementations.

**Checklist:**

- [ ] Map current Kaira run sections to canonical sections.
- [ ] Map current Kaira cross-run dashboard tabs to canonical sections.
- [ ] Map current Inside Sales run sections to canonical sections.
- [ ] Map current Inside Sales cross-run dashboard tabs to canonical sections.
- [ ] Preserve Kaira prompt-gap analysis and adversarial reporting.
- [ ] Preserve Inside Sales agent slices, compliance, and flag/coaching emphasis.
- [ ] Verify report generation still supports provider/model overrides and correctly reflects the chosen model in cached metadata.
- [ ] Remove shape coercion that forces Inside Sales through Kaira-centric shared props.

**Verification:**

- Run: `npm test -- analytics`
- Manual QA:
  - Kaira standard run report
  - Kaira adversarial run report
  - Kaira cross-run dashboard
  - Inside Sales run report
  - Inside Sales cross-run dashboard
  - PDF export for both apps

**Exit gate:**

- Kaira and Inside Sales run entirely on canonical report and export contracts with no app-specific frontend analytics pages remaining on the critical path.

---

## Phase 8: Voice Rx Onboarding, Cleanup, Docs, and Verification

**Objective:** Finish the normalization by bringing Voice Rx under the same backbone and removing legacy assumptions.

**Primary files:**

- Create: `backend/app/services/reports/analytics_profiles/voice_rx.py`
- Modify: `src/features/voiceRx/*` reporting entry points as needed
- Modify: `docs/PROJECT 101.md`
- Modify: `src/features/guide/pages/Pipelines.tsx`
- Retire/replace: legacy report registries and old schema files

**Implementation scheme:**

- Add a first-pass Voice Rx analytics profile on canonical contracts.
- Update docs, guides, and diagrams to reference the normalized system.
- Remove legacy registries, old payload types, and app-specific PDF templates.

**Checklist:**

- [ ] Seed Voice Rx analytics config and profile wiring.
- [ ] Implement Voice Rx canonical run report section set.
- [ ] Decide whether Voice Rx cross-run analytics ships in v1 or remains config-disabled but structurally supported.
- [ ] Remove legacy backend analytics registry if no longer needed.
- [ ] Remove legacy frontend analytics registry and old payload type families.
- [ ] Update architecture docs and guide diagrams to describe the new reporting backbone.
- [ ] Re-run full analytics and export verification.

**Verification:**

- Run: `pytest backend/tests/test_reporting_routes.py backend/tests/test_reporting_jobs.py -v`
- Run: `npm run lint`
- Run: `npx tsc -b`

**Exit gate:**

- All active apps participate in the normalized analytics system, legacy hardcoded reporting paths are removed, and docs/tests describe the new backbone accurately.

---

## Known Risk Areas

- Hidden readers of old payload shapes in frontend utility code or exports
- Narrative generation prompts implicitly tied to old payload schemas
- Regressions in the provider/model picker UX while moving to a shared analytics shell
- PDF regressions from page-break and table layout differences
- Cache invalidation gaps when app config or report assets change
- Voice Rx analytics scope ambiguity if not explicitly defined before Phase 8

## Required Verification Matrix

- Single-run Kaira report generation, refresh, and PDF export
- Single-run Kaira adversarial report generation, refresh, and PDF export
- Kaira cross-run refresh and AI summary
- Single-run Inside Sales report generation, refresh, and PDF export
- Inside Sales cross-run refresh and AI summary
- Provider/model picker behavior for initial generate and refresh flows
- Metadata sync of chosen provider/model after cache load and regeneration
- Narrative contract validation for Kaira run, Inside Sales run, and cross-run summaries
- Voice Rx report generation on canonical payload when onboarded
- App config loading for all three apps with analytics subtree
- Cache invalidation and regeneration after schema version change

---

## Completion Criteria

The implementation is complete only when:

- no frontend analytics page chooses components via hardcoded app registries
- no backend report route chooses payload families via hardcoded app IDs
- one canonical run report contract exists
- one canonical cross-run contract exists
- one canonical print document contract exists
- PDF export uses one shared HTML renderer
- Kaira, Inside Sales, and Voice Rx are represented in app analytics config
- report-side assets are resolved through normalized config/settings paths
- tests cover adapters, composers, routes, jobs, and export rendering

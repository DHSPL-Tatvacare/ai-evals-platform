# Reporting Normalization v1 — Design Spec

**Date:** 2026-04-02
**Status:** Proposed implementation direction
**Scope:** Analytics/reporting rewrite across run-level reports, cross-run analytics, AI summaries, and Playwright-backed PDF export

## Implementation Artifacts

Phase 1 contract-freeze artifacts live in `docs/plans/reporting-normalization-v1/phase-1-inventory.md` and `backend/tests/fixtures/reports/`.

---

## 1. Problem Statement

The platform's analytics layer has a shared shell but not a shared backbone.

- Backend routing is shared, but report generation is selected by app-specific code registry entries.
- Frontend routing is shared, but run reports and cross-run dashboards are still implemented as app-specific React views.
- PDF export is shared only at the Playwright invocation layer; HTML rendering is still per-app template code.
- App config does not currently describe reporting capabilities, section composition, export contracts, or report-side assets.
- `voice-rx` is effectively missing from the analytics system rather than represented as a first-class app with a partial analytics config.

This creates the same problem the platform has been addressing elsewhere:

- app IDs leak into code
- payload contracts diverge by app
- shared UI is limited to low-level widgets rather than page composition
- adding a new app requires code changes in multiple frontend and backend locations
- PDF fidelity and screen composition are maintained by duplicate templates rather than a shared document model
- report-generation LLM prompt and schema contracts are not normalized across narrators

The rewrite must preserve the intent and quality of the current Kaira and Inside Sales reporting experiences, while replacing hardcoded app-specific layering with a configuration-driven, scalable platform contract.

### 1.1 What This Rewrite Must Cover

This is a full rewrite of the analytics layer end to end:

- single-run report generation
- cross-run analytics generation and caching
- AI summary generation for run and cross-run views
- provider/model selection UX for report generation
- report rendering in the frontend
- Playwright-backed PDF export
- report-side content assets that influence analysis and export
- app configuration for analytics capabilities and composition
- cache contracts and versioning
- background jobs for report generation

### 1.2 What This Rewrite Does Not Need To Do

- It does not need frontend drag-and-drop report builders.
- It does not need runtime end-user customization of layouts.
- It does not need to move domain-specific analytics math into config.
- It does not need to preserve old cache payload shapes; caches can be invalidated and regenerated.

### 1.3 Design Constraints From This Repo

- Frontend remains a thin client. All analytics computation, narrative generation, and PDF HTML assembly belong on the backend.
- Long-running report work remains job-backed. No component-level polling loops may be introduced.
- App-specific execution logic may remain in backend service code where the domain truly differs.
- Shared components must not branch on `if (appId === ...)` for layout behavior.
- App config is already becoming the control plane for platform normalization and must now absorb reporting composition.
- `evaluation_analytics` remains the analytics cache store unless a new cache table is strictly necessary. Prefer extending the existing model over adding a competing store.
- The platform is pre-launch. Clean cutovers and cache reseeding are preferred over long backwards-compatibility windows.
- The existing provider/model picker behavior in report generation is part of the product and must survive the rewrite.
- Narrative prompt and JSON schema contracts must be explicit, typed, and normalized rather than left as ad hoc prompt modules.

### 1.4 Traceability Rule For This Spec

Every structural decision below names:

- **Upstream impact:** current routes, stores, caches, services, or templates that force the design
- **Downstream impact:** which APIs, UI composers, jobs, export renderers, and app onboarding flows will change because of the design

If a decision cannot be traced both directions, it is not designed well enough.

---

## 2. Current-State Findings

### 2.1 Shared Shell, Fragmented Core

Current reporting has a common shell in:

- `backend/app/routes/reports.py`
- `backend/app/models/evaluation_analytics.py`
- `src/features/analytics/AppReportTab.tsx`
- `src/features/analytics/AnalyticsDashboardPage.tsx`

But the core is still split by app:

- backend registry mapping app IDs to services, payloads, and PDF renderers
- different single-run payload schemas for Kaira vs Inside Sales
- different cross-run payload schemas for Kaira vs Inside Sales
- different run report components
- different cross-run dashboards
- different HTML templates for PDF export

### 2.2 The Existing Registry Is Not Real Normalization

There is a backend analytics registry and a frontend analytics registry, but both are code-first lookup tables keyed by app ID. That is an integration convenience, not a scalable platform contract.

This means:

- the frontend still knows which report component belongs to each app
- the backend still knows which payload shape belongs to each app
- PDF export remains app-specific HTML functions
- config-driven onboarding of future apps is not possible

### 2.3 Shared Components Already Exist, But Only at the Wrong Level

There are already reusable report widgets:

- dimension breakdown charts
- heatmap tables
- compliance panels
- issue/recommendation panels
- tabs and summary cards

This is useful, but insufficient. The missing layer is a standard report section model and a composer that renders sections declaratively.

### 2.4 PDF Export Has the Same Structural Problem

The platform correctly uses Playwright with self-contained HTML for fidelity and deterministic export, which should be preserved. The problem is not the rendering engine; the problem is that HTML assembly is still app-specific and duplicated.

Today:

- screen composition and print composition are separate implementations
- Kaira PDF is one template
- Inside Sales PDF is another template
- there is no canonical document contract bridging analytics payloads to export

### 2.5 Hardcoded Report-Side Assets Exist Outside App Config

Prompt references used by Kaira report analysis are still static backend constants. That is the same category of problem as hardcoded evaluator/rule/UI contracts and should be normalized with the reporting layer rather than left behind.

### 2.6 Narrative Contracts and Report LLM UX Are Uneven

The report-generation shell already has meaningful behavior:

- provider/model selection for report generation and refresh
- selector state synced back from cached/generated report metadata
- credential gating before generate/refresh

That behavior must be preserved.

At the same time, the narrative layer is inconsistent:

- Kaira run narrative uses an explicit JSON schema
- cross-run AI summary uses an explicit JSON schema
- Inside Sales narrative relies on prompt instructions plus model validation, but not on the same shared schema contract pattern

This means the rewrite must normalize both:

- the user-facing LLM config shell
- the backend prompt/schema contract layer

### 2.7 Worker Contract Has Tightened Beyond What Reporting Documents Today

The job system is no longer a simple queued/background convenience. It now has a DB-backed worker contract with:

- queue metadata promoted to first-class columns
- lease ownership and lease expiry
- heartbeat refresh while a job is running
- retry scheduling for retry-safe job types
- dead-letter semantics when retry budget is exhausted
- startup and periodic recovery of stale jobs and stale eval runs
- cooperative cancellation semantics used by long-running execution paths

Reporting already participates in this model through `generate-report` and `generate-cross-run-report`, but the reporting design has not yet spelled out the consequences:

- report generation must be idempotent under retries
- cache writes must tolerate duplicate execution attempts safely
- routes must not keep a second inline generation path once cutover is complete
- long-running report work must cooperate with cancellation and lease-loss semantics

That mismatch is now a design risk. The normalized reporting backbone must be designed against the real worker contract, not the older "background job" abstraction.

---

## 3. Approaches Considered

### 3.1 Option A: Extract More Shared React Components, Keep Current Payloads

**Summary:** Keep app-specific backend payloads and services, but reuse more UI widgets and clean up the registries.

**Pros:**

- Lowest short-term risk
- Smaller migration
- Faster to land

**Cons:**

- Does not remove app-specific report contracts
- Does not normalize PDF export
- Does not enable future app onboarding by config
- Leaves frontend and backend registry duplication intact

**Decision:** Rejected. This is a cosmetic refactor, not platform normalization.

### 3.2 Option B: One Universal Analytics Payload For Everything

**Summary:** Force every app to emit exactly the same metric model and exactly the same section types, with domain differences flattened aggressively into generic fields.

**Pros:**

- Maximum uniformity
- Simplest frontend renderer once complete

**Cons:**

- Over-normalizes domain-specific analytics
- Risks losing expressive power for Kaira adversarial analytics and Inside Sales coaching slices
- Encourages vague generic contracts that hide important business meaning

**Decision:** Rejected. Too rigid and likely to create a lowest-common-denominator system.

### 3.3 Option C: Canonical Section Contracts + Backend Adapters + Config-Driven Composition

**Summary:** Keep domain-specific analytics computation in backend adapters, but require them to emit canonical report and export sections. Use app config to declare capabilities, section order, section variants, and export composition.

**Pros:**

- Preserves domain-specific computation
- Removes hardcoded frontend app branches
- Generalizes PDF export cleanly
- Scales to future apps without drag-and-drop complexity
- Matches the existing platform normalization direction

**Cons:**

- Requires contract design on both backend and frontend
- Requires coordinated cache and route cutover
- Needs careful migration of Kaira and Inside Sales to avoid regressions

**Decision:** Recommended.

---

## 4. Recommended Architecture

## 4.1 Architecture Summary

The normalized reporting backbone will have five layers:

1. **Analytics app config**
2. **Backend analytics adapters**
3. **Canonical report contracts**
4. **Frontend interpreter on shared reporting component library**
5. **Canonical print document contract + shared HTML renderer**

Only layer 2 remains app-specific in code, and even there the extension point is adapter registration by analytics profile, not frontend branching by app ID.

## 4.2 New Reporting Control Plane in App Config

Add an `analytics` subtree to app config.

It will describe:

- capabilities
- adapter key
- tab composition for single-run reports
- tab composition for cross-run dashboards
- component selection for each section slot
- export options
- AI summary options
- references to report-side assets such as prompt references or narrative assets

### Proposed shape

```ts
interface AppAnalyticsConfig {
  profile: string; // backend adapter profile key, e.g. "kaira_v1", "inside_sales_v1"
  capabilities: {
    singleRunReport: boolean;
    crossRunAnalytics: boolean;
    crossRunAiSummary: boolean;
    pdfExport: boolean;
  };
  singleRun: {
    tabs: AnalyticsTabConfig[];
    export: AnalyticsExportConfig;
  };
  crossRun: {
    tabs: AnalyticsTabConfig[];
    export?: AnalyticsExportConfig;
  };
  assets: {
    promptReferencesKey?: string;
    narrativeTemplateKey?: string;
    glossaryKey?: string;
  };
}
```

Where `AnalyticsTabConfig` is a declarative list of section/component bindings, for example:

```ts
interface AnalyticsTabConfig {
  id: string;
  label: string;
  sections: AnalyticsSectionConfig[];
}

interface AnalyticsSectionConfig {
  id: string;
  type: string; // canonical semantic type
  component: string; // semantic library component key
  title?: string;
  description?: string;
  variant?: string;
}
```

### Decision

Use app config for composition and capability wiring. Use shareable settings for longer-lived report assets and content references.

The frontend must interpret config into tabs and semantic section components. It must not hardcode app-specific report pages, and it must not flatten all apps into one visually-generic renderer.

### Why this split

- App config is the right home for structural composition and capabilities.
- Long-form report assets should be shareable and publishable without code edits.
- This follows the same direction as evaluator/rule normalization: config declares capability; settings provide mutable content.

---

## 5. Canonical Backend Contracts

## 5.1 Do Not Reuse App-Specific Payloads As Platform Contracts

Kaira and Inside Sales can keep different computations, but they must stop emitting unrelated top-level payload families directly to the frontend.

Instead the backend should emit canonical, section-oriented contracts.

## 5.2 Canonical Single-Run Contract

Introduce a canonical `PlatformRunReportPayload`:

```ts
interface PlatformRunReportPayload {
  schemaVersion: 'v1';
  metadata: PlatformReportMetadata;
  sections: PlatformReportSection[];
  exportDocument: PlatformReportDocument;
}
```

Where `PlatformReportSection` is a discriminated union such as:

- `summary_cards`
- `narrative`
- `metric_breakdown`
- `distribution_chart`
- `compliance_table`
- `heatmap`
- `entity_slices`
- `flags`
- `issues_recommendations`
- `exemplars`
- `prompt_gap_analysis`
- `callout`

Each section has:

- `id`
- `type`
- `component`
- `title`
- `description`
- `variant`
- `data`

### Important constraint

`type` identifies the semantic data family.

`component` identifies which reporting-library component should render that section.

These are related but not identical:

- multiple components may render the same canonical `type`
- a specialized component may still live in the common reporting library
- component keys must be semantic, not app-branded

Examples:

- good: `agent_dimension_heatmap`, `exemplar_threads`, `rule_compliance_matrix`
- bad: `kaira_report_view`, `inside_sales_agent_panel`

## 5.3 Canonical Cross-Run Contract

Introduce a canonical `PlatformCrossRunPayload`:

```ts
interface PlatformCrossRunPayload {
  schemaVersion: 'v1';
  metadata: PlatformCrossRunMetadata;
  sections: PlatformReportSection[];
  exportDocument?: PlatformReportDocument;
}
```

This lets cross-run views reuse the same composition model as single-run views rather than living in a separate dashboard-specific world.

## 5.4 Canonical Print Contract

Introduce a canonical `PlatformReportDocument` for export:

```ts
interface PlatformReportDocument {
  schemaVersion: 'v1';
  title: string;
  subtitle?: string;
  theme: PrintThemeTokenSet;
  blocks: PlatformDocumentBlock[];
}
```

Document blocks are print-safe equivalents of report sections:

- `cover`
- `stat_grid`
- `prose`
- `table`
- `heatmap_table`
- `metric_bar_list`
- `recommendation_list`
- `entity_table`
- `page_break`

This separates:

- analytics meaning
- on-screen composition
- print composition

without duplicating app-specific HTML templates.

## 5.5 Asset Resolution Contract

Report-side assets should be resolved by a service before section generation.

Examples:

- prompt references for gap analysis
- narrative instruction templates
- labels/glossaries for exported documents

These are not hardcoded constants in report services anymore. They are resolved through:

- app config asset keys
- settings-backed report asset rows

---

## 6. Backend Service Architecture

## 6.1 Shared Orchestrator, App-Specific Adapter

Replace the current `ReportService` vs `InsideSalesReportService` payload split with a shared orchestration pipeline:

- load source data
- resolve analytics profile
- run app adapter
- assemble canonical sections
- assemble canonical export document
- optionally generate narratives
- cache canonical payload

### New layers

- `analytics_profiles/registry.py`
- `analytics_profiles/base.py`
- `analytics_profiles/kaira.py`
- `analytics_profiles/inside_sales.py`
- `report_composer.py`
- `document_composer.py`
- `asset_resolver.py`

### Rule

App adapters compute domain analytics and emit canonical section input. Shared composers turn those inputs into canonical report/export contracts.

## 6.2 Backend Extension Model

App extensibility remains backend-driven for now.

Adding a new app requires:

- registering a backend analytics profile
- seeding app config with the profile key and section composition
- optionally publishing report assets in settings

It must not require:

- new frontend registry entries
- new ad hoc report pages
- new PDF template functions

## 6.3 Cache Model

Continue using `evaluation_analytics`, but normalize the stored payload shape and add explicit versioning.

### Required additions

- `schema_version` in `analytics_data`
- `analytics_kind` in payload metadata or a dedicated field if needed
- cache invalidation rules when app config analytics profile changes
- cache invalidation rules when report assets change materially

### Preferred cutover

Atomic cutover with cache invalidation/regeneration.

Because the platform is pre-launch, preserving old cached payload shapes adds complexity without product value.

## 6.4 Job Model

Preserve job-backed generation:

- `generate-report`
- `generate-cross-run-report`

But route them through canonical composers and profile adapters.

The cross-run AI summary job should stop accepting app-shaped payload assumptions from the frontend. It should operate on canonical issue/recommendation/trend sections or on a canonical summary input assembled server-side.

### Required worker semantics

- Reporting jobs must remain retry-safe and idempotent. A retry or worker recovery may execute the same report generation path more than once, and the resulting cache state must still be correct.
- Reporting jobs must write progress in a way that remains meaningful across retries, queued retry delays, and resumed polling.
- Reporting jobs must not assume uninterrupted ownership of a run. If lease ownership changes before completion, stale workers must not overwrite final state.
- Reporting generation paths must cooperate with cancellation where the work is long-lived enough to matter, especially across narrative generation, multi-step composition, and future export-side jobs if added.
- Reporting caches must be keyed and written so duplicate attempts converge on the same authoritative row rather than creating divergent report state.
- The normalized system should have one job-backed generation path per reporting workflow. Inline route-side generation is a transitional state and should be removed from the critical path.

### Upstream impact

- `backend/app/services/job_worker.py`
- `backend/app/worker.py`
- `backend/app/models/job.py`
- `backend/app/routes/jobs.py`
- `backend/app/routes/reports.py`
- `backend/app/models/evaluation_analytics.py`

### Downstream impact

- report generation submit/poll UX
- cache invalidation and regeneration behavior
- retry and dead-letter handling for reporting jobs
- stale worker recovery without corrupted report caches
- future onboarding of new analytics profiles without bypassing worker semantics

## 6.5 Narrative Prompt and Schema Contract Layer

Narrative generation must become a first-class contract layer, not a collection of loosely related narrator modules.

### Required normalization

- explicit output models for every narrative family
- explicit JSON schemas for every narrative family
- shared prompt-builder pattern for run and cross-run narratives
- app/profile-specific prompt builders only where framing truly differs
- settings/config-backed asset resolution for long-form prompt references where needed

### Decision

Introduce a narrative contract layer that owns:

- prompt input models
- prompt asset resolution
- JSON schema generation or declaration
- output model validation

Narrator services remain orchestration wrappers over these contracts.

### Why this matters

- safer provider/model swapping during report generation
- fewer hidden prompt/schema assumptions
- easier onboarding of future apps
- better testability than current prompt-text-first implementations

## 6.6 Preserve Existing LLM Config UX in Report Generation

The current report-generation LLM config surface must remain intact in product behavior.

Preserve:

- provider/model chooser for initial generate
- provider/model chooser for refresh/regenerate
- selector sync from cached/generated report metadata
- current credential gating behavior
- the ability to regenerate a report using a different provider/model

The rewrite may move this into a more canonical shared shell, but the experience and semantics must remain as-is.

---

## 7. Frontend Architecture

## 7.1 Replace App Registries With a Config-Driven Interpreter

Remove the frontend analytics registry as the primary integration mechanism.

Instead:

- `AppReportTab` loads a canonical payload
- `AnalyticsDashboardPage` loads a canonical cross-run payload
- `useAppStore().getAppConfig(appId).analytics` drives composition
- a shared `RunReportInterpreter` renders tabs and sections in declared order
- a shared `CrossRunInterpreter` renders tabs and sections in declared order
- the interpreter resolves section `component` keys against a reporting component library

The interpreter is not a generic visual renderer. Its job is:

- read tab config
- read section config
- resolve the library component for each section
- bind canonical section data into that component
- preserve configured ordering and tab layout

It must not own app-specific semantics directly, and it must not force all apps through one generic card/table treatment.

## 7.2 Shared Reporting Component Library

Standardize report UI into a reporting component library with a stable API.

Examples:

- `ReportSummaryCardsSection`
- `ReportNarrativeSection`
- `ReportMetricBreakdownSection`
- `ReportDistributionSection`
- `ReportComplianceSection`
- `ReportHeatmapSection`
- `ReportEntitySlicesSection`
- `ReportFlagsSection`
- `ReportIssuesSection`
- `ReportExemplarsSection`
- `ReportPromptGapSection`
- `ReportAgentDimensionHeatmapSection`
- `ReportRuleComplianceMatrixSection`
- `ReportAdversarialGoalHeatmapSection`

Current low-level widgets should be preserved where useful, but promoted into a clearer shared section system.

### Naming rule

Specialized components are allowed, but they still belong to the shared reporting library and must use semantic names rather than app names.

For example:

- `ExemplarThreadsSection` may initially be used only by Kaira
- `AgentDimensionHeatmapSection` may initially be used only by Inside Sales

That is acceptable. What is not acceptable is binding those components to one app in their identity or path.

### Reuse rule

If a future app can benefit from a component first introduced for Kaira or Inside Sales, it should be able to select that component through config with no renaming or extraction step.

## 7.2.1 Shared LLM Config Shell

The report shell must include a shared LLM config surface used by:

- single-run report generation
- single-run report refresh/regeneration
- cross-run AI summary generation where enabled

This belongs in the normalized analytics shell, not in app-specific report views.

## 7.3 Screen and Print Must Share Semantics, Not Markup

The frontend should render canonical sections for screen. The backend should render canonical document blocks for print.

Do not attempt to print the React screen directly.

Why:

- screen layout and print layout have different constraints
- Playwright fidelity is best when given self-contained print HTML
- section semantics can be shared without coupling DOM structures

## 7.4 Preserve Existing UX Spirit

The rewrite must preserve the spirit of current analytics UX:

- Kaira still feels like a health/adversarial evaluation report
- Inside Sales still feels like a scorecard/coaching report
- issues, trends, compliance, flags, agent slices, exemplars, and recommendations remain recognizable

What changes is the composition mechanism, not the meaning of the product.

### Explicit preservation rule

The normalized frontend may replace app-specific page shells, but it must preserve:

- major tab structure
- recognizable section layout
- specialized interaction patterns such as agent-by-dimension heatmaps
- app-specific visual emphasis where it communicates product meaning

Shared composition must not erase specialized report affordances.

---

## 8. PDF / Export Architecture

## 8.1 Keep Playwright, Replace Per-App HTML Templates

Playwright-based HTML export remains the correct rendering engine.

The normalization target is:

- one shared print CSS system
- one shared HTML block renderer
- one canonical print document contract
- no per-app raw HTML template functions

## 8.2 Export Contract

App config declares export capabilities and document composition, for example:

- cover style
- section order
- whether a section is printable
- whether cross-run export is enabled

Backend document composition resolves this into `PlatformReportDocument`.

## 8.3 Shared HTML Renderer

Introduce a backend HTML renderer that converts document blocks into HTML fragments with:

- shared typography
- shared colors/tokens
- page-break rules
- table/heatmap rendering rules
- print-safe legends and metric bars

This renderer owns print presentation. App adapters do not return HTML.

## 8.4 Export Fidelity Rule

PDF output should be a print-optimized representation of the same canonical report blocks, not a screenshot or exact DOM clone of the screen view.

This yields:

- high fidelity
- deterministic exports
- scalable maintenance
- freedom to optimize print layout separately

---

## 9. Upstream and Downstream Touchpoints

## 9.1 Backend Touchpoints

**Current upstream files that force this design**

- `backend/app/routes/reports.py`
- `backend/app/services/reports/registry.py`
- `backend/app/services/reports/base_report_service.py`
- `backend/app/services/reports/report_service.py`
- `backend/app/services/reports/inside_sales_report_service.py`
- `backend/app/services/reports/cross_run_aggregator.py`
- `backend/app/services/reports/inside_sales_cross_run.py`
- `backend/app/services/reports/schemas.py`
- `backend/app/services/reports/inside_sales_schemas.py`
- `backend/app/services/reports/pdf_template.py`
- `backend/app/services/reports/inside_sales_pdf_template.py`
- `backend/app/services/reports/prompts/production_prompts.py`
- `backend/app/services/job_worker.py`
- `backend/app/models/evaluation_analytics.py`
- `backend/app/models/app.py`
- `backend/app/routes/apps.py`

**Downstream backend areas that must change**

- apps config schema and app config seeding
- analytics adapter registry
- report/cross-run route response contracts
- job handler inputs and outputs
- cache regeneration and validation
- PDF renderer contracts
- report asset resolution

## 9.2 Frontend Touchpoints

**Current upstream files that force this design**

- `src/features/analytics/registry.tsx`
- `src/features/analytics/AppReportTab.tsx`
- `src/features/analytics/AnalyticsDashboardPage.tsx`
- `src/features/analytics/KairaCrossRunDashboard.tsx`
- `src/features/analytics/InsideSalesCrossRunDashboard.tsx`
- `src/features/evalRuns/components/report/ReportTab.tsx`
- `src/features/evalRuns/components/report/KairaReportView.tsx`
- `src/features/insideSales/components/report/InsideSalesReportView.tsx`
- `src/stores/crossRunStore.ts`
- `src/services/api/reportsApi.ts`
- `src/types/reports.ts`
- `src/types/crossRunAnalytics.ts`
- `src/types/insideSalesReport.ts`
- `src/types/insideSalesCrossRun.ts`
- existing shared report widgets under `src/components/report/`

**Downstream frontend areas that must change**

- app config types/store loading
- report payload types
- cross-run payload types
- section composer components
- run detail pages and dashboard pages
- shared report-generation shell with preserved provider/model selection behavior
- screen-print parity assumptions
- report loading and refresh flows

## 9.3 Docs / Guide / Tests Touchpoints

These must be updated with the new backbone:

- guide pages that describe report jobs and pipelines
- architecture docs that mention app-specific report services
- backend unit tests for registry/aggregators
- frontend tests for report tabs and dashboards
- tests for provider/model picker persistence and report regeneration flows
- any educational diagrams that still point to `cross_run_aggregator.py` as the whole cross-run pipeline

---

## 10. Migration Strategy

## 10.1 Migration Style

Use a staged but coordinated rewrite:

1. Land canonical contracts and app config
2. Land backend adapters and composers
3. Land shared frontend composers
4. Migrate Kaira and Inside Sales onto the new backbone
5. Enable Voice Rx on the new contract, even if with a smaller section set
6. Remove legacy registries and app-specific templates

## 10.2 Compatibility Window

Avoid prolonged dual-contract support.

Short-term temporary compatibility is acceptable inside the rollout, but the target should be a clean v1 cutover where:

- canonical contracts become the only public frontend contract
- old caches are invalidated
- old per-app HTML templates are removed
- old frontend analytics registries are removed

## 10.3 Risk Control

The highest risks are:

- semantic regressions in analytics meaning
- UI regressions in Kaira and Inside Sales section coverage
- export regressions in PDF fidelity
- hidden references to old payload shapes

Mitigation:

- golden fixture tests for current reports
- adapter-level contract tests
- composer rendering tests
- PDF snapshot or structural HTML tests
- explicit migration checklist per app

---

## 11. Design Decisions Locked

1. Reporting normalization is section-based, not app-page-based.
2. App config gains an `analytics` subtree and becomes the structural control plane.
3. Domain-specific computation stays in backend adapters; config does not encode analytics math.
4. Frontend rendering becomes config-driven from canonical report sections.
5. PDF export is normalized through a canonical document contract and a shared HTML renderer.
6. Report assets move out of hardcoded Python constants into config/settings-backed resolution.
7. `evaluation_analytics` remains the cache store, with contract versioning and regeneration.
8. Voice Rx must become a first-class analytics app under the new backbone, not remain “unsupported by omission”.

---

## 12. Open Decisions Resolved For Planning

These were ambiguous before planning and are now fixed for implementation:

- **Backend-only app extensibility for now:** yes
- **Config-driven composition, not end-user layout editing:** yes
- **Print-optimized PDFs from canonical blocks, not screen DOM printing:** yes
- **App config for structure, settings for long-form report assets:** yes
- **Atomic payload/cache cutover preferred over long compatibility:** yes

---

## 13. Success Criteria

The rewrite is successful when:

- no shared frontend analytics component branches on app ID for composition
- no backend route branches on app ID for payload shape selection
- adding a new app requires backend adapter registration plus app config, not new frontend registries
- PDF export uses one shared HTML renderer and one canonical document contract
- Kaira, Inside Sales, and Voice Rx all render from the same backbone
- report assets and prompt references are resolved through the normalized platform model
- caches and tests clearly encode schema versioning and migration expectations

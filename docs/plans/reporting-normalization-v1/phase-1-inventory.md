# Reporting Normalization v1 Phase 1 Inventory

## Touchpoint Matrix

| Area | Current touchpoint | Why it matters in phases 1 to 3 |
| --- | --- | --- |
| Apps API | `backend/app/routes/apps.py`, `backend/app/schemas/app_config.py` | App config becomes the control plane for reporting capabilities and composition. |
| Single-run generation | `backend/app/routes/reports.py`, `backend/app/services/job_worker.py` | Both currently resolve report behavior from app-id registry entries. |
| Legacy backend registry | `backend/app/services/reports/registry.py` | This is the hardcoded app switch that phases 2 and 3 replace with profile-backed config. |
| Single-run payloads | `backend/app/services/reports/schemas.py`, `backend/app/services/reports/inside_sales_schemas.py` | These fixtures define the legacy semantics that the canonical contracts must preserve. |
| Cross-run analytics | `backend/app/services/reports/cross_run_aggregator.py`, `backend/app/services/reports/inside_sales_cross_run.py` | Cross-run data stays domain-specific in computation, but not in public contract shape. |
| PDF export | `backend/app/services/reports/pdf_template.py`, `backend/app/services/reports/inside_sales_pdf_template.py` | Current HTML block coverage is the baseline for the future shared renderer. |
| Frontend report routing | `src/features/analytics/registry.tsx`, `src/features/analytics/AppReportTab.tsx`, `src/features/analytics/AnalyticsDashboardPage.tsx` | Phase 2 starts moving capability gating into config while phase 6 removes app-specific render registries entirely. |
| Cache store | `backend/app/models/evaluation_analytics.py` | Cache rows remain the single store, but phase 3 adds explicit schema-version conventions around payloads. |

## Frozen Legacy Fixtures

- `backend/tests/fixtures/reports/kaira-standard-run.json`
- `backend/tests/fixtures/reports/kaira-adversarial-run.json`
- `backend/tests/fixtures/reports/inside-sales-run.json`
- `backend/tests/fixtures/reports/kaira-cross-run.json`
- `backend/tests/fixtures/reports/inside-sales-cross-run.json`

These fixtures capture the current product semantics that phases 4 to 8 must preserve while migrating to canonical contracts.

## Current PDF Block Coverage

### Kaira PDF

- Header score rail
- Executive summary
- Top issues
- Recommendations
- Verdict distributions
- Rule compliance
- Friction analysis
- Adversarial breakdown when present
- Exemplar threads
- Prompt gap analysis

### Inside Sales PDF

- Header score rail
- Executive summary cards
- QA dimension breakdown
- Compliance gates
- Behavioral signals and outcomes
- Agent performance
- Narrative and recommendations

## Canonical Section Inventory Required By Current UX

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

## Report-Side Asset Inventory

- Kaira prompt-gap analysis currently depends on `backend/app/services/reports/prompts/production_prompts.py`
- Kaira report narrative currently uses `backend/app/services/reports/prompts/narrative_prompt.py`
- Inside Sales report narrative currently uses `backend/app/services/reports/prompts/inside_sales_narrative_prompt.py`
- Cross-run AI summary currently lives in `backend/app/services/reports/cross_run_narrator.py`

Phase 2 moves the structural asset keys into app config. Phase 4 will resolve the content itself through backend asset resolution.

## ReportTab Behavior To Preserve

- Provider/model selection remains user-driven in `src/features/evalRuns/components/report/ReportTab.tsx`
- Cached report metadata syncs the selected provider/model back into the UI after load
- Report generation remains job-backed through `generate-report`
- PDF export stays server-driven
- LLM credential readiness gates generate/regenerate actions before submission

## Narrator Entry Point Divergence To Normalize

- Kaira single-run narrative: `backend/app/services/reports/narrator.py`
- Inside Sales single-run narrative: `backend/app/services/reports/inside_sales_narrator.py`
- Cross-run summary: `backend/app/services/reports/cross_run_narrator.py`
- Kaira prompt references: `backend/app/services/reports/prompts/production_prompts.py`

Phase 3 defines the canonical narrative contracts. Phase 4 will wire these generators behind shared builders and asset resolution.

# Kaira Evals Reports — Implementation Overview

## Goal

Add an **AI-powered evaluation report** to the existing RunDetail page — an on-screen "Report" tab with professional PDF export. Single-run scope. The system is designed as a **platform-level reporting foundation** reusable across all apps (voice-rx, kaira-bot, future apps).

## Architecture

```
                         ┌──────────────────────────┐
                         │   RunDetail.tsx           │
                         │   New "Report" tab        │
                         │   (on-screen + PDF btn)   │
                         └────────────┬─────────────┘
                                      │
                            GET /api/reports/{run_id}
                                      │
                    ┌─────────────────▼──────────────────┐
                    │       BACKEND REPORT SERVICE        │
                    │                                     │
                    │  1. Aggregator  (pure computation)  │
                    │  2. Narrator    (LLM interpretation)│
                    │  3. Assembler   (payload builder)   │
                    └─────────────────────────────────────┘
```

**Backend** = data aggregation + AI narrative (no PDF, no presentation).
**Frontend** = interactive report view + PDF export (owns all presentation).
**Contract** = `ReportPayload` JSON — the single interface between them.

## Key Design Principles

1. **App-agnostic core**: `backend/app/services/reports/` is NOT Kaira-specific. Aggregator, health score, narrator are generic. App-specific logic lives in pluggable resolvers.
2. **Reuse existing abstractions**: LLM calls via `llm_base.py`, eval data via existing SQLAlchemy models, charts via existing Recharts, PDF via existing jsPDF.
3. **No code duplication**: Verdict color maps, badge styles, distribution rendering — shared between on-screen and PDF.
4. **Clean separation**: Backend computes, frontend renders. The `ReportPayload` is fully self-contained — frontend needs zero additional API calls.

## Phases

| Phase | Scope | Builds On | Files Created |
|-------|-------|-----------|---------------|
| 1 | **Infrastructure** — Backend service scaffolding, schemas, router, health score calculator, frontend API client | Nothing | ~10 files |
| 2 | **Aggregation Engine** — Rule compliance matrix, friction analysis, exemplar selection, verdict distributions | Phase 1 | ~4 files |
| 3 | **AI Narrative** — LLM prompt templates, narrator service, structured output, production prompt constants | Phase 2 | ~5 files |
| 4 | **Frontend Report Tab** — React components, Recharts charts, on-screen report view in RunDetail | Phase 3 | ~12 files |
| 5 | **PDF Export** — Enhanced jsPDF module, chart capture, professional layout, callout system | Phase 4 | ~3 files |
| 6 | **Polish & Integration** — Caching, error states, loading UX, mobile, testing guidance | Phase 5 | ~2 files |

## File Structure (Final State)

```
backend/app/
├── routes/
│   └── reports.py                          # GET /api/reports/{run_id}
└── services/
    └── reports/
        ├── __init__.py
        ├── report_service.py               # Orchestrator
        ├── aggregator.py                   # Metrics, matrices, exemplars
        ├── narrator.py                     # LLM prompt builder + caller
        ├── health_score.py                 # Weighted composite calculator
        ├── schemas.py                      # Pydantic response models
        └── prompts/
            ├── __init__.py
            ├── narrative_prompt.py         # System/user prompt templates
            └── production_prompts.py       # Static Kaira prompts (show-and-tell)

src/
├── services/
│   └── api/
│       └── reportsApi.ts                   # fetchReport(runId)
├── features/
│   └── evalRuns/
│       ├── pages/
│       │   └── RunDetail.tsx               # Extended with Report tab
│       ├── components/
│       │   └── report/
│       │       ├── index.ts                # Barrel export
│       │       ├── ReportTab.tsx           # Container: fetch + render
│       │       ├── ExecutiveSummary.tsx     # Health score + AI narrative
│       │       ├── VerdictDistributions.tsx # Recharts bar/pie/histogram
│       │       ├── RuleComplianceTable.tsx  # Compliance heatmap
│       │       ├── FrictionAnalysis.tsx     # Cause breakdown + patterns
│       │       ├── AdversarialBreakdown.tsx # Category/difficulty charts
│       │       ├── ExemplarThreads.tsx      # Best/worst thread cards
│       │       ├── PromptGapAnalysis.tsx    # Source→eval mapping
│       │       ├── Recommendations.tsx     # Prioritized actions + impact
│       │       └── shared/
│       │           ├── CalloutBox.tsx       # Info/success/warning/danger/insight/suggest
│       │           ├── SectionHeader.tsx    # Consistent section titles
│       │           └── MetricCard.tsx       # Score card with progress bar
│       └── export/
│           └── reportPdfExporter.ts        # Professional PDF generation
└── types/
    └── reports.ts                          # ReportPayload, NarrativeOutput, etc.
```

## Health Score Formula

```
numeric = (intent_accuracy × 25) + (correctness_rate × 25) +
          (efficiency_rate × 25) + (task_completion × 25)

Where:
  intent_accuracy  = avg across threads (0–1 scaled to 0–100)
  correctness_rate = PASS / total_evaluated (0–100)
  efficiency_rate  = (EFFICIENT + ACCEPTABLE) / total_evaluated (0–100)
  task_completion  = success_status / total_evaluated (0–100)

Grade Map:
  ≥95 → A+   ≥90 → A   ≥85 → A-
  ≥80 → B+   ≥75 → B   ≥70 → B-
  ≥65 → C+   ≥60 → C   ≥55 → C-
  ≥50 → D+   ≥45 → D   <45 → F
```

## Exemplar Selection

```
composite = (intent_accuracy × 0.25)
          + (correctness_ordinal × 0.25)
          + (efficiency_ordinal × 0.25)
          + (task_completed × 0.25)

Ordinal maps:
  Correctness: PASS=1.0, NOT_APPLICABLE=0.8, SOFT_FAIL=0.5, HARD_FAIL=0.2, CRITICAL=0.0
  Efficiency:  EFFICIENT=1.0, ACCEPTABLE=0.7, INCOMPLETE=0.4, FRICTION=0.2, BROKEN=0.0

best_5  = top 5 by composite DESC
worst_5 = bottom 5 by composite ASC
```

## Cross-references

- Phase details: `PHASE_1_INFRASTRUCTURE.md` through `PHASE_6_POLISH.md`
- Existing eval system: `backend/app/services/evaluators/`
- Existing export system: `src/services/export/`
- Existing RunDetail: `src/features/evalRuns/pages/RunDetail.tsx`
- PDF design spec: Whiteboarded in conversation (color palette, page layouts, callout system)

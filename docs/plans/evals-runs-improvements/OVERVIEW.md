# Eval Runs Improvements — 3-Phase Plan

## Problem Statement

1. **Custom evaluators in Kaira batch**: Selection works, backend executes them, DB stores results — but the UI only shows built-in evaluator columns (Intent Acc, Correctness, Efficiency). Custom evaluator results are invisible in table view and have no distribution bars or stat pills.

2. **VoiceRx full_evaluation**: Never populates `summary`, so RunList shows `--` for score. No RunDetail page exists — clicking a run goes to raw Logs view.

3. **VoiceRx custom evaluators**: Must click "Run" 10 separate times for 10 evaluators. No "Run All" capability.

4. **Kaira batch custom evals run sequentially**: 10 custom evaluators = 10 serial LLM calls per thread. Slow at scale.

## Phase Overview

| Phase | Focus | Backend | Frontend | Testable Outcome |
|-------|-------|---------|----------|------------------|
| **1** | Backend Foundation + Shared Components | Enrich summary, parallel exec, VoiceRx summary fix, Run All endpoint, evaluator descriptors | OutputFieldRenderer, types | Backend returns richer data; shared component renders evaluator output |
| **2** | Kaira Dynamic Results UI | — | Dynamic EvalTable, stat pills, distribution bars, parallel toggle | Custom evaluator results visible in Kaira RunDetail |
| **3** | VoiceRx RunDetail + Run All UI | — | VoiceRxRunDetail page, Run All overlay, route updates | VoiceRx has rich result views and batch custom eval execution |

## Key Abstraction: OutputFieldRenderer

The ONE shared component across all scenarios. Given an `output_schema` (field definitions from Evaluator model) and `output` (actual values), renders each field with type-appropriate formatting:

- `number` + thresholds → colored score badge/bar
- `text` + isMainMetric → prominent display
- `boolean` → checkmark/cross badge
- `text` with observed enum values → VerdictBadge

Used in:
- Kaira RunDetail table cells (Phase 2)
- Kaira RunDetail detail cards (Phase 2)
- VoiceRx RunDetail output display (Phase 3)
- VoiceRx custom eval result cards (Phase 3)

## Key Abstraction: EvaluatorDescriptor

Metadata object returned by the backend with each run, describing how to render each evaluator's results. Both built-in and custom evaluators produce the same shape. Drives dynamic column generation.

```typescript
interface EvaluatorDescriptor {
  id: string;                    // "intent" | "correctness" | evaluator UUID
  name: string;                  // "Intent Accuracy" | "Health Accuracy Checker"
  type: "built-in" | "custom";
  outputSchema?: OutputFieldDef[];
  primaryField?: {
    key: string;                 // "verdict" | "safety_score" | "intent_accuracy"
    format: "verdict" | "percentage" | "number" | "boolean" | "text";
    verdictOrder?: string[];     // ["PASS","SOFT FAIL","HARD FAIL","CRITICAL"]
  };
  aggregation?: {
    distribution?: Record<string, number>;
    average?: number;
    completedCount: number;
    errorCount: number;
  };
}
```

## Data Flow Changes

```
BEFORE:
  batch_runner → ThreadEvaluation.result.custom_evaluations = {id: {name, status, output}}
  EvalRun.summary.custom_evaluations = {id: {name, completed, errors}}
  Frontend: hardcoded 3 columns

AFTER:
  batch_runner → same, PLUS summary enriched with:
    - output_schema per evaluator
    - distribution of primary field values
    - average score if numeric
  eval_runs API → returns evaluator_descriptors[] in run response
  Frontend: dynamic columns from descriptors
```

## Files Touched (All Phases)

### Backend
- `backend/app/services/evaluators/batch_runner.py` — enrich summary, parallel execution
- `backend/app/services/evaluators/voice_rx_runner.py` — populate summary
- `backend/app/services/evaluators/voice_rx_batch_custom_runner.py` — NEW: Run All handler
- `backend/app/routes/eval_runs.py` — evaluator_descriptors in response
- `backend/app/services/job_worker.py` — register new handler

### Frontend
- `src/types/evalRuns.ts` — EvaluatorDescriptor, OutputFieldDef types
- `src/features/evalRuns/components/OutputFieldRenderer.tsx` — NEW: shared renderer
- `src/features/evalRuns/components/EvalTable.tsx` — dynamic columns
- `src/features/evalRuns/pages/RunDetail.tsx` — dynamic stats/bars
- `src/features/evalRuns/components/NewBatchEvalOverlay.tsx` — parallel toggle
- `src/features/voiceRx/pages/VoiceRxRunDetail.tsx` — NEW: detail page
- `src/features/voiceRx/components/RunAllOverlay.tsx` — NEW: run all UI
- `src/config/routes.ts` — new routes
- `src/app/Router.tsx` — new route entries

# Intent Classification Evaluation — End-to-End Flow Analysis

**Date:** 2026-02-28

## 1. Chain Overview

```
NewBatchEvalOverlay (UI)
  ── handleSubmit() ──────────────────────────────────────────────────────►
  Sends: evaluate_intent: true, evaluate_correctness: false,
         evaluate_efficiency: false, intent_system_prompt: string|null
                                                                          │
POST /api/jobs  { jobType: "evaluate-batch", params: {...} }              │
                                                                          ▼
backend/app/routes/jobs.py                                                │
  Creates Job record (status: "queued")                                   │
  Returns { id, status, progress }                                        │
                                                                          │
Frontend polls GET /api/jobs/{id} for job.progress.run_id                 │
                                                                          ▼
backend/app/services/job_worker.py  ── worker_loop() ────────────────────►│
  Picks queued job → marks "running"                                      │
  Dispatches to handle_evaluate_batch(job_id, params)                     │
                                                                          ▼
backend/app/services/evaluators/batch_runner.py                           │
  ── run_batch_evaluation() ──────────────────────────────────────────────►│
  1. Creates EvalRun record                                               │
  2. Writes run_id to job.progress (frontend redirect)                    │
  3. Loads CSV via DataLoader                                             │
  4. For each thread:                                                     │
     └─ _evaluate_one_thread()                                            │
        ├─ IntentEvaluator(llm, system_prompt=intent_system_prompt)       │
        ├─ evaluate_thread(messages) → List[IntentEvaluation]             │
        ├─ Computes intent_accuracy                                       │
        └─ Saves ThreadEvaluation row to DB                               │
  5. Aggregates summary (avg_intent_accuracy)                             │
  6. Finalizes EvalRun status                                             │
                                                                          ▼
Frontend reads results                                                    │
  GET /api/eval-runs/{run_id}/threads → ThreadEvalRow[]                   │
  IntentTab renders per-message results                                   │
  RunDetail / Dashboard shows avg_intent_accuracy                         │
```

## 2. Key Files

| Layer | File | Role |
|-------|------|------|
| UI Submit | `src/features/evalRuns/components/NewBatchEvalOverlay.tsx` | Multi-step wizard, builds params, calls submitJob |
| UI Evaluator Config | `src/features/evalRuns/components/EvaluatorToggleStep.tsx` | Toggle switches for intent/correctness/efficiency, intent system prompt textarea |
| Submit Hook | `src/hooks/useSubmitAndRedirect.ts` | Wraps jobsApi.submit, polls for run_id, navigates |
| API Client | `src/services/api/jobsApi.ts` | POST /api/jobs, GET /api/jobs/{id} |
| Job Polling | `src/services/api/jobPolling.ts` | pollJobUntilComplete with configurable interval |
| Job Tracker Store | `src/stores/jobTrackerStore.ts` | Tracks active jobs and resolved run_ids in sessionStorage |
| Backend Route | `backend/app/routes/jobs.py` | Creates/reads/cancels Job records |
| Job Worker | `backend/app/services/job_worker.py` | Worker loop, handler registry, progress updates |
| Batch Runner | `backend/app/services/evaluators/batch_runner.py` | Orchestrates all evaluators, persists results |
| Intent Evaluator | `backend/app/services/evaluators/intent_evaluator.py` | System prompt parsing, LLM-as-judge, accuracy comparison |
| Data Loader | `backend/app/services/evaluators/data_loader.py` | CSV parsing, thread assembly |
| Data Models | `backend/app/services/evaluators/models.py` | ChatMessage, IntentEvaluation dataclasses |
| DB Model | `backend/app/models/eval_run.py` | ThreadEvaluation ORM table |
| Results Route | `backend/app/routes/eval_runs.py` | GET /threads, /stats/summary, evaluator descriptors |
| Intent Results UI | `src/features/evalRuns/components/threadReview/IntentTab.tsx` | Per-message intent table with correct/incorrect filter |
| Summary Bar | `src/features/evalRuns/components/threadReview/SummaryBar.tsx` | Thread-level intent accuracy display |
| Run Detail | `src/features/evalRuns/pages/RunDetail.tsx` | Run-level aggregation of intent accuracy |
| Dashboard | `src/features/evalRuns/pages/Dashboard.tsx` | Cross-run avg_intent_accuracy display |

## 3. Data Transformations

### 3a. CSV → ChatMessage

`DataLoader` reads CSV via pandas. `ChatMessage.from_csv_row()` maps columns:

| CSV Column | ChatMessage Field | Usage in Intent Eval |
|------------|-------------------|---------------------|
| `query_text` | `query_text` | Sent to LLM as the input to classify |
| `intent_detected` | `intent_detected` | Ground truth for `is_correct_intent` comparison |
| `intent_query_type` | `intent_query_type` | Ground truth for `is_correct_query_type` comparison |
| `final_response_message` | `final_response_message` | Not used by intent evaluator |

### 3b. System Prompt → Enum Constraints

`IntentEvaluator.__init__` resolves valid agent/query_type enums:

1. If `valid_intents` explicitly passed → use those
2. Else parse from `system_prompt` via regex (`_parse_agents_from_prompt`)
3. Else fall back to Kaira defaults: `[FoodAgent, CgmAgent, FoodInsightAgent, General, Greeting]`

Same 3-tier resolution for `valid_query_types` (defaults: `[logging, question]`).

These enums are injected into the JSON schema as `enum` constraints, so the LLM is forced to pick from the allowed set.

### 3c. LLM Response → IntentEvaluation

LLM returns JSON with `predicted_agent`, `query_type`, `confidence`, `reasoning`, `all_predictions`.

Correctness comparison uses `_normalize_intent()`:
```python
def _normalize_intent(value: str) -> str:
    return value.strip().lower().replace("_", "").replace(" ", "")
```

This allows "FoodAgent", "food_agent", "Food Agent" to all match. Comparison:
```python
is_correct_intent = _normalize_intent(predicted) == _normalize_intent(ground_truth)
is_correct_query_type = _normalize_intent(predicted_qt) == _normalize_intent(ground_truth_qt)
```

### 3d. IntentEvaluation → DB

Serialized via `serialize()` into the `result` JSONB column of `ThreadEvaluation`.
The `intent_accuracy` float is stored as a separate indexed column for sorting/aggregation.

### 3e. DB → Frontend

`_thread_to_dict()` returns `intent_accuracy` (float) and `result` (full JSONB).
Frontend `IntentTab` reads `result.intent_evaluations[]` and renders each entry.

## 4. Findings

### F1 — `success_status` always `False` in intent-only runs [HIGH]

**Location:** `batch_runner.py:471-473`

```python
is_success = bool(
    efficiency_result and efficiency_result.task_completed
)
```

When efficiency is disabled, `efficiency_result` is `None`. Therefore `is_success` is always `False`. Every `ThreadEvaluation` row gets `success_status=False`.

**Observation:** The `success_status` column is sortable/filterable in `EvalTable`. An intent-only run with 100% intent accuracy will appear as 100% failures in the success column. The metric is semantically tied to efficiency's `task_completed`, but the column name and UI presentation don't communicate this — it just looks broken.

### F2 — `intent_system_prompt: null` propagates as `None` to LLM [MEDIUM]

**Chain:**

1. `NewBatchEvalOverlay.tsx:223` — `intent_system_prompt: intentSystemPrompt || null`
   When the textarea is empty, sends `null`.

2. `job_worker.py:343` — `intent_system_prompt=params.get("intent_system_prompt", "")`
   The default `""` only applies if the key is absent. The key IS present with value `None`, so Python returns `None`.

3. `batch_runner.py:308` — `IntentEvaluator(worker_llm, system_prompt=intent_system_prompt)`
   Passes `None` as `system_prompt`.

4. `intent_evaluator.py:171` — `self.system_prompt = system_prompt`
   Stores `None`. The enum parsing (`_parse_agents_from_prompt(None)`) returns `[]`, falling through to Kaira defaults — this part works.

5. `intent_evaluator.py:217` — `system_prompt=self.system_prompt`
   Passes `None` to the LLM provider's `generate_json()`.

**Observation:** Whether the LLM provider handles `None` vs `""` identically is an implementation detail. Today it works because the Gemini provider treats both as "no system prompt." But any provider change, wrapper, or logging that distinguishes `None` from `""` could cause unexpected behavior. The contract between frontend and backend is unclear: the frontend intends "no custom prompt" but expresses it as `null` rather than empty string.

### F3 — Phantom correctness/efficiency counts in summary [MEDIUM]

**Location:** `batch_runner.py:456-468, 590-598`

When correctness and efficiency are disabled:
- `worst_correctness` defaults to `"NOT APPLICABLE"`
- `efficiency_verdict` defaults to `"N/A"`

These default values are returned in the worker result dict and aggregated into `results_summary["correctness_verdicts"]` and `results_summary["efficiency_verdicts"]`. The run's `summary` dict then contains `{"correctness_verdicts": {"NOT APPLICABLE": N}, "efficiency_verdicts": {"N/A": N}}` even though those evaluators never ran.

**Observation:** The evaluator descriptor logic in `eval_runs.py` correctly gates on `batch_metadata.get("evaluate_correctness", True)` — it won't show a correctness card for an intent-only run. But the raw summary data still carries these phantom counts, and any code that reads `summary.correctness_verdicts` without checking the batch_metadata flags will see misleading data.

### F6 — `query_type` is evaluated but invisible in the UI [LOW]

**Backend produces:** `predicted_query_type`, `is_correct_query_type` in every `IntentEvaluation`.

**Frontend IntentTab renders:** `predicted_intent`, `is_correct_intent`, `confidence`, `reasoning`.

**Missing from UI:** `predicted_query_type`, `is_correct_query_type`, `all_predictions`.

The LLM evaluates query type on every message. The data is serialized to JSONB and returned via the API. But the IntentTab never renders it. The TypeScript type now includes these fields (added in the recent audit fix), but no component reads them.

**Observation:** Each intent LLM call produces query_type classification output that is stored but never shown. This is wasted compute per message, multiplied across all threads.

### F7 — Empty `intent_query_type` gives false negatives [LOW]

**Location:** `models.py:120`
```python
intent_query_type="" if pd.isna(row["intent_query_type"]) else row["intent_query_type"]
```

When the CSV lacks an `intent_query_type` column or the value is NaN, the ground truth is `""`. The LLM will predict something like `"logging"`. The comparison:
```python
_normalize_intent("logging") == _normalize_intent("")  # → "logging" == "" → False
```

Every message with missing ground truth is marked `is_correct_query_type=False`.

**Observation:** Not visible today because query_type accuracy isn't shown in the UI (see F6). But if the UI ever displays it, the false negative rate will be inflated for any CSV that doesn't populate `intent_query_type`.

### F8 — Client vs server `avg_intent_accuracy` mismatch [LOW]

**Server-side** (`batch_runner.py:589-590`): Only adds `intent_accuracy` to the sum for threads where `is_error=False`. Error threads are excluded from the average.

**Client-side** (`RunDetail.tsx`):
```typescript
threadEvals.reduce((s, e) => s + (e.intent_accuracy ?? 0), 0) / threadEvals.length
```
Includes ALL threads, including error threads where `intent_accuracy=0.0`.

**Observation:** When some threads error (e.g., LLM timeout), the dashboard shows the server-computed average (correct — excludes errors) while the run detail page shows the client-computed average (lower — includes 0.0 from errors). The discrepancy grows with the number of errored threads.

### F12 — No `app_id` from frontend [NOTE]

`NewBatchEvalOverlay` does not send `app_id` in the job params. The backend defaults to `"kaira-bot"`:
```python
app_id=params.get("app_id", "kaira-bot")
```

This is correct for the current product (only Kaira uses batch eval). But the plumbing is missing if another app ever needs it.

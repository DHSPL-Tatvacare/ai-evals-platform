# Correctness Evaluation — End-to-End Flow Analysis

**Date:** 2026-02-28

## 1. Chain Overview

```
NewBatchEvalOverlay (UI)
  ── handleSubmit() ──────────────────────────────────────────────────────►
  Sends: evaluate_intent: false, evaluate_correctness: true,
         evaluate_efficiency: false
                                                                          │
POST /api/jobs  { jobType: "evaluate-batch", params: {...} }              │
                                                                          ▼
backend/app/routes/jobs.py                                                │
  Creates Job record (status: "queued")                                   │
                                                                          │
Frontend polls GET /api/jobs/{id} for job.progress.run_id                 │
                                                                          ▼
backend/app/services/job_worker.py  ── worker_loop() ────────────────────►│
  Picks queued job → handle_evaluate_batch(job_id, params)                │
                                                                          ▼
backend/app/services/evaluators/batch_runner.py                           │
  ── run_batch_evaluation() ──────────────────────────────────────────────►│
  1. Creates EvalRun record                                               │
  2. Writes run_id to job.progress                                        │
  3. Loads CSV via DataLoader                                             │
  4. For each thread:                                                     │
     └─ _evaluate_one_thread()                                            │
        ├─ CorrectnessEvaluator(llm)                                      │
        ├─ evaluate_thread(thread) → List[CorrectnessEvaluation]          │
        │    └─ For each message:                                         │
        │       ├─ is_meal_summary? ── No  → NOT APPLICABLE (no LLM)     │
        │       └─ is_meal_summary? ── Yes → LLM call with prompt+schema │
        ├─ Computes worst_correctness (max severity)                      │
        └─ Saves ThreadEvaluation row to DB                               │
  5. Aggregates correctness_verdicts in summary                           │
  6. Finalizes EvalRun                                                    │
                                                                          ▼
Frontend reads results                                                    │
  GET /api/eval-runs/{run_id}/threads → ThreadEvalRow[]                   │
  CorrectnessTab renders per-message verdicts (NOT APPLICABLE filtered)   │
  RunDetail builds correctnessDist from worst_correctness                 │
  Dashboard shows correctness_distribution from /stats/summary            │
```

## 2. Key Files

| Layer | File | Role |
|-------|------|------|
| UI Submit | `src/features/evalRuns/components/NewBatchEvalOverlay.tsx` | Builds and sends job params |
| UI Evaluator Config | `src/features/evalRuns/components/EvaluatorToggleStep.tsx` | Evaluator on/off toggles |
| Batch Runner | `backend/app/services/evaluators/batch_runner.py` | Orchestrates evaluators per thread |
| Correctness Evaluator | `backend/app/services/evaluators/correctness_evaluator.py` | System prompt, JSON schema, LLM call, result parsing |
| Rule Catalog | `backend/app/services/evaluators/rule_catalog.py` | Production rules sent to LLM for compliance checking |
| Data Models | `backend/app/services/evaluators/models.py` | ChatMessage.is_meal_summary, CorrectnessEvaluation |
| Data Loader | `backend/app/services/evaluators/data_loader.py` | CSV → ChatMessage → ConversationThread |
| DB Model | `backend/app/models/eval_run.py` | ThreadEvaluation table (worst_correctness column) |
| Results Route | `backend/app/routes/eval_runs.py` | GET /threads, /stats/summary, /trends, evaluator descriptors |
| Correctness Results UI | `src/features/evalRuns/components/threadReview/CorrectnessTab.tsx` | Per-message verdict table with filter pills |
| Verdict Badge | `src/features/evalRuns/components/VerdictBadge.tsx` | Colored badge rendering for all verdict types |
| Distribution Bar | `src/features/evalRuns/components/DistributionBar.tsx` | Stacked bar chart for verdict distribution |
| Run Detail | `src/features/evalRuns/pages/RunDetail.tsx` | Aggregates correctnessDist from thread rows |
| Dashboard | `src/features/evalRuns/pages/Dashboard.tsx` | Cross-run correctness_distribution display |
| Trend Chart | `src/features/evalRuns/components/TrendChart.tsx` | 30-day correctness trend lines |

## 3. Data Transformations

### 3a. CSV → ChatMessage

Same as intent flow. Key fields for correctness:

| CSV Column | ChatMessage Field | Usage in Correctness Eval |
|------------|-------------------|--------------------------|
| `query_text` | `query_text` | Sent to LLM as user input |
| `final_response_message` | `final_response_message` | Sent to LLM as bot response to audit; also used by `is_meal_summary` |
| `has_image` | `has_image` | Determines image context handling (skip quantity coherence) |

### 3b. is_meal_summary Pre-filter

Before any LLM call, the evaluator checks `message.is_meal_summary`:

```python
indicators = ["total calories", "kcal", "meal summary", "consumed at"]
resp = self.final_response_message.lower()
return any(ind in resp for ind in indicators)
```

- Returns `True` → proceeds to LLM evaluation
- Returns `False` → immediately returns `CorrectnessEvaluation(verdict="NOT APPLICABLE")` with no LLM call

This is a cost-saving heuristic: non-meal bot responses (greetings, questions, error messages) are skipped without spending an LLM call. The tradeoff is that meal summaries without these exact keywords are silently skipped.

### 3c. LLM Call Setup

For messages that pass the pre-filter:

1. **Image context detection:** Checks current message and last 2 history messages for `has_image`
2. **History assembly:** Last 4 turns as context block
3. **Rule loading:** `get_rules_for_correctness()` returns 5 rules:
   - `exact_calorie_values` — Use exact values from nutrition API
   - `single_item_one_table` — No duplicate table for single items
   - `multi_food_multi_tables` — Show per-item breakdown for multiple foods
   - `require_xml_chips` — Meal summary must have confirm/edit action chips
   - `composite_dish_single_item` — Treat composite dish as one item
4. **Prompt assembly:** History block + current turn + image note + rules block
5. **LLM call:** `generate_json(prompt, system_prompt=CORRECTNESS_JUDGE_PROMPT, json_schema=CORRECTNESS_JSON_SCHEMA)`

### 3d. LLM Response → CorrectnessEvaluation

`_parse_result()` normalizes the LLM output:

1. **Verdict normalization:** `replace("_", " ")` converts `SOFT_FAIL` → `SOFT FAIL`
2. **Verdict validation:** Must be one of `PASS, SOFT FAIL, HARD FAIL, CRITICAL, NOT APPLICABLE`; defaults to `SOFT FAIL` if unrecognized
3. **Image override:** If image context + quantity coherence caused the fail + calories/arithmetic are OK → overrides verdict to `PASS`
4. **Rule compliance backfill:** Any rules the LLM omitted get appended with `followed=True, evidence="Not evaluated by judge"`

### 3e. Per-Thread Aggregation

In `_evaluate_one_thread()`:

```python
worst_correctness = "NOT APPLICABLE"
severity = ["NOT APPLICABLE", "PASS", "SOFT FAIL", "HARD FAIL", "CRITICAL"]
for ce in correctness_results:
    if severity.index(ce.verdict) > severity.index(worst_correctness):
        worst_correctness = ce.verdict
```

The worst (highest severity) verdict across all messages becomes the thread's `worst_correctness`.

### 3f. DB Persistence

`ThreadEvaluation` row stores:
- `worst_correctness` (VARCHAR) — thread-level summary
- `result` (JSONB) — full serialized data including per-message `correctness_evaluations[]`

### 3g. API Response

Two key endpoints:

1. **`GET /eval-runs/{run_id}/threads`** — Returns `worst_correctness` per thread + full `result` JSONB
2. **`GET /eval-runs/stats/summary`** — Queries `ThreadEvaluation.worst_correctness` across all runs, grouped by verdict → `correctness_distribution`

Evaluator descriptor (when correctness was enabled):
```python
{
    "id": "correctness",
    "name": "Correctness",
    "primaryField": {"key": "worst_correctness", "format": "verdict"},
    "aggregation": {"distribution": summary.correctness_verdicts}
}
```

### 3h. Frontend Display

**CorrectnessTab:**
- Filters out `NOT APPLICABLE` evaluations by default
- Shows only messages where the bot produced a meal summary
- If all messages are NOT APPLICABLE → shows "No applicable correctness evaluations"
- Expandable rows show reasoning + rule compliance via `RuleComplianceInline`

**EvalTable:**
- Renders `worst_correctness` per thread as a `VerdictBadge`
- Sortable by verdict severity via `CORRECTNESS_RANK` mapping

**RunDetail:**
- Client-side aggregation: iterates thread rows, counts `worst_correctness` values into `correctnessDist`
- Renders as `DistributionBar`

**Dashboard:**
- Server-side aggregation via `/stats/summary` → `correctness_distribution`
- Also renders as `DistributionBar`

## 4. Findings

### F1 — `success_status` always `False` in correctness-only runs [HIGH]

Identical to the intent audit finding. `efficiency_result` is `None` when efficiency is disabled, so `is_success = bool(None and ...)` is always `False`. Every thread appears as a failure.

See `INTENT_FLOW_ANALYSIS.md` F1 for full details.

### F4 — `is_meal_summary` false negatives silently skip evaluation [MEDIUM]

**Location:** `models.py:127-135`

The keyword heuristic checks for 4 exact substrings: `"total calories"`, `"kcal"`, `"meal summary"`, `"consumed at"`. If the bot's response contains nutritional data but uses different wording, the message is silently marked NOT APPLICABLE with no LLM call.

Examples of responses that would be missed:
- "Eggs — 140 calories" (uses "calories" not "total calories")
- "Here's your meal breakdown: 250 cal" (uses "cal" not "kcal")
- Responses formatted with tables or markdown where keywords appear differently
- Non-English bot responses

There is no warning to the user. A correctness-only run on data with non-standard bot formatting could evaluate zero messages, showing "No applicable correctness evaluations" for every thread without explanation.

The heuristic is intentionally inclusive (false positives are cheap — the LLM returns NOT_APPLICABLE). But the indicator list is narrow enough that false negatives are plausible in production data.

### F5 — Dashboard stats polluted by phantom entries from other run types [MEDIUM]

**Location:** `eval_runs.py:145-151`

The `/stats/summary` endpoint queries `ThreadEvaluation.worst_correctness` across ALL thread evaluation records:

```python
select(ThreadEvaluation.worst_correctness, func.count())
    .where(ThreadEvaluation.worst_correctness.isnot(None))
    .group_by(ThreadEvaluation.worst_correctness)
```

This includes:
1. Threads from correctness-enabled runs (legitimate data)
2. Threads from intent-only runs where `worst_correctness` defaults to `"NOT APPLICABLE"` (phantom data — see F3)

Both contribute to the dashboard's correctness distribution. There is no filter for "only include threads where correctness was actually enabled." Intent-only runs inject `NOT APPLICABLE` counts into a metric they have nothing to do with.

The same problem exists for efficiency: intent-only and correctness-only runs inject `"N/A"` into the efficiency distribution.

### F9 — All-NOT-APPLICABLE threads lack diagnostic context [LOW]

**Location:** `CorrectnessTab.tsx:46-56`

When every message in a thread returns `is_meal_summary=False`, all correctness evaluations are `NOT APPLICABLE`. The tab filters them out and shows: "No applicable correctness evaluations."

This message is accurate but provides no diagnostic context:
- The user doesn't know whether the evaluator ran and found no meals, or failed silently
- There's no indication of what the `is_meal_summary` heuristic looked for
- The `worst_correctness` column in the eval table shows `NOT APPLICABLE`, which doesn't distinguish "no meals to check" from "evaluator was skipped/disabled"

### F10 — Underscore/space verdict normalization is implicit [LOW]

The correctness flow has a multi-step normalization chain:

1. **LLM produces:** `SOFT_FAIL` (underscore, as constrained by JSON schema enum)
2. **Backend `_parse_result`:** `replace("_", " ")` → `SOFT FAIL`
3. **DB stores:** `SOFT FAIL` (space)
4. **API returns:** `SOFT FAIL` (space)
5. **TypeScript type:** `"SOFT FAIL"` (space)
6. **Frontend `normalizeLabel`:** `replace(/_/g, " ").toUpperCase()` → `SOFT FAIL` (idempotent)

This chain works but is implicit — the contract that verdicts use spaces internally is not documented. The LLM schema uses underscores because JSON keys with spaces are unusual, but the backend immediately converts to spaces. Any new code path that compares verdicts must know about this normalization, and there is no centralized constant or enum for the canonical verdict forms.

### F11 — Image context lookback limited to 2 messages [NOTE]

**Location:** `correctness_evaluator.py:142-147`

```python
has_image_context = message.has_image
if not has_image_context and conversation_history:
    for m in conversation_history[-2:]:
        if m.has_image:
            has_image_context = True
            break
```

Only the current message and last 2 history messages are checked for image context. If an image was uploaded 3+ turns ago and the bot is still referencing it in the current meal summary, `has_image_context` is `False`. This means:
- Quantity coherence check runs (should be skipped for image-sourced food)
- A false `HARD FAIL` or `CRITICAL` could result from quantity mismatches that exist because the food was identified from an image, not from user text

In practice this is rare — most image-based meals are evaluated within 2 turns of the image upload. But for longer conversations with corrections/edits, the lookback window may be too short.

### F3 — Phantom counts in run summary (shared with intent) [MEDIUM]

See `INTENT_FLOW_ANALYSIS.md` F3. When correctness is the only enabled evaluator:
- `intent_accuracy` defaults to `0.0` (phantom — dragged down by non-evaluation)
- `efficiency_verdict` defaults to `"N/A"` (phantom)

These are aggregated into the summary and stored, even though intent and efficiency never ran.

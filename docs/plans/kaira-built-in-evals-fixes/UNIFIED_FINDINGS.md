# Unified Findings — Intent & Correctness Built-in Evaluators

**Date:** 2026-02-28

This document consolidates all findings from the intent-only and correctness-only evaluation flow audits. Each finding is described once with cross-references to which flows it affects.

---

## F1 — `success_status` always `False` when efficiency is disabled [HIGH]

**Affects:** Intent-only runs, correctness-only runs, any run without efficiency enabled
**Location:** `backend/app/services/evaluators/batch_runner.py:471-473`

```python
is_success = bool(
    efficiency_result and efficiency_result.task_completed
)
```

When the efficiency evaluator is disabled, `efficiency_result` is `None`. The expression `bool(None and ...)` is always `False`. Every `ThreadEvaluation` row in a non-efficiency run gets `success_status=False` regardless of how well intent or correctness performed.

**What this affects:**
- The `success_status` column in the `thread_evaluations` table
- The `success_status` field in the `result` JSONB
- The EvalTable frontend component, which can sort/filter by success
- Any downstream analytics that treats `success_status` as a meaningful metric

**What the user sees:** An intent-only run with 100% accuracy shows every thread as "failed." A correctness-only run with all PASS verdicts shows every thread as "failed." The metric is semantically tied to efficiency's `task_completed` but is presented as a general success indicator.

---

## F2 — `intent_system_prompt: null` propagates as `None` to LLM provider [MEDIUM]

**Affects:** Intent-only runs (and any run with intent enabled where the user leaves the system prompt empty)
**Locations:**
- `src/features/evalRuns/components/NewBatchEvalOverlay.tsx:223`
- `backend/app/services/job_worker.py:343`
- `backend/app/services/evaluators/intent_evaluator.py:171`

**The chain:**

| Step | Code | Value |
|------|------|-------|
| Frontend sends | `intentSystemPrompt \|\| null` | `null` |
| JSON serialization | `{"intent_system_prompt": null}` | JSON null |
| Python receives | `params.get("intent_system_prompt", "")` | `None` (key exists, value is None; default `""` not used) |
| Evaluator stores | `self.system_prompt = system_prompt` | `None` |
| LLM call | `system_prompt=self.system_prompt` | `None` |

The enum parsing (`_parse_agents_from_prompt(None)`) guards with `if not system_prompt: return []` and falls through to Kaira defaults. This works.

But `self.system_prompt = None` is stored and later passed to the LLM provider as the system prompt. Whether `None` vs `""` behaves identically depends on the provider implementation. Currently works because the Gemini provider treats both as "no system prompt." This is a fragile implicit contract.

---

## F3 — Phantom metric values from disabled evaluators pollute run summary [MEDIUM]

**Affects:** All single-evaluator runs (intent-only, correctness-only)
**Location:** `backend/app/services/evaluators/batch_runner.py:451-468, 586-598`

When an evaluator is disabled, its output defaults to a zero/neutral value. These defaults are still aggregated into the run summary:

| Disabled Evaluator | Default Value | Where It Appears |
|-------------------|---------------|-----------------|
| Intent | `intent_accuracy = 0.0` | `summary.avg_intent_accuracy` (drags average to 0) |
| Correctness | `worst_correctness = "NOT APPLICABLE"` | `summary.correctness_verdicts` dict |
| Efficiency | `efficiency_verdict = "N/A"` | `summary.efficiency_verdicts` dict |

The evaluator descriptor logic in `eval_runs.py` correctly gates on `batch_metadata.evaluate_X` — it won't show a card for a disabled evaluator. But the raw summary data carries phantom values that leak into other views (see F5).

---

## F4 — `is_meal_summary` false negatives silently skip correctness evaluation [MEDIUM]

**Affects:** Correctness-only runs, any run with correctness enabled
**Location:** `backend/app/services/evaluators/models.py:127-135`

```python
indicators = ["total calories", "kcal", "meal summary", "consumed at"]
resp = self.final_response_message.lower()
return any(ind in resp for ind in indicators)
```

This is the only gate before the LLM correctness call. If the bot's response has nutritional data but doesn't contain any of these 4 exact substrings, the message gets `verdict="NOT APPLICABLE"` with no LLM call and no warning.

**False negative examples:**
- "Eggs — 140 calories" (has "calories" but not "total calories")
- "250 cal" (has "cal" but not "kcal")
- Markdown-formatted tables where keywords are split across lines
- Non-English responses

**What the user sees:** "No applicable correctness evaluations" on threads that actually contain meal summaries. No indication that the heuristic skipped them or what it was looking for.

---

## F5 — Dashboard stats polluted by phantom entries from unrelated run types [MEDIUM]

**Affects:** Correctness distribution and efficiency distribution on Dashboard
**Locations:**
- `backend/app/routes/eval_runs.py:145-151` (stats/summary endpoint)
- `src/features/evalRuns/pages/Dashboard.tsx:134-144` (distribution bar)

The `/stats/summary` endpoint queries `ThreadEvaluation.worst_correctness` and `efficiency_verdict` across ALL thread evaluation records with no filter for whether that evaluator was actually enabled:

```python
select(ThreadEvaluation.worst_correctness, func.count())
    .where(ThreadEvaluation.worst_correctness.isnot(None))
    .group_by(ThreadEvaluation.worst_correctness)
```

This means:
- Every intent-only run injects `{"NOT APPLICABLE": N}` into correctness_distribution and `{"N/A": N}` into efficiency_distribution
- Every correctness-only run injects `{"N/A": N}` into efficiency_distribution
- These phantom counts accumulate with every run

The dashboard distribution bars show inflated NOT APPLICABLE / N/A segments that represent threads where the evaluator was never invoked.

---

## F6 — `query_type` evaluated by LLM but never displayed in UI [LOW]

**Affects:** Intent evaluation results display
**Locations:**
- `backend/app/services/evaluators/intent_evaluator.py:224-231` (LLM evaluation)
- `src/features/evalRuns/components/threadReview/IntentTab.tsx` (display)

The LLM is asked to classify both `predicted_agent` and `query_type` on every message. Both are stored in the JSONB result. But `IntentTab` only renders:
- `is_correct_intent` (checkmark/cross)
- `predicted_intent` (column)
- `message.intent_detected` (ground truth column)
- `confidence`, `reasoning`

`predicted_query_type`, `is_correct_query_type`, and `all_predictions` are never shown. The data exists in the API response and now has TypeScript types, but no component reads it.

---

## F7 — Empty `intent_query_type` ground truth produces false negatives [LOW]

**Affects:** `is_correct_query_type` field in IntentEvaluation
**Locations:**
- `backend/app/services/evaluators/models.py:120` (CSV parsing)
- `backend/app/services/evaluators/intent_evaluator.py:231` (comparison)

When `intent_query_type` is NaN or absent in the CSV, the ground truth is stored as `""`. The LLM predicts a value like `"logging"`. The comparison:

```python
_normalize_intent("") == _normalize_intent("logging")  →  "" == "logging"  →  False
```

Every message with missing ground truth gets `is_correct_query_type=False` — a false negative. Not currently visible in the UI (F6), but the data is stored in JSONB and would produce misleading accuracy numbers if ever surfaced.

---

## F8 — Client-side vs server-side `avg_intent_accuracy` diverge on error threads [LOW]

**Affects:** Intent accuracy display when some threads have LLM errors
**Locations:**
- `backend/app/services/evaluators/batch_runner.py:586-590` (server aggregation)
- `src/features/evalRuns/pages/RunDetail.tsx` (client aggregation)

**Server-side:** Only sums `intent_accuracy` for non-error threads. Error threads are excluded from both numerator and denominator.

**Client-side:**
```typescript
threadEvals.reduce((s, e) => s + (e.intent_accuracy ?? 0), 0) / threadEvals.length
```
Includes ALL threads. Error threads contribute `0.0` to the sum but count in the denominator.

**Example:** 10 threads, 9 succeed with 90% accuracy, 1 errors.
- Server: `(9 * 0.9) / 9 = 0.9` (90%)
- Client: `(9 * 0.9 + 0.0) / 10 = 0.81` (81%)

The dashboard shows 90%. The run detail page shows 81%. The discrepancy grows with more errors.

---

## F9 — All-NOT-APPLICABLE threads lack diagnostic context [LOW]

**Affects:** Correctness tab in thread detail view
**Location:** `src/features/evalRuns/components/threadReview/CorrectnessTab.tsx:46-56`

When every message in a thread has `is_meal_summary=False`, all correctness evaluations are NOT APPLICABLE. The tab filters them out and shows:

> "No applicable correctness evaluations."

This is accurate but gives the user no context:
- No indication of why (the `is_meal_summary` heuristic found no keywords)
- No list of what keywords were checked
- No way to distinguish "no meals in this thread" from "evaluator error" from "evaluator disabled"
- The SummaryBar shows NOT APPLICABLE for worst_correctness, which looks identical to the phantom entries from intent-only runs (F5)

---

## F10 — Underscore/space verdict normalization chain is implicit and undocumented [LOW]

**Affects:** Correctness verdicts throughout the stack
**Locations:** Multiple files across backend and frontend

The normalization chain:

```
LLM produces    →  SOFT_FAIL  (underscore, from JSON schema enum)
_parse_result   →  SOFT FAIL  (space, via .replace("_", " "))
DB stores       →  SOFT FAIL  (space)
API returns     →  SOFT FAIL  (space)
TS type         →  "SOFT FAIL" (space)
normalizeLabel  →  SOFT FAIL  (space, via .replace(/_/g, " ").toUpperCase())
```

This works but is implicit. There is no shared constant, enum, or documentation that declares the canonical form. New code that compares verdicts must know about this normalization. The schema sends underscored enums to the LLM, but every other layer uses spaces.

---

## F11 — Image context lookback limited to 2 messages [NOTE]

**Affects:** Correctness evaluation of image-based meals in long conversations
**Location:** `backend/app/services/evaluators/correctness_evaluator.py:142-147`

The evaluator checks the current message and last 2 history messages for `has_image`. If an image was uploaded 3+ turns ago, `has_image_context` is `False`. This means:
- The quantity coherence check runs (should be skipped for image meals)
- A false HARD FAIL or CRITICAL could result from quantity mismatches

In practice this is uncommon — most image meals are evaluated within 2 turns. But conversations with multiple corrections or edits could exceed the lookback window.

---

## F12 — No `app_id` from frontend; hardcoded to `kaira-bot` [NOTE]

**Affects:** Both intent and correctness flows
**Locations:**
- `src/features/evalRuns/components/NewBatchEvalOverlay.tsx` (no app_id in params)
- `backend/app/services/job_worker.py:337` (default: `"kaira-bot"`)

The batch evaluation wizard does not send `app_id`. The backend defaults to `"kaira-bot"`. Correct for the current product state, but prevents other apps from using batch evaluation without backend changes.

---

## Summary by Severity

### HIGH (1)

| # | Finding | Root Cause |
|---|---------|-----------|
| F1 | success_status always False | `is_success` is gated on efficiency_result which is None when efficiency disabled |

### MEDIUM (4)

| # | Finding | Root Cause |
|---|---------|-----------|
| F2 | null system prompt propagates to LLM | Frontend sends null, Python passes None through instead of coercing to "" |
| F3 | Phantom metric values in summary | Disabled evaluators still produce default values that get aggregated |
| F4 | is_meal_summary skips valid meals | Keyword list is too narrow for all possible bot response formats |
| F5 | Dashboard stats include phantom entries | Stats query has no filter for whether evaluator was enabled |

### LOW (5)

| # | Finding | Root Cause |
|---|---------|-----------|
| F6 | query_type invisible in UI | IntentTab doesn't render predicted_query_type or is_correct_query_type |
| F7 | Empty ground truth = false negative | Missing CSV field → empty string → comparison always fails |
| F8 | Client/server accuracy mismatch | Client includes error threads (0.0) in average, server excludes them |
| F9 | NOT APPLICABLE shows no diagnostic | CorrectnessTab shows a generic message with no context on why |
| F10 | Verdict normalization is implicit | Underscore→space conversion is not documented or centralized |

### NOTE (2)

| # | Finding | Root Cause |
|---|---------|-----------|
| F11 | Image lookback too short | Only checks last 2 messages for has_image |
| F12 | app_id hardcoded | Frontend doesn't send it, backend defaults to kaira-bot |

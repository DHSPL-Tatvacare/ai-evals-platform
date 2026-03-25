# Phase 1: Backend Foundation + Shared Components

## Goal
Enrich the backend data so the frontend has everything it needs to render custom evaluator results dynamically. Fix VoiceRx summary bug. Add Run All backend support. Create the shared OutputFieldRenderer component.

## Prerequisites
- Docker Compose running (PostgreSQL + backend)
- Existing data can be wiped (no migration concerns)

---

## Change 1: Enrich Batch Summary with Custom Evaluator Distributions

**File:** `backend/app/services/evaluators/batch_runner.py`

### What to change

Currently (lines 302-306, 315-319), the summary for custom evaluators only stores `{name, completed, errors}`. We need to also aggregate the primary output field's distribution (for verdict-type fields) or average (for numeric fields).

### How

**Step 1:** After loading custom evaluators (line 215), detect each evaluator's primary field from its `output_schema`:

```python
def _detect_primary_field(output_schema: list[dict]) -> dict | None:
    """Find the primary field for summary aggregation.

    Priority: isMainMetric=true > first enum-like field > first number field > first field.
    """
    if not output_schema:
        return None

    # 1. Explicit main metric
    for f in output_schema:
        if f.get("isMainMetric"):
            return {"key": f["key"], "type": f.get("type", "text"), "thresholds": f.get("thresholds")}

    # 2. First number field (likely a score)
    for f in output_schema:
        if f.get("type") == "number":
            return {"key": f["key"], "type": "number", "thresholds": f.get("thresholds")}

    # 3. First text field (likely a verdict)
    for f in output_schema:
        if f.get("type") == "text":
            return {"key": f["key"], "type": "text"}

    # 4. First field regardless
    return {"key": output_schema[0]["key"], "type": output_schema[0].get("type", "text")}
```

Place this as a module-level function near the top of batch_runner.py.

**Step 2:** Initialize richer summary structure. Currently (around line 227, in the setup before the thread loop):

Change the `results_summary["custom_evaluations"]` initialization. After loading custom evaluators, build a map:

```python
# After loading custom_evaluators (line 215)
custom_eval_meta = {}
for cev in custom_evaluators:
    pf = _detect_primary_field(cev.output_schema)
    custom_eval_meta[str(cev.id)] = {
        "name": cev.name,
        "output_schema": cev.output_schema,
        "primary_field": pf,
    }

# In results_summary initialization, replace existing custom_evaluations init:
results_summary["custom_evaluations"] = {
    str(cev.id): {
        "name": cev.name,
        "completed": 0,
        "errors": 0,
        "output_schema": cev.output_schema,
        "primary_field": custom_eval_meta[str(cev.id)]["primary_field"],
        "distribution": {},   # For verdict-type: {"PASS": 5, "FAIL": 2}
        "values": [],         # For number-type: collect all values for avg
    }
    for cev in custom_evaluators
}
```

**Step 3:** After each successful custom eval (line 306), aggregate the primary field value:

```python
# After: results_summary["custom_evaluations"][str(cev.id)]["completed"] += 1
# Add:
pf_meta = custom_eval_meta.get(str(cev.id), {}).get("primary_field")
if pf_meta and output:
    pf_val = output.get(pf_meta["key"])
    if pf_val is not None:
        entry = results_summary["custom_evaluations"][str(cev.id)]
        if pf_meta["type"] == "number" and isinstance(pf_val, (int, float)):
            entry["values"].append(pf_val)
        elif isinstance(pf_val, str):
            entry["distribution"][pf_val] = entry["distribution"].get(pf_val, 0) + 1
```

**Step 4:** Before saving final summary (around line 428), compute averages and clean up:

```python
# After all threads processed, before final EvalRun update:
for cev_id, cev_summary in results_summary.get("custom_evaluations", {}).items():
    values = cev_summary.pop("values", [])
    if values:
        cev_summary["average"] = sum(values) / len(values)
```

### Result

`EvalRun.summary.custom_evaluations` becomes:
```json
{
  "uuid-1": {
    "name": "Health Accuracy",
    "completed": 48,
    "errors": 2,
    "output_schema": [{"key": "verdict", "type": "text", ...}, ...],
    "primary_field": {"key": "verdict", "type": "text"},
    "distribution": {"SAFE": 30, "CAUTION": 15, "UNSAFE": 3}
  },
  "uuid-2": {
    "name": "Empathy Score",
    "completed": 50,
    "errors": 0,
    "output_schema": [{"key": "score", "type": "number", "isMainMetric": true, ...}],
    "primary_field": {"key": "score", "type": "number"},
    "average": 0.78
  }
}
```

---

## Change 2: Return Evaluator Descriptors in Run API Response

**File:** `backend/app/routes/eval_runs.py`

### What to change

The `_run_to_dict()` function (around line 325) needs to include `evaluator_descriptors` so the frontend knows what columns to render.

### How

Add a helper function and call it from `_run_to_dict`:

```python
def _build_evaluator_descriptors(run: EvalRun) -> list[dict]:
    """Build evaluator descriptors from run metadata for frontend rendering."""
    descriptors = []
    summary = run.summary or {}
    batch_meta = run.batch_metadata or {}

    # Built-in evaluators (only if they were enabled)
    # Check batch_metadata for flags, or if summary has their data
    if batch_meta.get("evaluate_intent", True):
        descriptors.append({
            "id": "intent",
            "name": "Intent Accuracy",
            "type": "built-in",
            "primaryField": {
                "key": "intent_accuracy",
                "format": "percentage",
            },
            "aggregation": {
                "average": summary.get("avg_intent_accuracy"),
                "completedCount": summary.get("completed", 0),
                "errorCount": summary.get("errors", 0),
            },
        })

    if batch_meta.get("evaluate_correctness", True):
        descriptors.append({
            "id": "correctness",
            "name": "Correctness",
            "type": "built-in",
            "primaryField": {
                "key": "worst_correctness",
                "format": "verdict",
                "verdictOrder": ["PASS", "NOT APPLICABLE", "SOFT FAIL", "HARD FAIL", "CRITICAL"],
            },
            "aggregation": {
                "distribution": summary.get("correctness_verdicts", {}),
                "completedCount": summary.get("completed", 0),
                "errorCount": summary.get("errors", 0),
            },
        })

    if batch_meta.get("evaluate_efficiency", True):
        descriptors.append({
            "id": "efficiency",
            "name": "Efficiency",
            "type": "built-in",
            "primaryField": {
                "key": "efficiency_verdict",
                "format": "verdict",
                "verdictOrder": ["EFFICIENT", "ACCEPTABLE", "FRICTION", "BROKEN"],
            },
            "aggregation": {
                "distribution": summary.get("efficiency_verdicts", {}),
                "completedCount": summary.get("completed", 0),
                "errorCount": summary.get("errors", 0),
            },
        })

    # Custom evaluators from summary
    custom_evals = summary.get("custom_evaluations", {})
    for cev_id, cev_data in custom_evals.items():
        pf = cev_data.get("primary_field", {})
        pf_format = "text"
        if pf.get("type") == "number":
            pf_format = "number"
        elif cev_data.get("distribution"):
            pf_format = "verdict"

        desc = {
            "id": cev_id,
            "name": cev_data.get("name", "Unknown"),
            "type": "custom",
            "outputSchema": cev_data.get("output_schema", []),
            "primaryField": {
                "key": pf.get("key", ""),
                "format": pf_format,
            },
            "aggregation": {
                "completedCount": cev_data.get("completed", 0),
                "errorCount": cev_data.get("errors", 0),
            },
        }

        if cev_data.get("distribution"):
            desc["primaryField"]["verdictOrder"] = list(cev_data["distribution"].keys())
            desc["aggregation"]["distribution"] = cev_data["distribution"]

        if cev_data.get("average") is not None:
            desc["aggregation"]["average"] = cev_data["average"]
            desc["primaryField"]["format"] = "percentage" if cev_data["average"] <= 1 else "number"

        descriptors.append(desc)

    return descriptors
```

Then in `_run_to_dict`, add to the returned dict:

```python
# Add after existing fields (around line 389):
"evaluator_descriptors": _build_evaluator_descriptors(r),
```

### Also store evaluator flags in batch_metadata

**File:** `backend/app/services/evaluators/batch_runner.py`

When creating the EvalRun, store the evaluator toggle flags so `_build_evaluator_descriptors` can read them. In the batch_metadata dict (around lines 115-122):

```python
batch_metadata={
    # ... existing fields ...
    "evaluate_intent": evaluate_intent,
    "evaluate_correctness": evaluate_correctness,
    "evaluate_efficiency": evaluate_efficiency,
    "custom_evaluator_ids": [str(eid) for eid in (custom_evaluator_ids or [])],
},
```

---

## Change 3: Parallel Custom Evaluator Execution

**File:** `backend/app/services/evaluators/batch_runner.py`

### What to change

Currently custom evaluators run sequentially (lines 285-319). Add opt-in parallel execution.

### How

**Step 1:** Add `parallel_custom_evals: bool = False` parameter to `run_batch_evaluation()`.

**Step 2:** Replace the sequential loop (lines 285-319) with a conditional:

```python
# Run custom evaluators on this thread
if custom_evaluators:
    interleaved = []
    for m in thread.messages:
        interleaved.append({"role": "user", "content": m.query_text})
        interleaved.append({"role": "assistant", "content": m.final_response_message})

    async def _run_one_custom(cev):
        """Execute a single custom evaluator. Returns (cev_id, result_dict)."""
        cev_id = str(cev.id)
        try:
            resolve_ctx = {"messages": interleaved}
            resolved = resolve_prompt(cev.prompt, resolve_ctx)
            prompt_text = resolved["prompt"]
            json_schema = generate_json_schema(cev.output_schema)
            output = await llm.generate_json(
                prompt=prompt_text,
                json_schema=json_schema,
            )
            return cev_id, {
                "evaluator_id": cev_id,
                "evaluator_name": cev.name,
                "status": "completed",
                "output": output,
            }, None
        except Exception as ce_err:
            logger.error("Custom evaluator %s failed for thread %s: %s", cev.id, thread_id, ce_err)
            return cev_id, {
                "evaluator_id": cev_id,
                "evaluator_name": cev.name,
                "status": "failed",
                "error": safe_error_message(ce_err),
            }, ce_err

    if parallel_custom_evals:
        # Parallel execution via asyncio.gather
        results_list = await asyncio.gather(
            *[_run_one_custom(cev) for cev in custom_evaluators],
            return_exceptions=False,  # exceptions handled inside _run_one_custom
        )
    else:
        # Sequential execution (default, safer for rate limits)
        results_list = []
        for cev in custom_evaluators:
            results_list.append(await _run_one_custom(cev))

    # Process results
    for cev_id, result_dict, exc in results_list:
        custom_results[cev_id] = result_dict
        entry = results_summary["custom_evaluations"].get(cev_id)
        if not entry:
            # Safety: should already be initialized, but handle edge case
            cev_obj = next((c for c in custom_evaluators if str(c.id) == cev_id), None)
            entry = {"name": cev_obj.name if cev_obj else "Unknown", "completed": 0, "errors": 0}
            results_summary["custom_evaluations"][cev_id] = entry

        if result_dict["status"] == "completed":
            entry["completed"] += 1
            # Aggregate primary field (same logic as Change 1 Step 3)
            pf_meta = custom_eval_meta.get(cev_id, {}).get("primary_field")
            if pf_meta and result_dict.get("output"):
                pf_val = result_dict["output"].get(pf_meta["key"])
                if pf_val is not None:
                    if pf_meta["type"] == "number" and isinstance(pf_val, (int, float)):
                        entry.setdefault("values", []).append(pf_val)
                    elif isinstance(pf_val, str):
                        entry["distribution"] = entry.get("distribution", {})
                        entry["distribution"][pf_val] = entry["distribution"].get(pf_val, 0) + 1
        else:
            entry["errors"] += 1
```

**Step 3:** Add `import asyncio` at top of file if not already present.

**Step 4:** Thread the `parallel_custom_evals` parameter through from `handle_evaluate_batch` in job_worker.py:

In `backend/app/services/job_worker.py`, around line 216:
```python
@register_job_handler("evaluate-batch")
async def handle_evaluate_batch(job_id, params: dict) -> dict:
    from app.services.evaluators.batch_runner import run_batch_evaluation
    return await run_batch_evaluation(
        job_id=job_id,
        # ... existing params ...
        parallel_custom_evals=params.get("parallel_custom_evals", False),
    )
```

---

## Change 4: Fix VoiceRx Summary Population

**File:** `backend/app/services/evaluators/voice_rx_runner.py`

### What to change

The `summary` field is never set for `full_evaluation` runs. VoiceRxRunList shows `--` because `extractMainScore()` finds nothing in `summary`.

### How

Before the final `update(EvalRun)` call (around line 548-556), compute and store a summary:

```python
# Build summary from evaluation result
summary_data = None
if evaluation.get("status") == "completed":
    summary_data = {}

    if is_api_flow and evaluation.get("apiCritique"):
        critique = evaluation["apiCritique"]
        if isinstance(critique, dict):
            # Extract scores from API critique
            for score_key in ["overall_score", "accuracy_score", "factual_integrity_score"]:
                if score_key in critique:
                    summary_data[score_key] = critique[score_key]
            if critique.get("segments"):
                total = len(critique["segments"])
                matches = sum(1 for s in critique["segments"]
                            if s.get("accuracy", "").lower() in ("match", "none"))
                summary_data["overall_accuracy"] = matches / total if total > 0 else 0
                summary_data["total_segments"] = total
                severity_dist = {}
                for s in critique["segments"]:
                    sev = s.get("severity", "none").upper()
                    severity_dist[sev] = severity_dist.get(sev, 0) + 1
                summary_data["severity_distribution"] = severity_dist

    elif evaluation.get("critique"):
        critique = evaluation["critique"]
        if isinstance(critique, dict):
            segments = critique.get("segments", [])
            total = len(segments)
            if total > 0:
                matches = sum(1 for s in segments
                            if s.get("accuracy", "").lower() in ("match", "none"))
                summary_data["overall_accuracy"] = matches / total
                summary_data["total_segments"] = total

                severity_dist = {}
                for s in segments:
                    sev = s.get("severity", "none").upper()
                    severity_dist[sev] = severity_dist.get(sev, 0) + 1
                summary_data["severity_distribution"] = severity_dist
                summary_data["critical_errors"] = severity_dist.get("CRITICAL", 0)
                summary_data["moderate_errors"] = severity_dist.get("MODERATE", 0)
                summary_data["minor_errors"] = severity_dist.get("MINOR", 0)

            if critique.get("overallScore") is not None:
                summary_data["overall_score"] = critique["overallScore"]

# Then in the update call, add summary=summary_data:
async with async_session() as db:
    await db.execute(
        update(EvalRun).where(EvalRun.id == eval_run_id).values(
            status="completed",
            completed_at=completed_at,
            duration_ms=duration_ms,
            result=evaluation,
            summary=summary_data,  # NEW
        )
    )
    await db.commit()
```

---

## Change 5: VoiceRx "Run All" Backend Handler

**File:** `backend/app/services/evaluators/voice_rx_batch_custom_runner.py` (NEW)

### What this does

A new job handler that takes a list of evaluator IDs + a listing_id, and runs all evaluators on that listing. Creates N separate EvalRun rows (one per evaluator) so results appear individually in VoiceRxRunList, but orchestrates them in a single job.

### Full file:

```python
"""Voice-RX batch custom evaluator runner — runs multiple evaluators on one listing.

Creates N EvalRun rows (one per evaluator, eval_type='custom').
Called by the job worker when processing 'evaluate-custom-batch' jobs.
"""
import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import update

from app.database import async_session
from app.models.evaluator import Evaluator
from app.models.eval_run import EvalRun
from app.models.job import Job
from app.services.evaluators.custom_evaluator_runner import run_custom_evaluator
from app.services.job_worker import is_job_cancelled, JobCancelledError, safe_error_message

logger = logging.getLogger(__name__)


async def run_voice_rx_batch_custom(job_id, params: dict) -> dict:
    """Run multiple custom evaluators on a single listing/session.

    Params:
        evaluator_ids: list[str]  - UUIDs of evaluators to run
        listing_id: str           - UUID of listing (voice-rx)
        session_id: str           - UUID of session (kaira-bot) — optional
        app_id: str               - "voice-rx" or "kaira-bot"
        parallel: bool            - Run evaluators in parallel (default: True)
        timeouts: dict            - LLM timeout config
    """
    evaluator_ids = params["evaluator_ids"]
    listing_id = params.get("listing_id")
    session_id = params.get("session_id")
    app_id = params.get("app_id", "voice-rx")
    parallel = params.get("parallel", True)
    total = len(evaluator_ids)

    # Validate evaluators exist
    async with async_session() as db:
        valid_ids = []
        for eid in evaluator_ids:
            ev = await db.get(Evaluator, eid)
            if ev:
                valid_ids.append(eid)
            else:
                logger.warning("Evaluator %s not found, skipping", eid)

        if not valid_ids:
            raise ValueError("No valid evaluators found")

    total = len(valid_ids)
    completed = 0
    errors = 0
    eval_run_ids = []

    async def _update_progress(current, message):
        async with async_session() as db:
            await db.execute(
                update(Job).where(Job.id == job_id).values(
                    progress={
                        "current": current,
                        "total": total,
                        "message": message,
                    }
                )
            )
            await db.commit()

    await _update_progress(0, f"Starting {total} evaluators...")

    async def _run_one(eid, index):
        """Run one evaluator, creating its own job-like context."""
        nonlocal completed, errors

        if await is_job_cancelled(job_id):
            raise JobCancelledError("Batch cancelled")

        # Build params for the existing custom evaluator runner
        sub_params = {
            "evaluator_id": eid,
            "app_id": app_id,
            "timeouts": params.get("timeouts"),
        }
        if listing_id:
            sub_params["listing_id"] = listing_id
        if session_id:
            sub_params["session_id"] = session_id

        try:
            # Reuse existing custom_evaluator_runner but with our job_id
            result = await run_custom_evaluator(job_id=job_id, params=sub_params)
            eval_run_ids.append(result.get("eval_run_id"))
            completed += 1
            return result
        except Exception as e:
            errors += 1
            logger.error("Batch custom eval %s failed: %s", eid, e)
            return {"evaluator_id": eid, "status": "failed", "error": safe_error_message(e)}

    try:
        if parallel:
            # Run all in parallel
            tasks = [_run_one(eid, i) for i, eid in enumerate(valid_ids)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            # Handle any unexpected exceptions from gather
            for i, r in enumerate(results):
                if isinstance(r, Exception):
                    errors += 1
                    logger.error("Batch custom eval %s raised: %s", valid_ids[i], r)
        else:
            # Run sequentially with progress updates
            for i, eid in enumerate(valid_ids):
                await _update_progress(i, f"Running evaluator {i + 1}/{total}...")
                await _run_one(eid, i)

        await _update_progress(total, f"Completed: {completed} success, {errors} failed")

    except JobCancelledError:
        logger.info("Batch custom eval cancelled at %d/%d", completed, total)
        raise

    return {
        "total": total,
        "completed": completed,
        "errors": errors,
        "eval_run_ids": eval_run_ids,
    }
```

### Register in job_worker.py

**File:** `backend/app/services/job_worker.py`

Add after the existing `handle_evaluate_custom` handler (around line 282):

```python
@register_job_handler("evaluate-custom-batch")
async def handle_evaluate_custom_batch(job_id, params: dict) -> dict:
    """Run multiple custom evaluators on a single entity."""
    from app.services.evaluators.voice_rx_batch_custom_runner import run_voice_rx_batch_custom
    return await run_voice_rx_batch_custom(job_id=job_id, params=params)
```

### Important note on `run_custom_evaluator` reuse

The existing `custom_evaluator_runner.py:run_custom_evaluator()` creates its own EvalRun row. When called from the batch runner, each call creates a separate EvalRun, which is what we want — each evaluator result shows as its own run in VoiceRxRunList.

However, `run_custom_evaluator` currently uses `job_id` to set `EvalRun.job_id`. When multiple EvalRuns share the same parent job_id, the Job → EvalRun link becomes one-to-many. This is fine for queries (the API queries by run_id not job_id), but note that `cancel_job()` in `jobs.py` currently does:

```python
await db.execute(
    update(EvalRun).where(EvalRun.job_id == job_id, ...).values(status="cancelled")
)
```

This will correctly cancel ALL associated EvalRuns when the batch job is cancelled. This is the desired behavior.

---

## Change 6: Frontend Types

**File:** `src/types/evalRuns.ts`

### Add these types

```typescript
/** Definition of a single output field from an evaluator's schema. */
export interface OutputFieldDef {
  key: string;
  label?: string;
  type: 'number' | 'text' | 'boolean' | 'array';
  description?: string;
  isMainMetric?: boolean;
  thresholds?: { green: number; yellow?: number; red?: number };
  displayMode?: 'badge' | 'bar' | 'hidden';
  enumValues?: string[];
}

/** Describes how to render an evaluator's results in the UI. */
export interface EvaluatorDescriptor {
  id: string;
  name: string;
  type: 'built-in' | 'custom';
  outputSchema?: OutputFieldDef[];
  primaryField?: {
    key: string;
    format: 'verdict' | 'percentage' | 'number' | 'boolean' | 'text';
    verdictOrder?: string[];
  };
  aggregation?: {
    distribution?: Record<string, number>;
    average?: number;
    completedCount: number;
    errorCount: number;
  };
}
```

### Update the Run type

Add `evaluatorDescriptors` to the existing `Run` interface (check exact interface name in `src/types/evalRuns.ts`):

```typescript
// Add to Run interface:
evaluator_descriptors?: EvaluatorDescriptor[];
// or camelCase if that's the convention:
evaluatorDescriptors?: EvaluatorDescriptor[];
```

**Note:** The backend returns both camelCase and snake_case. Check which the frontend uses and add accordingly. The `_run_to_dict` will return `evaluator_descriptors` (snake_case). You may need to add the camelCase alias in the backend serialization too.

---

## Change 7: OutputFieldRenderer Component

**File:** `src/features/evalRuns/components/OutputFieldRenderer.tsx` (NEW)

### What this component does

Takes an evaluator's output_schema and actual output values, renders each field with appropriate formatting. Used across all scenarios.

### Component API

```typescript
interface OutputFieldRendererProps {
  /** Field definitions from evaluator's output_schema */
  schema: OutputFieldDef[];
  /** Actual output values from evaluation result */
  output: Record<string, unknown>;
  /**
   * Rendering mode:
   * - 'card': Full card with labels and descriptions (detail view)
   * - 'inline': Compact key:value pairs (expanded table row)
   * - 'badge': Just the primary field as a badge (table cell)
   */
  mode: 'card' | 'inline' | 'badge';
  /** If set, only render this field (for table cell mode) */
  fieldKey?: string;
}
```

### Implementation guidance

```tsx
export function OutputFieldRenderer({ schema, output, mode, fieldKey }: OutputFieldRendererProps) {
  const fields = fieldKey
    ? schema.filter(f => f.key === fieldKey)
    : schema.filter(f => f.displayMode !== 'hidden');

  if (mode === 'badge') {
    // Render just the value with appropriate formatting
    const field = fields[0];
    if (!field) return null;
    const value = output[field.key];
    return <FieldValue field={field} value={value} compact />;
  }

  if (mode === 'inline') {
    return (
      <div className="space-y-1">
        {fields.map(f => (
          <div key={f.key} className="flex items-start gap-2 text-sm">
            <span className="text-[var(--text-muted)] shrink-0 font-medium">
              {f.label || f.key}:
            </span>
            <FieldValue field={f} value={output[f.key]} />
          </div>
        ))}
      </div>
    );
  }

  // mode === 'card'
  return (
    <div className="space-y-2">
      {fields.map(f => (
        <div key={f.key} className="flex items-start gap-3">
          <div className="min-w-[120px]">
            <span className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
              {f.label || f.key}
            </span>
            {f.description && (
              <p className="text-xs text-[var(--text-muted)] mt-0.5">{f.description}</p>
            )}
          </div>
          <FieldValue field={f} value={output[f.key]} />
        </div>
      ))}
    </div>
  );
}
```

### FieldValue sub-component (in same file)

```tsx
function FieldValue({ field, value, compact }: { field: OutputFieldDef; value: unknown; compact?: boolean }) {
  if (value == null) return <span className="text-[var(--text-muted)]">—</span>;

  switch (field.type) {
    case 'number': {
      const num = Number(value);
      const color = getScoreColor(num, field.thresholds);
      if (compact) {
        // For table cells: just the number with color
        const display = num <= 1 ? `${(num * 100).toFixed(0)}%` : String(num);
        return <span style={{ color }} className="font-semibold">{display}</span>;
      }
      return (
        <div className="flex items-center gap-2">
          <span style={{ color }} className="font-semibold text-sm">
            {num <= 1 ? `${(num * 100).toFixed(0)}%` : num}
          </span>
          {field.thresholds && <ScoreBar value={num} thresholds={field.thresholds} />}
        </div>
      );
    }

    case 'boolean':
      return value
        ? <span className="text-[var(--color-success)] font-medium text-sm">Pass</span>
        : <span className="text-[var(--color-error)] font-medium text-sm">Fail</span>;

    case 'text': {
      const str = String(value);
      // If it looks like a verdict (short uppercase string), render as badge
      if (str.length <= 30 && str === str.toUpperCase().replace(/[^A-Z_ ]/g, '')) {
        // Use existing VerdictBadge or a simple colored badge
        return <VerdictBadge verdict={str} category="custom" />;
      }
      // Long text: truncate in compact mode
      if (compact && str.length > 40) {
        return <span className="text-sm text-[var(--text-primary)] truncate max-w-[200px]">{str}</span>;
      }
      return <span className="text-sm text-[var(--text-primary)] break-words">{str}</span>;
    }

    case 'array':
      if (compact) return <span className="text-sm text-[var(--text-muted)]">[{Array.isArray(value) ? value.length : 0} items]</span>;
      return (
        <pre className="text-xs text-[var(--text-secondary)] bg-[var(--bg-tertiary)] rounded p-2 max-h-32 overflow-auto">
          {JSON.stringify(value, null, 2)}
        </pre>
      );

    default:
      return <span className="text-sm">{JSON.stringify(value)}</span>;
  }
}

function getScoreColor(value: number, thresholds?: { green: number; yellow?: number; red?: number }): string {
  if (!thresholds) {
    // Default: 0-1 scale
    const v = value > 1 ? value / 100 : value;
    if (v >= 0.7) return 'var(--color-success)';
    if (v >= 0.4) return 'var(--color-warning)';
    return 'var(--color-error)';
  }
  if (value >= thresholds.green) return 'var(--color-success)';
  if (thresholds.yellow != null && value >= thresholds.yellow) return 'var(--color-warning)';
  return 'var(--color-error)';
}

function ScoreBar({ value, thresholds }: { value: number; thresholds: { green: number } }) {
  const pct = Math.min(100, Math.max(0, (value / thresholds.green) * 100));
  const color = getScoreColor(value, thresholds);
  return (
    <div className="flex-1 h-1.5 bg-[var(--bg-tertiary)] rounded-full max-w-[80px]">
      <div className="h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: color }} />
    </div>
  );
}
```

### Register in exports

**File:** `src/features/evalRuns/components/index.ts`

Add:
```typescript
export { OutputFieldRenderer } from './OutputFieldRenderer';
```

### VerdictBadge for custom verdicts

The existing `VerdictBadge` component may need to handle unknown verdict strings gracefully. Check if it falls back for unknown categories. If it doesn't, add a `"custom"` category fallback in `labelDefinitions.ts` that gives a neutral color to any unknown verdict string.

---

## Testing Phase 1

After implementing all changes:

1. **Start fresh:** `docker compose down -v && docker compose up --build`
2. **Run a Kaira batch with custom evaluators:**
   - Upload a CSV, enable all 3 built-ins + 2 custom evaluators
   - Wait for completion
   - Check the API response: `GET /api/eval-runs/{id}` should include `evaluator_descriptors`
   - Check `summary.custom_evaluations` has `distribution` or `average` + `output_schema`
3. **Run a VoiceRx full evaluation:**
   - Evaluate a listing
   - Check the API response: `summary` should now have accuracy metrics
   - VoiceRxRunList should show a score instead of `--`
4. **Test OutputFieldRenderer in isolation:**
   - Import in any existing component, pass mock data, verify it renders correctly
   - Test each mode: 'card', 'inline', 'badge'
5. **Test parallel execution:**
   - Run a batch with `parallel_custom_evals: true` (you'll need to pass this through temporarily)
   - Verify all custom evaluators complete without errors

---

## Notes

- No DB migrations needed. All changes are in JSONB columns (summary, batch_metadata).
- Existing completed runs will have `evaluator_descriptors: []` (empty) since their summary doesn't have the new fields. This is acceptable.
- The `voice_rx_batch_custom_runner.py` reuses `custom_evaluator_runner.py` — no code duplication.
- The `_detect_primary_field` function is intentionally simple. It can be made smarter later (e.g., detecting enum fields from InlineSchemaBuilder metadata).

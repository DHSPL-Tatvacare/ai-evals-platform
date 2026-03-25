# Implementation Plan: Clean Custom Evaluation Pipeline

## Principles

1. **No migration, no fallback, no legacy code** — Dev environment, data can be wiped
2. **Backend is source of truth** — Variable registry lives on backend; frontend fetches via API
3. **Same contract everywhere** — Custom evals get the same submit → poll → track → redirect → display flow as standard evals
4. **Small, validated diffs** — Each phase is independently testable
5. **Standard pipelines stay in code** — Their prompts, schemas, and logic remain hardcoded
6. **Delete, don't deprecate** — When replacing something, delete the old code entirely

---

## Phase 1: Runner Consolidation & Poll Contract Fix

**Goal**: Custom batch evals get the same job tracking / polling / redirect UX as standard evals. Eliminate duplicated code across runners.

**Why first**: Mechanical changes, immediate UX improvement, zero risk to standard pipelines.

### 1.1 Create `runner_utils.py`

**New file**: `backend/app/services/evaluators/runner_utils.py`

Four shared utilities extracted from 4 runner files (see `05-custom-runner-consolidation.md` Step 4 for full code):

| Function | Replaces | Duplication eliminated |
|----------|----------|----------------------|
| `save_api_log(log_entry)` | `_save_api_log()` × 4 runners | ~25 lines × 4 = 100 lines |
| `create_eval_run(*, id, app_id, eval_type, job_id, ...)` | Inline `db.add(EvalRun(...))` × 4 runners | ~10 lines × 4 = 40 lines |
| `finalize_eval_run(run_id, *, status, duration_ms, ...)` | Inline `update(EvalRun).values(status=...)` in try/except/except × 4 runners | ~30 lines × 4 = 120 lines |
| `find_primary_field(output_schema)` | `_detect_primary_field()` in batch_runner + inline scan in `_extract_scores()` | ~25 lines × 2 = 50 lines |

**~120 lines total. Eliminates ~310 lines of duplication across runners.**

### 1.2 Expand `job_worker.update_job_progress()` with `**extra`

The existing function only accepts `(job_id, current, total, message)`. Expand to accept `**extra` so runners can pass `run_id`, `listing_id`, etc. without custom progress functions.

Replaces:
- `voice_rx_runner._update_progress()` (local function with custom signature)
- `custom_evaluator_runner` inline `update(Job).where(...)` SQL
- `voice_rx_batch_custom_runner._update_progress()` (closure)

`batch_runner` and `adversarial_runner` already use it via `progress_callback` — no change needed for those.

### 1.3 Merge batch runner into `custom_evaluator_runner.py`

Move `run_voice_rx_batch_custom()` into `custom_evaluator_runner.py` as `run_custom_eval_batch()`.

Key changes from current:
- Use `asyncio.as_completed()` for parallel mode (not `asyncio.gather()`) so we can capture the first completed `run_id`
- Write `run_id` to job.progress via `update_job_progress()` as soon as first evaluator completes
- Use `save_api_log`, `create_eval_run`, `finalize_eval_run` from `runner_utils`

**DELETE** `voice_rx_batch_custom_runner.py`.

### 1.4 Update all runners to use shared utilities

Files: `custom_evaluator_runner.py`, `voice_rx_runner.py`, `batch_runner.py`, `adversarial_runner.py`

In each:
- Delete local `_save_api_log()` → import `save_api_log` from `runner_utils`
- Replace inline EvalRun create/finalize boilerplate → use `create_eval_run()` / `finalize_eval_run()`
- Replace local `_update_progress()` or inline SQL → use `update_job_progress()` from `job_worker`
- In `batch_runner`: delete `_detect_primary_field()` → import `find_primary_field` from `runner_utils`
- In `custom_evaluator_runner._extract_scores()`: replace inline primary field scan → use `find_primary_field()`

### 1.5 Update `job_worker.py` import

```python
@register_job_handler("evaluate-custom-batch")
async def handle_evaluate_custom_batch(job_id, params: dict) -> dict:
    from app.services.evaluators.custom_evaluator_runner import run_custom_eval_batch
    return await run_custom_eval_batch(job_id=job_id, params=params)
```

### 1.6 Fix `RunAllOverlay.tsx`

- Replace fire-and-forget `jobsApi.submit()` with `useSubmitAndRedirect` hook
- Add `sessionId?: string` prop for Kaira session support
- Remove local `submitting` state (hook provides `isSubmitting`)
- Pass `session_id` in params when present

### 1.7 Verify the parent that mounts `RunAllOverlay`

Check that the Kaira session evaluators view has a "Run All" button that renders `RunAllOverlay` with `sessionId`. If it doesn't exist, add it.

### Validation

- Run a batch custom eval from Voice RX listing page → verify job appears in JobCompletionWatcher → verify redirect to RunDetail
- Run a batch custom eval from Kaira session page → same verification
- Check that single custom eval flow still works unchanged
- Check that all 4 standard pipelines still work (runner logic unchanged, only lifecycle calls replaced)

---

## Phase 2: Backend Variable Registry

**Goal**: Create the authoritative variable registry on the backend with API endpoints for the frontend to consume.

### 2.1 Create `variable_registry.py`

**New file**: `backend/app/services/evaluators/variable_registry.py`

Contents:
- `VariableDefinition` dataclass (frozen)
- `VariableRegistry` class with `_register_voice_rx_variables()`, `_register_kaira_variables()`
- `get_for_app(app_id, source_type)` → list of variable metadata
- `validate_prompt(prompt, app_id, source_type)` → validation result
- `get_registry()` singleton accessor

All variables from the current `prompt_resolver.py` must be registered with their metadata. Cross-reference with the current frontend `variableRegistry.ts` to ensure nothing is missed.

**~150 lines.**

### 2.2 Add API endpoints to `evaluators.py` route

Three new endpoints:

```
GET  /api/evaluators/variables?appId=...&sourceType=...
POST /api/evaluators/validate-prompt    { prompt, appId, sourceType }
GET  /api/evaluators/variables/api-paths?listingId=...
```

The `api-paths` endpoint replaces the frontend's `apiVariableExtractor.ts` — it reads a listing's `api_response` and returns all available `rx.*` dot-notation paths.

**~50 lines.**

### 2.3 Wire registry into custom runner (validation logging)

In `custom_evaluator_runner.py`, add a non-blocking validation step:

```python
from app.services.evaluators.variable_registry import get_registry
validation = get_registry().validate_prompt(evaluator.prompt, app_id)
if validation["unknown_variables"]:
    logger.warning("Unknown variables in evaluator %s: %s", evaluator.name, validation["unknown_variables"])
```

**~5 lines.**

### Validation

- `GET /api/evaluators/variables?appId=voice-rx` returns all voice-rx variables
- `GET /api/evaluators/variables?appId=voice-rx&sourceType=upload` excludes api-only variables
- `GET /api/evaluators/variables?appId=kaira-bot` returns `chat_transcript`
- `POST /api/evaluators/validate-prompt` with `{{transcript}} {{bogus}}` returns `unknown_variables: ["bogus"]`
- `GET /api/evaluators/variables/api-paths?listingId=...` returns `rx.vitals.temperature` etc. for an API listing

---

## Phase 3: Schema Builder Enhancements

**Goal**: Add `enum` field type and explicit `role` to the output schema system for robust metrics.

### 3.1 Add `enum` to `schema_generator.py`

In `_generate_field_schema()`:

```python
elif field_type == "enum":
    allowed = field.get("enumValues", [])
    return {**base, "type": "string", "enum": allowed}
```

**~3 lines.**

### 3.2 Add `enum` type to frontend

- `evaluator.types.ts`: Add `'enum'` to `EvaluatorFieldType`, add `enumValues?: string[]` to `EvaluatorOutputField`
- `CreateEvaluatorOverlay.tsx`: Add `<option value="enum">Enum</option>` to type selector; show tag-input for allowed values when enum is selected
- `OutputFieldRenderer.tsx`: Add `case 'enum':` that renders via `VerdictBadge` directly (no heuristic)

### 3.3 Add `role` field to output schema

- `evaluator.types.ts`: Add `role?: 'metric' | 'reasoning' | 'detail'` to `EvaluatorOutputField`
- `CreateEvaluatorOverlay.tsx`: Add optional role selector (small dropdown or radio) per field
- `_extract_scores()` in `custom_evaluator_runner.py`: Check `role` first, fall back to substring heuristic

### 3.4 Update seeded evaluators in `seed_defaults.py`

Update the 4 existing Kaira seeded evaluators to use `role` and `enum` where appropriate. Since we can wipe data, just update the seed definitions.

### Validation

- Create evaluator with an `enum` field → verify LLM output is constrained to allowed values
- Create evaluator with `role: reasoning` on a text field → verify `_extract_scores()` picks it up
- Verify `OutputFieldRenderer` renders enum values as `VerdictBadge` without heuristic fallback
- Verify existing number/text/boolean/array fields still work

---

## Phase 4: Frontend Variable Integration (Replace Hardcoded Registry)

**Goal**: Frontend fetches variables from backend API. Delete the hardcoded frontend registry entirely.

### 4.1 Rewrite `VariablePickerPopover.tsx`

Replace the hardcoded `TEMPLATE_VARIABLES` import with an API fetch:

```tsx
const [variables, setVariables] = useState<VariableInfo[]>([]);

useEffect(() => {
  if (!isOpen) return;
  evaluatorsApi.getVariables(effectiveAppId, sourceType).then(setVariables);
}, [isOpen, effectiveAppId, sourceType]);
```

Group by `category` for display. Show `description` and `example` on hover. For voice-rx API listings, also fetch `GET /api/evaluators/variables/api-paths?listingId=...` and show those in a separate "API Response Data" section (same as current behavior, but data comes from backend).

### 4.2 Add prompt validation to `CreateEvaluatorOverlay.tsx`

On save, call `POST /api/evaluators/validate-prompt`:
- Show warnings (amber) for unknown variables — non-blocking, still allows save
- Show info badges if `requiresAudio` or `requiresEvalOutput`

### 4.3 Delete frontend registry files

**DELETE**: `src/services/templates/variableRegistry.ts` (395 lines)
**DELETE**: `src/services/templates/apiVariableExtractor.ts`

Update any remaining imports. The only consumers are `VariablePickerPopover.tsx` (rewritten in 4.1) and any validation calls in the evaluator builder (rewritten in 4.2).

### 4.4 Add `VariableInfo` type to frontend types

```typescript
// src/types/evaluator.types.ts
export interface VariableInfo {
  key: string;
  displayName: string;
  description: string;
  category: string;
  valueType: string;
  requiresAudio: boolean;
  requiresEvalOutput: boolean;
  sourceTypes: string[] | null;
  example: string;
}
```

### 4.5 Add API functions

```typescript
// In evaluators API service
async getVariables(appId: string, sourceType?: string): Promise<VariableInfo[]>
async validatePrompt(prompt: string, appId: string, sourceType?: string): Promise<PromptValidation>
async getApiPaths(listingId: string): Promise<string[]>
```

### Validation

- Open CreateEvaluatorOverlay for voice-rx → VariablePicker shows backend-sourced variables
- Open for kaira-bot → shows only `chat_transcript`
- Open for voice-rx API listing → shows API Response Data paths from backend
- Type `{{bogus}}` in prompt → save shows warning
- Verify the deleted frontend files are not imported anywhere (build check: `npm run build`)

---

## Phase 5: Batch Custom-Only Mode for Kaira (Optional)

**Goal**: Allow running only custom evaluators on a data file without running intent/correctness/efficiency.

### 5.1 Add `custom_only` parameter to `batch_runner.py`

```python
async def run_batch_evaluation(
    ...
    custom_only: bool = False,
    ...
):
    if custom_only:
        # Skip IntentEvaluator, CorrectnessEvaluator, EfficiencyEvaluator
        # Only run custom evaluators from custom_evaluator_ids
        ...
```

When `custom_only=True`:
- Skip built-in evaluators entirely
- ThreadEvaluation results contain only `custom_evaluations`
- Summary contains only custom aggregation

### 5.2 Wire through `job_worker.py`

Pass `custom_only=params.get("custom_only", False)` in the `handle_evaluate_batch` handler.

### 5.3 Frontend toggle

Add a "Custom Evaluators Only" checkbox to the batch eval submission form when custom evaluators are selected. When checked, hides the intent/correctness/efficiency toggles.

---

## Phase 6: Standard vs Custom Labeling & Documentation

**Goal**: Clear visual distinction in the UI between standard and custom runs.

### 6.1 Eval type badges

The frontend already derives display name from `eval_type` via `getEvalRunName()`. Ensure the run list pages show:
- **Standard** badge (blue) for `full_evaluation`, `batch_thread`, `batch_adversarial`
- **Custom** badge (purple) for `custom`
- Evaluator name next to custom badge

### 6.2 Inline documentation in code

Add docstrings to each standard pipeline documenting:
- Which prompts are hardcoded and where
- Which schemas are hardcoded and where
- What server-side logic is performed
- What guarantees the pipeline provides

This is documentation only, not code changes.

---

## File Change Summary

| Phase | File | Change Type | Est. Lines |
|-------|------|-------------|------------|
| **1.1** | `backend/app/services/evaluators/runner_utils.py` | **New** | ~120 |
| **1.2** | `backend/app/services/job_worker.py` | Edit (expand `update_job_progress`) | ~5 |
| **1.3** | `backend/app/services/evaluators/custom_evaluator_runner.py` | Edit (add batch fn, use shared utils) | +60, -65 |
| **1.3** | `backend/app/services/evaluators/voice_rx_batch_custom_runner.py` | **DELETE** | -120 |
| **1.4** | `backend/app/services/evaluators/voice_rx_runner.py` | Edit (use shared utils) | -70, +5 |
| **1.4** | `backend/app/services/evaluators/batch_runner.py` | Edit (use shared utils) | -65, +5 |
| **1.4** | `backend/app/services/evaluators/adversarial_runner.py` | Edit (use shared utils) | -50, +5 |
| **1.5** | `backend/app/services/job_worker.py` | Edit (update import) | ~3 |
| **1.6** | `src/features/voiceRx/components/RunAllOverlay.tsx` | Edit | ~20 |
| **2.1** | `backend/app/services/evaluators/variable_registry.py` | **New** | ~150 |
| **2.2** | `backend/app/routes/evaluators.py` | Edit | +50 |
| **2.3** | `backend/app/services/evaluators/custom_evaluator_runner.py` | Edit | +5 |
| **3.1** | `backend/app/services/evaluators/schema_generator.py` | Edit | +3 |
| **3.2** | `src/types/evaluator.types.ts` | Edit | +5 |
| **3.2** | `src/features/evals/components/CreateEvaluatorOverlay.tsx` | Edit | +30 |
| **3.2** | `src/features/evalRuns/components/OutputFieldRenderer.tsx` | Edit | +5 |
| **3.3** | `backend/app/services/evaluators/custom_evaluator_runner.py` | Edit | +10 |
| **3.4** | `backend/app/services/seed_defaults.py` | Edit | ~10 |
| **4.1** | `src/components/ui/VariablePickerPopover.tsx` | Edit | ~40 (rewrite data source) |
| **4.2** | `src/features/evals/components/CreateEvaluatorOverlay.tsx` | Edit | +20 |
| **4.3** | `src/services/templates/variableRegistry.ts` | **DELETE** | -395 |
| **4.3** | `src/services/templates/apiVariableExtractor.ts` | **DELETE** | -50 |
| **4.4** | `src/types/evaluator.types.ts` | Edit | +10 |
| **4.5** | `src/services/api/evaluatorsApi.ts` (or equivalent) | Edit | +15 |
| **5.1** | `backend/app/services/evaluators/batch_runner.py` | Edit | +15 |
| **5.2** | `backend/app/services/job_worker.py` | Edit | +3 |
| **6.1** | Various frontend components | Edit | +15 |

**Total new code**: ~340 lines across 2 new files (`runner_utils.py`, `variable_registry.py`)
**Total deleted**: ~935 lines (frontend registry, api extractor, batch custom runner, `_save_api_log` × 4, EvalRun lifecycle boilerplate × 4, local `_update_progress` × 2, `_detect_primary_field`)
**Total edits**: ~280 lines across existing files
**Net**: **~-315 lines** (codebase gets significantly smaller)

---

## Execution Order

```
Phase 1: Runner Consolidation + Poll Contract Fix    ◄── DO FIRST
  1.1  Create runner_utils.py (save_api_log, create_eval_run, finalize_eval_run, find_primary_field)
  1.2  Expand job_worker.update_job_progress() with **extra
  1.3  Merge batch runner + use shared utils in custom_evaluator_runner
  1.4  Update voice_rx_runner, batch_runner, adversarial_runner to use shared utils
  1.5  Update job_worker.py evaluate-custom-batch import
  1.6  Fix RunAllOverlay.tsx (useSubmitAndRedirect + sessionId prop)
  1.7  Verify Kaira session "Run All" entry point
  ↓
Phase 2: Backend Variable Registry
  2.1  Create variable_registry.py
  2.2  Add API endpoints
  2.3  Wire validation logging into custom runner
  ↓
Phase 3: Schema Builder Enhancements
  3.1  Add enum to schema_generator.py
  3.2  Add enum type to frontend
  3.3  Add role field + update _extract_scores
  3.4  Update seeded evaluators
  ↓
Phase 4: Frontend Variable Integration               ◄── Depends on Phase 2
  4.1  Rewrite VariablePickerPopover to use API
  4.2  Add prompt validation to CreateEvaluatorOverlay
  4.3  DELETE variableRegistry.ts + apiVariableExtractor.ts
  4.4  Add VariableInfo type
  4.5  Add API functions
  ↓
Phase 5: Batch Custom-Only Mode (Optional)
  ↓
Phase 6: Labeling & Documentation (Anytime)
```

Phase 3 is independent of Phase 2 and could run in parallel. Phase 6 can be done at any time.

---

## End-to-End Contracts Summary

### BE/FE Contract: Evaluator CRUD

```
POST   /api/evaluators              → Create evaluator (prompt, output_schema with role/enum, model)
GET    /api/evaluators?appId=...    → List evaluators
PUT    /api/evaluators/{id}         → Update evaluator
DELETE /api/evaluators/{id}         → Delete evaluator
POST   /api/evaluators/{id}/fork    → Fork evaluator
```

### BE/FE Contract: Variable Registry

```
GET  /api/evaluators/variables?appId=...&sourceType=...     → Variable catalog
POST /api/evaluators/validate-prompt  { prompt, appId }     → Validation result
GET  /api/evaluators/variables/api-paths?listingId=...      → Dynamic rx.* paths
```

### BE/FE Contract: Job Submission

```
POST /api/jobs { job_type, params }     → { id, status }

Job types for custom:
  evaluate-custom       → { evaluator_id, listing_id|session_id, app_id, timeouts }
  evaluate-custom-batch → { evaluator_ids, listing_id|session_id, app_id, parallel, timeouts }
```

### BE/FE Contract: Job Polling

```
GET /api/jobs/{id}    → { status, progress: { current, total, message, run_id? } }

Frontend polls progress.run_id → when present, can redirect to RunDetail:
  /voice-rx/runs/{run_id}  (for app_id=voice-rx)
  /eval-runs/{run_id}      (for app_id=kaira-bot)
```

### BE/FE Contract: Run Display

```
GET /api/eval-runs/{id}      → EvalRun with config, result, summary
GET /api/eval-runs/{id}/logs → API logs for this run

For eval_type=custom:
  config.evaluator_name     → Display name
  config.output_schema      → Field definitions for OutputFieldRenderer
  result.output             → Field values
  summary.overall_score     → Primary metric (from isMainMetric field)
  summary.breakdown         → All visible fields
  summary.reasoning         → From role=reasoning field (or heuristic)
  summary.metadata          → { main_metric_key, main_metric_type, thresholds }
```

### BE/FE Contract: RunList Display

```
GET /api/eval-runs?appId=...&evalType=...&listingId=...

Each run row:
  getEvalRunName(run) → summary.evaluator_name ?? config.evaluator_name ?? evalType
  Status badge (completed/failed/running/cancelled)
  Duration, model, timestamp
  Click → navigates to RunDetail
```

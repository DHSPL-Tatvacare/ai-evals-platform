# Phase 4: Inside Sales — Eval Wizard + Job Runner

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the 6-step evaluation wizard overlay and the backend job handler that transcribes and evaluates calls against selected rubric evaluators.

**Architecture:** Frontend uses the existing `WizardOverlay` shell with 6 steps: Run Info (reuse `RunInfoStep`), Select Calls (new), Transcription Config (new, adapted from Voice Rx), Evaluators (adapt `EvaluatorToggleStep`), LLM Config (reuse `LLMConfigStep` + `ParallelConfigSection`), Review (reuse `ReviewStep`). Backend registers a new `evaluate-inside-sales` job handler that orchestrates transcription (reusing Voice Rx pipeline) then rubric evaluation.

**Tech Stack:** Python (FastAPI, job worker), TypeScript (React, WizardOverlay), existing LLM factory, existing transcription pipeline.

**Branch:** `feat/phase-4-eval-wizard`

**Depends on:** Phase 1 (shell), Phase 2 (LSQ client for call selection), Phase 3 (evaluators for picker).

---

## Background

The eval wizard follows the exact `NewBatchEvalOverlay` pattern: `WizardOverlay` shell with step components, validation per step (`canGoNext`), review summary using `ReviewStep`, and job submission via `submitAndPollJob()`.

The job runner follows the `evaluate-batch` handler pattern: registered via `@register_job_handler`, receives params with `tenant_id` and `user_id`, creates `EvalRun` + `ThreadEvaluation` records, uses `is_job_cancelled()` for cooperative cancellation, and `update_job_progress()` for progress reporting.

Transcription reuses the Voice Rx pipeline (Gemini/Whisper audio transcription with language, script, and diarization options).

## Key files to reference

- `docs/plans/call-quality-evals/inside-sales-design.md` — design spec sections 6 (Wizard) and resolved questions
- `src/features/evalRuns/components/WizardOverlay.tsx` — wizard shell
- `src/features/evalRuns/components/NewBatchEvalOverlay.tsx` — reference for full wizard wiring
- `src/features/evalRuns/components/RunInfoStep.tsx` — reuse directly
- `src/features/evalRuns/components/EvaluatorToggleStep.tsx` — adapt for rubric picker
- `src/features/evalRuns/components/LLMConfigStep.tsx` — reuse directly
- `src/features/evalRuns/components/ParallelConfigSection.tsx` — reuse directly
- `src/features/evalRuns/components/ReviewStep.tsx` — reuse directly
- `src/features/evals/components/EvaluationOverlay.tsx` — reference for transcription config UI
- `backend/app/services/job_worker.py` — job registration pattern, `@register_job_handler`
- `backend/app/services/evaluators/llm_base.py` — LLM provider factory
- `backend/app/models/eval_run.py` — EvalRun, ThreadEvaluation models
- `src/services/api/jobPolling.ts` — `submitAndPollJob()`
- `src/hooks/useSubmitAndRedirect.ts` — wizard submission hook

## Guidelines

- **Reuse step components directly** where possible. Only create new step components for Select Calls and Transcription Config.
- **Job handler** must check `is_job_cancelled()` in the loop. Must call `update_job_progress()` for each call processed.
- **Transcription** reuses the existing Voice Rx transcription logic. Reference how `handle_evaluate_voice_rx` does the transcription call.
- **EvalRun records:** `app_id="inside-sales"`, `eval_type="call_quality"`. One `ThreadEvaluation` row per call evaluated.

---

### Task 1: Create SelectCallsStep component

**Files:**
- Create: `src/features/insideSales/components/SelectCallsStep.tsx`

- [ ] **Step 1:** This replaces `CsvUploadStep` for inside-sales. Read the design spec wizard step 2 for exact fields.

- [ ] **Step 2:** Build with:
  - Info callout (reuse existing callout pattern from `NewBatchEvalOverlay`)
  - Date range (from/to inputs)
  - Agent dropdown + Direction dropdown
  - Selection mode: 3 buttons (All Matching / Random Sample / Specific Calls)
  - Toggles: Skip previously evaluated, Minimum duration
  - Stats display (Matching → After Filters → Not Yet Evaluated)
  - Preview table (first 5 calls)

- [ ] **Step 3:** Component calls LSQ API via `apiRequest('/api/inside-sales/calls?...')` to get live stats and preview. Debounce the API call on filter changes.

- [ ] **Step 4:** Props interface:
```typescript
interface SelectCallsStepProps {
  dateFrom: string;
  dateTo: string;
  agent: string;
  direction: string;
  selectionMode: 'all' | 'sample' | 'specific';
  sampleSize: number;
  selectedCallIds: string[];
  skipEvaluated: boolean;
  minDuration: boolean;
  onConfigChange: (updates: Partial<CallSelectionConfig>) => void;
  matchingCount: number;
  filteredCount: number;
  unevaluatedCount: number;
  previewCalls: CallRecord[];
}
```

- [ ] **Step 5:** Commit.

---

### Task 2: Create TranscriptionConfigStep component

**Files:**
- Create: `src/features/insideSales/components/TranscriptionConfigStep.tsx`

- [ ] **Step 1:** Read `EvaluationOverlay.tsx` prerequisites tab for the transcription config patterns (language dropdown, script, model, toggles).

- [ ] **Step 2:** Adapt into a wizard step format. Include:
  - Stats: total calls, already transcribed, need transcription
  - Language dropdown (Hindi, English, Hindi-English mixed, etc.)
  - Source script (Auto-detect, Devanagari, Latin)
  - Transcription model dropdown
  - Toggles: Force re-transcription, Preserve code-switching, Speaker diarization

- [ ] **Step 3:** Props follow the same pattern as other step components.

- [ ] **Step 4:** Commit.

---

### Task 3: Build the NewInsideSalesEvalOverlay

**Files:**
- Create: `src/features/insideSales/components/NewInsideSalesEvalOverlay.tsx`

- [ ] **Step 1:** Read `NewBatchEvalOverlay.tsx` closely. Follow the exact same pattern: `WizardOverlay` shell, step state, `canGoNext` validation, step content switch, review summary/sections, `useSubmitAndRedirect` for submission.

- [ ] **Step 2:** Define 6 steps:
```typescript
const STEPS: WizardStep[] = [
  { key: 'info', label: 'Run Info' },
  { key: 'calls', label: 'Select Calls' },
  { key: 'transcription', label: 'Transcription' },
  { key: 'evaluators', label: 'Evaluators' },
  { key: 'llm', label: 'LLM Config' },
  { key: 'review', label: 'Review' },
];
```

- [ ] **Step 3:** Step content rendering:
  - Step 0: `<RunInfoStep ... />` (reuse directly)
  - Step 1: `<SelectCallsStep ... />` (new, Task 1)
  - Step 2: `<TranscriptionConfigStep ... />` (new, Task 2)
  - Step 3: Adapt `<EvaluatorToggleStep ... />` or build a simpler picker for inside-sales evaluators
  - Step 4: `<LLMConfigStep ... />` + `<ParallelConfigSection ... />` (reuse directly)
  - Step 5: `<ReviewStep summary={...} sections={...} />` (reuse directly)

- [ ] **Step 4:** Build `reviewSummary` and `reviewSections` memos following the exact `NewBatchEvalOverlay` pattern. Sections: Call Selection, Transcription, Evaluators, Execution.

- [ ] **Step 5:** `handleSubmit` calls `submitJob('evaluate-inside-sales', { ...params })`.

- [ ] **Step 6:** Wire entry points:
  - Add to `MainLayout.tsx`: `{activeModal === 'insideSalesEval' && <NewInsideSalesEvalOverlay onClose={closeModal} />}`
  - Sidebar "New" button opens `openModal('insideSalesEval')`
  - "Evaluate Selected" button on Listing page opens with pre-selected calls
  - "New Run" on Runs page opens the overlay

- [ ] **Step 7:** Commit incrementally — first the skeleton, then each step wired, then submission.

---

### Task 4: Register backend job handler

**Files:**
- Create: `backend/app/services/runners/inside_sales_runner.py`
- Modify: `backend/app/services/job_worker.py`

- [ ] **Step 1:** Read the existing `handle_evaluate_batch` and `handle_evaluate_voice_rx` handlers in `job_worker.py` for patterns.

- [ ] **Step 2:** Create the runner. High-level flow per call:
  1. Fetch call recording URL from params (already provided by wizard)
  2. If transcript doesn't exist: transcribe using LLM provider (reuse Voice Rx transcription logic)
  3. Run rubric evaluation: send transcript + evaluator prompt to LLM → get structured JSON scores
  4. Store results in `ThreadEvaluation` row

```python
# backend/app/services/runners/inside_sales_runner.py

async def evaluate_calls(
    job_id: str,
    params: dict,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
) -> dict:
    """Evaluate inside sales calls against rubric evaluators."""
    # Extract params
    call_data = params["call_data"]  # List of call records from wizard
    evaluator_ids = params["evaluator_ids"]
    llm_config = params["llm_config"]
    transcription_config = params.get("transcription_config", {})
    parallel_workers = params.get("parallel_workers", 3)

    # Create EvalRun
    # ... (follow existing pattern)

    # Process calls with parallelism
    semaphore = asyncio.Semaphore(parallel_workers)
    total = len(call_data)

    for i, call in enumerate(call_data):
        if await is_job_cancelled(job_id):
            break

        async with semaphore:
            # 1. Transcribe if needed
            # 2. Evaluate against each evaluator
            # 3. Store ThreadEvaluation
            pass

        await update_job_progress(job_id, i + 1, total, f"Processed {i+1}/{total} calls")

    # Compute summary
    # ... return result
```

- [ ] **Step 3:** Register in `job_worker.py`:
```python
from app.services.runners.inside_sales_runner import evaluate_calls

@register_job_handler("evaluate-inside-sales")
async def handle_evaluate_inside_sales(job_id, params, *, tenant_id, user_id):
    return await evaluate_calls(job_id, params, tenant_id=tenant_id, user_id=user_id)
```

- [ ] **Step 4:** The runner must:
  - Create one `EvalRun` with `app_id="inside-sales"`, `eval_type="call_quality"`
  - Create one `ThreadEvaluation` per call with the call's activity ID as `thread_id`
  - Store dimension scores + compliance results + critique in `ThreadEvaluation.result` JSON
  - Use `LoggingLLMWrapper` for all LLM calls
  - Check `is_job_cancelled()` in the loop
  - Handle errors gracefully (log, mark call as failed, continue to next)

- [ ] **Step 5:** Test by submitting a job via the wizard with 1-2 calls and verifying results appear.

- [ ] **Step 6:** Commit.

---

### Task 5: Verify and merge

- [ ] **Step 1:** Full checks:
```bash
npx tsc -b && npm run lint && npm run build
```

- [ ] **Step 2:** End-to-end test:
  - Open wizard from sidebar, listing page, or runs page
  - Walk through all 6 steps
  - Submit with 2-3 test calls
  - Verify job progress tracking works
  - Verify toast on completion
  - Verify EvalRun + ThreadEvaluation records created in DB

- [ ] **Step 3:** Merge:
```bash
git checkout main && git merge feat/phase-4-eval-wizard
```

# Implementation Prompts

Copy-paste these prompts into separate Claude Code sessions. Execute sequentially — each phase depends on the previous one being committed.

---

## Before Starting

```
git checkout main && git pull
```

Verify clean working tree (or stash unrelated changes).

---

## Phase 1 Prompt

```
Read the fix plan at docs/plans/ai-evals-runner-fixes/PHASE_1_IMPORT_HYGIENE.md and implement all changes described there. This is import-only cleanup — no logic changes.

Summary of what to do:

1. batch_runner.py:
   - Add `func` and `random` to module-level imports (line 29 area for sqlalchemy, line 25 area for random).
   - Add `from datetime import datetime, timezone` at module level (it's missing entirely).
   - Remove the local `from sqlalchemy import func, select` at line 580.
   - Remove the two `from datetime import datetime, timezone` at lines 560 and 588.
   - Remove the `import random` at line 187.

2. adversarial_runner.py:
   - Add `from sqlalchemy import update` at module level (after line 24).
   - Add `EvalRun` to the existing `from app.models.eval_run import ...` at line 28.
   - Remove the local `from sqlalchemy import update` at line 150.
   - Remove the local `from app.models.eval_run import EvalRun` at line 151.

3. custom_evaluator_runner.py:
   - Add `update` to the existing `from sqlalchemy import select` at line 17.
   - Add `from app.models.eval_run import EvalRun` at module level (after line 23).
   - Remove the local `from sqlalchemy import update` at line 242.
   - Remove the local `from app.models.eval_run import EvalRun` at line 244.

After making changes:
- Run: python -c "import py_compile; py_compile.compile('backend/app/services/evaluators/batch_runner.py', doraise=True)"
- Run: python -c "import py_compile; py_compile.compile('backend/app/services/evaluators/adversarial_runner.py', doraise=True)"
- Run: python -c "import py_compile; py_compile.compile('backend/app/services/evaluators/custom_evaluator_runner.py', doraise=True)"
- Run: cd backend && PYTHONPATH=. python -c "from app.services.evaluators.batch_runner import run_batch_evaluation; print('batch OK')" && cd ..
- Run: cd backend && PYTHONPATH=. python -c "from app.services.evaluators.adversarial_runner import run_adversarial_evaluation; print('adversarial OK')" && cd ..
- Run: cd backend && PYTHONPATH=. python -c "from app.services.evaluators.custom_evaluator_runner import run_custom_evaluator; print('custom OK')" && cd ..
- Grep all 3 files for remaining mid-function `from ` imports. Only settings_helper and variable_registry imports should remain (they are intentionally lazy/conditional).

Do NOT change any logic. Do NOT change any function signatures. Do NOT change any behavior. This is purely moving imports from inside function bodies to module level.

Commit with message: "fix: hoist mid-function imports to module level across all runners

Fixes UnboundLocalError crash in batch_runner.py where `from sqlalchemy
import func, select` inside except block shadowed the module-level
`select` import, making it inaccessible at line 170 when
skip_previously_processed=True.

Also hoists datetime, update, EvalRun, and random imports in
batch_runner, adversarial_runner, and custom_evaluator_runner to
prevent the same class of shadowing bug."
```

---

## Phase 2 Prompt

```
Read the fix plan at docs/plans/ai-evals-runner-fixes/PHASE_2_CANCELLATION_CHAIN.md and implement all changes described there. This fixes cancellation propagation in voice-rx and custom evaluator paths.

Summary of what to do:

1. voice_rx_runner.py — V1 fix (PipelineStepError handler):
   - Replace the direct DB update in the `except PipelineStepError` block (around line 444-468) with a call to `finalize_eval_run()`. The function is already imported.
   - Keep the evaluation dict mutations (status, error, failedStep, partial_result merge) — they prepare the `evaluation` dict which is passed as `result=evaluation` to finalize_eval_run.
   - Keep the `raise` at the end.
   - The call should be:
     ```python
     await finalize_eval_run(
         eval_run_id,
         status="failed",
         duration_ms=(time.monotonic() - start_time) * 1000,
         error_message=f"[{e.step}] {e.message}",
         result=evaluation,
     )
     ```
   - Remove the `async with async_session() as db:` block that did the direct update.

2. custom_evaluator_runner.py — M3 fix (swallowed cancel):
   - In `run_custom_evaluator`, at the end of the `except JobCancelledError:` block (around line 302-309), add `raise` after the logger.info line.
   - That's it. The fall-through code at lines 323-334 becomes unreachable after cancel, which is correct.

3. custom_evaluator_runner.py — M1 fix (batch cancel dead code):
   - In `run_custom_eval_batch`'s `_run_one` function, add `except JobCancelledError: raise` BEFORE the existing `except Exception as e:` block. This lets cancel propagate while still catching regular errors.
   - In the parallel execution path, change from `asyncio.gather(*tasks, return_exceptions=True)` to a pattern that lets JobCancelledError propagate:
     ```python
     tasks = [asyncio.create_task(_run_one(eid, i)) for i, eid in enumerate(valid_ids)]
     try:
         await asyncio.gather(*tasks)
     except JobCancelledError:
         for t in tasks:
             if not t.done():
                 t.cancel()
         await asyncio.gather(*tasks, return_exceptions=True)
         raise
     ```
   - Remove the `for i, r in enumerate(results): if isinstance(r, Exception):` error-counting loop — it's no longer needed because gather either succeeds (all results are dicts) or raises JobCancelledError.
   - The outer `except JobCancelledError: raise` at line 433 is now reachable.

After making changes:
- Run py_compile on both files.
- Run import checks on both files.
- Read through the changed code and verify:
  a. Every except JobCancelledError block either re-raises or returns (voice_rx returns, which is acceptable per the plan).
  b. finalize_eval_run is called before re-raise/return in every cancel handler.
  c. The parallel path in run_custom_eval_batch properly cancels remaining tasks on JobCancelledError.

Do NOT change batch_runner.py or adversarial_runner.py — their cancellation chains are already correct.
Do NOT change parallel_engine.py or runner_utils.py.
Do NOT change any job_worker.py logic.

Commit with message: "fix: repair cancellation chain in voice-rx and custom evaluator runners

V1: Replace direct DB update in voice_rx_runner PipelineStepError
handler with finalize_eval_run() for consistency and cancel-guard.

M3: Add re-raise after JobCancelledError handling in
run_custom_evaluator so cancellation propagates to callers.

M1: Restructure run_custom_eval_batch to let JobCancelledError
propagate through _run_one and asyncio.gather, properly cancelling
remaining tasks instead of silently continuing after cancel."
```

---

## Phase 3 Prompt

```
Read the fix plan at docs/plans/ai-evals-runner-fixes/PHASE_3_FUNCTIONAL_GAPS.md and implement all changes described there.

Summary of what to do:

1. custom_evaluator_runner.py — M2 fix (thinking param):
   - In `run_custom_evaluator`, find the two LLM calls (around lines 268-281).
   - Add `thinking=thinking` to both `llm.generate_with_audio()` and `llm.generate_json()`.
   - The `thinking` variable is already extracted at line 219: `thinking = params.get("thinking", "low")`.
   - Optionally add `"thinking": thinking` to the config_snapshot dict for audit trail.

Before implementing, verify that `generate_with_audio` and `generate_json` in llm_base.py accept a `thinking` parameter. Read the method signatures first.

After making changes:
- Run py_compile on the file.
- Run import check.
- Grep all 4 runner files for `generate_json\(` and `generate_with_audio\(` calls to verify thinking is passed everywhere. The only calls that should NOT have thinking are in modules outside the runners (e.g., settings_helper, if any).

Commit with message: "fix: pass thinking param through custom evaluator LLM calls

The thinking parameter was extracted from job params but never passed
to generate_with_audio() or generate_json() in run_custom_evaluator.
User's thinking level selection was silently ignored. All other runners
already pass it correctly."
```

---

## After All 3 Phases

Run the full stack and verify these flows work:

```
docker compose up --build
```

1. **Batch eval (kaira-bot)** — Run with skip_previously_processed=True on data that has some evaluated threads. Verify no crash, skipping works.
2. **Custom eval (voice-rx)** — Run on a listing. Verify completes.
3. **Custom eval (kaira-bot)** — Run on a chat session. Verify completes.
4. **Cancel a custom eval** — Start one, cancel mid-run. Verify eval_run shows "cancelled".
5. **Custom eval batch** — Run 2+ evaluators on a listing. Verify all complete.
6. **Cancel a custom eval batch** — Start one with 3+ evaluators, cancel during execution. Verify remaining evaluators stop.

Check Docker logs for any errors:
```
docker compose logs -f backend
```

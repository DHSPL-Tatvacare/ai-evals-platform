# Phase 1: Import Hygiene

**Goal:** Fix the active B1 crash and eliminate all mid-function imports that risk future shadowing crashes.
**Risk Level:** Low — purely mechanical import relocation. No logic changes. No behavior changes.
**Files Changed:** `batch_runner.py`, `adversarial_runner.py`, `custom_evaluator_runner.py`
**Files NOT Changed:** `voice_rx_runner.py` (already clean), `job_worker.py`, `parallel_engine.py`, `runner_utils.py`

---

## Problem Statement

Python's compiler determines variable scope at function definition time, not at runtime. If a name is assigned anywhere inside a function body (including via `from X import name`), Python marks that name as **local** for the **entire** function — even lines above the import. Accessing the name before the import line raises `UnboundLocalError`.

B1 is an active crash caused by exactly this. B2-B5 are the same pattern waiting to trigger.

## Reference: What Clean Imports Look Like

`voice_rx_runner.py` is the gold standard in this codebase. All imports at module level, no mid-function imports except `settings_helper` (which is conditional and uses a unique name not used elsewhere in the function):

```python
# voice_rx_runner.py — lines 13-59 (module level, clean)
from sqlalchemy import select, update
from datetime import datetime, timezone
from app.models.eval_run import EvalRun
# ... etc
```

---

## Bug B1: `batch_runner.py` — Active Crash

### Root Cause

```
Line 29:  from sqlalchemy import select, update          ← module-level import
Line 170: select(DBThreadEval.thread_id).distinct()      ← usage (BEFORE L580)
Line 580: from sqlalchemy import func, select             ← local re-import (inside except block)
```

Line 580 is inside `except JobCancelledError` (L575). Python sees this `import select` and marks `select` as local for the entire `run_batch_evaluation` function. Line 170 executes before 580, so it hits `UnboundLocalError`.

### Trigger Condition

`skip_previously_processed=True` AND `app_id="kaira-bot"` — this is the only code path that uses `select()` inside the function body (L170). The `except JobCancelledError` block (L580) also uses `select()` but would only execute on cancellation.

### Fix

**Step 1:** Add `func` to the existing module-level import at line 29:

```python
# Line 29 — BEFORE:
from sqlalchemy import select, update

# Line 29 — AFTER:
from sqlalchemy import func, select, update
```

**Step 2:** Remove the local re-import at line 580:

```python
# Line 580 — BEFORE:
from sqlalchemy import func, select

# Line 580 — AFTER:
# (delete this line entirely)
```

### What NOT to Change

- Do NOT change the `select(...)` usage at line 170 or line 583. The query logic is correct.
- Do NOT change the `except JobCancelledError` block structure.
- Do NOT move any other code in this block.

---

## Bug B2: `batch_runner.py` — `datetime` mid-function

### Root Cause

```
Line 560: from datetime import datetime, timezone    ← inside try block (success path)
Line 588: from datetime import datetime, timezone    ← inside except JobCancelledError
```

Module level has NO `datetime` import. Currently works because `datetime` is not used before these lines within the function. But if anyone adds `datetime.now(timezone.utc)` earlier in the function (e.g., for timing), it will crash with `UnboundLocalError`.

### Fix

**Step 1:** Add to module-level imports (after line 27, near the other stdlib imports):

```python
from datetime import datetime, timezone
```

Note: `batch_runner.py` currently imports `time` (L24) and `uuid` (L25) at module level but NOT `datetime`. This is an omission — every other runner imports `datetime` at module level.

**Step 2:** Remove line 560 and line 588 entirely.

### What NOT to Change

- Do NOT change any `datetime.now(timezone.utc)` usage. The calls are correct.

---

## Bug B3: `adversarial_runner.py` — `update` and `EvalRun` mid-function

### Root Cause

```
Line 28:  from app.models.eval_run import AdversarialEvaluation as DBAdversarialEval  ← module-level
Line 150: from sqlalchemy import update                                                ← mid-function
Line 151: from app.models.eval_run import EvalRun                                      ← mid-function
```

The module already imports from `app.models.eval_run` at line 28. `EvalRun` lives in the same module. Adding it to the existing import is trivial and introduces no circular dependency.

`sqlalchemy.update` is used at line 153-154 in a DB update block. Currently safe because `update` is not referenced before line 150. But fragile.

### Fix

**Step 1:** Add `update` to sqlalchemy imports. The file currently has NO sqlalchemy import at module level. Add one:

```python
# After line 24 (from typing import ...), add:
from sqlalchemy import update
```

**Step 2:** Add `EvalRun` to the existing eval_run import at line 28:

```python
# Line 28 — BEFORE:
from app.models.eval_run import AdversarialEvaluation as DBAdversarialEval

# Line 28 — AFTER:
from app.models.eval_run import AdversarialEvaluation as DBAdversarialEval, EvalRun
```

**Step 3:** Remove lines 150-151 entirely.

### Circular Dependency Check

- `adversarial_runner.py` imports from `job_worker.py` at module level (L42-44).
- `job_worker.py` imports `adversarial_runner.py` ONLY inside the handler function (L307, lazy import).
- `app.models.eval_run` has no imports from any runner or job_worker.
- No circular dependency. Safe to hoist.

---

## Bug B4: `custom_evaluator_runner.py` — `update` and `EvalRun` mid-function

### Root Cause

```
Line 17:  from sqlalchemy import select                     ← module-level (select only)
Line 242: from sqlalchemy import update                     ← mid-function in run_custom_evaluator
Line 244: from app.models.eval_run import EvalRun           ← mid-function (nested inside async with)
```

### Fix

**Step 1:** Add `update` to existing sqlalchemy import at line 17:

```python
# Line 17 — BEFORE:
from sqlalchemy import select

# Line 17 — AFTER:
from sqlalchemy import select, update
```

**Step 2:** Add `EvalRun` import at module level. Add after line 22:

```python
from app.models.eval_run import EvalRun
```

**Step 3:** Remove line 242 and line 244 entirely.

### Circular Dependency Check

- `custom_evaluator_runner.py` imports from `job_worker.py` at module level (L34-36).
- `job_worker.py` imports `custom_evaluator_runner.py` ONLY inside handler functions (L345, L352, lazy imports).
- `app.models.eval_run` has no imports from any runner.
- No circular dependency. Safe to hoist.

---

## Bug B5: `batch_runner.py` — `random` mid-function

### Root Cause

```
Line 187: import random    ← inside function body, conditional path (sample_size)
```

### Fix

Add to module-level imports (after line 25, with other stdlib imports):

```python
import random
```

Remove line 187.

---

## Post-Fix Validation

### Automated Checks

1. **Syntax check all 3 files:**
   ```bash
   python -c "import py_compile; py_compile.compile('backend/app/services/evaluators/batch_runner.py', doraise=True)"
   python -c "import py_compile; py_compile.compile('backend/app/services/evaluators/adversarial_runner.py', doraise=True)"
   python -c "import py_compile; py_compile.compile('backend/app/services/evaluators/custom_evaluator_runner.py', doraise=True)"
   ```

2. **Import resolution check** (verify no circular imports):
   ```bash
   cd backend && python -c "from app.services.evaluators.batch_runner import run_batch_evaluation; print('batch OK')"
   cd backend && python -c "from app.services.evaluators.adversarial_runner import run_adversarial_evaluation; print('adversarial OK')"
   cd backend && python -c "from app.services.evaluators.custom_evaluator_runner import run_custom_evaluator; print('custom OK')"
   cd backend && python -c "from app.services.evaluators.voice_rx_runner import run_voice_rx_evaluation; print('voice_rx OK')"
   ```

3. **Grep for remaining mid-function imports** (should return ONLY `settings_helper` and `variable_registry` lazy imports, which are intentionally conditional):
   ```bash
   grep -n "^\s*from\s" backend/app/services/evaluators/batch_runner.py | grep -v "^[0-9]*:from"
   grep -n "^\s*from\s" backend/app/services/evaluators/adversarial_runner.py | grep -v "^[0-9]*:from"
   grep -n "^\s*from\s" backend/app/services/evaluators/custom_evaluator_runner.py | grep -v "^[0-9]*:from"
   ```

   Expected remaining mid-function imports (intentional, no shadowing risk):
   - `batch_runner.py`: `from app.services.evaluators.settings_helper import get_llm_settings_from_db` (conditional, unique name)
   - `adversarial_runner.py`: `from app.services.evaluators.settings_helper import get_llm_settings_from_db` (conditional, unique name)
   - `custom_evaluator_runner.py`: `from app.services.evaluators.variable_registry import get_registry` (unique name) and `from app.services.evaluators.settings_helper import get_llm_settings_from_db` (unique name)

### Manual Flow Checks

These flows should work exactly as before (no behavior change expected):

| Flow | How to Test | What to Verify |
|---|---|---|
| Batch eval (kaira-bot, skip_previously_processed=True) | Run batch eval with skip duplicates enabled on a dataset that has some previously evaluated threads | **B1 fix**: No crash. Previously processed threads are skipped. New threads are evaluated. Summary includes `skipped_previously_processed` count. |
| Batch eval (kaira-bot, sample_size=5) | Run batch eval with sampling | **B5 fix**: Sampling works. 5 random threads selected. |
| Batch eval (kaira-bot, cancel mid-run) | Start batch eval, cancel after a few threads | **B2 fix**: Cancellation path completes. Summary shows processed count. Eval_run status is "cancelled". |
| Adversarial eval (kaira-bot) | Run adversarial eval with default settings | **B3 fix**: Eval completes. Eval_run has correct llm_provider and llm_model. |
| Custom eval (voice-rx, single) | Run a custom evaluator on a voice-rx listing | **B4 fix**: Eval completes. Eval_run has correct config snapshot with provider and model. |
| Custom eval (kaira-bot, session) | Run a custom evaluator on a kaira-bot chat session | **B4 fix**: Same check as above. |

### Flow Preservation Check

After Phase 1, the following causal chains must remain unchanged:

1. **Job lifecycle**: queued -> running -> handler -> runner -> completed/failed/cancelled. No change.
2. **EvalRun lifecycle**: created(running) -> work -> finalized(terminal). No change.
3. **Progress/polling**: run_id written to job.progress early. Frontend redirects. No change.
4. **Error propagation**: Runner exception -> finalize_eval_run(failed) -> re-raise -> worker_loop marks job failed. No change.
5. **Cancel propagation**: All cancel paths unchanged (Phase 2 will fix the broken ones).

Phase 1 is strictly mechanical. If any flow behaves differently after Phase 1, something was changed beyond imports and you must investigate.

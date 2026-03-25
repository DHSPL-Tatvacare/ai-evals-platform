# Backend Path

## Files to Change

- `backend/app/services/evaluators/batch_runner.py`
- `backend/app/services/job_worker.py`

No model changes and no new DB table.

## Injection Point

Inject skip filtering in `run_batch_evaluation()` immediately after candidate thread IDs are resolved and before any evaluator execution starts.

This is the narrowest point that controls all thread scopes (`all`, `sample`, `specific`) without touching evaluator internals.

## Planned Behavior

### 1) New runner input flag

Add optional runner argument:
- `skip_previously_processed: bool = False`

### 2) Kaira-only guard

Apply skip lookup only when both are true:
- `skip_previously_processed` is enabled
- `app_id == 'kaira-bot'`

Otherwise, keep current logic unchanged.

### 3) One DB lookup for processed IDs

For candidate thread IDs, run one query:
- `SELECT DISTINCT thread_evaluations.thread_id`
- `JOIN eval_runs ON thread_evaluations.run_id = eval_runs.id`
- `WHERE eval_runs.app_id = 'kaira-bot'`
- `AND thread_evaluations.thread_id IN (<candidate ids>)`

Then split into:
- `ids_to_evaluate` (unseen)
- `skipped_previously_processed` (already seen)

### 4) Apply filtering by scope

- `specific`: filter selected IDs.
- `all`: filter full set.
- `sample`: filter full set first, then sample from remaining IDs.

Sampling from the remaining pool preserves the expected sample size behavior for unseen conversations.

### 5) Metadata and summary visibility

Persist skip-related counters in run metadata/summary, for example:
- requested thread count
- skipped previously processed count
- final evaluated count

This keeps result interpretation clear in Run Detail.

### 6) Job handler wiring

Pass-through new param in:
- `handle_evaluate_batch()` in `job_worker.py`

No other handlers are touched.

## Why This Is Low Disruption

- No evaluator logic changes.
- No parallel engine changes.
- No job polling changes.
- No database migration.
- Single pre-execution filter stage plus one param pass-through.

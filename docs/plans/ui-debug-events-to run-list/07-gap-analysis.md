# Gap Analysis — What SHOULD Happen vs What ACTUALLY Happens

## Summary

After tracing all 6 flows, we identified **18 unique bugs** across the job lifecycle. They cluster around **4 root causes**:

1. **Orphaned eval_runs** — The biggest issue. When a job is cancelled or the worker crashes, the eval_run can get stuck in "running" forever. There's no recovery mechanism, no reconciliation in the frontend, and no way to clean up from the UI.

2. **Lost `run_id` in job progress** — The frontend can't reliably redirect to RunDetail after submission because the batch runner's `run_id` in `job.progress` gets overwritten by the next `progress_callback`.

3. **ApiError discards backend detail** — Every HTTP error the user sees is generic ("API error 400: Bad Request") because `client.ts` puts the useful backend message in `.data` but every catch handler reads `.message`.

4. **Inconsistent error UX** — A mix of full-page error banners (destructive), toasts (non-destructive), and silent swallows (invisible) with no pattern.

---

## Root Cause 1: Orphaned Eval Runs

### What SHOULD happen

When a job reaches a terminal state (cancelled/failed/completed), its associated eval_run should ALWAYS be updated to a matching terminal state. If a crash prevents this, a recovery mechanism should reconcile them on startup. The frontend should never show a "Running" eval_run whose job is already terminal.

### What ACTUALLY happens

There are TWO independent mechanisms that set eval_run to "cancelled":

1. **Cancel route** (`jobs.py:68-72`): `UPDATE eval_runs SET status='cancelled' WHERE job_id=X AND status='running'`
2. **Worker's `JobCancelledError` handler** (e.g., `batch_runner.py:404-423`): `UPDATE eval_runs SET status='cancelled' WHERE id=run_id`

Both can fail independently:
- Cancel route's UPDATE may not match (race with worker creating/updating the eval_run)
- Worker may crash/restart before reaching the `JobCancelledError` handler
- Docker restart kills the worker mid-LLM-call; `recover_stale_jobs()` only recovers **jobs**, not **eval_runs**

**DB evidence**: `eval_run eed28526` has `status='running'` while its `job 34971418` has `status='cancelled'`. This eval_run has been orphaned since the original investigation began.

### Cascading failures from orphaned eval_runs

| Downstream Effect | Severity | Flow |
|---|---|---|
| RunDetail page permanently stuck in "Running" | HIGH | Flow 2, 4 |
| Cancel button visible but futile (early return skips eval_run update) | HIGH | Flow 3, 4 |
| Delete button disabled ("Cancel it first") — but cancel can't fix it | HIGH | Flow 4, 5 |
| Delete API rejects with 400 — undeletable from UI or API | HIGH | Flow 5 |
| RunList polls every 5s indefinitely (orphaned run triggers `hasRunning`) | MEDIUM | Flow 4 |
| Elapsed timer counts forever | LOW | Flow 4 |
| No progress bar shown (job cancelled but run "running") | LOW | Flow 2 |

### Fix Plan

**Backend fix (primary)**:

1. **Add `recover_stale_eval_runs()` to startup** — Find all `eval_runs` with `status='running'` whose associated job is terminal. Set them to match the job's status.

```python
async def recover_stale_eval_runs():
    async with async_session() as db:
        # Find eval_runs stuck in "running" with a terminal job
        result = await db.execute(
            select(EvalRun).join(Job, EvalRun.job_id == Job.id).where(
                EvalRun.status == "running",
                Job.status.in_(["completed", "failed", "cancelled"]),
            )
        )
        for run in result.scalars():
            job = await db.get(Job, run.job_id)
            run.status = "cancelled" if job.status == "cancelled" else "failed"
            run.error_message = f"Recovered on startup: job was {job.status}"
            run.completed_at = datetime.now(timezone.utc)
        await db.commit()
```

2. **Make cancel route idempotent for eval_runs** — Remove the early return for already-cancelled jobs. Always attempt the eval_run update:

```python
# BEFORE (broken)
if job.status == "cancelled":
    return {"id": str(job_id), "status": "cancelled"}

# AFTER (idempotent)
if job.status == "cancelled":
    # Still try to fix any orphaned eval_run
    await db.execute(
        update(EvalRun)
        .where(EvalRun.job_id == job_id, EvalRun.status == "running")
        .values(status="cancelled", completed_at=datetime.now(timezone.utc))
    )
    await db.commit()
    return {"id": str(job_id), "status": "cancelled"}
```

**Frontend fix (safety net)**:

3. **Reconcile job vs eval_run status in RunDetail** — When the polling loop detects a terminal job but the eval_run is still "running", treat the run as cancelled/failed:

```typescript
if (["completed", "failed", "cancelled"].includes(job.status)) {
    const r = await fetchRun(runId);
    // Reconcile: if job is terminal but run is still "running", override
    if (r.status.toLowerCase() === "running") {
        r.status = job.status === "cancelled" ? "cancelled" : "failed";
    }
    setRun(r);
    break;
}
```

4. **Reconcile in RunList/RunCard** — Same pattern: if `run.job_id` exists, fetch job status and reconcile.

---

## Root Cause 2: Lost `run_id` in Job Progress

### What SHOULD happen

After the backend creates an eval_run and writes `run_id` to `job.progress`, the frontend should be able to reliably read it and redirect the user to the RunDetail page.

### What ACTUALLY happens

The batch runner writes `run_id` to `job.progress` at initialization:
```python
progress={"current": 0, "total": 0, "message": "Initializing...", "run_id": str(run_id)}
```

But `update_job_progress()` (`job_worker.py:73-81`) **overwrites the entire JSON**:
```python
progress={"current": current, "total": total, "message": message}
```

The first `progress_callback` call destroys `run_id`. The frontend's 10-second polling window rarely catches it.

Additionally, different runners use different keys:

| Runner | Progress key | Preserved? |
|---|---|---|
| `batch_runner` | `run_id` | NO — overwritten |
| `adversarial_runner` | `run_id` | YES — local `report_progress` preserves it |
| `voice_rx_runner` | `eval_run_id` | YES — but wrong key! |
| `custom_evaluator_runner` | `eval_run_id` | YES — but wrong key! |

The frontend only looks for `progress.run_id`, so voice_rx and custom runners NEVER support redirect.

**DB evidence**: All recent jobs show progress WITHOUT `run_id`:
```
34971418 | {"current": 4, "total": 10, "message": "Evaluating thread 4/10"}
734e1bc6 | {"current": 1, "total": 1, "message": "Done"}
```

The worker loop completion handler also overwrites without `run_id`:
```python
job.progress = {"current": 1, "total": 1, "message": "Done"}
```

### Fix Plan

**Option A (recommended): Preserve `run_id` in `update_job_progress()`**

```python
async def update_job_progress(job_id, current: int, total: int, message: str = "", **extra):
    async with async_session() as db:
        job = await db.get(Job, job_id)
        if job:
            new_progress = {"current": current, "total": total, "message": message}
            # Preserve run_id if it was set previously
            if isinstance(job.progress, dict) and "run_id" in job.progress:
                new_progress["run_id"] = job.progress["run_id"]
            new_progress.update(extra)
            job.progress = new_progress
            await db.commit()
```

**Option B (alternative): Write `run_id` to a dedicated column on `jobs`**

Add `jobs.eval_run_id` column (nullable UUID FK). Set it once when the runner creates the eval_run. The frontend reads `job.eval_run_id` instead of `job.progress.run_id`. This is cleaner and doesn't rely on JSON key preservation.

**Also fix**: Standardize the key across all runners to `run_id`, and update the frontend to check both `run_id` and `eval_run_id` for backwards compatibility (or just `eval_run_id` if using Option B).

**Also fix**: Worker loop completion handler should preserve `run_id`:
```python
# BEFORE
job.progress = {"current": 1, "total": 1, "message": "Done"}

# AFTER
job.progress = {
    "current": 1, "total": 1, "message": "Done",
    **({"run_id": job.progress.get("run_id")} if isinstance(job.progress, dict) and "run_id" in job.progress else {})
}
```

---

## Root Cause 3: ApiError Discards Backend Detail

### What SHOULD happen

When the backend returns `{"detail": "Cannot delete a running evaluation. Cancel it first."}` with status 400, the user should see that message.

### What ACTUALLY happens

`client.ts:44-47`:
```typescript
throw new ApiError(
    response.status,
    `API error ${response.status}: ${response.statusText}`,  // ← ALWAYS generic
    errorData,                                                 // ← Detail is HERE, never read
);
```

Every catch handler in the codebase uses `e.message`:
```typescript
catch (e: any) {
    setError(e.message);          // "API error 400: Bad Request"
    // e.data.detail has the real message — never accessed
}
```

**Impact**: Every API error the user sees is generic. Backend detail messages are systematically lost.

| Backend Response | User Sees | Should See |
|---|---|---|
| `400 {"detail": "Cannot delete a running evaluation"}` | `"API error 400: Bad Request"` | `"Cannot delete a running evaluation. Cancel it first."` |
| `404 {"detail": "Run not found"}` | `"API error 404: Not Found"` | `"Run not found"` |
| `400 {"detail": "Cannot cancel job in 'completed' state"}` | `"API error 400: Bad Request"` | `"Cannot cancel job in 'completed' state"` |
| `422 {"detail": "Failed to parse CSV: ..."}` | `"API error 422: Unprocessable Entity"` | `"Failed to parse CSV: ..."` |

### Fix Plan

**Single-point fix in `client.ts`**:

```typescript
if (!response.ok) {
    const text = await response.text();
    let errorData: unknown = text;
    try { errorData = JSON.parse(text); } catch {}

    // Extract detail from FastAPI's standard error response
    const detail = (typeof errorData === 'object' && errorData !== null && 'detail' in errorData)
        ? String((errorData as Record<string, unknown>).detail)
        : null;

    throw new ApiError(
        response.status,
        detail || `API error ${response.status}: ${response.statusText}`,
        errorData,
    );
}
```

This is a zero-risk change — it improves every API error message across the entire app. No catch handlers need to change.

Also fix `apiUpload` and `apiDownload` to read the response body for errors (currently they don't).

---

## Root Cause 4: Inconsistent Error UX

### What SHOULD happen

- **Transient action errors** (delete/cancel failures): Show a toast notification. User retains page context.
- **Initial load errors** (page can't render): Show an error banner with retry/back options.
- **Polling errors**: Retry silently (already correct).

### What ACTUALLY happens

| Scenario | Current UX | Correct UX |
|---|---|---|
| Delete fails (running run) | Full-page error banner, entire RunList gone | Toast notification, list preserved |
| Cancel fails (completed job) | Full-page error banner, entire RunDetail gone | Toast notification, page preserved |
| Initial data load fails | Full-page error banner, no retry | Error banner with "Back to runs" link |
| Navigate to deleted run | `"API error 404: Not Found"` — no back link | "Run not found" message with link to runs list |
| Polling network error | Silent | Silent (correct) |

### Fix Plan

1. **Action errors → toasts**: Change `handleCancel`, `handleDelete`, `handleDeleteCustom` from `setError(e.message)` to `notificationService.error(e.message)`.
2. **Initial load 404 → friendly message**: Detect 404 status and show "Run not found" with a link back to runs list.
3. **Add retry to error banners**: Replace bare `{error}` div with a component that includes a "Try Again" button.

---

## Complete Bug Inventory (Deduplicated)

All bugs from Flows 1-6, deduplicated and prioritized.

### Priority 1: CRITICAL (Broken core flows, no workaround)

| # | Bug | Root Cause | Flows | Fix |
|---|---|---|---|---|
| C1 | Orphaned eval_runs stuck in "running" forever | No recovery for eval_runs on startup; cancel route can't fix once job already cancelled | 1,2,3,4 | Add `recover_stale_eval_runs()` to startup |
| C2 | Cancel route skips eval_run update for already-cancelled jobs | Early return at `jobs.py:62-63` | 3,4 | Make cancel idempotent — always attempt eval_run UPDATE |
| C3 | Orphaned runs are undeletable | Delete route rejects "running" runs; cancel can't fix; infinite loop | 4,5 | Combine C1+C2 fixes; also add frontend reconciliation |
| C4 | Frontend doesn't reconcile job vs eval_run status | `RunDetail` trusts `eval_run.status` blindly | 2,4 | Add job-vs-run reconciliation in polling final fetch |

### Priority 2: HIGH (Major UX impact, workarounds exist)

| # | Bug | Root Cause | Flows | Fix |
|---|---|---|---|---|
| H1 | `run_id` lost from job progress (batch runner) | `update_job_progress()` overwrites entire JSON | 1 | Preserve `run_id` in progress updates (or use dedicated column) |
| H2 | ApiError.message discards backend detail | `client.ts` builds generic message, ignores response body | 6 | Extract `detail` from JSON response in `client.ts` |
| H3 | RunList polls indefinitely for orphaned runs | `hasRunning` check includes orphaned eval_run | 2,4 | Fix C1-C4 (no more orphaned runs) |
| H4 | Failed thread evals not saved for completed_with_errors runs | Per-thread except may fail silently, or error occurs before loop | 6 | Ensure error ThreadEvaluation rows are always committed |

### Priority 3: MEDIUM (UX degradation, minor impact)

| # | Bug | Root Cause | Flows | Fix |
|---|---|---|---|---|
| M1 | `setError()` replaces entire page for action errors | Delete/cancel failures use setError instead of toasts | 5,6 | Use `notificationService.error()` for transient errors |
| M2 | Empty error string in failed thread evaluations | `str(e)` is empty for some cancellation-race exceptions | 2,6 | Default to `"Evaluation interrupted"` when `str(e)` is empty |
| M3 | Inconsistent progress key between runners | `run_id` vs `eval_run_id` | 1 | Standardize to `run_id` across all runners |
| M4 | Raw "API error 404: Not Found" for deleted runs | No 404 handling in RunDetail | 5 | Show "Run not found" with back link |
| M5 | No LLM retry for transient errors (429s) | No retry logic in `llm_base.py` | 6 | Add exponential backoff for 429 responses |
| M6 | Cancel during LLM call has unbounded latency | `is_job_cancelled()` only checked between iterations | 3 | Document as known limitation (asyncio cancellation is complex) |

### Priority 4: LOW (Cosmetic, data hygiene, dead code)

| # | Bug | Root Cause | Flows | Fix |
|---|---|---|---|---|
| L1 | Associated job never cleaned up after eval_run delete | No reverse cascade from eval_runs to jobs | 5 | Add job cleanup to delete route (or accept as data hygiene) |
| L2 | CSV content stored and returned in job params | Entire CSV in `job.params.csv_content` sent on every poll | 1 | Strip `csv_content` from API response (or move to file storage) |
| L3 | Worker error recovery can overwrite "cancelled" with "failed" on eval_run | Runner's `except Exception` has no cancelled guard for eval_run | 3,6 | Check eval_run status before overwriting in runner's except block |
| L4 | AppError system unused in eval flows | Legacy from storage migration | 6 | Either adopt it or remove it (tech debt) |

---

## Recommended Fix Order

### Phase A: Stop the Bleeding (Backend — 4 fixes)

These fixes prevent NEW orphaned eval_runs and heal existing ones.

1. **`recover_stale_eval_runs()` on startup** — Heals all existing orphaned eval_runs
2. **Idempotent cancel route** — Every cancel attempt fixes any orphaned eval_run
3. **Preserve `run_id` in `update_job_progress()`** — Fix redirect after submission
4. **Standardize progress key to `run_id`** — All runners use same key

### Phase B: Frontend Resilience (Frontend — 4 fixes)

These fixes make the frontend handle edge cases gracefully even if backend has issues.

5. **Job-vs-run reconciliation in RunDetail** — If job terminal but run "running", treat as cancelled/failed
6. **Extract detail from ApiError** — One-line fix in `client.ts`, improves all error messages
7. **Action errors → toasts** — Don't nuke the page for delete/cancel failures
8. **404 handling for deleted runs** — Show "Run not found" with back link

### Phase C: Quality of Life (Both — 4 fixes)

9. **Default error message for empty `str(e)`** — No more invisible thread failures
10. **Worker loop preserves `run_id` in completion progress** — Belt-and-suspenders for redirect
11. **Failed thread eval rows always committed** — Users can see which threads failed
12. **Strip CSV from job API response** — Reduce poll payload size

### Phase D: Optional Improvements (Future)

13. LLM retry with exponential backoff for 429s
14. Job cleanup on eval_run delete
15. AppError system adoption or removal
16. Eval_run runner cancelled-guard in except block

---

## DB State Snapshot at Time of Investigation

### Orphaned eval_run (the primary evidence)

```sql
-- Eval run stuck in "running" with cancelled job
SELECT er.id, er.status, er.completed_at, j.id AS job_id, j.status AS job_status
FROM eval_runs er JOIN jobs j ON er.job_id = j.id
WHERE er.status = 'running' AND j.status != 'running';

-- Result:
-- er.id=eed28526  er.status=running  er.completed_at=NULL  j.status=cancelled
```

### Orphaned jobs (no eval_run references them)

```
0e35a83d | failed  | "cannot access local variable 'auth_method'"
fbf73350 | failed  | "StringDataRightTruncationError: value too long for VARCHAR(20)"
dbf02f6a | completed | (custom evaluator — eval_run was deleted)
```

### Status column widths

| Table | Column | Max Length | Longest Value | Fits? |
|---|---|---|---|---|
| `eval_runs` | `status` | 30 | `completed_with_errors` (22) | YES |
| `jobs` | `status` | 20 | `cancelled` (9) | YES |

Note: The `fbf73350` job error confirms a historical attempt to write `completed_with_errors` (22 chars) to a table with VARCHAR(20). This was the `eval_runs.status` column BEFORE it was widened to VARCHAR(30). The column has since been fixed.

### API log error distribution

| Error Type | Count | Retryable? |
|---|---|---|
| 429 RESOURCE_EXHAUSTED | 12 | YES — retry delay provided in response |
| Empty string | 2 | Unknown |
| 404 NOT_FOUND (wrong model) | 1 | NO — config error |
| JSON parse error | 2 | YES — retry may produce valid JSON |

---

## Visual Summary: The Core Bug Loop

```
                     ┌─────────────────────────────────────┐
                     │  User submits evaluation job         │
                     └──────────────┬──────────────────────┘
                                    │
                                    ▼
                     ┌──────────────────────────────────────┐
                     │  Job created (queued)                 │
                     │  Worker picks up → creates eval_run   │
                     │  run_id written to progress           │
                     │  ▸ BUG: run_id overwritten by next    │
                     │    progress_callback                  │
                     └──────────────┬───────────────────────┘
                                    │
              ┌─────────────────────┼─────────────────────┐
              │                     │                     │
              ▼                     ▼                     ▼
     ┌────────────────┐  ┌──────────────────┐  ┌─────────────────┐
     │  Completes OK  │  │  User cancels    │  │  Worker crashes  │
     │  eval_run →    │  │                  │  │                  │
     │  completed     │  │  Job → cancelled │  │  Job → running   │
     │  ✓ Works       │  │  eval_run → ???  │  │  eval_run →      │
     └────────────────┘  └────────┬─────────┘  │  running         │
                                  │            │  (NO RECOVERY)   │
                         ┌────────┴────────┐   └────────┬─────────┘
                         │                 │            │
                         ▼                 ▼            │
                ┌─────────────┐  ┌──────────────┐       │
                │ Cancel route │  │ Worker detects│      │
                │ UPDATE works │  │ JobCancelled  │      │
                │ eval_run →   │  │ eval_run →    │      │
                │ cancelled ✓  │  │ cancelled ✓   │      │
                └──────────────┘  └──────────────┘       │
                                                         │
                         ┌───────────────────────────────┘
                         │ If BOTH fail:
                         ▼
                ┌─────────────────────────────────────────┐
                │  ORPHANED EVAL_RUN (status: "running")  │
                │                                         │
                │  ▸ RunDetail: stuck in "Running"        │
                │  ▸ Cancel button: visible but futile    │
                │  ▸ Delete button: disabled forever      │
                │  ▸ RunList: polls every 5s forever      │
                │  ▸ Timer: counts up forever             │
                │  ▸ No escape from UI                    │
                │                                         │
                │  Only fix: direct DB UPDATE              │
                └─────────────────────────────────────────┘
```

---

## Verified Data Sources

All findings in this document are based on:

1. **Source code reading**: Every file listed in `00-overview.md` Key Files tables
2. **DB queries**: `docker exec evals-postgres psql` against live database
3. **Playwright MCP**: API response observation, UI state verification, network request analysis
4. **Flow documents 01-06**: Detailed step-by-step traces with code line references

No assumptions were made — every claim is backed by code, DB evidence, or observed behavior.

# Flow 6: Error Handling Audit

## Summary

The error handling chain has **three independent systems that don't talk to each other**:

1. **Backend**: FastAPI's `HTTPException` for route-level errors; per-runner try/except for LLM and orchestration errors; worker-loop catch-all for unhandled exceptions.
2. **Frontend API client**: `ApiError` class that captures HTTP status + status text but **discards the backend's `detail` message**.
3. **Frontend UI**: A mix of `setError(e.message)` (full-page error banners), `notificationService.error()` (toasts), and silent `catch {}` blocks — with no consistent pattern.

The `AppError` system (`createAppError`, `handleError`, `useErrorHandler`) exists but is **never used in the eval/jobs flows**. It's a legacy holdover from the storage migration era. The eval flows use raw `try/catch` with `e.message` strings everywhere.

**The result**: Backend error messages (often very useful — rate limit details, model not found, etc.) are systematically lost by the time they reach the user. The user sees generic strings like `"API error 400: Bad Request"` instead of `"Cannot delete a running evaluation. Cancel it first."`.

---

## Layer 1: Backend Error Sources

### 1.1 Route-Level Errors (FastAPI HTTPException)

Routes use `HTTPException(status_code, detail_message)` for expected errors:

| Route | Condition | Status | Detail |
|-------|-----------|--------|--------|
| `GET /api/jobs/{id}` | Job not found | 404 | `"Job not found"` |
| `POST /api/jobs/{id}/cancel` | Job not found | 404 | `"Job not found"` |
| `POST /api/jobs/{id}/cancel` | Job completed/failed | 400 | `"Cannot cancel job in '{status}' state"` |
| `GET /api/eval-runs/{id}` | Run not found | 404 | `"Run not found"` |
| `DELETE /api/eval-runs/{id}` | Run not found | 404 | `"Run not found"` |
| `DELETE /api/eval-runs/{id}` | Run is running | 400 | `"Cannot delete a running evaluation. Cancel it first."` |
| `POST /api/eval-runs/preview` | Not CSV | 400 | `"File must be a CSV"` |
| `POST /api/eval-runs/preview` | Not UTF-8 | 400 | `"File must be UTF-8 encoded text"` |
| `POST /api/eval-runs/preview` | Parse error | 422 | `"Failed to parse CSV: {e}"` |

FastAPI serializes these as `{"detail": "...message..."}`. The frontend's `ApiError` stores this in `data` but **never reads it** — the `message` field is always `"API error {status}: {statusText}"`.

**Finding**: All meaningful backend error messages are discarded by the API client.

### 1.2 Worker-Level Errors

The worker loop (`job_worker.py:91-157`) has a catch-all:

```python
except Exception as e:
    logger.error(f"Job {job.id} failed: {e}")
    logger.error(traceback.format_exc())
    # Retry up to 3 times to mark job as failed
    for attempt in range(3):
        try:
            j.status = "failed"
            j.error_message = str(e)[:2000]
            j.completed_at = now
            await db2.commit()
            break
        except Exception as db_err:
            ...
```

**Good**: Retries DB writes up to 3 times, truncates error to 2000 chars.
**Good**: Traceback is logged.
**Issue**: If all 3 retry attempts fail, the job stays in "running" forever (only recovered by `recover_stale_jobs` on next startup, after 15-minute timeout).

### 1.3 Runner-Level Errors (Batch/Adversarial/VoiceRx/Custom)

All four runners follow the same triple-except pattern:

```python
try:
    # ... main processing loop ...
except JobCancelledError:
    # Set eval_run to "cancelled"
except Exception as e:
    # Set eval_run to "failed" with error_message=str(e)
    raise  # Re-raise so worker loop also catches it
```

**Good**: Both eval_run AND job get marked as failed.
**Good**: `error_message` is set on the eval_run for display in the UI.
**Issue**: The `raise` propagates to the worker loop, which sets `job.error_message = str(e)[:2000]` — duplicating the error between `jobs` and `eval_runs` tables with potentially different truncation.

### 1.4 Per-Thread/Per-Test Error Boundaries

**Batch runner** (`batch_runner.py:334-353`): Each thread has its own try/except:
```python
except Exception as e:
    error_msg = str(e)
    results_summary["errors"] += 1
    # Save a failed thread evaluation
    db.add(DBThreadEval(
        run_id=run_id, thread_id=thread_id,
        success_status=False,
        result={"error": error_msg},
    ))
```

**Adversarial runner** (`adversarial_runner.py:217-239`): Each test case has its own try/except:
```python
except Exception as e:
    error_count += 1
    result_data = {"test_case": serialize(tc), "error": str(e)}
    # Save failed adversarial evaluation
```

**Good**: Individual failures don't abort the entire run.
**Issue**: `str(e)` can be empty for some exceptions (notably `JobCancelledError` when caught in the per-thread handler after a race). This is confirmed by DB evidence:
```sql
-- Two threads with empty error strings
SELECT result FROM thread_evaluations WHERE success_status=false AND run_id='eed28526...';
-- {"error": ""} (both rows)
```

### 1.5 LLM-Level Errors

`llm_base.py` wraps all LLM calls with `asyncio.wait_for()`:

```python
try:
    return await asyncio.wait_for(
        asyncio.to_thread(self._sync_generate, ...),
        timeout=timeout,
    )
except asyncio.TimeoutError:
    raise LLMTimeoutError(f"LLM generate call timed out after {timeout}s")
```

`LoggingLLMWrapper` catches exceptions to log them, then re-raises:
```python
except Exception as e:
    error_text = str(e)
    raise
finally:
    await self._save_log(..., error=error_text, ...)
```

**Good**: Timeouts produce clear messages.
**Good**: All LLM errors are logged to `api_logs` table with error text.
**Issue**: No retry logic for transient errors (rate limits, 429s). A single 429 fails the entire thread/test.

**DB evidence**: 12 out of 17 error log entries are `429 RESOURCE_EXHAUSTED` — all would have benefited from retry.

---

## Layer 2: Frontend API Client (`client.ts`)

### 2.1 ApiError Construction

```typescript
if (!response.ok) {
    const text = await response.text();
    let errorData: unknown = text;
    try { errorData = JSON.parse(text); } catch { /* keep as plain text */ }
    throw new ApiError(
        response.status,
        `API error ${response.status}: ${response.statusText}`,  // ← GENERIC message
        errorData,                                                 // ← Backend detail is HERE
    );
}
```

**Critical issue**: The `message` is always `"API error {status}: {statusText}"` (e.g., `"API error 400: Bad Request"`). The actual backend detail (e.g., `"Cannot delete a running evaluation. Cancel it first."`) is stored in `errorData` — which is available as `ApiError.data` but **never consumed by any frontend code**.

Every `catch (e: any) { setError(e.message) }` or `notificationService.error(e.message)` in the entire codebase shows the generic message, not the useful one.

### 2.2 Upload and Download Errors

`apiUpload` and `apiDownload` are even worse:
```typescript
throw new ApiError(response.status, `Upload failed: ${response.statusText}`);
// No errorData at all — backend detail completely lost
```

### 2.3 What the User Sees vs What Exists

| Backend Response | `ApiError.message` (shown to user) | `ApiError.data` (never shown) |
|---|---|---|
| `400 {"detail": "Cannot delete a running evaluation"}` | `"API error 400: Bad Request"` | `{"detail": "Cannot delete a running evaluation"}` |
| `404 {"detail": "Run not found"}` | `"API error 404: Not Found"` | `{"detail": "Run not found"}` |
| `400 {"detail": "Cannot cancel job in 'completed' state"}` | `"API error 400: Bad Request"` | `{"detail": "Cannot cancel job in 'completed' state"}` |
| `422 {"detail": "Failed to parse CSV: ..."}` | `"API error 422: Unprocessable Entity"` | `{"detail": "Failed to parse CSV: ..."}` |

---

## Layer 3: Frontend Error Display Patterns

### 3.1 Pattern A: `setError(e.message)` → Full-Page Error Banner

Used in: `RunDetail`, `RunList`, `Dashboard`, `Logs`, `ThreadDetail`, `AdversarialDetail`.

```typescript
const [error, setError] = useState("");
// ...
.catch((e: Error) => setError(e.message));
// ...
if (error) {
    return (
        <div className="bg-[var(--surface-error)] ...">
            {error}  {/* Raw ApiError.message — e.g., "API error 404: Not Found" */}
        </div>
    );
}
```

**Issues**:
- Replaces the ENTIRE page with a single error message
- No way to recover except browser refresh
- Uses the generic `ApiError.message`, not the useful backend detail
- No "Back" link or retry button
- In RunList: a single failed delete wipes out the entire runs list view

### 3.2 Pattern B: `notificationService.error()` → Toast

Used in: `useSubmitAndRedirect`, `JobCompletionWatcher`, `useEvaluatorRunner`, `useAIEvaluation`, `useUnifiedEvaluation`, upload hooks.

```typescript
catch (err) {
    const msg = err instanceof Error ? err.message : 'Failed to submit job.';
    notificationService.error(msg);
}
```

**Issues**:
- Same generic `ApiError.message`
- Toast auto-dismisses after 6 seconds (error duration default)
- Dedup window of 2 seconds prevents rapid-fire errors from showing

**Good**: Toasts don't destroy the page — user retains context.

### 3.3 Pattern C: Silent `catch {}` — No Error Shown

Used in: Polling loops, incremental data fetches.

```typescript
// RunDetail polling loop
try {
    const job = await jobsApi.get(runJobId!);
    // ...
} catch {
    // Polling error — wait and retry
}

// Thread/adversarial incremental fetch
fetchRunThreads(runId).catch(() => ({ evaluations: [] as ThreadEvalRow[] }))
```

**Good**: Transient network errors during polling don't crash the page.
**Issue**: Persistent errors are silently swallowed. If the backend is down, the user sees a frozen page with no error indication.

### 3.4 Pattern D: `JobCompletionWatcher` Toast

```typescript
if (job.status === 'failed') {
    notificationService.error(
        `${tracked.label} failed${job.errorMessage ? `: ${job.errorMessage}` : ''}`,
        'Job Failed',
    );
}
```

**Good**: Uses `job.errorMessage` from the API response (the backend's `error_message` field), not the generic ApiError message.
**Issue**: `job.errorMessage` is only populated for jobs that failed at the worker level. Jobs that fail during submission (HTTP error) never reach this path.

### 3.5 Pattern E: Run Status Banners

```tsx
// FailureBanner — shows eval_run.error_message from DB
{run.status.toLowerCase() === "failed" && run.error_message && !isRunActive && (
    <FailureBanner message={run.error_message} />
)}

// ErrorWarningBanner — shows X of Y failed
{summaryErrors > 0 && summaryCompleted > 0 && !isRunActive && (
    <ErrorWarningBanner errors={summaryErrors} total={summaryTotal} completed={summaryCompleted} />
)}
```

**Good**: Uses the rich `error_message` from the eval_run (set by the runner).
**Issue**: Only shown when `!isRunActive` — orphaned running runs never show error banners.

---

## Layer 4: The Unused AppError System

### 4.1 What Exists

```
src/services/errors/errorHandler.ts   — createAppError(), handleError(), isAppError()
src/hooks/useErrorHandler.ts          — useErrorHandler() hook
src/types/                            — AppError, ErrorCode, ErrorSeverity, ERROR_MESSAGES
```

`createAppError` creates structured errors with codes like `STORAGE_MIGRATION_FAILED`, `FILE_CORRUPTED`, `UNKNOWN_ERROR`. `handleError` wraps any error into an `AppError`. `useErrorHandler` hook adds errors to `useUIStore` and fires notifications.

### 4.2 Where It's Used

**Nowhere in the eval/jobs flows.** Grep confirms:
- `useErrorHandler` is imported in only `src/hooks/index.ts` and its own definition
- Not used in RunDetail, RunList, RunCard, useSubmitAndRedirect, JobCompletionWatcher, or any eval component
- The `ErrorCode` types are storage-migration focused: `STORAGE_MIGRATION_FAILED`, `FILE_CORRUPTED`, `QUOTA_EXCEEDED`, etc.

### 4.3 What Actually Gets Used

Every eval/jobs error handler uses raw `try/catch` with `e.message`:
```typescript
// This pattern appears 15+ times in evalRuns/ pages and components
catch (e: any) {
    setError(e.message);   // or notificationService.error(e.message)
}
```

---

## Layer 5: Error Recovery Mechanisms

### 5.1 `recover_stale_jobs()` — Backend Startup

```python
async def recover_stale_jobs(stale_minutes: int = 15):
    stale_jobs = select(Job).where(
        Job.status == "running", Job.started_at < cutoff
    )
    for job in stale_jobs:
        job.status = "failed"
        job.error_message = f"Recovered on startup: job was running for >{stale_minutes} minutes"
```

**Good**: Prevents jobs from being stuck forever after a crash.
**Issue**: Only recovers `jobs` table. Eval_runs stuck in "running" are NOT recovered. (Documented in Flow 3.)

### 5.2 Worker Error Retry (3 attempts)

The worker loop retries DB writes up to 3 times with 1-second sleep between attempts:
```python
for attempt in range(3):
    try:
        j.status = "failed"
        j.error_message = str(e)[:2000]
        await db2.commit()
        break
    except Exception:
        if attempt < 2: await asyncio.sleep(1)
```

**Good**: Handles transient DB connection issues.
**Issue**: Uses a fresh session but doesn't check if the job was cancelled between the error and the retry — could overwrite "cancelled" with "failed".

### 5.3 No LLM Retry

No LLM calls have retry logic. A single `429 RESOURCE_EXHAUSTED` fails the entire thread/test.

**DB evidence**: 12 of 17 API log errors are rate limits — all could potentially succeed on retry.

---

## DB Evidence: Error Data Quality

### Eval Run Error Messages

| Status | Count | Has error_message | Quality |
|--------|-------|-------------------|---------|
| `failed` | 5 | 5 (100%) | Detailed — raw LLM SDK exception strings (429, 404, etc.) |
| `completed_with_errors` | 1 | 1 (100%) | Good — "9 of 10 thread evaluations failed" |
| `cancelled` | 1 | 0 (0%) | N/A — cancelled, not an error |
| `running` (orphaned) | 1 | 0 (0%) | **Missing** — should have been set but worker crashed |
| `completed` | 2 | 0 (0%) | N/A — no errors |

### Thread Evaluation Errors

| Total failed threads | With non-empty `result.error` | With empty `result.error` |
|---|---|---|
| 3 | 1 (from run `2145351c`, `success_status=false` but has full result data) | 2 (from orphaned run `eed28526`, error string is `""`) |

The 2 empty-string errors from the orphaned run are threads that were being processed when cancellation was triggered — the exception message for the race condition between cancellation and per-thread processing was empty.

### Jobs Error Messages

| Status | Count | Has error_message | Quality |
|--------|-------|-------------------|---------|
| `failed` | 6 | 6 (100%) | Detailed — includes full SDK error dicts, SQL errors, Python tracebacks |
| `cancelled` | 2 | 0 | N/A |
| `completed` | 3 | 0 | N/A |

**Notable job errors observed**:
- `"429 RESOURCE_EXHAUSTED"` — rate limit with retry delay info (3 occurrences)
- `"404 NOT_FOUND"` — model not found (wrong Vertex AI project)
- `"cannot access local variable 'auth_method'"` — Python bug
- `"StringDataRightTruncationError: value too long for type character varying(20)"` — `eval_runs.status` column is VARCHAR(20), which is too short for `"completed_with_errors"` (22 chars)

### Critical Finding: `completed_with_errors` Exceeds Status Column Width

The `eval_runs.status` column is `VARCHAR(30)` (30 chars) — this is fine for `"completed_with_errors"` (22 chars). But the `jobs.status` column is `VARCHAR(20)` — and the error in the DB (`StringDataRightTruncationError`) confirms a previous attempt to write a too-long status value to some table. This may be a historical bug that's been fixed.

### API Log Errors

| Error Type | Count | Retryable? |
|---|---|---|
| `429 RESOURCE_EXHAUSTED` | 12 | YES — retry delay provided |
| Empty string | 2 | Unknown |
| `404 NOT_FOUND` (wrong model) | 1 | NO — config error |
| `JSON parse error` | 2 | YES — LLM can produce valid JSON on retry |

---

## End-to-End Error Propagation Chains

### Chain A: LLM Rate Limit → Thread Failure → User Sees Nothing

```
1. Gemini returns 429 RESOURCE_EXHAUSTED with retry delay
2. google-genai SDK raises exception with full error dict
3. LoggingLLMWrapper catches → logs error to api_logs → re-raises
4. Per-thread except in batch_runner catches → error_msg = str(e)
5. Saves ThreadEvaluation(result={"error": "429 RESOURCE_EXHAUSTED..."})
6. Increments results_summary["errors"]
7. At finalization: eval_run.status = "completed_with_errors"
   eval_run.error_message = "9 of 10 thread evaluations failed"
8. Frontend RunDetail loads eval_run → shows ErrorWarningBanner
   "9 of 10 thread evaluations failed. Results below are from the 1 thread that succeeded."
9. User sees ThreadDetailCard for the failed thread:
   - result.error is truthy → error banner: "Evaluation failed: 429 RESOURCE_EXHAUSTED..."
   ✓ Error message DOES reach the user in this case
```

**Assessment**: This chain works — the user sees both the summary banner and per-thread errors. The error messages are raw SDK strings (not user-friendly) but at least informative.

### Chain B: LLM Timeout → Thread Failure → User Sees Error

```
1. asyncio.wait_for times out → LLMTimeoutError("LLM generate call timed out after 60s")
2. Same chain as above
3. ThreadEvaluation saved with result={"error": "LLM generate call timed out after 60s"}
4. User sees "Evaluation failed: LLM generate call timed out after 60s"
✓ Works correctly
```

### Chain C: Rate Limit Immediately → Eval Run Fails → User Sees Banner

```
1. First LLM call hits 429 immediately (before any thread processing)
2. Exception propagates up through batch_runner's outer except
3. eval_run.status = "failed", error_message = "429 RESOURCE_EXHAUSTED..."
4. Re-raise to worker loop → job.status = "failed", error_message = same
5. Frontend loads RunDetail → FailureBanner: "Evaluation failed: 429 RESOURCE_EXHAUSTED..."
✓ Works, but error message is raw SDK text — not user-friendly
```

### Chain D: Cancel During LLM Call → Empty Error String (BUG)

```
1. Cancel route sets job.status = "cancelled"
2. Worker is mid-LLM call for thread 4
3. LLM call finishes/fails while cancel is pending
4. Per-thread except catches: error_msg = str(e) → "" (empty for some exceptions)
5. Saves ThreadEvaluation(result={"error": ""})
6. Next iteration: is_job_cancelled() → True → JobCancelledError
7. Frontend: result.error === "" → falsy → error banner NOT shown
8. Thread appears with 0 msgs, N/A verdicts, no explanation
✗ BUG: Empty error string makes the failure invisible
```

### Chain E: Submission HTTP Error → User Sees Generic Toast

```
1. POST /api/jobs fails (e.g., 500 Internal Server Error)
2. apiRequest throws ApiError(500, "API error 500: Internal Server Error", data)
3. useSubmitAndRedirect catches: notificationService.error("API error 500: Internal Server Error")
4. User sees toast: "API error 500: Internal Server Error"
✗ Backend detail is lost — user doesn't know why it failed
```

### Chain F: Delete Running Run → User Sees Generic Error

```
1. DELETE /api/eval-runs/{id} → 400 {"detail": "Cannot delete a running evaluation. Cancel it first."}
2. apiRequest throws ApiError(400, "API error 400: Bad Request", {"detail": "..."})
3. RunDetail: setError(e.message) → "API error 400: Bad Request"
4. Entire page replaced with error banner: "API error 400: Bad Request"
✗ User sees "Bad Request" instead of the helpful "Cannot delete a running evaluation. Cancel it first."
```

### Chain G: Navigate to Deleted Run → User Sees Generic Error

```
1. GET /api/eval-runs/{id} → 404 {"detail": "Run not found"}
2. ApiError(404, "API error 404: Not Found", {"detail": "Run not found"})
3. RunDetail: setError(e.message) → "API error 404: Not Found"
4. Full-page error banner: "API error 404: Not Found"
✗ No "Run not found" message, no back link, no redirect
```

---

## Bugs & Issues Found

### BUG 1: ApiError.message Discards Backend Detail

**Severity: HIGH — affects EVERY API error the user sees**

`client.ts` line 44-48: The `ApiError.message` is always `"API error {status}: {statusText}"`. The backend's detail message is stored in `ApiError.data` but never consumed by any catch handler. Every `setError(e.message)` and `notificationService.error(e.message)` in the codebase shows the generic message.

**Fix**: Extract `detail` from the JSON response body:
```typescript
const detail = (typeof errorData === 'object' && errorData !== null && 'detail' in errorData)
    ? (errorData as any).detail
    : null;
const message = detail
    ? String(detail)
    : `API error ${response.status}: ${response.statusText}`;
throw new ApiError(response.status, message, errorData);
```

### BUG 2: Empty Error String in Failed Thread Evaluations

**Severity: MEDIUM — thread failures invisible to user**

When cancellation races with per-thread error handling, `str(e)` can produce an empty string. The frontend checks `result?.error` which is falsy for `""`, so the error banner is never shown.

**DB evidence**: 2 of 3 failed thread evaluations have `result = {"error": ""}`.

### BUG 3: setError() Replaces Entire Page

**Severity: MEDIUM — destructive UX for non-fatal errors**

In RunList, a single failed delete call sets `error` state, which replaces the entire list with an error banner. The user loses visibility of all other runs and has to refresh.

Used in: `RunList.handleDelete`, `RunList.handleDeleteCustom`, `RunDetail.handleDeleteConfirm`, `RunDetail.handleCancel`.

**Fix**: Use toasts for transient action errors (delete/cancel failures). Reserve `setError()` for initial data load failures only.

### BUG 4: No Error Recovery on Pages

**Severity: MEDIUM — user stuck on error screen**

Once `setError()` fires, the page renders a bare error div with no:
- Retry button
- Back link
- Auto-retry mechanism

The only recovery is browser refresh.

### BUG 5: No LLM Retry for Transient Errors

**Severity: MEDIUM — 70% of API log errors are retryable**

Rate limits (429) include explicit `retryDelay` values (11s, 42s, 48s observed). No retry logic exists — a single 429 fails the thread.

**DB evidence**: 12 of 17 API log errors are `429 RESOURCE_EXHAUSTED`.

### BUG 6: AppError System Unused in Eval Flows

**Severity: LOW — dead code**

`createAppError`, `handleError`, `useErrorHandler` exist but are never used in the eval/jobs flows. All error handling is raw `try/catch` with `e.message`. The `ErrorCode` enum doesn't include eval-related codes.

### BUG 7: Worker Error Recovery Can Overwrite "cancelled" Status

**Severity: LOW — theoretical race condition**

The worker's error handler (line 136-152) checks `j.status not in ("completed", "cancelled")` before setting "failed". This is correct. But between the exception and the retry loop, the cancel route could set the job to "cancelled". The fresh `db.get(Job, job.id)` reads the latest status, so the guard should work. However, there's no equivalent guard for eval_run status — the runner's `except Exception` handler always sets eval_run to "failed", even if it was already "cancelled" by the cancel route.

### BUG 8: `recover_stale_jobs()` Doesn't Recover Eval Runs

**Severity: HIGH — documented in Flow 3, repeated here for completeness**

Only jobs are recovered. Eval_runs stuck in "running" with a terminal job remain orphaned forever.

### BUG 9: Thread Evaluation Errors Not Saved for completed_with_errors Runs

**Severity: MEDIUM — errors counted but not visible**

For eval_run `10342750` (status `completed_with_errors`, summary says 9 errors), the `thread_evaluations` table only has 1 row (the successful one). The 9 failed threads have NO rows — meaning the per-thread `except` block either:
1. Failed to write the error ThreadEvaluation row (the inner `try` failed silently)
2. The error occurred before the thread processing loop (e.g., data loading failed for those threads)

**Impact**: RunDetail shows 1 thread in the table and says "9 of 10 failed" in the banner, but the user can't see WHICH threads failed or why.

### BUG 10: Raw SDK Error Messages Shown to Users

**Severity: LOW — confusing but informative**

Error messages like `"429 RESOURCE_EXHAUSTED. {'error': {'code': 429, ...}}"` are shown verbatim in the FailureBanner and thread error displays. These are technically correct but not user-friendly.

---

## Error Handling Comparison Across Flows

| Error Scenario | Backend Handling | API Client | Frontend Display | User Experience |
|---|---|---|---|---|
| Job submission fails (network) | N/A | ApiError thrown | Toast (useSubmitAndRedirect) | Generic "API error..." toast |
| Job submission fails (validation) | HTTPException 400 | ApiError (detail lost) | Toast | Generic "API error 400: Bad Request" |
| Worker handler crashes | Job → failed, error_message set | N/A | JobCompletionWatcher toast uses `job.errorMessage` | **Good** — real error shown |
| Individual thread fails (LLM) | ThreadEvaluation saved | N/A | Thread error banner | **Good** — error in thread detail |
| Individual thread fails (empty error) | ThreadEvaluation saved with `""` | N/A | Nothing shown | **Bad** — invisible failure |
| Entire run fails (rate limit) | EvalRun → failed, error_message | N/A | FailureBanner | **Good** — raw but informative |
| Cancel fails (completed job) | HTTPException 400 | ApiError (detail lost) | Full-page error banner | **Bad** — "API error 400: Bad Request" |
| Delete fails (running run) | HTTPException 400 | ApiError (detail lost) | Full-page error banner | **Bad** — "API error 400: Bad Request" |
| Navigate to deleted run | HTTPException 404 | ApiError (detail lost) | Full-page error banner | **Bad** — "API error 404: Not Found" |
| Polling error (transient) | N/A | Caught silently | Nothing | **Acceptable** — retries on next cycle |
| All threads fail | EvalRun → failed | N/A | FailureBanner | **Good** — error shown |

---

## Error Surface Summary

### Backend → DB (Writing errors)
**Good overall.** Every runner writes error info to the DB (eval_run.error_message, thread_evaluation.result.error, api_logs.error). The worker loop has a retry mechanism for DB writes.

### DB → API (Reading errors)
**Good.** All error fields are included in API responses (errorMessage, error_message, result.error, etc.).

### API → Frontend Client (HTTP errors)
**Broken.** ApiError.message is always generic. The backend detail is captured but never consumed.

### Frontend Display (Showing errors to user)
**Mixed.** Toast notifications work but show generic messages. Full-page error banners are too destructive. Polling errors are silently swallowed. Status banners and thread detail error displays work well when they have real data.

---

## Verified via DB Queries

| Query | Result |
|---|---|
| Eval runs with error_message | 6 of 10 — all failed/completed_with_errors runs have messages |
| Thread evaluations with empty error | 2 of 3 — both from orphaned run during cancellation race |
| Jobs with error_message | 6 of 11 — all failed jobs have messages |
| API logs with errors | 17 of 48 — 12 are rate limits, 2 are JSON parse, 1 is 404, 2 are empty |
| completed_with_errors run missing thread rows | 9 of 10 error threads have no rows in thread_evaluations |

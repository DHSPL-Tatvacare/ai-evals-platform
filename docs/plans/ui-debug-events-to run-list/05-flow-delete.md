# Flow 5: User Deletes a Run

## Summary

Deleting a run is available from two places: RunDetail page and RunList page. Both paths call `DELETE /api/eval-runs/{runId}`. The backend validates that the run exists and isn't "running", then issues `db.delete(run)` which cascades to `thread_evaluations`, `adversarial_evaluations`, and `api_logs`. The frontend removes the run from local state and either navigates back (RunDetail) or updates the list in-place (RunList).

**The happy path works correctly.** Cascade deletes work, navigation is sensible, and confirmation dialogs prevent accidental deletion. The main issues are:
1. **Orphaned runs can never be deleted** — the "running" guard blocks deletion, and the cancel flow can't fix the orphaned status (documented in Flow 4).
2. **The associated `jobs` row is never cleaned up** — it stays in the DB forever after the eval_run is deleted.
3. **Error messages shown to the user are raw API errors** — no user-friendly formatting.
4. **Navigating to a deleted run URL shows a raw error string** — no "Run not found" page or redirect.

---

## Step-by-Step Trace

### Path A: Delete from RunDetail (Completed/Failed/Cancelled Run)

#### 1. User Clicks Delete Button

**RunDetail.tsx, line 483-490:**

```typescript
<button
  onClick={() => setConfirmDelete(true)}
  disabled={deleting || isRunActive}
  title={isRunActive ? "Cannot delete a running evaluation. Cancel it first." : undefined}
>
  {deleting ? "Deleting…" : "Delete"}
</button>
```

**Guard**: `disabled={deleting || isRunActive}` — button is disabled if:
- `deleting` state is true (deletion in progress)
- `isRunActive` is true (`run.status.toLowerCase() === "running"`)

**Tooltip**: When `isRunActive`, title shows "Cannot delete a running evaluation. Cancel it first."

#### 2. Confirmation Dialog Opens

**RunDetail.tsx, line 703-714:**

```typescript
<ConfirmDialog
  isOpen={confirmDelete}
  onClose={() => setConfirmDelete(false)}
  onConfirm={handleDeleteConfirm}
  title="Delete Evaluation Run"
  description={`Delete run ${run.run_id.slice(0, 12)}... and all its evaluations? This cannot be undone.`}
  confirmLabel={deleting ? "Deleting..." : "Delete"}
  variant="danger"
  isLoading={deleting}
/>
```

**Verified via Playwright**: Dialog appears with:
- Title: "Delete Evaluation Run"
- Description: "Delete run 2145351c-2c0... and all its evaluations? This cannot be undone."
- Buttons: "Cancel" and "Delete" (danger variant — red)
- Modal blocks background interaction
- Clicking "Cancel" or clicking outside closes the dialog without action

#### 3. User Confirms — handleDeleteConfirm Fires

**RunDetail.tsx, line 233-244:**

```typescript
const handleDeleteConfirm = useCallback(async () => {
  if (!runId || !run) return;
  setDeleting(true);
  setConfirmDelete(false);          // Close dialog immediately
  try {
    await deleteRun(runId);          // DELETE /api/eval-runs/{runId}
    navigate(routes.kaira.runs, { replace: true });  // Navigate to RunList
  } catch (e: any) {
    setError(e.message);             // Show error in UI
    setDeleting(false);
  }
}, [runId, run, navigate]);
```

**Sequence**:
1. `setDeleting(true)` — Delete button shows "Deleting…", dialog closed
2. `setConfirmDelete(false)` — dialog disappears
3. `deleteRun(runId)` — HTTP DELETE to backend
4. On success: `navigate(routes.kaira.runs, { replace: true })` — redirects to `/kaira/runs`, using `replace: true` so back-button won't return to the deleted run
5. On error: `setError(e.message)` — shows raw error message, `setDeleting(false)` re-enables button

**Note**: `setDeleting(false)` is NOT called on success (no `finally` block). This is fine because the component unmounts during navigation, but if navigation somehow fails, the button stays in "Deleting…" state forever.

#### 4. API Call: DELETE /api/eval-runs/{runId}

**Frontend: evalRunsApi.ts, line 86-88:**

```typescript
export async function deleteRun(runId: string): Promise<{ deleted: boolean; run_id: string }> {
  return apiRequest(`/api/eval-runs/${runId}`, { method: 'DELETE' });
}
```

**Backend: eval_runs.py, line 250-260:**

```python
@router.delete("/{run_id}")
async def delete_eval_run(run_id: UUID, db: AsyncSession = Depends(get_db)):
    """Delete an eval run and all its cascaded data."""
    run = await db.get(EvalRun, run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    if run.status == "running":
        raise HTTPException(400, "Cannot delete a running evaluation. Cancel it first.")
    await db.delete(run)  # CASCADE deletes threads, adversarial, logs
    await db.commit()
    return {"deleted": True, "run_id": str(run_id)}
```

**Backend logic**:
1. Fetch run by ID — 404 if not found
2. Check status — 400 if "running"
3. `db.delete(run)` — SQLAlchemy issues DELETE on `eval_runs`, DB cascades to children
4. `db.commit()` — commits transaction
5. Returns `{"deleted": true, "run_id": "..."}`

#### 5. DB Cascade

**Verified via Playwright and psql**: Deleting eval_run `4d803362` cascaded correctly.

| Table | Before | After |
|-------|--------|-------|
| `eval_runs` | 1 row | 0 rows |
| `thread_evaluations` (via `run_id` FK, `ON DELETE CASCADE`) | N rows | 0 rows |
| `adversarial_evaluations` (via `run_id` FK, `ON DELETE CASCADE`) | N rows | 0 rows |
| `api_logs` (via `run_id` FK, `ON DELETE CASCADE`) | N rows | 0 rows |
| `jobs` (no FK from jobs→eval_runs) | 1 row | **1 row (ORPHANED)** |

**FK constraints verified**:
```
 child_table             | fk_column | delete_rule
 thread_evaluations      | run_id    | CASCADE
 adversarial_evaluations | run_id    | CASCADE
 api_logs                | run_id    | CASCADE
```

The `eval_runs.job_id → jobs.id` FK has `ON DELETE SET NULL`, meaning if a job were deleted first, the eval_run's `job_id` would become NULL. But in the reverse direction (deleting eval_run), there's no constraint that cleans up the associated job.

#### 6. Navigation After Delete

**Verified via code**: `navigate(routes.kaira.runs, { replace: true })` navigates to `/kaira/runs`.

- `replace: true` replaces the current history entry, so pressing browser back doesn't return to the deleted run's URL
- RunList remounts and re-fetches all runs from the API — the deleted run is gone

---

### Path B: Delete from RunList (Batch Runs)

#### 1. RunCard Delete Flow

**RunCard.tsx, line 17-35:**

```typescript
const isActive = run.status.toLowerCase() === "running";

function handleDeleteConfirm() {
  if (!onDelete) return;
  setDeleting(true);
  setConfirmDelete(false);
  onDelete(run.run_id);  // Calls parent's handleDelete
}
```

**RunRowCard.tsx, line 109-117:**

```typescript
{onDelete && (
  <button
    onClick={(e) => { e.preventDefault(); e.stopPropagation(); onDelete(); }}
    disabled={deleteDisabled || isRunning}
    title={isRunning ? 'Stop the run before deleting' : 'Delete run'}
  >
    <Trash2 />
  </button>
)}
```

**Guard**: `deleteDisabled={deleting || isActive}` — button disabled if run is active or delete in progress.

**Verification from Playwright**: Orphaned run (`eed28526`) shows delete button as `[disabled]` with tooltip "Stop the run before deleting".

#### 2. ConfirmDialog in RunCard

Same `ConfirmDialog` pattern as RunDetail:
- Title: "Delete Evaluation Run"
- Description: `Delete run ${run.run_id.slice(0, 12)}... and all its evaluations? This cannot be undone.`
- Confirm triggers `onDelete(run.run_id)`

#### 3. RunList handleDelete Callback

**RunList.tsx, line 123-130:**

```typescript
const handleDelete = useCallback(async (runId: string) => {
  try {
    await deleteRun(runId);                               // DELETE API call
    setRuns((prev) => prev.filter((r) => r.run_id !== runId));  // Remove from state
  } catch (e: any) {
    setError(e.message);                                  // Show error
  }
}, []);
```

**Sequence**:
1. API call: `DELETE /api/eval-runs/{runId}`
2. On success: Removes run from `runs` state via filter — instant UI update
3. On error: Sets error state — entire RunList is replaced by error message

**Issue**: On error, `setError(e.message)` replaces the ENTIRE RunList with an error banner. The user loses visibility of all other runs. A toast notification would be less destructive.

---

### Path C: Delete from RunList (Custom Evaluator Runs)

#### 1. Custom Run Delete Flow

**RunList.tsx, line 132-144:**

```typescript
const handleDeleteCustom = useCallback(async () => {
  if (!deleteTarget) return;
  setIsDeleting(true);
  try {
    await deleteEvalRun(deleteTarget.id);                           // DELETE API call
    setCustomRuns((prev) => prev.filter((r) => r.id !== deleteTarget.id));  // Remove from state
    setDeleteTarget(null);                                          // Close dialog
  } catch (e: unknown) {
    setError(e instanceof Error ? e.message : 'Delete failed');
  } finally {
    setIsDeleting(false);
  }
}, [deleteTarget]);
```

Same pattern as batch delete but:
- Uses `deleteEvalRun()` (same endpoint, different function name — legacy)
- Targets `deleteTarget.id` instead of `runId`
- Has a `finally` block (unlike batch's `handleDelete` which doesn't reset `deleting` state)

---

### Path D: Delete from VoiceRx RunList

**VoiceRxRunList.tsx, line 156-168:**

```typescript
const handleDelete = useCallback(async () => {
  if (!deleteTarget) return;
  setIsDeleting(true);
  try {
    await deleteEvalRun(deleteTarget.id);
    setRuns((prev) => prev.filter((r) => r.id !== deleteTarget.id));
    setDeleteTarget(null);
  } catch (e: unknown) {
    setError(e instanceof Error ? e.message : 'Delete failed');
  } finally {
    setIsDeleting(false);
  }
}, [deleteTarget]);
```

Same pattern as RunList custom delete. Uses `deleteEvalRun()`, same endpoint.

**Note**: VoiceRx runs have no RunDetail page — they link to `${routes.voiceRx.logs}?entity_id=${run.id}` (logs page). Delete is only available from the list view.

---

## Navigating to a Deleted Run's URL

**Verified via Playwright**: Navigating directly to `/kaira/runs/4d803362-...` (deleted run) shows:

```
"API error 404: Not Found"
```

This is the raw `ApiError.message` string from `client.ts`. The error is caught by the `catch` block in the initial data load effect:

```typescript
.catch((e: Error) => {
  if (!cancelled) setError(e.message);
});
```

And rendered by:

```typescript
if (error) {
  return (
    <div className="bg-[var(--surface-error)] ...">
      {error}
    </div>
  );
}
```

The message `"API error 404: Not Found"` is not user-friendly. There's no "Run not found" message, no link back to the runs list, and no redirect.

---

## DB Evidence

### Before Delete (run `4d803362`)

```sql
SELECT id, status, job_id FROM eval_runs WHERE id = '4d803362-6370-4285-8f51-0f1021fb938a';
-- status: failed, job_id: fbf73350-...

SELECT count(*) FROM thread_evaluations WHERE run_id = '4d803362-...';
-- 0

SELECT count(*) FROM api_logs WHERE run_id = '4d803362-...';
-- (some count)
```

### After Delete

```sql
SELECT count(*) FROM eval_runs WHERE id = '4d803362-...';
-- 0

SELECT count(*) FROM thread_evaluations WHERE run_id = '4d803362-...';
-- 0

SELECT count(*) FROM api_logs WHERE run_id = '4d803362-...';
-- 0

-- But the job still exists:
SELECT id, status FROM jobs WHERE id = 'fbf73350-8caa-4dac-9f91-4ec08c0bd3ff';
-- status: failed (ORPHANED — no eval_run references it anymore)
```

### Cascade Delete Verification

All three child FK constraints use `ON DELETE CASCADE`:
```
 child_table             | fk_column | delete_rule
 thread_evaluations      | run_id    | CASCADE
 adversarial_evaluations | run_id    | CASCADE
 api_logs                | run_id    | CASCADE
```

SQLAlchemy ORM also has `cascade="all, delete-orphan"` on the relationships:
```python
thread_evaluations = relationship(cascade="all, delete-orphan", passive_deletes=True)
adversarial_evaluations = relationship(cascade="all, delete-orphan", passive_deletes=True)
api_logs = relationship(cascade="all, delete-orphan", passive_deletes=True)
```

Both ORM-level and DB-level cascades are in place. `passive_deletes=True` means SQLAlchemy trusts the DB to handle cascades rather than issuing individual DELETEs for each child.

---

## State Management Summary

### RunDetail Delete Flow

| Step | State Change | Effect |
|------|-------------|--------|
| Click Delete | `confirmDelete = true` | Dialog opens |
| Click Confirm | `deleting = true`, `confirmDelete = false` | Dialog closes, button shows "Deleting…" |
| API success | `navigate('/kaira/runs', { replace: true })` | Component unmounts, RunList loads |
| API error | `error = e.message`, `deleting = false` | Error banner replaces entire page |

### RunList Delete Flow (Batch)

| Step | State Change | Effect |
|------|-------------|--------|
| Click trash icon | `confirmDelete = true` (in RunCard) | Dialog opens |
| Click Confirm | `deleting = true`, `confirmDelete = false` | Dialog closes |
| Parent `onDelete` called | (async) | DELETE API fires |
| API success | `runs = prev.filter(r => r.run_id !== runId)` | Run removed from list instantly |
| API error | `error = e.message` | **Entire RunList replaced by error banner** |

### RunList Delete Flow (Custom)

| Step | State Change | Effect |
|------|-------------|--------|
| Click trash icon | `deleteTarget = run` | Dialog opens |
| Click Confirm | `isDeleting = true` | Dialog button shows "Deleting..." |
| API success | `customRuns = prev.filter(...)`, `deleteTarget = null` | Run removed, dialog closes |
| API error | `error = e.message` | **Entire RunList replaced by error banner** |
| Finally | `isDeleting = false` | (No visible effect if dialog is already closed) |

---

## API Sequence Diagram

### Happy Path: Delete from RunDetail (Completed Run)

```
[User on RunDetail page — completed run]
    │
    ├── Click "Delete" button
    │   → setConfirmDelete(true)
    │   → ConfirmDialog renders
    │
    ├── Click "Delete" in dialog
    │   → setDeleting(true), setConfirmDelete(false)
    │   → DELETE /api/eval-runs/{runId}
    │       → Backend: db.get(EvalRun, run_id) → found
    │       → Backend: run.status == "completed" → not "running" → proceed
    │       → Backend: db.delete(run) → CASCADE to children
    │       → Backend: db.commit()
    │       → 200: {"deleted": true, "run_id": "..."}
    │
    └── navigate('/kaira/runs', { replace: true })
        → RunList mounts
        → GET /api/eval-runs?limit=100 → deleted run NOT in results
```

### Error Path: Delete Blocked for Running Run

```
[User on RunDetail — orphaned "running" run]
    │
    ├── Delete button is DISABLED (isRunActive = true)
    │   → title="Cannot delete a running evaluation. Cancel it first."
    │   → User cannot click
    │
    └── [Even if they bypass UI with curl:]
        DELETE /api/eval-runs/{runId}
        → Backend: run.status == "running" → HTTP 400
        → {"detail": "Cannot delete a running evaluation. Cancel it first."}
```

### Delete from RunList (Batch Run)

```
[User on RunList page]
    │
    ├── Hover over run card → trash icon appears (opacity transition)
    │   └── If isActive (running) → trash icon disabled, title="Stop the run before deleting"
    │
    ├── Click trash icon (non-running run)
    │   → e.preventDefault() + e.stopPropagation() (prevents link navigation)
    │   → setConfirmDelete(true) in RunCard
    │   → ConfirmDialog renders
    │
    ├── Click "Delete" in dialog
    │   → handleDeleteConfirm() → onDelete(run.run_id) → parent handleDelete()
    │   → DELETE /api/eval-runs/{runId}
    │       → 200: {"deleted": true, "run_id": "..."}
    │
    └── setRuns(prev => prev.filter(r => r.run_id !== runId))
        → Run disappears from list instantly (no re-fetch needed)
```

---

## Verified via Playwright

| Test | Result |
|------|--------|
| RunList: orphaned running run has disabled delete button | `[disabled]`, tooltip "Stop the run before deleting" |
| RunList: completed/failed/cancelled runs have enabled delete button | Enabled, shows on hover |
| RunDetail (completed): Delete button enabled | Enabled |
| RunDetail (completed): Click Delete → confirmation dialog | Dialog with title, description, Cancel/Delete buttons |
| RunDetail (completed): Click Cancel in dialog | Dialog closes, no action |
| RunDetail (orphaned running): Delete button disabled | `[disabled]` with tooltip |
| RunDetail (orphaned running): Cancel button visible | Yes (but futile — see Flow 4) |
| API: DELETE orphaned running run | 400: "Cannot delete a running evaluation. Cancel it first." |
| API: DELETE failed run | 200: `{"deleted": true, "run_id": "..."}` |
| DB: eval_run deleted | Row removed from `eval_runs` |
| DB: cascade to children | `thread_evaluations`, `adversarial_evaluations`, `api_logs` all cleared |
| DB: associated job after delete | **Still exists** — orphaned in `jobs` table |
| Navigate to deleted run URL | Shows raw error: "API error 404: Not Found" |

---

## Bugs & Issues Specific to This Flow

### BUG 1: Orphaned Runs Cannot Be Deleted (Inherited from Flow 4)

**Severity: HIGH — no cleanup path**

The backend's delete endpoint rejects runs with `status: "running"`:
```python
if run.status == "running":
    raise HTTPException(400, "Cannot delete a running evaluation. Cancel it first.")
```

The frontend disables the Delete button when `isRunActive` (same guard). But as documented in Flow 4, the cancel route cannot fix the orphaned status. The user is stuck in an infinite cycle:
- "Cancel it first" → Cancel → Backend early return → Status still "running" → "Cancel it first" → ...

The only escape is direct DB access: `UPDATE eval_runs SET status = 'cancelled' WHERE id = '...'`.

### BUG 2: Associated Job Record is Never Cleaned Up

**Severity: LOW — data hygiene issue**

When an eval_run is deleted, its associated job row stays in the `jobs` table forever. The `eval_runs.job_id → jobs.id` FK only has `ON DELETE SET NULL` (for when a *job* is deleted, the eval_run's FK becomes NULL). There's no reverse cleanup.

Over time, the `jobs` table accumulates orphaned rows with no eval_run pointing to them. This isn't a functional bug but wastes DB space and could confuse admin queries.

### BUG 3: Error During Delete Replaces Entire RunList

**Severity: MEDIUM — poor UX**

In RunList, both `handleDelete` (batch) and `handleDeleteCustom` (custom) set `setError(e.message)` on failure. The error state replaces the entire RunList with an error banner:

```typescript
if (error) {
  return (
    <div className="bg-[var(--surface-error)] ...">
      Failed to load runs: {error}
    </div>
  );
}
```

A single failed delete wipes out the entire list view. The user loses all context and has to refresh the page. A toast notification would be more appropriate for transient errors.

### BUG 4: Raw Error Message Shown for 404 on Deleted Run

**Severity: LOW — poor UX**

Navigating to a deleted run's URL shows:
```
API error 404: Not Found
```

This is the raw `ApiError` message from `client.ts`. There's no:
- User-friendly "Run not found" message
- Link back to the runs list
- Automatic redirect to RunList

### BUG 5: RunCard Batch Delete Doesn't Reset `deleting` State on Success

**Severity: LOW — cosmetic, masked by list re-render**

**RunCard.tsx, line 30-35:**
```typescript
function handleDeleteConfirm() {
  if (!onDelete) return;
  setDeleting(true);
  setConfirmDelete(false);
  onDelete(run.run_id);  // Async — no await, no finally
}
```

`onDelete` is called but not awaited. `setDeleting(true)` is never reset to `false`. The card shows "Deleting…" state indefinitely until the parent's `setRuns(prev.filter(...))` causes the RunCard to unmount. This works in practice because the parent removes the card from the list, but if the delete API fails, the RunCard stays in a permanently "deleting" state (button disabled, showing "Deleting…"). The parent's error handler doesn't notify the child RunCard of the failure.

### BUG 6: No Confirmation for Batch Delete in RunList via handleDelete

**Severity: N/A — actually handled, but confusing code path**

The batch delete path goes: RunCard click → RunCard ConfirmDialog → RunCard `handleDeleteConfirm` → parent `handleDelete(runId)`. The confirmation IS shown (via RunCard's own ConfirmDialog). However, the `handleDelete` callback in RunList is a simple async function with no loading state management — it relies entirely on RunCard's local state for UI feedback. This coupling is fragile.

### ISSUE 7: Two Identical Delete Functions in evalRunsApi.ts

**Severity: NONE — code smell**

```typescript
export async function deleteEvalRun(runId) { ... }  // Line 41
export async function deleteRun(runId) { ... }       // Line 86
```

Both call `DELETE /api/eval-runs/${runId}`. Legacy naming from migration phases. Not a bug, just dead weight.

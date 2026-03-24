# Inside Sales Eval Pipeline — UX Improvements Design

**Date:** 2026-03-24
**Scope:** 5 targeted UX improvements to the inside sales evaluation pipeline
**Principle:** Homogenous patterns across the platform; no new abstractions beyond what is required

---

## Context

The inside sales pipeline has a complete backend evaluation stack (runner, job handler, seed evaluators) but several frontend UX gaps compared to the VoiceRx and Kaira pipelines. This spec covers 5 improvements in dependency order.

---

## Item 5 — Score Utility (Foundation)

### Problem
`scoreColor(score)` and `getScoreBand(score)` are defined inline in `InsideSalesRunDetail.tsx` and duplicated in `InsideSalesRunList.tsx`. Different threshold constants (80/65 in run list, 8/5 in call detail for a 0–15 scale).

### Design
Create `src/utils/scoreUtils.ts`:

```typescript
// Accepts 0–100 scores. Thresholds: 80+ green, 65+ amber, else red.
export function scoreColor(score: number | null): string
export function getScoreBand(score: number | null): string  // "Strong" | "Good" | "Needs work" | "Poor" | "Unknown"
```

- Input is always treated as 0–100 (inside sales rubric produces 0–100 scores)
- Remove the named `scoreColor` / `getScoreBand` definitions from `InsideSalesRunDetail.tsx`; import from here
- In `InsideSalesRunList.tsx`, `scoreColor` is not a named function — it is an inline ternary inside `getScore()` (line 85: `rounded >= 80 ? ... : rounded >= 65 ? ...`). Replace that ternary with a call to `scoreColor(rounded)`. `getScoreBand` is absent from this file entirely — only add an import if it gets used
- No behaviour change — same 80/65 thresholds

### Files Touched
- **New:** `src/utils/scoreUtils.ts`
- **Edit:** `src/features/insideSales/pages/InsideSalesRunDetail.tsx` (remove inline, import)
- **Edit:** `src/features/insideSales/pages/InsideSalesRunList.tsx` (remove inline, import)

---

## Item 4 — Disabled Evaluate Button Tooltip

### Problem
The Evaluate button on `InsideSalesCallDetail` is disabled for missed calls and calls without recordings, but gives no feedback on why.

### Design
Wrap the `Button` in a `<span>` when disabled, carrying the `title` attribute (native `title` is suppressed on disabled elements).

```tsx
const disabledReason = !isAnswered
  ? 'Cannot evaluate missed calls'
  : !call.recordingUrl
  ? 'No recording available'
  : undefined;

// Render:
<span title={disabledReason} className={disabledReason ? 'cursor-not-allowed' : undefined}>
  <Button size="sm" disabled={!!disabledReason} onClick={() => setEvalOpen(true)}>
    Evaluate
  </Button>
</span>
```

**Note:** The existing `InsideSalesCallDetail.tsx` has `evalOpen` state declared after the `if (!call) return` guard. This violates React's Rules of Hooks and must be fixed as part of the Item 4 touch — move all `useState` / `useCallback` / `useEffect` declarations above the early return.

### Files Touched
- **Edit:** `src/features/insideSales/pages/InsideSalesCallDetail.tsx`

---

## Item 3 — Run List Status Filter

### Problem
`InsideSalesRunList` has only a search box. No status filter, no debounced search, no delete confirmation, and a shimmer flicker on poll updates.

### Design
Port the VoiceRx pattern directly:

**Status filter chips** (same layout as `VoiceRxRunList`):
```
All · Running · Completed · Failed · Cancelled
```
No type filter — inside sales has one eval type.

**Search:** wrap `searchQuery` in `useDebouncedValue(searchQuery, 300)` before filtering.

**Shimmer fix:** use `useStableEvalRunUpdate(setRuns)` instead of `setRuns` directly in `loadRuns`. This prevents list flicker on poll.

**Delete confirmation:** replace the direct `deleteEvalRun` call with a `ConfirmDialog` (already used in VoiceRx). State: `deleteTarget: EvalRun | null`.

**Filtering logic** (client-side, same as VoiceRx):
```typescript
// Status: match run.status, with 'partial' mapping to 'completed_with_errors'
// Search: run name (from config.run_name) or run.id
```

### Files Touched
- **Edit:** `src/features/insideSales/pages/InsideSalesRunList.tsx`
- Imports: `useStableEvalRunUpdate`, `useDebouncedValue` from `@/features/evalRuns/hooks`; `ConfirmDialog` from `@/components/ui`

---

## Item 2 — Eval Status Column on Listing

### Problem
The calls listing has no signal on whether a call has been evaluated. The `evalStatus` filter exists in the store but has no data backing it.

### Design

#### Backend — `backend/app/routes/inside_sales.py`

After `final_calls` is assembled, extract `activity_ids` and run a single batch query:

```python
from sqlalchemy import select, func
from app.models.eval_run import ThreadEvaluation, EvalRun

activity_ids = [c["activityId"] for c in final_calls]

# Latest ThreadEvaluation per thread_id for this tenant/user/app
subq = (
    select(
        ThreadEvaluation.thread_id,
        func.max(ThreadEvaluation.id).label("latest_id"),
        func.count(ThreadEvaluation.id).label("eval_count"),
    )
    .join(EvalRun, ThreadEvaluation.run_id == EvalRun.id)
    .where(
        ThreadEvaluation.thread_id.in_(activity_ids),
        EvalRun.tenant_id == auth.tenant_id,
        EvalRun.user_id == auth.user_id,
        EvalRun.app_id == "inside-sales",
        EvalRun.status == "completed",
    )
    .group_by(ThreadEvaluation.thread_id)
    .subquery()
)

result = await db.execute(
    select(ThreadEvaluation, subq.c.eval_count)
    .join(subq, ThreadEvaluation.id == subq.c.latest_id)
)
rows = result.all()
```

Rows are `(ThreadEvaluation instance, eval_count int)` tuples — unpack explicitly:
```python
eval_map: dict[str, dict] = {}
for te, count in rows:
    raw = te.result or {}
    evals = raw.get("evaluations") or []
    score = None
    if evals:
        out = evals[0].get("output") or {}
        score = out.get("overall_score")           # primary path
        if score is None:
            score = raw.get("output", {}).get("overall_score")  # fallback
    eval_map[te.thread_id] = {"score": score, "count": count}
```

Merge into `final_calls` before constructing `CallRecord` objects:
```python
for call in final_calls:
    info = eval_map.get(call["activityId"], {})
    call["lastEvalScore"] = info.get("score")
    call["evalCount"] = info.get("count", 0)
```

Note: `final_calls` and `db` are already defined in the existing route — no signature changes needed.

#### Schema — `backend/app/schemas/inside_sales.py`

Add to `CallRecord`:
```python
last_eval_score: Optional[float] = None
eval_count: int = 0
```

#### Frontend Store — `src/stores/insideSalesStore.ts`

Add to `CallRecord` interface:
```typescript
lastEvalScore?: number;
evalCount?: number;
```

#### Frontend Listing — `src/features/insideSales/pages/InsideSalesListing.tsx`

Add "Score" column to the table (between Duration and Direction):
```tsx
<th>Score</th>
// ...
<td>
  {call.evalCount && call.evalCount > 0 ? (
    <span style={{ color: scoreColor(call.lastEvalScore ?? null) }} className="text-xs font-mono font-semibold">
      {call.lastEvalScore !== null && call.lastEvalScore !== undefined
        ? Math.round(call.lastEvalScore)
        : '—'}
    </span>
  ) : (
    <span className="text-[var(--text-muted)] text-xs">—</span>
  )}
</td>
```

Uses `scoreColor` from `scoreUtils.ts` (Item 5).

### Files Touched
- **Edit:** `backend/app/routes/inside_sales.py`
- **Edit:** `backend/app/schemas/inside_sales.py`
- **Edit:** `src/stores/insideSalesStore.ts`
- **Edit:** `src/features/insideSales/pages/InsideSalesListing.tsx`

---

## Item 1 — Unified Call Detail with Eval History

### Problem
`InsideSalesCallDetail` (reached from the listing) always shows empty "not yet evaluated" states even after a call has been evaluated. The `CallEvalDetail` rendering logic (transcript + scorecard) is locked inside `InsideSalesRunDetail.tsx` as a nested component.

### Design

#### Step 1 — Extract `CallResultPanel`

Create `src/features/insideSales/components/CallResultPanel.tsx`.

Extracted from `CallEvalDetail` in `InsideSalesRunDetail.tsx`. Takes a single `thread: ThreadEvalRow` prop. Renders the split-pane layout: transcript on the left, scorecard/compliance tabs on the right. No breadcrumb, no run context, no sibling navigation — those stay in `CallEvalDetail`.

```typescript
interface CallResultPanelProps {
  thread: ThreadEvalRow;
}
```

`CallEvalDetail` in `InsideSalesRunDetail.tsx` is updated to use `<CallResultPanel thread={thread} />` for the content area, keeping its own breadcrumb, summary bar, and sibling navigator.

#### Step 2 — Update `InsideSalesCallDetail`

On mount (when `call` is available), call `fetchThreadHistory(call.activityId)`. This hits the existing `GET /api/threads/{thread_id}/history` endpoint — no backend work needed.

```typescript
const [evalHistory, setEvalHistory] = useState<ThreadEvalRow[]>([]);
const [evalIdx, setEvalIdx] = useState(0);        // 0 = most recent
const [evalLoading, setEvalLoading] = useState(false);

// fetchThreadHistory returns { thread_id, history: ThreadEvalRow[], total }
useEffect(() => {
  if (!call?.activityId) return;
  setEvalLoading(true);
  fetchThreadHistory(call.activityId)
    .then((r) => setEvalHistory(r.history))
    .catch(() => { /* supplemental — silent fail */ })
    .finally(() => setEvalLoading(false));
}, [call?.activityId]);
```

**Run selector** — shown only when `evalHistory.length > 0`, rendered above the Tabs:

```
[←]  Run 2 of 3 · 24 Mar, 2:15 PM  [→]
```

- Left arrow: `evalIdx < evalHistory.length - 1` → increment (older)
- Right arrow: `evalIdx > 0` → decrement (newer)
- Muted timestamp from `evalHistory[evalIdx].created_at`
- Same inline-flex style as the sibling navigator in `CallEvalDetail`

**Tab content:**
- If `evalHistory.length === 0`: existing empty states unchanged
- If `evalHistory.length > 0`: `<CallResultPanel thread={evalHistory[evalIdx]} />`

**Reset on call change:** `useEffect(() => setEvalIdx(0), [call?.activityId])`

#### Step 3 — Delete `ScorecardTab.tsx`

`src/features/insideSales/components/ScorecardTab.tsx` is unreferenced. Delete it.

### Files Touched
- **New:** `src/features/insideSales/components/CallResultPanel.tsx`
- **Edit:** `src/features/insideSales/pages/InsideSalesCallDetail.tsx`
- **Edit:** `src/features/insideSales/pages/InsideSalesRunDetail.tsx` (use `CallResultPanel`, import `scoreColor`/`getScoreBand` from scoreUtils)
- **Delete:** `src/features/insideSales/components/ScorecardTab.tsx`

#### Extraction boundary for `CallResultPanel`

The content that moves into `CallResultPanel` is everything inside the split-pane container: the `<div className="hidden md:flex flex-1 min-h-0">` block (transcript left pane + tab right pane) and the mobile stacked fallback below it.

What stays in `CallEvalDetail`: the outer `flex flex-col` wrapper, the header row (breadcrumb + sibling navigator), and the summary bar (score/verdict/compliance/agent/duration pills).

`CallResultPanel` props:
```typescript
interface CallResultPanelProps {
  thread: ThreadEvalRow;
}
```
It has no run context, no navigation, no side effects.

#### Dimension-bar color inside `CallResultPanel`

The per-dimension score bars use a **different scale** (0–15 per dimension) with inline thresholds (`score >= 8` → green, `score >= 5` → amber). This is intentionally **not** replaced by `scoreColor()` from `scoreUtils`. Leave the inline ternary as-is inside `CallResultPanel`. `scoreColor()` is only used for the overall 0–100 score.

#### Pre-existing `evalStatus` / `scoreMin` / `scoreMax` filters

These filter fields exist in the store and are counted in `activeFilterCount` but have no backend support. They are **out of scope** for this spec — do not wire or remove them.

---

## Implementation Order

| Step | Item | Why |
|------|------|-----|
| 1 | Item 5 — Score utility | Blocks items 1, 2, 3 (all import from it) |
| 2 | Item 4 — Tooltip | Independent, trivial |
| 3 | Item 3 — Run list filter | Frontend-only, independent of backend changes |
| 4 | Item 2 — Eval status on listing | Backend + frontend; self-contained |
| 5 | Item 1 — Unified call detail | Most complex; builds on Item 5 |

---

## Invariants & Constraints

- All backend queries filter by `tenant_id` + `user_id` from `AuthContext` — no exceptions
- No raw `fetch` in frontend — all API calls via `apiRequest` from `client.ts`
- No direct `console.log` — use `logger` / `notificationService` where feedback is needed
- `scoreUtils.ts` uses the 80/65 thresholds already established in `InsideSalesRunDetail` — do not change thresholds
- `CallResultPanel` must be a pure display component — no data fetching, no side effects
- The `GET /api/threads/{thread_id}/history` endpoint already filters by `tenant_id` + `user_id` — no additional auth work needed
- Do not change the `ThreadEvaluation` schema or add columns — score extraction happens in Python from the `result` JSON
- `InsideSalesCallDetail` note: the file was recently updated to include lead data fetching (`fetchLead`, `leadData` state) — the plan must not revert or conflict with those additions

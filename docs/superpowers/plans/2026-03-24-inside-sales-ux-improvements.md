# Inside Sales UX Improvements — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Five targeted UX improvements to the inside sales evaluation pipeline: score utility, disabled-button tooltip, run list status filter, eval status on the calls listing, and unified call detail with full eval history.

**Architecture:** Tasks 1–3 are pure frontend. Task 4 adds a batch DB query to the backend listing endpoint and a new column to the frontend table. Task 5 extracts a `CallResultPanel` component and wires `InsideSalesCallDetail` to display eval history fetched via the existing `/api/threads/{thread_id}/history` endpoint.

**Tech Stack:** React 18, TypeScript strict, Zustand, FastAPI + SQLAlchemy async, PostgreSQL. Tailwind v4 via `cn()`. No test infrastructure exists — verify with `npx tsc -b --noEmit` and manual UI inspection.

---

## File Map

| File | Action | Task |
|------|--------|------|
| `src/utils/scoreUtils.ts` | **Create** | 1 |
| `src/features/insideSales/pages/InsideSalesRunDetail.tsx` | Modify (remove inline fns, import scoreUtils) | 1 |
| `src/features/insideSales/pages/InsideSalesRunList.tsx` | Modify (inline ternary → scoreColor import) | 1 |
| `src/features/insideSales/pages/InsideSalesCallDetail.tsx` | Modify (fix hook order, tooltip) | 2 |
| `src/features/insideSales/pages/InsideSalesRunList.tsx` | Modify (status filter, debounce, shimmer, confirm) | 3 |
| `backend/app/routes/inside_sales.py` | Modify (batch eval-status query) | 4 |
| `backend/app/schemas/inside_sales.py` | Modify (add lastEvalScore, evalCount) | 4 |
| `src/stores/insideSalesStore.ts` | Modify (CallRecord interface) | 4 |
| `src/features/insideSales/pages/InsideSalesListing.tsx` | Modify (Score column) | 4 |
| `src/features/insideSales/components/CallResultPanel.tsx` | **Create** | 5 |
| `src/features/insideSales/pages/InsideSalesRunDetail.tsx` | Modify (use CallResultPanel) | 5 |
| `src/features/insideSales/pages/InsideSalesCallDetail.tsx` | Modify (eval history, run selector) | 5 |
| `src/features/insideSales/components/ScorecardTab.tsx` | **Delete** | 5 |

---

## Task 1: Score Utility

**Files:**
- Create: `src/utils/scoreUtils.ts`
- Modify: `src/features/insideSales/pages/InsideSalesRunDetail.tsx`
- Modify: `src/features/insideSales/pages/InsideSalesRunList.tsx`

- [ ] **Step 1.1 — Create `scoreUtils.ts`**

```typescript
// src/utils/scoreUtils.ts

/** Color for a 0–100 overall score. */
export function scoreColor(score: number | null): string {
  if (score === null) return 'var(--text-muted)';
  if (score >= 80) return 'var(--color-success)';
  if (score >= 65) return 'var(--color-warning)';
  return 'var(--color-error)';
}

/** Text band label for a 0–100 overall score. */
export function getScoreBand(score: number | null): string {
  if (score === null) return 'Unknown';
  if (score >= 80) return 'Strong';
  if (score >= 65) return 'Good';
  if (score >= 50) return 'Needs work';
  return 'Poor';
}
```

- [ ] **Step 1.2 — Update `InsideSalesRunDetail.tsx`**

Remove the two named function definitions at lines 58–71:
```typescript
// DELETE these two functions:
function getScoreBand(score: number | null): string { ... }  // lines 58-64
function scoreColor(score: number | null): string { ... }    // lines 66-71
```

Add this import after the existing `@/` imports:
```typescript
import { scoreColor, getScoreBand } from '@/utils/scoreUtils';
```

- [ ] **Step 1.3 — Update `InsideSalesRunList.tsx`**

In `getScore()` (around line 85), replace the inline ternary:
```typescript
// BEFORE:
const color = rounded >= 80 ? 'var(--color-success)' : rounded >= 65 ? 'var(--color-warning)' : 'var(--color-error)';

// AFTER:
const color = scoreColor(rounded);
```

Add import:
```typescript
import { scoreColor } from '@/utils/scoreUtils';
```

- [ ] **Step 1.4 — Typecheck**

```bash
npx tsc -b --noEmit
```
Expected: no errors.

- [ ] **Step 1.5 — Commit**

```bash
git add src/utils/scoreUtils.ts src/features/insideSales/pages/InsideSalesRunDetail.tsx src/features/insideSales/pages/InsideSalesRunList.tsx
git commit -m "refactor: extract scoreColor/getScoreBand into scoreUtils utility"
```

---

## Task 2: Disabled Evaluate Button Tooltip + Fix Hook Order

**Files:**
- Modify: `src/features/insideSales/pages/InsideSalesCallDetail.tsx`

The current file has `const [evalOpen, setEvalOpen] = useState(false)` at line 110, which is **after** the `if (!call) return` guard at line 86. This is a React Rules of Hooks violation. Fix it as part of this task.

- [ ] **Step 2.1 — Move `evalOpen` state above the early return**

Move line 110 (`const [evalOpen, setEvalOpen] = useState(false);`) up to join the other `useState` declarations at lines 62–63.

The hooks block should read (in order):
```typescript
const [leadData, setLeadData] = useState<LeadDetail | null>(null);
const [leadLoading, setLeadLoading] = useState(false);
const [evalOpen, setEvalOpen] = useState(false);

const fetchLead = useCallback(...);
useEffect(...);

if (!call) return (...);   // early return — all hooks above this line
```

- [ ] **Step 2.2 — Add `disabledReason` and wrap the button**

After the existing `canEvaluate` line (currently line 114), add:
```typescript
const disabledReason = !isAnswered
  ? 'Cannot evaluate missed calls'
  : !call.recordingUrl
  ? 'No recording available'
  : undefined;
```

Replace the `<Button>` render (currently line 228) with:
```tsx
<span title={disabledReason} className={disabledReason ? 'cursor-not-allowed' : undefined}>
  <Button size="sm" disabled={!!disabledReason} onClick={() => setEvalOpen(true)}>
    Evaluate
  </Button>
</span>
```

Remove the now-redundant `canEvaluate` const (it's replaced by `disabledReason`).

- [ ] **Step 2.3 — Typecheck**

```bash
npx tsc -b --noEmit
```
Expected: no errors.

- [ ] **Step 2.4 — Verify manually**

Navigate to a missed call → button shows tooltip "Cannot evaluate missed calls".
Navigate to an answered call with recording → button is enabled.

- [ ] **Step 2.5 — Commit**

```bash
git add src/features/insideSales/pages/InsideSalesCallDetail.tsx
git commit -m "fix: move evalOpen hook above early return; add tooltip to disabled Evaluate button"
```

---

## Task 3: Run List Status Filter

**Files:**
- Modify: `src/features/insideSales/pages/InsideSalesRunList.tsx`

Port the VoiceRx pattern. Add status filter chips, debounced search, shimmer fix, and delete confirmation.

- [ ] **Step 3.1 — Add new imports**

```typescript
import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useStableEvalRunUpdate, useDebouncedValue } from '@/features/evalRuns/hooks';
import { ConfirmDialog } from '@/components/ui';
import { scoreColor } from '@/utils/scoreUtils';
```

Remove `scoreColor` inline usage — it's now imported (Task 1 already did this).

- [ ] **Step 3.2 — Add STATUS_FILTERS constant and new state**

Add above the component function:
```typescript
const STATUS_FILTERS: Array<{ key: string; label: string; dotColor?: string }> = [
  { key: 'all', label: 'All' },
  { key: 'running', label: 'Running', dotColor: 'var(--color-info)' },
  { key: 'completed', label: 'Completed', dotColor: 'var(--color-success)' },
  { key: 'partial', label: 'Partial', dotColor: 'var(--color-warning)' },
  { key: 'failed', label: 'Failed', dotColor: 'var(--color-error)' },
  { key: 'cancelled', label: 'Cancelled', dotColor: 'var(--color-warning)' },
];
```

Add to component state:
```typescript
const [statusFilter, setStatusFilter] = useState('all');
const [deleteTarget, setDeleteTarget] = useState<EvalRun | null>(null);
const [isDeleting, setIsDeleting] = useState(false);
const isInitialLoad = useRef(true);
const debouncedSearch = useDebouncedValue(searchQuery, 300);
const stableSetRuns = useStableEvalRunUpdate(setRuns);
```

- [ ] **Step 3.3 — Update `loadRuns` to use shimmer fix**

```typescript
const loadRuns = useCallback(() => {
  if (isInitialLoad.current) setIsLoading(true);
  fetchEvalRuns({ app_id: 'inside-sales' })
    .then(stableSetRuns)
    .catch(() => {})
    .finally(() => {
      setIsLoading(false);
      isInitialLoad.current = false;
    });
}, [stableSetRuns]);
```

- [ ] **Step 3.4 — Update `filteredRuns` to include status filter**

```typescript
const filteredRuns = useMemo(() => {
  let result = runs;

  // Status filter — 'partial' maps to 'completed_with_errors'
  if (statusFilter !== 'all') {
    result = result.filter((r) => {
      if (statusFilter === 'partial') return r.status === 'completed_with_errors';
      return r.status === statusFilter;
    });
  }

  // Debounced search on run name or id
  const q = debouncedSearch.toLowerCase().trim();
  if (q) {
    result = result.filter((r) => {
      const config = r.config as Record<string, unknown> | undefined;
      const name = (config?.run_name as string) || r.evalType || '';
      return name.toLowerCase().includes(q) || r.id.includes(q);
    });
  }

  return result;
}, [runs, statusFilter, debouncedSearch]);
```

Also add a `useEffect` to reset page when filters change (if pagination is later added):
```typescript
// Reset-friendly: no pagination yet, but keep the pattern
useEffect(() => { /* reserved */ }, [statusFilter, debouncedSearch]);
```

- [ ] **Step 3.5 — Replace delete handler to use confirmation**

```typescript
const handleDeleteConfirmed = useCallback(async () => {
  if (!deleteTarget) return;
  setIsDeleting(true);
  try {
    await deleteEvalRun(deleteTarget.id);
    notificationService.success('Run deleted');
    loadRuns();
  } catch {
    notificationService.error('Delete failed');
  } finally {
    setIsDeleting(false);
    setDeleteTarget(null);
  }
}, [deleteTarget, loadRuns]);
```

Update `RunRowCard` `onDelete` to set target instead of deleting immediately:
```typescript
onDelete={() => setDeleteTarget(run)}
```

- [ ] **Step 3.6 — Add filter chips UI**

Add between the search input and the runs list:
```tsx
{/* Status filter chips */}
<div className="flex items-center gap-1.5 mb-3 flex-wrap">
  {STATUS_FILTERS.map((f) => (
    <button
      key={f.key}
      onClick={() => setStatusFilter(f.key)}
      className={cn(
        'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium transition-colors border',
        statusFilter === f.key
          ? 'border-[var(--color-brand-accent)] bg-[var(--color-brand-accent)]/10 text-[var(--text-brand)]'
          : 'border-[var(--border-default)] text-[var(--text-muted)] hover:border-[var(--border-brand)] hover:text-[var(--text-primary)]'
      )}
    >
      {f.dotColor && (
        <span
          className="inline-block h-1.5 w-1.5 rounded-full"
          style={{ background: f.dotColor }}
        />
      )}
      {f.label}
    </button>
  ))}
</div>
```

- [ ] **Step 3.7 — Add `ConfirmDialog` at the end of the return**

```tsx
<ConfirmDialog
  open={!!deleteTarget}
  title="Delete run"
  message={`Delete "${deleteTarget ? ((deleteTarget.config as Record<string,unknown>)?.run_name as string) ?? deleteTarget.id.slice(0, 8) : ''}"? This cannot be undone.`}
  confirmLabel="Delete"
  onConfirm={handleDeleteConfirmed}
  onCancel={() => setDeleteTarget(null)}
  isLoading={isDeleting}
/>
```

- [ ] **Step 3.8 — Typecheck**

```bash
npx tsc -b --noEmit
```
Expected: no errors.

- [ ] **Step 3.9 — Verify manually**

Open Runs page → filter chips appear → clicking "Running" filters list → clicking "Failed" filters list → delete button shows confirmation dialog before deleting.

- [ ] **Step 3.10 — Commit**

```bash
git add src/features/insideSales/pages/InsideSalesRunList.tsx
git commit -m "feat: add status filter, debounced search, shimmer fix, and delete confirmation to run list"
```

---

## Task 4: Eval Status Column on Calls Listing

**Files:**
- Modify: `backend/app/routes/inside_sales.py`
- Modify: `backend/app/schemas/inside_sales.py`
- Modify: `src/stores/insideSalesStore.ts`
- Modify: `src/features/insideSales/pages/InsideSalesListing.tsx`

- [ ] **Step 4.1 — Add eval status fields to schema**

In `backend/app/schemas/inside_sales.py`, update `CallRecord`:
```python
from typing import Optional
# (already imported)

class CallRecord(CamelModel):
    activity_id: str
    prospect_id: str
    agent_name: str
    agent_email: str
    event_code: int
    direction: str
    status: str
    call_start_time: str
    duration_seconds: int
    recording_url: str
    phone_number: str
    display_number: str
    call_notes: str
    call_session_id: str
    created_on: str
    lead_name: str
    # eval status — null/0 if never evaluated
    last_eval_score: Optional[float] = None
    eval_count: int = 0
```

- [ ] **Step 4.2 — Add batch eval-status query to backend route**

In `backend/app/routes/inside_sales.py`, add imports at the top:
```python
from sqlalchemy import select, func, desc
from app.models.eval_run import ThreadEvaluation, EvalRun as EvalRunModel
```

After the block that assembles `final_calls` (after the `await cache_calls(...)` call, before the `return CallListResponse(...)`), add:

```python
    # ── Batch eval status lookup ──────────────────────────────────────────
    if final_calls:
        activity_ids = [c["activityId"] for c in final_calls]

        # Subquery: latest ThreadEvaluation id + count per thread_id
        subq = (
            select(
                ThreadEvaluation.thread_id,
                func.max(ThreadEvaluation.id).label("latest_id"),
                func.count(ThreadEvaluation.id).label("eval_count"),
            )
            .join(EvalRunModel, ThreadEvaluation.run_id == EvalRunModel.id)
            .where(
                ThreadEvaluation.thread_id.in_(activity_ids),
                EvalRunModel.tenant_id == auth.tenant_id,
                EvalRunModel.user_id == auth.user_id,
                EvalRunModel.app_id == "inside-sales",
                EvalRunModel.status == "completed",
            )
            .group_by(ThreadEvaluation.thread_id)
            .subquery()
        )

        eval_rows = await db.execute(
            select(ThreadEvaluation, subq.c.eval_count)
            .join(subq, ThreadEvaluation.id == subq.c.latest_id)
        )

        eval_map: dict[str, dict] = {}
        for te, count in eval_rows.all():
            raw = te.result or {}
            evals = raw.get("evaluations") or []
            score = None
            if evals:
                out = evals[0].get("output") or {}
                score = out.get("overall_score")
                if score is None:
                    score = raw.get("output", {}).get("overall_score")
            eval_map[te.thread_id] = {"score": score, "count": int(count)}

        for call in final_calls:
            info = eval_map.get(call["activityId"], {})
            call["lastEvalScore"] = info.get("score")
            call["evalCount"] = info.get("count", 0)
```

- [ ] **Step 4.3 — Update frontend `CallRecord` type in store**

In `src/stores/insideSalesStore.ts`, update the `CallRecord` interface:
```typescript
export interface CallRecord {
  activityId: string;
  prospectId: string;
  agentName: string;
  agentEmail: string;
  eventCode: number;
  direction: string;
  status: string;
  callStartTime: string;
  durationSeconds: number;
  recordingUrl: string;
  phoneNumber: string;
  displayNumber: string;
  callNotes: string;
  callSessionId: string;
  createdOn: string;
  leadName: string;
  lastEvalScore?: number;   // add
  evalCount?: number;        // add
}
```

- [ ] **Step 4.4 — Add Score column to listing table**

In `src/features/insideSales/pages/InsideSalesListing.tsx`, add import:
```typescript
import { scoreColor } from '@/utils/scoreUtils';
```

In the `<thead>`, add a header between Duration and Direction:
```tsx
<th className="px-3 py-2 text-left font-medium text-[var(--text-secondary)]">Score</th>
```

In the `<tbody>` row mapping, add a cell in the same position:
```tsx
<td className="px-3 py-2.5 text-center">
  {call.evalCount && call.evalCount > 0 ? (
    <span
      className="text-xs font-bold font-mono tabular-nums"
      style={{ color: scoreColor(call.lastEvalScore ?? null) }}
    >
      {call.lastEvalScore != null ? Math.round(call.lastEvalScore) : '—'}
    </span>
  ) : (
    <span className="text-[var(--text-muted)] text-xs">—</span>
  )}
</td>
```

- [ ] **Step 4.5 — Typecheck**

```bash
npx tsc -b --noEmit
```
Expected: no errors.

- [ ] **Step 4.6 — Verify manually**

Restart backend: `docker compose up --build backend`.
Open the calls listing. Calls that have been evaluated show a colored score; unevaluated calls show `—`.

- [ ] **Step 4.7 — Commit**

```bash
git add backend/app/routes/inside_sales.py backend/app/schemas/inside_sales.py src/stores/insideSalesStore.ts src/features/insideSales/pages/InsideSalesListing.tsx
git commit -m "feat: add eval status score column to calls listing"
```

---

## Task 5: Unified Call Detail with Eval History

**Files:**
- Create: `src/features/insideSales/components/CallResultPanel.tsx`
- Modify: `src/features/insideSales/pages/InsideSalesRunDetail.tsx`
- Modify: `src/features/insideSales/pages/InsideSalesCallDetail.tsx`
- Delete: `src/features/insideSales/components/ScorecardTab.tsx`

### Step 5.1 — Create `CallResultPanel.tsx`

This component owns the transcript + scorecard/compliance rendering. It is extracted from `CallEvalDetail` in `InsideSalesRunDetail.tsx` (the content inside the outer split-pane container: lines 488–655 of `InsideSalesRunDetail.tsx`).

**Important:** The per-dimension progress bar color uses 0–15 scale thresholds (`score >= 8` → green, `score >= 5` → amber). This is intentionally **not** replaced by `scoreColor()` — leave it as-is.

- [ ] **Step 5.1.1 — Create the file**

```typescript
// src/features/insideSales/components/CallResultPanel.tsx
import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { cn } from '@/utils';
import { scoreColor } from '@/utils/scoreUtils';
import type { ThreadEvalRow } from '@/types';

interface CallResultPanelProps {
  thread: ThreadEvalRow;
}

export function CallResultPanel({ thread }: CallResultPanelProps) {
  const [activeTab, setActiveTab] = useState<'scorecard' | 'compliance'>('scorecard');

  const result = thread.result as unknown as Record<string, unknown> | undefined;
  const evals = result?.evaluations as Array<Record<string, unknown>> | undefined;
  const evalOutput = evals?.[0]?.output as Record<string, unknown> | undefined;
  const reasoning = evalOutput?.reasoning as string | undefined;
  const transcript = result?.transcript as string | undefined;

  const overallScore: number | null = (() => {
    if (evalOutput && typeof evalOutput.overall_score === 'number') return evalOutput.overall_score;
    const out = result?.output as Record<string, unknown> | undefined;
    if (out && typeof out.overall_score === 'number') return out.overall_score;
    return null;
  })();

  // Dimension scores: numeric fields excluding overall_score and reasoning
  const dimensions = evalOutput
    ? Object.entries(evalOutput).filter(
        ([k, v]) => typeof v === 'number' && k !== 'overall_score'
      )
    : [];

  // Compliance gates: boolean fields
  const complianceGates = evalOutput
    ? Object.entries(evalOutput).filter(([, v]) => typeof v === 'boolean')
    : [];

  return (
    <>
      {/* Desktop: split pane */}
      <div className="hidden md:flex flex-1 min-h-0">
        {/* Left: transcript */}
        <div className="w-[35%] min-w-[280px] max-w-[420px] flex flex-col min-h-0 border-r border-[var(--border-subtle)]">
          <div className="px-3 py-2 border-b border-[var(--border-subtle)] text-xs font-semibold text-[var(--text-muted)] uppercase">
            Transcript
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto px-3 py-2">
            {transcript ? (
              <div className="text-xs text-[var(--text-secondary)] whitespace-pre-wrap leading-relaxed font-mono">
                {transcript}
              </div>
            ) : (
              <p className="text-xs text-[var(--text-muted)] py-4 text-center">No transcript available.</p>
            )}
          </div>
        </div>

        {/* Right: tabs */}
        <div className="flex-1 min-w-0 flex flex-col min-h-0">
          <div className="flex border-b border-[var(--border-subtle)]">
            {(['scorecard', 'compliance'] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={cn(
                  'px-4 py-2 text-xs font-semibold transition-colors border-b-2',
                  activeTab === tab
                    ? 'border-[var(--interactive-primary)] text-[var(--text-brand)]'
                    : 'border-transparent text-[var(--text-muted)] hover:text-[var(--text-primary)]'
                )}
              >
                {tab === 'scorecard' ? 'Scorecard' : 'Compliance'}
              </button>
            ))}
          </div>

          <div className="flex-1 min-h-0 overflow-y-auto px-4 py-3">
            {activeTab === 'scorecard' && (
              <div className="space-y-0">
                {dimensions.map(([key, val]) => {
                  const label = key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
                  const score = val as number;
                  // Per-dimension bars use 0-15 scale thresholds intentionally
                  const pctVal = Math.min(100, Math.max(0, score * 100 / (score <= 15 ? 15 : 100)));
                  return (
                    <div key={key} className="flex items-center gap-2 py-2 border-b border-[var(--border-subtle)] last:border-b-0">
                      <span className="text-xs text-[var(--text-primary)] w-[45%] shrink-0">{label}</span>
                      <div className="flex-1 h-2 rounded-full bg-[var(--bg-tertiary)] overflow-hidden">
                        <div
                          className="h-full rounded-full"
                          style={{
                            width: `${pctVal}%`,
                            background: score >= 8 ? 'var(--color-success)' : score >= 5 ? 'var(--color-warning)' : 'var(--color-error)',
                          }}
                        />
                      </div>
                      <span className="text-xs font-bold w-12 text-right" style={{ color: scoreColor(score) }}>
                        {score}
                      </span>
                    </div>
                  );
                })}
                {overallScore !== null && (
                  <div className="flex items-center justify-between mt-3 px-3 py-2.5 bg-[var(--bg-secondary)] rounded-md border border-[var(--border-subtle)]">
                    <span className="text-[13px] font-semibold text-[var(--text-primary)]">Total</span>
                    <span className="text-lg font-bold" style={{ color: scoreColor(overallScore) }}>
                      {overallScore}/100
                    </span>
                  </div>
                )}
                {reasoning && (
                  <div className="mt-4 pt-3 border-t border-[var(--border-subtle)]">
                    <h4 className="text-xs font-semibold text-[var(--text-muted)] uppercase mb-2">Reasoning</h4>
                    <div className="text-xs text-[var(--text-secondary)] leading-relaxed prose prose-sm prose-invert max-w-none [&_strong]:text-[var(--text-primary)] [&_p]:mb-2 [&_ol]:pl-4 [&_li]:mb-1">
                      <ReactMarkdown>{reasoning}</ReactMarkdown>
                    </div>
                  </div>
                )}
              </div>
            )}

            {activeTab === 'compliance' && (
              <div>
                <div className="flex flex-wrap gap-1 pb-3">
                  <span className="px-2 py-0.5 text-xs rounded-full border border-[var(--border-brand)] bg-[var(--surface-info)] text-[var(--text-brand)]">
                    All ({complianceGates.length})
                  </span>
                  <span className="px-2 py-0.5 text-xs rounded-full border border-[var(--border-subtle)] text-[var(--text-secondary)]">
                    Violations ({complianceGates.filter(([, v]) => !v).length})
                  </span>
                  <span className="px-2 py-0.5 text-xs rounded-full border border-[var(--border-subtle)] text-[var(--text-secondary)]">
                    Passed ({complianceGates.filter(([, v]) => v).length})
                  </span>
                </div>
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-[var(--border-subtle)]">
                      <th className="text-center w-12 py-1.5 px-2 font-semibold text-[var(--text-muted)]">Status</th>
                      <th className="text-left py-1.5 px-2 font-semibold text-[var(--text-muted)]">Rule</th>
                    </tr>
                  </thead>
                  <tbody>
                    {complianceGates.map(([key, val]) => {
                      const label = key.replace(/^compliance_/, '').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
                      const passed = val as boolean;
                      return (
                        <tr key={key} className="border-b border-[var(--border-subtle)]">
                          <td className="text-center py-2 px-2">
                            <span className={cn(
                              'inline-flex items-center justify-center w-5 h-5 rounded-full text-[11px] font-bold',
                              passed ? 'bg-green-500/15 text-green-400' : 'bg-red-500/15 text-red-400'
                            )}>
                              {passed ? '✓' : '✗'}
                            </span>
                          </td>
                          <td className="py-2 px-2">
                            <span className={cn(
                              'text-[13px] font-semibold',
                              passed ? 'text-[var(--color-success)]' : 'text-[var(--color-error)]'
                            )}>
                              {label}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Mobile: stacked */}
      <div className="flex flex-col flex-1 min-h-0 md:hidden space-y-3 overflow-y-auto">
        {transcript && (
          <details className="shrink-0">
            <summary className="text-xs text-[var(--text-muted)] font-medium cursor-pointer py-1.5 px-1">
              Transcript
            </summary>
            <div className="max-h-[300px] overflow-y-auto px-2 py-1">
              <div className="text-xs text-[var(--text-secondary)] whitespace-pre-wrap leading-relaxed font-mono">
                {transcript}
              </div>
            </div>
          </details>
        )}
        {dimensions.length > 0 && (
          <div className="px-2">
            {dimensions.map(([key, val]) => {
              const label = key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
              const score = val as number;
              return (
                <div key={key} className="flex items-center justify-between py-1.5 border-b border-[var(--border-subtle)] text-xs">
                  <span className="text-[var(--text-secondary)]">{label}</span>
                  <span className="font-bold" style={{ color: scoreColor(score) }}>{score}</span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}
```

### Step 5.2 — Update `InsideSalesRunDetail.tsx` to use `CallResultPanel`

- [ ] **Step 5.2.1 — Add import**

```typescript
import { CallResultPanel } from '../components/CallResultPanel';
```

- [ ] **Step 5.2.2 — Replace split-pane + mobile content in `CallEvalDetail`**

In `CallEvalDetail`, remove everything from line 487 (`{/* Split pane: ... */}`) through line 655 (end of mobile stacked `</div>`).

Replace with:
```tsx
<CallResultPanel thread={thread} />
```

Also remove the now-unused local derivations that `CallResultPanel` handles internally: `activeTab` state, `transcript`, `evalOutput`, `dimensions`, `complianceGates` (note: keep `meta`, `overallScore`, `allPassed`, `complianceGates` for the summary bar — these are still needed in `CallEvalDetail` for rendering the pills).

Wait — `CallEvalDetail` still needs `complianceGates` and `overallScore` for the summary bar. Keep those derivations. Only the `activeTab` state and `transcript` const can be removed (since `CallResultPanel` derives them internally).

Specifically, **remove from `CallEvalDetail`**:
- `const [activeTab, setActiveTab]` (line 394)
- `const transcript = result?.transcript` (line 402)

**Keep in `CallEvalDetail`**:
- `result`, `meta`, `evals`, `evalOutput`, `reasoning` derivations (for summary bar)
- `overallScore` (for summary bar)
- `dimensions` derivation (only if used in summary bar — it's not, so remove it)
- `complianceGates` + `allPassed` (for summary bar Compliance pill)
- All navigation logic (`currentIdx`, `prevThread`, `nextThread`, `goToThread`)

After cleanup, `CallEvalDetail` renders: outer wrapper → header (breadcrumb + sibling nav) → summary bar → `<CallResultPanel thread={thread} />`.

### Step 5.3 — Update `InsideSalesCallDetail.tsx`

- [ ] **Step 5.3.1 — Add imports**

```typescript
import { fetchThreadHistory } from '@/services/api/evalRunsApi';
import { CallResultPanel } from '../components/CallResultPanel';
import type { ThreadEvalRow } from '@/types';
import { ChevronLeft, ChevronRight } from 'lucide-react';
```

- [ ] **Step 5.3.2 — Add eval history state (above the early return)**

Add alongside the other state declarations (before `if (!call) return`):
```typescript
const [evalHistory, setEvalHistory] = useState<ThreadEvalRow[]>([]);
const [evalIdx, setEvalIdx] = useState(0);
const [evalLoading, setEvalLoading] = useState(false);
```

- [ ] **Step 5.3.3 — Add `useEffect` to fetch eval history**

Add below the existing lead `useEffect`:
```typescript
useEffect(() => {
  if (!call?.activityId) return;
  setEvalIdx(0);
  setEvalLoading(true);
  fetchThreadHistory(call.activityId)
    .then((r) => setEvalHistory(r.history))
    .catch(() => { /* supplemental — silent fail */ })
    .finally(() => setEvalLoading(false));
}, [call?.activityId]);
```

- [ ] **Step 5.3.4 — Add run selector and swap tab content**

Replace the existing `transcriptTab`, `scorecardTab` definitions and the `<Tabs ...>` render with:

```tsx
{/* Eval history — run selector + result panel */}
{evalHistory.length > 0 ? (
  <div className="flex flex-col flex-1 min-h-0">
    {/* Run selector */}
    <div className="shrink-0 flex items-center justify-center gap-2 py-2 border-b border-[var(--border-subtle)]">
      <button
        disabled={evalIdx >= evalHistory.length - 1}
        onClick={() => setEvalIdx((i) => i + 1)}
        className="p-1 disabled:opacity-30 hover:bg-[var(--interactive-secondary)] rounded transition-colors disabled:cursor-default"
        title="Older evaluation"
      >
        <ChevronLeft className="h-3.5 w-3.5" />
      </button>
      <span className="text-xs text-[var(--text-secondary)] tabular-nums">
        Run {evalIdx + 1} of {evalHistory.length}
        {evalHistory[evalIdx]?.created_at && (
          <span className="text-[var(--text-muted)] ml-2">
            · {new Date(evalHistory[evalIdx].created_at).toLocaleString('en-IN', {
                day: '2-digit', month: 'short',
                hour: '2-digit', minute: '2-digit', hour12: true,
              })}
          </span>
        )}
      </span>
      <button
        disabled={evalIdx <= 0}
        onClick={() => setEvalIdx((i) => i - 1)}
        className="p-1 disabled:opacity-30 hover:bg-[var(--interactive-secondary)] rounded transition-colors disabled:cursor-default"
        title="Newer evaluation"
      >
        <ChevronRight className="h-3.5 w-3.5" />
      </button>
    </div>
    {/* Result panel */}
    <CallResultPanel thread={evalHistory[evalIdx]} />
  </div>
) : (
  /* Empty states — unchanged */
  <Tabs
    tabs={[
      {
        id: 'transcript',
        label: 'Transcript',
        content: (
          <div className="flex items-center justify-center py-16">
            <EmptyState
              icon={PhoneIcon}
              title="No transcript yet"
              description={evalLoading ? 'Checking for evaluations…' : 'Transcription will be available after evaluation.'}
              compact
            />
          </div>
        ),
      },
      {
        id: 'scorecard',
        label: 'Scorecard',
        content: (
          <div className="flex items-center justify-center py-16">
            <EmptyState
              icon={PhoneIcon}
              title="Not yet evaluated"
              description="Run an evaluation to see the scorecard."
              compact
            />
          </div>
        ),
      },
    ]}
    defaultTab="transcript"
    fillHeight
  />
)}
```

### Step 5.4 — Delete `ScorecardTab.tsx`

- [ ] **Step 5.4.1 — Delete the file**

```bash
rm src/features/insideSales/components/ScorecardTab.tsx
```

Confirm it's not imported anywhere:
```bash
grep -r "ScorecardTab" src/
```
Expected: no output.

### Step 5.5 — Typecheck and verify

- [ ] **Step 5.5.1 — Typecheck**

```bash
npx tsc -b --noEmit
```
Expected: no errors.

- [ ] **Step 5.5.2 — Verify run detail still works**

Navigate to Runs → pick a completed run → click a result row. Should show transcript on left, scorecard/compliance tabs on right. Sibling navigation (prev/next call) should work.

- [ ] **Step 5.5.3 — Verify call detail with eval history**

Navigate to Calls listing → click a call that has been evaluated. Should show:
- Run selector: "Run 1 of N · [timestamp]"
- Left/right arrows navigate between runs (older ← → newer)
- Transcript and scorecard populate from the selected run

Navigate to a call that has never been evaluated. Should show original empty state tabs.

- [ ] **Step 5.5.4 — Commit**

```bash
git add src/features/insideSales/components/CallResultPanel.tsx \
        src/features/insideSales/pages/InsideSalesRunDetail.tsx \
        src/features/insideSales/pages/InsideSalesCallDetail.tsx
git rm src/features/insideSales/components/ScorecardTab.tsx
git commit -m "feat: extract CallResultPanel; unify call detail with eval history navigation"
```

---

## ThreadEvalRow type reference

`ThreadEvalRow` (from `src/types`) has:
- `id: number`
- `runId: string`
- `thread_id: string`
- `result: Record<string, unknown>`
- `success_status: boolean`
- `created_at: string`

The `result` shape for inside-sales threads:
```json
{
  "transcript": "Agent: ...\nCustomer: ...",
  "call_metadata": { "agent": "...", "lead": "...", "duration": 120 },
  "evaluations": [
    {
      "evaluator_id": "...",
      "output": {
        "overall_score": 78,
        "call_opening": 8,
        "brand_positioning": 11,
        "no_misinformation": true,
        "reasoning": "..."
      }
    }
  ]
}
```

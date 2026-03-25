# Phase 2: Kaira Dynamic Results UI

## Goal
Make the Kaira RunDetail page fully dynamic — custom evaluator results show as table columns, distribution bars, stat pills, and filterable values. Add parallel execution toggle to the batch wizard.

## Prerequisites
- Phase 1 completed (backend returns `evaluator_descriptors`, summary has distributions)
- Docker Compose running with Phase 1 backend

---

## Change 1: Dynamic EvalTable Columns

**File:** `src/features/evalRuns/components/EvalTable.tsx`

### Current state (lines 136-143)

Hardcoded columns:
```tsx
<SortHeader label="Thread ID" k="thread_id" />
<SortHeader label="Msgs" k="thread_id" />
<SortHeader label="Intent Acc" k="intent_accuracy" />
<SortHeader label="Correctness" k="worst_correctness" />
<SortHeader label="Efficiency" k="efficiency_verdict" />
<SortHeader label="Completed" k="success_status" />
```

### New props

Add `evaluatorDescriptors` to the component props:

```typescript
interface EvalTableProps {
  evaluations: ThreadEvalRow[];
  evaluatorDescriptors?: EvaluatorDescriptor[];  // NEW
}
```

### New header rendering

Replace the hardcoded columns with:

```tsx
<thead>
  <tr>
    {/* Always present */}
    <SortHeader label="Thread ID" k="thread_id" />
    <SortHeader label="Msgs" k="thread_id" />

    {/* Dynamic columns from descriptors */}
    {(evaluatorDescriptors ?? DEFAULT_DESCRIPTORS).map(desc => (
      <SortHeader
        key={desc.id}
        label={desc.name}
        k={desc.type === 'built-in' ? desc.primaryField?.key ?? desc.id : `custom_${desc.id}`}
      />
    ))}

    {/* Always present */}
    <SortHeader label="Completed" k="success_status" />
  </tr>
</thead>
```

Define `DEFAULT_DESCRIPTORS` as a fallback for runs without descriptors (backward compat):

```typescript
const DEFAULT_DESCRIPTORS: EvaluatorDescriptor[] = [
  {
    id: 'intent',
    name: 'Intent Acc',
    type: 'built-in',
    primaryField: { key: 'intent_accuracy', format: 'percentage' },
  },
  {
    id: 'correctness',
    name: 'Correctness',
    type: 'built-in',
    primaryField: { key: 'worst_correctness', format: 'verdict' },
  },
  {
    id: 'efficiency',
    name: 'Efficiency',
    type: 'built-in',
    primaryField: { key: 'efficiency_verdict', format: 'verdict' },
  },
];
```

### New cell rendering

In the `ExpandableRow` component (or wherever table cells are rendered), replace the hardcoded cells.

Currently there are hardcoded cells like:
```tsx
<td>{pct(e.intent_accuracy)}</td>
<td><VerdictBadge verdict={e.worst_correctness} /></td>
<td><VerdictBadge verdict={e.efficiency_verdict} /></td>
```

Replace with a dynamic loop:

```tsx
{(evaluatorDescriptors ?? DEFAULT_DESCRIPTORS).map(desc => {
  const { value, state } = getCellValue(evaluation, desc);
  return (
    <td key={desc.id} className="...">
      {state === 'failed' ? (
        <span className="text-xs text-[var(--color-error)] font-medium">Failed</span>
      ) : state === 'skipped' ? (
        <span className="text-xs text-[var(--text-muted)]">Skipped</span>
      ) : (
        <CellRenderer desc={desc} value={value} />
      )}
    </td>
  );
})}
```

### Helper function: getCellValue

```typescript
function getCellValue(
  evaluation: ThreadEvalRow,
  desc: EvaluatorDescriptor,
): { value: unknown; state: 'ok' | 'failed' | 'skipped' } {
  const result = evaluation.result as Record<string, unknown> | undefined;

  if (desc.type === 'built-in') {
    // Check failed/skipped state
    const failedEvals = (result?.failed_evaluators ?? {}) as Record<string, string>;
    const skippedEvals = (result?.skipped_evaluators ?? []) as string[];

    if (failedEvals[desc.id]) return { value: null, state: 'failed' };
    if (skippedEvals.includes(desc.id)) return { value: null, state: 'skipped' };

    // Read from normalized column
    switch (desc.primaryField?.key) {
      case 'intent_accuracy': return { value: evaluation.intent_accuracy, state: 'ok' };
      case 'worst_correctness': return { value: evaluation.worst_correctness, state: 'ok' };
      case 'efficiency_verdict': return { value: evaluation.efficiency_verdict, state: 'ok' };
      default: return { value: null, state: 'ok' };
    }
  }

  // Custom evaluator — read from result.custom_evaluations
  const customEvals = (result?.custom_evaluations ?? {}) as Record<string, {
    status: string;
    output?: Record<string, unknown>;
    error?: string;
  }>;

  const ce = customEvals[desc.id];
  if (!ce) return { value: null, state: 'skipped' };
  if (ce.status === 'failed') return { value: null, state: 'failed' };

  // Extract primary field value from output
  const primaryKey = desc.primaryField?.key;
  if (primaryKey && ce.output) {
    return { value: ce.output[primaryKey], state: 'ok' };
  }

  return { value: null, state: 'ok' };
}
```

### Helper component: CellRenderer

```tsx
function CellRenderer({ desc, value }: { desc: EvaluatorDescriptor; value: unknown }) {
  if (value == null) return <span className="text-[var(--text-muted)]">—</span>;

  switch (desc.primaryField?.format) {
    case 'percentage': {
      const num = Number(value);
      return <span className="text-sm font-medium">{pct(num)}</span>;
    }
    case 'verdict':
      return <VerdictBadge verdict={String(value)} category={desc.type === 'built-in' ? desc.id : 'custom'} />;
    case 'number': {
      const num = Number(value);
      const display = num <= 1 ? `${(num * 100).toFixed(0)}%` : String(num);
      return <span className="text-sm font-medium">{display}</span>;
    }
    case 'boolean':
      return value
        ? <span className="text-[var(--color-success)]">Pass</span>
        : <span className="text-[var(--color-error)]">Fail</span>;
    default:
      return <span className="text-sm truncate max-w-[100px]">{String(value)}</span>;
  }
}
```

### Sorting support for custom columns

The existing sort logic needs to handle custom evaluator columns. In the sorting function, when `sortKey` starts with `custom_`:

```typescript
function getSortValue(evaluation: ThreadEvalRow, key: string): string | number {
  // Built-in columns
  if (key === 'thread_id') return evaluation.thread_id;
  if (key === 'intent_accuracy') return evaluation.intent_accuracy ?? 0;
  if (key === 'worst_correctness') return CORRECTNESS_SEVERITY[evaluation.worst_correctness ?? ''] ?? 0;
  if (key === 'efficiency_verdict') return EFFICIENCY_SEVERITY[evaluation.efficiency_verdict ?? ''] ?? 0;
  if (key === 'success_status') return evaluation.success_status ? 1 : 0;

  // Custom evaluator columns: key = "custom_{evaluator_id}"
  if (key.startsWith('custom_')) {
    const evalId = key.slice(7); // Remove "custom_" prefix
    const result = evaluation.result as Record<string, unknown> | undefined;
    const customEvals = (result?.custom_evaluations ?? {}) as Record<string, any>;
    const ce = customEvals[evalId];
    if (!ce || ce.status !== 'completed' || !ce.output) return '';

    // Find primary field from output — take first non-null value
    const desc = evaluatorDescriptors?.find(d => d.id === evalId);
    const primaryKey = desc?.primaryField?.key;
    if (primaryKey) {
      const val = ce.output[primaryKey];
      if (typeof val === 'number') return val;
      if (typeof val === 'string') return val;
      if (typeof val === 'boolean') return val ? 1 : 0;
    }
    return '';
  }

  return '';
}
```

### Expanded row detail for custom evaluators

In the `ExpandableRow` component, the expanded detail section currently renders:
- Transcript viewer
- Intent evaluations
- Correctness evaluations
- Efficiency evaluation
- CustomEvaluationsBlock

The existing `CustomEvaluationsBlock` already works (it iterates `result.custom_evaluations` and renders key-value pairs). Upgrade it to use `OutputFieldRenderer`:

```tsx
// In the existing CustomEvaluationsBlock, replace the raw key-value rendering:
// Instead of:
//   {Object.entries(ce.output).map(([key, value]) => (
//     <span>{key}: {String(value)}</span>
//   ))}
// Use:
{ce.output && desc && (
  <OutputFieldRenderer
    schema={desc.outputSchema ?? []}
    output={ce.output}
    mode="inline"
  />
)}
```

To get the descriptor for each custom evaluation, pass `evaluatorDescriptors` to `CustomEvaluationsBlock` and look up by evaluator_id.

---

## Change 2: Dynamic Stat Pills

**File:** `src/features/evalRuns/pages/RunDetail.tsx`

### Current state (lines 568-601)

Four hardcoded stat pills: Threads, Avg Intent Acc, Completion Rate, Completed/Errors.

### New approach

Replace the hardcoded stat pills with a dynamic system. Keep Threads and Completed as fixed pills, but make the evaluator-specific pills dynamic.

```tsx
{/* Fixed pills */}
<StatPill
  label="Threads"
  metricKey="total_threads"
  value={summaryTotal > 0 ? `${threadEvals.length} / ${summaryTotal}` : threadEvals.length}
/>

{/* Dynamic evaluator pills — only show evaluators with an average/percentage metric */}
{(run.evaluator_descriptors ?? [])
  .filter(d => d.aggregation?.average != null || d.primaryField?.format === 'percentage')
  .slice(0, 2)  // Max 2 evaluator pills to fit the grid
  .map(d => (
    <StatPill
      key={d.id}
      label={d.name}
      metricKey={d.id}
      value={d.aggregation?.average != null
        ? pct(d.aggregation.average)
        : '—'
      }
    />
  ))}

{/* Completion/Errors pill (always last) */}
{summaryErrors > 0 ? (
  <StatPill label="Errors" value={`${summaryErrors} / ${summaryTotal}`} color="var(--color-error)" />
) : (
  <StatPill label="Completed" metricKey="completed" value={`${threadEvals.filter(e => e.success_status).length} / ${threadEvals.length}`} />
)}
```

**Grid adjustment:** If there are more than 4 pills, use `grid-cols-2 md:grid-cols-4 lg:grid-cols-6` to accommodate.

---

## Change 3: Dynamic Distribution Bars

**File:** `src/features/evalRuns/pages/RunDetail.tsx`

### Current state (lines 604-621)

Two hardcoded distribution bars: Correctness and Efficiency.

### New approach

Replace with a dynamic loop over evaluator descriptors that have verdict-type primary fields with distributions:

```tsx
<div className="flex gap-4 flex-wrap">
  {(run.evaluator_descriptors ?? [])
    .filter(d => d.primaryField?.format === 'verdict' && d.aggregation?.distribution &&
                 Object.keys(d.aggregation.distribution).length > 0)
    .map(d => (
      <div key={d.id} className="flex-1 min-w-[260px]">
        <h3 className="text-xs uppercase tracking-wider text-[var(--text-muted)] font-semibold mb-1.5">
          {d.name}
        </h3>
        <DistributionBar
          distribution={d.aggregation!.distribution!}
          order={d.primaryField!.verdictOrder}
        />
      </div>
    ))}
</div>
```

### DistributionBar color handling for custom verdicts

**File:** `src/features/evalRuns/components/DistributionBar.tsx`

The existing `getVerdictColor()` function only knows built-in verdict strings (PASS, FAIL, EFFICIENT, etc.). For custom evaluator verdicts, it needs a fallback.

Check the existing `getVerdictColor` implementation. If it throws or returns undefined for unknown verdicts, add a fallback:

```typescript
function getVerdictColor(verdict: string): string {
  // Try existing lookup
  const known = existingGetVerdictColor(verdict);
  if (known) return known;

  // Fallback palette for custom evaluator verdicts
  // Use a consistent hash of the verdict string to pick a color
  const CUSTOM_PALETTE = [
    'var(--color-success)',     // green
    'var(--color-info)',        // blue
    'var(--color-warning)',     // yellow
    'var(--color-error)',       // red
    'var(--color-brand-accent)',// purple
    '#6b7280',                 // gray
  ];
  const hash = verdict.split('').reduce((h, c) => ((h << 5) - h + c.charCodeAt(0)) | 0, 0);
  return CUSTOM_PALETTE[Math.abs(hash) % CUSTOM_PALETTE.length];
}
```

Alternatively, in `labelDefinitions.ts`, add a `customVerdictColor(verdict)` export that implements this logic.

---

## Change 4: Custom Evaluator Summary Cards

**File:** `src/features/evalRuns/pages/RunDetail.tsx`

### Current state (lines 623-643)

The `customEvalSummary` section renders small cards showing `{name, completed, errors}`. With Phase 1 backend enrichment, we now also have `distribution` and `average`.

### Enhancement

If a custom evaluator has a distribution, render a mini distribution bar inside the card. If it has an average, show the score:

```tsx
{customEvalSummary.map(({ id, name, completed, errors, distribution, average }) => (
  <div
    key={id}
    className="bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded px-3 py-2"
    style={{ borderLeftWidth: 3, borderLeftColor: errors > 0 ? STATUS_COLORS.hardFail : STATUS_COLORS.pass }}
  >
    <p className="text-sm font-semibold text-[var(--text-primary)] truncate">{name}</p>
    <p className="text-xs text-[var(--text-muted)] mt-0.5">
      {completed} completed{errors > 0 ? `, ${errors} failed` : ""}
    </p>
    {average != null && (
      <p className="text-xs font-medium mt-1" style={{ color: getScoreColor(average) }}>
        Avg: {average <= 1 ? `${(average * 100).toFixed(0)}%` : average.toFixed(1)}
      </p>
    )}
    {distribution && Object.keys(distribution).length > 0 && (
      <div className="mt-1.5">
        <DistributionBar distribution={distribution} />
      </div>
    )}
  </div>
))}
```

**Update the `customEvalSummary` memo** to include the new fields:

```typescript
const customEvalSummary = useMemo(() => {
  const raw = (run?.summary?.custom_evaluations ?? {}) as Record<string, {
    name: string;
    completed: number;
    errors: number;
    distribution?: Record<string, number>;
    average?: number;
  }>;
  return Object.entries(raw).map(([id, v]) => ({ id, ...v }));
}, [run?.summary]);
```

---

## Change 5: Filtering by Custom Evaluator Verdicts

**File:** `src/features/evalRuns/pages/RunDetail.tsx`

### Current state

The verdict filter (lines 469-476, `toggleVerdictFilter`) only works with built-in correctness and efficiency verdicts from `allVerdicts`.

### Enhancement

Extend `allVerdicts` to include custom evaluator verdict values:

```typescript
const allVerdicts = useMemo(() => {
  const set = new Set<string>();
  for (const te of threadEvals) {
    if (te.worst_correctness) set.add(normalizeLabel(te.worst_correctness));
    if (te.efficiency_verdict) set.add(normalizeLabel(te.efficiency_verdict));

    // Add custom evaluator verdicts
    const result = te.result as Record<string, unknown> | undefined;
    const customEvals = (result?.custom_evaluations ?? {}) as Record<string, any>;
    for (const [ceId, ce] of Object.entries(customEvals)) {
      if (ce.status !== 'completed' || !ce.output) continue;
      const desc = run?.evaluator_descriptors?.find(d => d.id === ceId);
      if (desc?.primaryField?.format === 'verdict') {
        const val = ce.output[desc.primaryField.key];
        if (typeof val === 'string') set.add(normalizeLabel(val));
      }
    }
  }
  return Array.from(set);
}, [threadEvals, run?.evaluator_descriptors]);
```

Update the `filteredThreads` filter to check custom evaluator verdicts too:

```typescript
const filteredThreads = useMemo(() => {
  return threadEvals.filter((te) => {
    // ... existing search filter ...

    if (verdictFilter.size > 0) {
      const builtInMatch = [te.worst_correctness, te.efficiency_verdict]
        .filter(Boolean)
        .some(v => verdictFilter.has(normalizeLabel(v!)));

      // Check custom evaluator verdicts
      const result = te.result as Record<string, unknown> | undefined;
      const customEvals = (result?.custom_evaluations ?? {}) as Record<string, any>;
      let customMatch = false;
      for (const [ceId, ce] of Object.entries(customEvals)) {
        if (ce.status !== 'completed' || !ce.output) continue;
        const desc = run?.evaluator_descriptors?.find(d => d.id === ceId);
        if (desc?.primaryField?.format === 'verdict') {
          const val = ce.output[desc.primaryField.key];
          if (typeof val === 'string' && verdictFilter.has(normalizeLabel(val))) {
            customMatch = true;
            break;
          }
        }
      }

      if (!builtInMatch && !customMatch) return false;
    }

    return true;
  });
}, [threadEvals, search, verdictFilter, run?.evaluator_descriptors]);
```

---

## Change 6: Parallel Execution Toggle in Batch Wizard

**File:** `src/features/evalRuns/components/NewBatchEvalOverlay.tsx`

### What to add

In the evaluators step (or as an advanced option), add a toggle for parallel custom evaluator execution.

### Where

In the `handleSubmit` function (around line 183), add the new flag:

```typescript
// In the params object passed to submitJob:
parallel_custom_evals: parallelCustomEvals,
```

### UI

Add a state variable:

```typescript
const [parallelCustomEvals, setParallelCustomEvals] = useState(false);
```

In the `EvaluatorToggleStep` (or its advanced options section), add a toggle:

```tsx
{customEvaluatorIds.length > 1 && (
  <label className="flex items-center gap-2 text-sm text-[var(--text-secondary)] mt-2">
    <input
      type="checkbox"
      checked={parallelCustomEvals}
      onChange={(e) => setParallelCustomEvals(e.target.checked)}
      className="rounded border-[var(--border-subtle)]"
    />
    Run custom evaluators in parallel
    <span className="text-xs text-[var(--text-muted)]">(faster but may hit rate limits)</span>
  </label>
)}
```

Pass this through `EvaluatorToggleStep` props or keep it in the parent component.

---

## Change 7: Pass descriptors through component tree

### RunDetail.tsx → EvalTable

The `RunDetail` page passes `evaluations` to `EvalTable`. It also needs to pass `evaluatorDescriptors`:

```tsx
<EvalTable
  evaluations={filteredThreads}
  evaluatorDescriptors={run.evaluator_descriptors}
/>
```

### RunDetail.tsx → CustomEvaluationsBlock

Pass descriptors so it can use `OutputFieldRenderer`:

```tsx
<CustomEvaluationsBlock
  evaluations={result.custom_evaluations}
  evaluatorDescriptors={run.evaluator_descriptors}
/>
```

---

## Testing Phase 2

1. **Run a Kaira batch with 3 built-in + 2+ custom evaluators**
2. **Check RunDetail page:**
   - Table should show dynamic columns for all evaluators
   - Custom evaluator columns should show verdict badges or scores
   - Sorting by custom evaluator columns should work
   - Distribution bars should appear for custom evaluators with verdict-type outputs
   - Stat pills should show custom evaluator averages
   - Custom evaluator summary cards should show mini distribution bars
3. **Check filtering:**
   - Verdict filter chips should include custom evaluator verdict values
   - Filtering should correctly show/hide threads based on custom eval verdicts
4. **Check backward compatibility:**
   - Old runs (without `evaluator_descriptors`) should still render with default columns
   - The `DEFAULT_DESCRIPTORS` fallback should kick in
5. **Check parallel execution:**
   - Toggle parallel in wizard → submit batch
   - Verify all custom evaluators complete (check summary counts)
   - Compare timing with sequential execution
6. **Expanded row detail:**
   - Click a thread row → expanded detail should use `OutputFieldRenderer` for custom eval output
   - Compare with old JSON dump — should be much more readable

---

## Edge Cases to Handle

1. **Many custom evaluators (10+):** Table columns may overflow horizontally. Use `overflow-x-auto` on the table wrapper (already present). Consider a max visible columns setting or horizontal scroll indicator.

2. **Custom evaluator with no output (all failed):** Column should show "Failed" for all rows. Distribution bar should not render (empty).

3. **Mixed verdict and numeric evaluators:** Stat pills show numeric ones, distribution bars show verdict ones. Both types get columns.

4. **Old runs without descriptors:** `DEFAULT_DESCRIPTORS` fallback preserves existing behavior. No breakage.

5. **Custom evaluator with array output field as primary:** This shouldn't happen (primary field detection skips arrays), but if it does, the cell renders "[N items]".

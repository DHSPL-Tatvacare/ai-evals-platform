# Phase 3: VoiceRx RunDetail + Run All UI

## Goal
Give VoiceRx a proper RunDetail page for viewing evaluation results, and add "Run All Evaluators" capability to execute multiple custom evaluators on a listing in one click.

## Prerequisites
- Phase 1 completed (VoiceRx summary populated, `evaluate-custom-batch` handler registered, OutputFieldRenderer exists)
- Phase 2 completed (EvalTable dynamic columns work, DistributionBar handles custom verdicts)

---

## Change 1: VoiceRx Run Detail Page

**File:** `src/features/voiceRx/pages/VoiceRxRunDetail.tsx` (NEW)

### What this page handles

Two distinct eval_type cases:

1. **`full_evaluation`** — Two-call pipeline result (transcription + critique)
   - Shows: header, summary stats, segment comparison table, critique details
   - Data source: `EvalRun.result` (monolithic JSON, no ThreadEvaluation rows)

2. **`custom`** — Single custom evaluator result
   - Shows: header, evaluator output via OutputFieldRenderer, raw prompt/response
   - Data source: `EvalRun.result.output` + `EvalRun.summary`

### Page structure

```tsx
import { useState, useEffect } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { Loader2, AlertTriangle, CheckCircle2, XCircle, Clock, Calendar, Cpu, ArrowLeft } from 'lucide-react';
import { ConfirmDialog } from '@/components/ui';
import { VerdictBadge } from '@/features/evalRuns/components';
import { OutputFieldRenderer } from '@/features/evalRuns/components/OutputFieldRenderer';
import { fetchEvalRun, deleteEvalRun } from '@/services/api/evalRunsApi';
import { notificationService } from '@/services/notifications';
import { routes } from '@/config/routes';
import { formatTimestamp, formatDuration } from '@/utils/evalFormatters';
import type { EvalRun } from '@/types';

export function VoiceRxRunDetail() {
  const { runId } = useParams<{ runId: string }>();
  const navigate = useNavigate();
  const [run, setRun] = useState<EvalRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  // ... delete state ...

  useEffect(() => {
    if (!runId) return;
    setLoading(true);
    fetchEvalRun(runId)
      .then(setRun)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [runId]);

  if (loading) return <LoadingState />;
  if (error || !run) return <ErrorState error={error} />;

  return (
    <div className="space-y-4">
      {/* Breadcrumb */}
      <div className="flex items-center gap-1.5 text-sm text-[var(--text-muted)]">
        <Link to={routes.voiceRx.runs} className="hover:text-[var(--text-brand)]">Runs</Link>
        <span>/</span>
        <span className="font-mono text-[var(--text-secondary)]">{run.id.slice(0, 12)}</span>
      </div>

      {/* Header card — identical pattern to Kaira RunDetail */}
      <RunHeader run={run} onDelete={handleDelete} />

      {/* Route to correct detail renderer based on eval_type */}
      {run.evalType === 'full_evaluation' ? (
        <FullEvaluationDetail run={run} />
      ) : run.evalType === 'custom' ? (
        <CustomEvalDetail run={run} />
      ) : (
        <p className="text-sm text-[var(--text-muted)]">
          Unknown evaluation type: {run.evalType}
        </p>
      )}
    </div>
  );
}
```

### RunHeader sub-component

Reuses the same pattern from Kaira RunDetail — name, status badge, metadata row (model, duration, timestamp), action buttons (delete).

```tsx
function RunHeader({ run, onDelete }: { run: EvalRun; onDelete: () => void }) {
  const config = run.config as Record<string, unknown> | undefined;
  const evalName = (config?.evaluator_name as string) ?? run.evalType ?? 'Evaluation';

  return (
    <div className="bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-md px-4 py-2.5">
      <div className="flex items-center gap-2">
        <h1 className="text-[13px] font-bold text-[var(--text-primary)] truncate">{evalName}</h1>
        <VerdictBadge verdict={run.status} category="status" />
        <div className="ml-auto">
          <button onClick={onDelete} className="...delete button styles...">Delete</button>
        </div>
      </div>
      <div className="flex items-center gap-x-3 gap-y-0.5 flex-wrap mt-1 text-xs text-[var(--text-muted)]">
        <span className="font-mono">{run.id.slice(0, 12)}</span>
        <span className="flex items-center gap-1">
          <Calendar className="h-3 w-3" />
          {formatTimestamp(run.createdAt)}
        </span>
        {run.durationMs && (
          <span className="flex items-center gap-1">
            <Clock className="h-3 w-3" />
            {formatDuration(run.durationMs / 1000)}
          </span>
        )}
        {run.llmModel && (
          <span className="flex items-center gap-1">
            <Cpu className="h-3 w-3" />
            {run.llmProvider}/{run.llmModel}
          </span>
        )}
      </div>
    </div>
  );
}
```

### FullEvaluationDetail sub-component

Renders the VoiceRx two-call pipeline result:

```tsx
function FullEvaluationDetail({ run }: { run: EvalRun }) {
  const result = run.result as Record<string, unknown> | undefined;
  const summary = run.summary as Record<string, unknown> | undefined;
  const critique = result?.critique as Record<string, unknown> | undefined;
  const segments = (critique?.segments ?? []) as Array<Record<string, unknown>>;

  return (
    <div className="space-y-4">
      {/* Summary stats */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {summary.overall_accuracy != null && (
            <StatCard label="Overall Accuracy" value={pct(summary.overall_accuracy as number)} />
          )}
          {summary.total_segments != null && (
            <StatCard label="Total Segments" value={summary.total_segments as number} />
          )}
          {summary.critical_errors != null && (
            <StatCard
              label="Critical Errors"
              value={summary.critical_errors as number}
              color={(summary.critical_errors as number) > 0 ? 'var(--color-error)' : undefined}
            />
          )}
          {summary.moderate_errors != null && (
            <StatCard
              label="Moderate Errors"
              value={summary.moderate_errors as number}
              color={(summary.moderate_errors as number) > 0 ? 'var(--color-warning)' : undefined}
            />
          )}
        </div>
      )}

      {/* Severity distribution bar (if available) */}
      {summary?.severity_distribution && (
        <div>
          <h3 className="text-xs uppercase tracking-wider text-[var(--text-muted)] font-semibold mb-1.5">
            Severity Distribution
          </h3>
          <DistributionBar
            distribution={summary.severity_distribution as Record<string, number>}
            order={['NONE', 'MINOR', 'MODERATE', 'CRITICAL']}
          />
        </div>
      )}

      {/* Segment comparison table */}
      {segments.length > 0 && (
        <div>
          <h3 className="text-xs uppercase tracking-wider text-[var(--text-muted)] font-semibold mb-2">
            Segment Comparison ({segments.length} segments)
          </h3>
          <div className="overflow-x-auto rounded-md border border-[var(--border-subtle)]">
            <table className="w-full border-collapse bg-[var(--bg-primary)]">
              <thead>
                <tr className="bg-[var(--bg-secondary)]">
                  <th className="...">#</th>
                  <th className="...">Original</th>
                  <th className="...">AI Transcript</th>
                  <th className="...">Severity</th>
                  <th className="...">Reasoning</th>
                </tr>
              </thead>
              <tbody>
                {segments.map((seg, i) => (
                  <tr key={i} className="border-t border-[var(--border-subtle)]">
                    <td className="...">{i + 1}</td>
                    <td className="...">
                      <div className="text-xs">
                        <span className="text-[var(--text-muted)]">[{seg.original_speaker as string}]</span>{' '}
                        {seg.original_text as string}
                      </div>
                    </td>
                    <td className="...">
                      <div className="text-xs">
                        <span className="text-[var(--text-muted)]">[{seg.ai_speaker as string}]</span>{' '}
                        {seg.ai_text as string}
                      </div>
                    </td>
                    <td className="...">
                      <SeverityBadge severity={seg.severity as string} />
                    </td>
                    <td className="text-xs text-[var(--text-secondary)] max-w-[200px] truncate">
                      {seg.reasoning as string}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Raw prompts (collapsible) */}
      <details className="group">
        <summary className="text-xs font-semibold text-[var(--text-muted)] cursor-pointer">
          Show raw prompts & responses
        </summary>
        <pre className="mt-2 text-xs bg-[var(--bg-tertiary)] p-3 rounded overflow-auto max-h-64">
          {JSON.stringify(result, null, 2)}
        </pre>
      </details>
    </div>
  );
}

function SeverityBadge({ severity }: { severity: string }) {
  const s = (severity ?? 'none').toUpperCase();
  const styles: Record<string, { bg: string; text: string }> = {
    NONE:     { bg: 'var(--surface-success)', text: 'var(--color-success)' },
    MINOR:    { bg: 'var(--bg-tertiary)',     text: 'var(--text-muted)' },
    MODERATE: { bg: 'var(--surface-warning)', text: 'var(--color-warning)' },
    CRITICAL: { bg: 'var(--surface-error)',   text: 'var(--color-error)' },
  };
  const st = styles[s] ?? styles.MINOR;
  return (
    <span
      className="px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase"
      style={{ backgroundColor: st.bg, color: st.text }}
    >
      {s === 'NONE' ? 'Match' : s}
    </span>
  );
}
```

### CustomEvalDetail sub-component

Renders a single custom evaluator result using OutputFieldRenderer:

```tsx
function CustomEvalDetail({ run }: { run: EvalRun }) {
  const result = run.result as Record<string, unknown> | undefined;
  const config = run.config as Record<string, unknown> | undefined;
  const output = (result?.output ?? {}) as Record<string, unknown>;
  const outputSchema = (config?.output_schema ?? []) as OutputFieldDef[];
  const summary = run.summary as Record<string, unknown> | undefined;

  return (
    <div className="space-y-4">
      {/* Score summary card (if available) */}
      {summary?.overall_score != null && (
        <div className="bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-md px-4 py-3">
          <span className="text-xs text-[var(--text-muted)] uppercase font-semibold">Score</span>
          <p className="text-2xl font-bold mt-1" style={{
            color: getScoreColor(summary.overall_score as number, summary.metadata as any)
          }}>
            {formatScore(summary.overall_score)}
          </p>
        </div>
      )}

      {/* Output fields rendered via OutputFieldRenderer */}
      {Object.keys(output).length > 0 && outputSchema.length > 0 ? (
        <div className="bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-md px-4 py-3">
          <h3 className="text-xs uppercase tracking-wider text-[var(--text-muted)] font-semibold mb-3">
            Evaluator Output
          </h3>
          <OutputFieldRenderer schema={outputSchema} output={output} mode="card" />
        </div>
      ) : Object.keys(output).length > 0 ? (
        /* Fallback: no schema, just show raw output */
        <div className="bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-md px-4 py-3">
          <h3 className="text-xs uppercase tracking-wider text-[var(--text-muted)] font-semibold mb-3">
            Evaluator Output
          </h3>
          <div className="space-y-1.5">
            {Object.entries(output).map(([key, value]) => (
              <div key={key} className="flex items-start gap-2 text-sm">
                <span className="text-[var(--text-muted)] shrink-0 font-medium">{key}:</span>
                <span className="text-[var(--text-primary)] break-words">
                  {typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value ?? '—')}
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {/* Score breakdown (if available) */}
      {summary?.breakdown && (
        <div className="bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-md px-4 py-3">
          <h3 className="text-xs uppercase tracking-wider text-[var(--text-muted)] font-semibold mb-2">
            Score Breakdown
          </h3>
          <div className="space-y-1">
            {Object.entries(summary.breakdown as Record<string, unknown>).map(([key, val]) => (
              <div key={key} className="flex justify-between text-sm">
                <span className="text-[var(--text-muted)]">{key}</span>
                <span className="text-[var(--text-primary)] font-medium">{String(val)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Reasoning (if available) */}
      {summary?.reasoning && (
        <div className="bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-md px-4 py-3">
          <h3 className="text-xs uppercase tracking-wider text-[var(--text-muted)] font-semibold mb-2">
            Reasoning
          </h3>
          <p className="text-sm text-[var(--text-secondary)]">{summary.reasoning as string}</p>
        </div>
      )}

      {/* Raw data (collapsible) */}
      <details className="group">
        <summary className="text-xs font-semibold text-[var(--text-muted)] cursor-pointer">
          Show raw request & response
        </summary>
        <div className="mt-2 space-y-2">
          {result?.rawRequest && (
            <div>
              <p className="text-xs text-[var(--text-muted)] mb-1">Prompt</p>
              <pre className="text-xs bg-[var(--bg-tertiary)] p-3 rounded overflow-auto max-h-48">
                {result.rawRequest as string}
              </pre>
            </div>
          )}
          {result?.rawResponse && (
            <div>
              <p className="text-xs text-[var(--text-muted)] mb-1">Response</p>
              <pre className="text-xs bg-[var(--bg-tertiary)] p-3 rounded overflow-auto max-h-48">
                {result.rawResponse as string}
              </pre>
            </div>
          )}
        </div>
      </details>
    </div>
  );
}
```

---

## Change 2: Route Configuration

**File:** `src/config/routes.ts`

Add VoiceRx run detail route:

```typescript
voiceRx: {
  // ... existing routes ...
  runDetail: (runId: string) => `/runs/${runId}`,  // NEW
},
```

**File:** `src/app/Router.tsx`

Add the route entry. Find where VoiceRx routes are defined and add:

```tsx
import { VoiceRxRunDetail } from '@/features/voiceRx/pages/VoiceRxRunDetail';

// In the VoiceRx route section:
<Route path="/runs/:runId" element={<VoiceRxRunDetail />} />
```

**Ensure it's placed BEFORE the `/runs` route** so React Router matches the more specific path first.

---

## Change 3: Update VoiceRxRunList Navigation

**File:** `src/features/voiceRx/pages/VoiceRxRunList.tsx`

Currently, clicking a run card navigates to the Logs page. Change it to navigate to the new RunDetail page.

Find where `RunRowCard` is rendered and update the `to` prop:

```tsx
// BEFORE:
<RunRowCard
  to={`${routes.voiceRx.logs}?entity_id=${run.id}`}
  ...
/>

// AFTER:
<RunRowCard
  to={routes.voiceRx.runDetail(run.id)}
  ...
/>
```

Add a "Logs" link to the RunDetail page header so users can still access the raw logs view.

---

## Change 4: Run All Evaluators Overlay

**File:** `src/features/voiceRx/components/RunAllOverlay.tsx` (NEW)

### What this does

A modal overlay that shows all available evaluators for a listing and lets the user run them all (or a selection) in one click.

### Where it's triggered from

The listing detail page or the evaluators tab on a listing. Add a button: "Run All Evaluators" that opens this overlay.

### Component structure

```tsx
interface RunAllOverlayProps {
  listingId: string;
  appId: string;
  open: boolean;
  onClose: () => void;
}

export function RunAllOverlay({ listingId, appId, open, onClose }: RunAllOverlayProps) {
  const [evaluators, setEvaluators] = useState<EvaluatorDefinition[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [search, setSearch] = useState('');

  // Load evaluators from registry
  useEffect(() => {
    if (!open) return;
    evaluatorsRepository.getRegistry(appId)
      .then(list => {
        setEvaluators(list);
        // Select all by default
        setSelected(new Set(list.map(e => e.id)));
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [open, appId]);

  const filteredEvaluators = useMemo(() => {
    if (!search) return evaluators;
    const q = search.toLowerCase();
    return evaluators.filter(e =>
      e.name.toLowerCase().includes(q) || e.prompt.toLowerCase().includes(q)
    );
  }, [evaluators, search]);

  async function handleSubmit() {
    if (selected.size === 0) return;
    setSubmitting(true);

    try {
      // Submit a single batch job
      const { jobId } = await jobsApi.submit({
        job_type: 'evaluate-custom-batch',
        params: {
          evaluator_ids: Array.from(selected),
          listing_id: listingId,
          app_id: appId,
          parallel: true,
        },
      });

      notificationService.success(`Running ${selected.size} evaluators...`);
      onClose();

      // Optionally navigate to runs list to see progress
      // navigate(routes.voiceRx.runs);
    } catch (e) {
      notificationService.error(`Failed to start evaluators: ${(e as Error).message}`);
    } finally {
      setSubmitting(false);
    }
  }

  function toggleEvaluator(id: string) {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function selectAll() {
    setSelected(new Set(evaluators.map(e => e.id)));
  }

  function selectNone() {
    setSelected(new Set());
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-[var(--bg-primary)] border border-[var(--border-subtle)] rounded-lg w-full max-w-lg max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="px-4 py-3 border-b border-[var(--border-subtle)]">
          <h2 className="text-base font-semibold text-[var(--text-primary)]">Run All Evaluators</h2>
          <p className="text-xs text-[var(--text-muted)] mt-0.5">
            Select evaluators to run on this listing. They will execute in parallel.
          </p>
        </div>

        {/* Search + select all/none */}
        <div className="px-4 py-2 border-b border-[var(--border-subtle)] flex items-center gap-2">
          <input
            type="text"
            placeholder="Search evaluators..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="flex-1 text-sm bg-[var(--bg-secondary)] border border-[var(--border-subtle)] rounded px-2 py-1"
          />
          <button onClick={selectAll} className="text-xs text-[var(--text-brand)] hover:underline">All</button>
          <button onClick={selectNone} className="text-xs text-[var(--text-muted)] hover:underline">None</button>
        </div>

        {/* Evaluator list */}
        <div className="flex-1 overflow-y-auto px-4 py-2 space-y-1.5">
          {loading ? (
            <p className="text-sm text-[var(--text-muted)] text-center py-4">Loading...</p>
          ) : filteredEvaluators.length === 0 ? (
            <p className="text-sm text-[var(--text-muted)] text-center py-4">No evaluators found</p>
          ) : (
            filteredEvaluators.map(ev => (
              <label
                key={ev.id}
                className={`flex items-start gap-2 p-2 rounded cursor-pointer transition-colors ${
                  selected.has(ev.id)
                    ? 'bg-[var(--color-brand-accent)]/10 border border-[var(--color-brand-accent)]/30'
                    : 'bg-[var(--bg-secondary)] border border-transparent hover:border-[var(--border-subtle)]'
                }`}
              >
                <input
                  type="checkbox"
                  checked={selected.has(ev.id)}
                  onChange={() => toggleEvaluator(ev.id)}
                  className="mt-0.5 rounded"
                />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-[var(--text-primary)]">{ev.name}</p>
                  <p className="text-xs text-[var(--text-muted)] truncate">{ev.prompt.slice(0, 100)}...</p>
                  <p className="text-xs text-[var(--text-muted)]">{ev.outputSchema?.length ?? 0} output field(s)</p>
                </div>
              </label>
            ))
          )}
        </div>

        {/* Footer */}
        <div className="px-4 py-3 border-t border-[var(--border-subtle)] flex items-center justify-between">
          <span className="text-xs text-[var(--text-muted)]">{selected.size} selected</span>
          <div className="flex gap-2">
            <button onClick={onClose} className="px-3 py-1.5 text-sm text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] rounded">
              Cancel
            </button>
            <button
              onClick={handleSubmit}
              disabled={selected.size === 0 || submitting}
              className="px-3 py-1.5 text-sm font-medium text-white bg-[var(--color-brand-accent)] rounded hover:opacity-90 disabled:opacity-50"
            >
              {submitting ? 'Starting...' : `Run ${selected.size} Evaluator${selected.size !== 1 ? 's' : ''}`}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
```

### Where to add the trigger button

Find the component that renders the listing detail view with evaluators. Add a button near the evaluator list:

```tsx
<button
  onClick={() => setRunAllOpen(true)}
  className="px-3 py-1.5 text-sm font-medium text-[var(--color-brand-accent)] border border-[var(--color-brand-accent)] rounded hover:bg-[var(--color-brand-accent)]/10"
>
  Run All Evaluators
</button>

<RunAllOverlay
  listingId={listingId}
  appId="voice-rx"
  open={runAllOpen}
  onClose={() => setRunAllOpen(false)}
/>
```

**Identify the exact component by searching for:**
- Where `useEvaluatorRunner` is used
- Where the "Run" button per evaluator exists
- This is likely in a listing detail/evaluators tab component

---

## Change 5: Progress Tracking for Run All

When the user clicks "Run All" and a `evaluate-custom-batch` job is created, the VoiceRxRunList needs to show the individual EvalRun rows as they complete.

### How this works automatically

The batch custom runner creates N separate EvalRun rows (one per evaluator). These have `app_id='voice-rx'` and `eval_type='custom'`. The existing VoiceRxRunList already queries `fetchEvalRuns({ app_id: 'voice-rx' })` and has polling for running status. So the individual runs will appear in the list automatically.

### Optional: Group indicator

If you want to show that these runs were part of a batch, you could:
1. Store a `batch_id` in each EvalRun's `batch_metadata` (set by the batch custom runner)
2. In VoiceRxRunList, group runs with the same batch_id

This is optional and can be done later. The core functionality works without it.

---

## Change 6: Export and Index Updates

**File:** `src/features/voiceRx/pages/index.ts` (or wherever pages are exported)

Add:
```typescript
export { VoiceRxRunDetail } from './VoiceRxRunDetail';
```

**File:** `src/features/voiceRx/components/index.ts`

Add:
```typescript
export { RunAllOverlay } from './RunAllOverlay';
```

---

## Change 7: API Client Updates (if needed)

**File:** `src/services/api/evalRunsApi.ts`

The existing `fetchEvalRun(runId)` should work for VoiceRx runs since they use the same `eval_runs` table. Verify that the function exists and returns all necessary fields:

```typescript
export async function fetchEvalRun(runId: string): Promise<EvalRun> {
  return apiRequest<EvalRun>(`/api/eval-runs/${runId}`);
}
```

If it doesn't exist (it might be `fetchRun` for batch runs), add it.

---

## Testing Phase 3

### VoiceRx RunDetail — Full Evaluation
1. Go to VoiceRx > upload an audio file > click Evaluate
2. Wait for completion
3. Go to Runs > click the completed run
4. **Should see:** Header with name/status/model, summary stats (accuracy, segments, errors), severity distribution bar, segment comparison table, collapsible raw data
5. **Verify:** Score shows in RunList card (not `--` anymore, thanks to Phase 1 summary fix)

### VoiceRx RunDetail — Custom Evaluation
1. Go to VoiceRx > Evaluators tab > Run a custom evaluator on a listing
2. Go to Runs > click the completed run
3. **Should see:** Header, score card, evaluator output fields rendered via OutputFieldRenderer, score breakdown, reasoning, collapsible raw prompt/response

### Run All Evaluators
1. Go to VoiceRx > listing with evaluators
2. Click "Run All Evaluators"
3. **Should see:** Overlay with all evaluators listed, checkboxes, search, select all/none
4. Select 5 evaluators > click "Run 5 Evaluators"
5. **Should see:** Success notification
6. Go to Runs list > **Should see:** 5 new run cards appearing (as they complete)
7. Each card should show the evaluator name and score

### Navigation
1. From RunList > click a run > RunDetail opens (not Logs)
2. From RunDetail header > click "Logs" link > goes to Logs page
3. From RunDetail > back to RunList via breadcrumb

---

## Edge Cases

1. **Full evaluation with no critique segments:** Summary shows but segment table is empty. Show "No segments to compare" message.

2. **Custom eval with no output_schema:** Falls back to raw key-value rendering (no OutputFieldRenderer).

3. **Run All with 0 evaluators in registry:** Button disabled or message "No evaluators configured".

4. **Run All while already running:** The batch job creates runs with status='running'. If user clicks Run All again, duplicates will be created. Consider disabling the button while runs are active for this listing.

5. **Large number of evaluators (20+):** RunAllOverlay has scroll + search. Performance should be fine.

6. **VoiceRx full_evaluation result structure varies** between upload flow and API flow (different critique format: `critique` vs `apiCritique`). Handle both in `FullEvaluationDetail`.

---

## Summary of All New Files

| File | Type | Purpose |
|------|------|---------|
| `src/features/voiceRx/pages/VoiceRxRunDetail.tsx` | NEW | VoiceRx run detail page |
| `src/features/voiceRx/components/RunAllOverlay.tsx` | NEW | Run All evaluators modal |

## Summary of Modified Files

| File | Change |
|------|--------|
| `src/config/routes.ts` | Add `voiceRx.runDetail` route |
| `src/app/Router.tsx` | Add VoiceRxRunDetail route entry |
| `src/features/voiceRx/pages/VoiceRxRunList.tsx` | Navigate to RunDetail instead of Logs |
| `src/features/voiceRx/pages/index.ts` | Export VoiceRxRunDetail |
| `src/features/voiceRx/components/index.ts` | Export RunAllOverlay |
| Listing detail component (TBD) | Add "Run All Evaluators" button |

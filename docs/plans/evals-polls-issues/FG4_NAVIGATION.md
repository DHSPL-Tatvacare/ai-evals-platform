# FG-4: Navigation Fixes & Submit Loop

## Files

- `src/features/evalRuns/pages/RunList.tsx`
- `src/hooks/useSubmitAndRedirect.ts`
- `src/components/JobCompletionWatcher.tsx`

---

## Fix 1: Custom run "Logs" link uses wrong query param (Bug #1) — HIGH

### Problem
`RunList.tsx:271` links to `${routes.kaira.logs}?entity_id=${run.id}` but `Logs.tsx:40` reads `searchParams.get("run_id")`. The backend also expects `run_id`. So the filter is completely ignored — users see all logs.

### File: `src/features/evalRuns/pages/RunList.tsx`

### Current (line 271):
```typescript
to={`${routes.kaira.logs}?entity_id=${run.id}`}
```

### Fix:
```typescript
to={`${routes.kaira.logs}?run_id=${run.id}`}
```

One-line change. No other files affected.

---

## Fix 2: Abortable `useSubmitAndRedirect` (Bug #5)

### Problem
`useSubmitAndRedirect.ts:46-65` has a raw `while` loop that polls for up to 10 seconds. If the user closes the overlay or navigates away, the loop continues with stale state and can trigger unexpected navigation.

### Solution
Use a ref-based `AbortController` that is cancelled on unmount. Replace the raw while loop with `poll()` from jobPolling (reuse existing infrastructure, avoid duplication).

### File: `src/hooks/useSubmitAndRedirect.ts`

### Full rewrite:

```typescript
import { useState, useCallback, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { jobsApi } from '@/services/api/jobsApi';
import { notificationService } from '@/services/notifications';
import { useJobTrackerStore } from '@/stores';
import { runDetailForApp } from '@/config/routes';
import { poll } from '@/services/api/jobPolling';

interface SubmitAndRedirectOptions {
  appId: string;
  label: string;
  successMessage: string;
  fallbackRoute: string;
  onClose: () => void;
}

export function useSubmitAndRedirect(options: SubmitAndRedirectOptions) {
  const { appId, label, successMessage, fallbackRoute, onClose } = options;
  const navigate = useNavigate();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const controllerRef = useRef<AbortController | null>(null);

  // Abort on unmount
  useEffect(() => {
    return () => { controllerRef.current?.abort(); };
  }, []);

  const submit = useCallback(
    async (jobType: string, params: Record<string, unknown>) => {
      // Abort any previous in-flight submit
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;

      setIsSubmitting(true);
      try {
        const job = await jobsApi.submit(jobType, params);

        // Register in global tracker
        useJobTrackerStore.getState().trackJob({
          jobId: job.id,
          appId,
          jobType,
          label,
          trackedAt: Date.now(),
        });

        notificationService.success(successMessage);

        // Poll briefly for run_id (up to 10s, every 2s)
        let runId: string | undefined;
        try {
          await poll<string>({
            fn: async () => {
              const updated = await jobsApi.get(job.id);
              const rid = (updated.progress as Record<string, unknown>)
                ?.run_id as string | undefined;
              if (rid) {
                runId = rid;
                return { done: true, data: rid };
              }
              if (['completed', 'failed', 'cancelled'].includes(updated.status)) {
                return { done: true };
              }
              return { done: false };
            },
            intervalMs: 2000,
            signal: controller.signal,
            // Stop after ~10s: poll() runs fn immediately, then sleeps.
            // 5 iterations * 2s = 10s max.
            maxIterations: 5,
          });
        } catch {
          // AbortError or network error — fall through to redirect
        }

        // Don't navigate if aborted (component unmounted)
        if (controller.signal.aborted) return;

        if (runId) {
          useJobTrackerStore.getState().resolveRunId(job.id, runId);
          navigate(runDetailForApp(appId, runId));
        } else {
          navigate(fallbackRoute);
        }

        onClose();
      } catch (err) {
        if (controller.signal.aborted) return;
        const msg = err instanceof Error ? err.message : 'Failed to submit job.';
        notificationService.error(msg);
      } finally {
        setIsSubmitting(false);
      }
    },
    [appId, label, successMessage, fallbackRoute, onClose, navigate],
  );

  return { submit, isSubmitting };
}
```

### Required: Add `maxIterations` to `poll()` in `jobPolling.ts`

Add an optional `maxIterations` field to `PollConfig`:

```typescript
export interface PollConfig<T> {
  fn: () => Promise<{ done: boolean; data?: T }>;
  intervalMs?: number;
  signal?: AbortSignal;
  getBackoffMs?: () => number;  // from FG-1
  /** Stop after N iterations even if not done. */
  maxIterations?: number;
}
```

In the `poll()` function, add a counter:

```typescript
export async function poll<T>(config: PollConfig<T>): Promise<T | undefined> {
  const { fn, intervalMs = 5000, signal, maxIterations } = config;
  let iteration = 0;

  while (true) {
    // ... existing visibility pause + abort check ...

    const result = await fn();
    if (result.done) return result.data;

    iteration++;
    if (maxIterations != null && iteration >= maxIterations) return undefined;

    // ... existing sleep logic ...
  }
}
```

This keeps `poll()` backward-compatible while supporting the bounded polling use case.

---

## Fix 3: Parallel job polling in JobCompletionWatcher (Bug #10)

### Problem
`JobCompletionWatcher.tsx:25-87` loops through tracked jobs with `for...of`, meaning a slow API response for one job delays checking all others.

### Solution
Use `Promise.allSettled` to poll all jobs in parallel, then process results.

### File: `src/components/JobCompletionWatcher.tsx`

### Current (lines 25-87):
```typescript
for (const tracked of jobs) {
  try {
    const job = await jobsApi.get(tracked.jobId);
    // ... process job ...
  } catch {
    // skip
  }
}
```

### New:
```typescript
const results = await Promise.allSettled(
  jobs.map((tracked) => jobsApi.get(tracked.jobId).then((job) => ({ tracked, job })))
);

for (const result of results) {
  if (result.status === 'rejected') continue; // transient error, skip

  const { tracked, job } = result.value;

  // Resolve run_id if not yet known
  if (!tracked.runId) {
    const runId = (job.progress as Record<string, unknown>)?.run_id as string | undefined;
    if (runId) {
      resolveRunId(tracked.jobId, runId);
    }
  }

  // Check terminal state
  if (['completed', 'failed', 'cancelled'].includes(job.status)) {
    const runId =
      tracked.runId ??
      ((job.progress as Record<string, unknown>)?.run_id as string | undefined);

    const currentPath = window.location.pathname;
    const isOnRunDetail = runId != null && isRunDetailPath(currentPath, runId);

    if (!isOnRunDetail) {
      if (job.status === 'completed') {
        notificationService.notify({
          type: 'success',
          message: `${tracked.label} completed`,
          title: 'Job Complete',
          dismissible: true,
          priority: 'normal',
          ...(runId
            ? {
                action: {
                  label: 'View Run',
                  onClick: () => navigate(runDetailForApp(tracked.appId, runId)),
                },
              }
            : {}),
        });
      } else if (job.status === 'failed') {
        notificationService.error(
          `${tracked.label} failed${job.errorMessage ? `: ${job.errorMessage}` : ''}`,
          'Job Failed',
        );
      } else if (job.status === 'cancelled') {
        notificationService.warning(
          `${tracked.label} was cancelled`,
          'Job Cancelled',
        );
      }
    }

    untrackJob(tracked.jobId);
  }
}
```

The logic is identical — just the fetch is parallelized. With 3+ tracked jobs, this reduces latency from `N * avgResponseTime` to `max(responseTime1, ..., responseTimeN)`.

---

## Testing

1. **Logs link (Bug #1)**: Go to Kaira RunList → click "Logs" on a custom eval run → confirm the Logs page shows only logs for that specific run (not all logs)
2. **Submit & redirect (Bug #5)**: Open adversarial overlay → submit a job → immediately close the overlay before redirect happens → confirm no unexpected navigation occurs
3. **Submit & redirect**: Open batch overlay → submit → let it redirect normally → confirm it reaches the run detail page
4. **JobCompletionWatcher (Bug #10)**: Submit 2+ jobs → confirm both get completion toasts approximately simultaneously (not one after the other with noticeable delay)

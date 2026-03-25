# FG-3: Detail Page Polling + VoiceRx Progress

## Files

- `src/features/evalRuns/pages/RunDetail.tsx`
- `src/features/voiceRx/pages/VoiceRxRunDetail.tsx`

---

## Fix 1: RunDetail polls for `pending` runs too (Bug #4)

### Problem
`RunDetail.tsx:356` enables polling only when `runStatus?.toLowerCase() === "running"`. If the user navigates to the detail page while the run is still `pending`, polling never starts.

### Current code (line 356):
```typescript
enabled: runStatus?.toLowerCase() === "running" && !!runJobId,
```

### New code:
```typescript
import { isActiveStatus } from '@/utils/runStatus';

// ...

enabled: !!runStatus && isActiveStatus(runStatus) && !!runJobId,
```

Also update `isRunActive` on line 231 to use the same function:
```typescript
// Current:
const isRunActive = run != null && run.status.toLowerCase() === "running";

// New:
const isRunActive = run != null && isActiveStatus(run.status);
```

**Note**: The `RunProgressBar` component already handles `queued` status (shows "Queued" + pulsing bar), so showing it for pending runs is correct UX. No changes needed to `RunProgressBar`.

---

## Fix 2: VoiceRx RunDetail — add progress bar + cancel (Bugs #6, #7)

### Problem
VoiceRxRunDetail has no progress bar (unlike Kaira's RunDetail) and no cancel button. Users get no visual progress feedback during voice-rx evaluations.

### Approach
The VoiceRx RunDetail already polls `fetchEvalRun` every 5s while the run is active. To add a progress bar, we need to:

1. Also poll the **job** endpoint (using `run.jobId`) to get progress info
2. Render a progress bar component
3. Add a cancel button

We will NOT copy-paste `RunProgressBar` from `RunDetail.tsx`. Instead, we'll extract it to a shared component and import it in both places.

### Step 1: Extract `RunProgressBar` to shared component

Move the `RunProgressBar` function from `RunDetail.tsx` (lines 64-147) into a new file:

**`src/features/evalRuns/components/RunProgressBar.tsx`**

```typescript
import { Clock } from 'lucide-react';
import type { Job } from '@/services/api/jobsApi';

interface ProgressState {
  current: number;
  total: number;
  message: string;
}

export function RunProgressBar({
  job,
  elapsed,
}: {
  job: Job | null;
  elapsed: string;
}) {
  // ... exact same implementation as RunDetail.tsx lines 64-147
  // Just move it, don't change any logic or styling
}
```

**Also export from `src/features/evalRuns/components/index.ts`** (add to the barrel):
```typescript
export { RunProgressBar } from './RunProgressBar';
```

**Update `RunDetail.tsx`**: Remove the local `RunProgressBar` function and `ProgressState` interface. Import from the shared location instead:
```typescript
import { RunProgressBar } from '../components';
```

The `ProgressState` interface is only used inside `RunProgressBar`, so it moves with it.

### Step 2: Add job polling to VoiceRxRunDetail

Add state and polling for the job, plus cancel functionality. The changes below are to `VoiceRxRunDetail.tsx`:

```typescript
import { useState, useEffect, useCallback, useRef } from 'react';
import { usePoll } from '@/hooks';
import { jobsApi, type Job } from '@/services/api/jobsApi';
import { isActiveStatus } from '@/utils/runStatus';
import { RunProgressBar } from '@/features/evalRuns/components';
// ... existing imports

function computeElapsed(startedAt: string): string {
  const secs = Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000);
  if (secs < 0) return '0s';
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

function useElapsedTime(startedAt: string | null, active: boolean): string {
  const [elapsed, setElapsed] = useState(() =>
    startedAt && active ? computeElapsed(startedAt) : '',
  );
  useEffect(() => {
    if (!startedAt || !active) return;
    const id = setInterval(() => setElapsed(computeElapsed(startedAt)), 1000);
    return () => clearInterval(id);
  }, [startedAt, active]);
  return startedAt && active ? elapsed : '';
}
```

**NOTE**: `computeElapsed` and `useElapsedTime` already exist in `RunDetail.tsx`. To avoid duplication, extract them to a shared utility:

**`src/features/evalRuns/hooks/useElapsedTime.ts`** (NEW):
```typescript
import { useState, useEffect } from 'react';

function computeElapsed(startedAt: string): string {
  const secs = Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000);
  if (secs < 0) return '0s';
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

export function useElapsedTime(startedAt: string | null, active: boolean): string {
  const [elapsed, setElapsed] = useState(() =>
    startedAt && active ? computeElapsed(startedAt) : '',
  );
  useEffect(() => {
    if (!startedAt || !active) return;
    const id = setInterval(() => setElapsed(computeElapsed(startedAt)), 1000);
    return () => clearInterval(id);
  }, [startedAt, active]);
  return startedAt && active ? elapsed : '';
}
```

Export from `src/features/evalRuns/hooks/index.ts`:
```typescript
export { useElapsedTime } from './useElapsedTime';
```

**Update RunDetail.tsx**: Remove local `computeElapsed` + `useElapsedTime`, import from shared:
```typescript
import { useElapsedTime } from '../hooks';
```

### Step 3: Wire it up in VoiceRxRunDetail

In the `VoiceRxRunDetail` component, add:

```typescript
export function VoiceRxRunDetail() {
  // ... existing state ...
  const [activeJob, setActiveJob] = useState<Job | null>(null);
  const [cancelling, setCancelling] = useState(false);

  const isActive = !!runId && !!run && !TERMINAL_STATUSES.has(run.status);
  const elapsed = useElapsedTime(activeJob?.startedAt ?? run?.startedAt ?? null, isActive);

  // Existing run poll stays as-is (lines 39-46)

  // NEW: Job progress poll (only when run has a jobId)
  const runJobId = run?.jobId ?? null;
  usePoll({
    fn: async () => {
      if (!runJobId) return false;
      const job = await jobsApi.get(runJobId);
      setActiveJob(job);
      if (['completed', 'failed', 'cancelled'].includes(job.status)) {
        return false; // stop
      }
      return true;
    },
    enabled: isActive && !!runJobId,
  });

  const handleCancel = useCallback(async () => {
    if (!activeJob) return;
    setCancelling(true);
    try {
      await jobsApi.cancel(activeJob.id);
      setActiveJob((prev) => prev ? { ...prev, status: 'cancelled' } : prev);
      setRun((prev) => prev ? { ...prev, status: 'cancelled' as EvalRun['status'] } : prev);
    } catch (e: unknown) {
      notificationService.error(e instanceof Error ? e.message : 'Cancel failed');
    } finally {
      setCancelling(false);
    }
  }, [activeJob]);

  // ... rest of component ...
```

In the JSX, after the `<RunHeader>` and before the eval type routing, add:

```tsx
{/* Progress bar for active runs */}
{isActive && <RunProgressBar job={activeJob} elapsed={elapsed} />}
```

### Step 4: Add cancel button to VoiceRx RunHeader

Pass `onCancel`, `cancelling`, and `isActive` as additional props to `RunHeader`:

```typescript
function RunHeader({ run, onDelete, onCancel, cancelling, isActive }: {
  run: EvalRun;
  onDelete: () => void;
  onCancel?: () => void;
  cancelling?: boolean;
  isActive?: boolean;
}) {
```

Add cancel button in the header's action area (before the delete button):

```tsx
{isActive && onCancel && (
  <button
    onClick={onCancel}
    disabled={cancelling}
    className="inline-flex items-center gap-1 px-2 py-1 text-xs text-[var(--color-warning)] hover:bg-[var(--surface-warning)] rounded transition-colors disabled:opacity-50"
  >
    {cancelling ? 'Cancelling...' : 'Cancel'}
  </button>
)}
```

Update the `<RunHeader>` call in the main component:
```tsx
<RunHeader
  run={run}
  onDelete={() => setDeleteOpen(true)}
  onCancel={handleCancel}
  cancelling={cancelling}
  isActive={isActive}
/>
```

---

## Summary of new/moved files

| File | Action | Content |
|------|--------|---------|
| `src/features/evalRuns/components/RunProgressBar.tsx` | NEW (extracted from RunDetail) | `RunProgressBar` component |
| `src/features/evalRuns/hooks/useElapsedTime.ts` | NEW (extracted from RunDetail) | `useElapsedTime` hook + `computeElapsed` |
| `src/features/evalRuns/components/index.ts` | EDIT | Add `RunProgressBar` export |
| `src/features/evalRuns/hooks/index.ts` | EDIT | Add `useElapsedTime` export |
| `src/features/evalRuns/pages/RunDetail.tsx` | EDIT | Remove local defs, import shared; fix pending poll |
| `src/features/voiceRx/pages/VoiceRxRunDetail.tsx` | EDIT | Add job poll, progress bar, cancel |

---

## Testing

1. **Kaira RunDetail**: Navigate to a running run → confirm progress bar still works identically after extraction
2. **Kaira RunDetail**: Navigate while run is `pending` → confirm polling starts and progress bar shows "Queued"
3. **VoiceRx RunDetail**: Start a voice-rx evaluation → navigate to run detail while it's running → confirm progress bar appears with animated progress + elapsed time
4. **VoiceRx RunDetail**: Click "Cancel" on a running run → confirm it cancels, progress bar disappears, status shows cancelled
5. **VoiceRx RunDetail**: Navigate to a completed run → confirm no progress bar shown, no job polling

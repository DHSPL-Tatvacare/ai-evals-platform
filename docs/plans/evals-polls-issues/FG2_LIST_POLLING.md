# FG-2: List Polling for Pending + Running

## Files

- `src/utils/runStatus.ts` (NEW — 1 tiny utility)
- `src/features/evalRuns/pages/RunList.tsx`
- `src/features/voiceRx/pages/VoiceRxRunList.tsx`
- `src/features/evalRuns/hooks/useStableUpdate.ts`

## Fix 1: Shared `isActiveStatus()` utility (Bug #3)

### Problem
Three separate files check `status === 'running' || status === 'RUNNING'` and miss `pending`. This duplicated logic should be a single function.

### Solution
Create `src/utils/runStatus.ts` with one export:

```typescript
/**
 * Whether a run/job status represents an in-progress state
 * that should trigger polling.
 */
export function isActiveStatus(status: string): boolean {
  const s = status.toLowerCase();
  return s === 'running' || s === 'pending';
}
```

No barrel export needed — import directly where used. This is a pure function, no side effects.

---

## Fix 2: RunList `hasRunning` includes `pending` (Bug #3)

### File: `src/features/evalRuns/pages/RunList.tsx`

### Current code (lines 162-168):
```typescript
const hasRunning = useMemo(
  () => [...runs, ...customRuns].some((r) => {
    const status = 'status' in r ? r.status : '';
    return status === 'running' || status === 'RUNNING';
  }),
  [runs, customRuns],
);
```

### New code:
```typescript
import { isActiveStatus } from '@/utils/runStatus';

// ...

const hasActive = useMemo(
  () => [...runs, ...customRuns].some((r) => {
    const status = 'status' in r ? r.status : '';
    return isActiveStatus(status);
  }),
  [runs, customRuns],
);
```

Also rename the variable from `hasRunning` to `hasActive` (more accurate), and update its usage on line 172:
```typescript
usePoll({
  fn: async () => { loadRuns(); return true; },
  enabled: hasActive,
});
```

---

## Fix 3: VoiceRxRunList `hasRunning` includes `pending` (Bug #3)

### File: `src/features/voiceRx/pages/VoiceRxRunList.tsx`

### Current code (lines 163-166):
```typescript
const hasRunning = useMemo(
  () => runs.some((r) => r.status === 'running'),
  [runs],
);
```

### New code:
```typescript
import { isActiveStatus } from '@/utils/runStatus';

// ...

const hasActive = useMemo(
  () => runs.some((r) => isActiveStatus(r.status)),
  [runs],
);
```

Update usage on line 170:
```typescript
usePoll({
  fn: async () => { loadRuns(); return true; },
  enabled: hasActive,
});
```

---

## Fix 4: Stable update fingerprint includes error info (Bug #9)

### Problem
`useStableUpdate.ts` fingerprints on `id + status + summary` only. If `errorMessage` changes without status/summary changing (e.g., backend appends error detail while status stays `running`), the update is suppressed.

### File: `src/features/evalRuns/hooks/useStableUpdate.ts`

### Current fingerprint (line 8-10):
```typescript
function fingerprint(items: Array<{ id: string; status: string; summary?: unknown }>): string {
  return items.map((i) => `${i.id}:${i.status}:${JSON.stringify(i.summary ?? '')}`).join('|');
}
```

### New fingerprint:
```typescript
function fingerprint(items: Array<{ id: string; status: string; summary?: unknown; errorMessage?: string }>): string {
  return items.map((i) => `${i.id}:${i.status}:${i.errorMessage ?? ''}:${JSON.stringify(i.summary ?? '')}`).join('|');
}
```

Update the `useStableRunUpdate` normalized map (line 16-19):
```typescript
const normalized = incoming.map((r) => ({
  id: r.run_id,
  status: r.status,
  errorMessage: r.error_message ?? '',
  summary: r.summary,
}));
```

Update the `useStableEvalRunUpdate` normalized map (line 35-38):
```typescript
const normalized = incoming.map((r) => ({
  id: r.id,
  status: r.status,
  errorMessage: r.errorMessage ?? '',
  summary: r.summary,
}));
```

---

## Testing

1. Submit a job → before worker picks it up, the run shows `pending` on the list → confirm the list polls and the status updates to `running` without manual refresh
2. Confirm no shimmer/flicker on polling iterations when data hasn't changed (fingerprint still working)
3. Check both Kaira RunList and VoiceRx RunList

# Eval Polling & Progress Widget — Bug Fix Plan

## Scope

Fix 15 issues across the eval run polling, progress, and navigation subsystems. Changes span 8 frontend files and 0 backend files. Organized into 4 sequential fix groups to minimize blast radius.

## Fix Groups

| Group | File | Description |
|-------|------|-------------|
| [FG-1](./FG1_USEPOLL_CORE.md) | `usePoll.ts`, `jobPolling.ts` | Core polling resilience (error backoff, visibility leak) |
| [FG-2](./FG2_LIST_POLLING.md) | `RunList.tsx`, `VoiceRxRunList.tsx`, `useStableUpdate.ts` | List polling for pending+running, stable update fix |
| [FG-3](./FG3_DETAIL_PAGES.md) | `RunDetail.tsx`, `VoiceRxRunDetail.tsx` | Detail page polling for pending, VoiceRx progress bar |
| [FG-4](./FG4_NAVIGATION.md) | `RunList.tsx`, `useSubmitAndRedirect.ts`, `JobCompletionWatcher.tsx` | Broken logs link, abortable submit loop, sequential polling |

## Implementation Order

```
FG-1 (core) → FG-2 (lists) → FG-3 (details) → FG-4 (navigation)
```

FG-1 must go first because FG-2/FG-3 depend on the improved `usePoll`. FG-2 and FG-3 are independent of each other but both depend on FG-1. FG-4 is fully independent.

## Bug → Fix Mapping

| # | Bug | Severity | Fix Group | Fix |
|---|-----|----------|-----------|-----|
| 1 | Custom run "Logs" link uses `entity_id` instead of `run_id` | HIGH | FG-4 | One-line fix: `entity_id` → `run_id` |
| 2 | `usePoll` swallows all errors silently, no backoff | MED | FG-1 | Add error counter + exponential backoff in `usePoll` |
| 3 | RunList/VoiceRxRunList don't poll for `pending` status | MED | FG-2 | Extract `isActiveStatus()` helper, use in `hasRunning` |
| 4 | RunDetail polling doesn't start for `pending` runs | MED | FG-3 | Include `pending` in enabled condition |
| 5 | `useSubmitAndRedirect` polling loop not abortable | MED | FG-4 | Use `AbortController`, cancel on unmount via `useRef` |
| 6 | VoiceRx RunDetail has no progress bar | MED | FG-3 | Poll job endpoint, render `RunProgressBar` (shared) |
| 7 | VoiceRx RunDetail has no cancel button | MED | FG-3 | Add cancel handler + button (same pattern as kaira RunDetail) |
| 8 | Event listener leak in `poll()` visibility pause | LOW | FG-1 | Check `signal.aborted` before adding listener |
| 9 | Stable update fingerprint may suppress updates | LOW | FG-2 | Include `errorMessage` in fingerprint |
| 10 | Sequential job polling in JobCompletionWatcher | LOW | FG-4 | `Promise.allSettled` instead of sequential for-of |
| 11 | Duplicate polling between RunList and JobCompletionWatcher | LOW | — | Accepted. RunList needs full data; watcher needs status. Not worth coupling. |
| 12 | Stale data flicker during cancel | LOW | — | Accepted. Timing window is sub-100ms and self-corrects. |
| 13 | 200-run limit truncation | LOW | — | Accepted. Current scale doesn't warrant server pagination. |
| 14 | Race between onClose() and navigate() | LOW | — | Fixed implicitly by FG-4's abortable submit loop rewrite. |
| 15 | Run vs EvalRun type mismatch | LOW | — | Accepted. Backend sends both formats; runtime is correct. Full unification is a separate refactor. |

## Shared Utilities (Created in FG-1/FG-2)

### `isActiveStatus(status: string): boolean`
Centralized check for whether a run status means "still in progress". Used by RunList, VoiceRxRunList, RunDetail, VoiceRxRunDetail.

```typescript
// src/utils/runStatus.ts
export function isActiveStatus(status: string): boolean {
  const s = status.toLowerCase();
  return s === 'running' || s === 'pending';
}
```

This replaces scattered `status === 'running' || status === 'RUNNING'` checks.

## Files Touched (Total: 9)

1. `src/hooks/usePoll.ts` — FG-1
2. `src/services/api/jobPolling.ts` — FG-1
3. `src/utils/runStatus.ts` — FG-2 (NEW, 1 function)
4. `src/features/evalRuns/pages/RunList.tsx` — FG-2, FG-4
5. `src/features/voiceRx/pages/VoiceRxRunList.tsx` — FG-2
6. `src/features/evalRuns/hooks/useStableUpdate.ts` — FG-2
7. `src/features/evalRuns/pages/RunDetail.tsx` — FG-3
8. `src/features/voiceRx/pages/VoiceRxRunDetail.tsx` — FG-3
9. `src/hooks/useSubmitAndRedirect.ts` — FG-4
10. `src/components/JobCompletionWatcher.tsx` — FG-4

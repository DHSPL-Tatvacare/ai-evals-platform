# Frontend Path

## Files to Change

- `src/features/evalRuns/components/NewBatchEvalOverlay.tsx`
- `src/features/evalRuns/components/ThreadScopeStep.tsx`

Only Kaira batch overlay behavior is affected.

## Planned UX Addition

Add one new optional control in Thread Scope step:
- Checkbox label: `Skip previously processed conversations`
- Default: unchecked

When checked, include a backend flag in submitted job params:
- `skip_previously_processed: true`

## Component-Level Plan

## `NewBatchEvalOverlay.tsx`

- Add state: `skipPreviouslyProcessed` (default `false`).
- Pass `skipPreviouslyProcessed` and setter down to `ThreadScopeStep`.
- Include the value in review summary so users can verify their choice before submit.
- Submit payload includes:
  - `skip_previously_processed: skipPreviouslyProcessed || undefined`

This keeps payload minimal and backward compatible.

## `ThreadScopeStep.tsx`

- Extend props with:
  - `skipPreviouslyProcessed: boolean`
  - `onSkipPreviouslyProcessedChange: (checked: boolean) => void`
- Render a checkbox row below existing scope options.
- Add short helper text explaining this only skips thread IDs already evaluated in past Kaira batch runs.

## Notes

- No changes required in Dashboard/RunList wiring because they only open `NewBatchEvalOverlay`.
- No changes required in generic job submit hook (`useSubmitAndRedirect`), since params are pass-through.

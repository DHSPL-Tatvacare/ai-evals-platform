# Phase 4 — Frontend Polish

> UI correctness fixes and robustness improvements. No backend changes.

## F2: No `cancelled` status badge in EvaluatorCard

### Problem

`EvaluatorCard.tsx:97-103` only handles three status states:

```tsx
{isRunning && <span className="h-2 w-2 rounded-full bg-[var(--color-info)] animate-pulse" />}
{latestRun.status === 'completed' && <CheckCircle2 ... />}
{latestRun.status === 'failed' && <XCircle ... />}
```

A cancelled run shows no badge — indistinguishable from "never run."

### Fix

Add a cancelled status badge after the failed check. Use a muted/neutral icon
to distinguish from error:

```tsx
{latestRun.status === 'cancelled' && (
  <Tooltip content="Cancelled">
    <span className="h-2 w-2 rounded-full bg-[var(--text-muted)] opacity-60" />
  </Tooltip>
)}
```

Design reasoning: A small muted dot (not a red X) because cancelled is a user
action, not an error. It should be visible but not alarming. The Tooltip gives
context on hover.

Note: `Tooltip` is already imported (line 2). No new imports needed.

### Files Changed
- `src/features/evals/components/EvaluatorCard.tsx` — lines 97-103

### Test Plan

**Test F2-1: Cancelled run shows badge**
1. Run an evaluator, cancel it mid-run
2. Wait for card to update
3. **Assert:** Card header shows a muted dot (not empty, not error X)
4. **Assert:** Hovering shows "Cancelled" tooltip

**Test F2-2: Other statuses unchanged**
1. Run an evaluator to completion → green check
2. Run an evaluator that fails → red X
3. Running evaluator → blue pulse dot
4. **Assert:** No regressions in existing badges

---

## F3: `syncRuns` swallows errors silently

### Problem

`useEvaluatorRunner.ts:117-119`:

```typescript
} catch {
  // Silently fail — keep whatever we had
}
```

If the eval_runs API fails repeatedly, cards display stale data indefinitely.
No diagnostic information is captured.

### Fix

Add a failure counter and log after repeated failures. Import and use
`logger` (or `console.warn` since this is frontend).

```typescript
const syncFailCountRef = useRef(0);

const syncRuns = useCallback(async () => {
  const t = targetRef.current;
  const listingId = t.listingId || (t.appId !== 'kaira-bot' ? t.entityId : undefined);
  const sessionId = t.sessionId || (t.appId === 'kaira-bot' ? t.entityId : undefined);

  if (!listingId && !sessionId) return;

  try {
    const runs = await fetchEvalRuns({
      listing_id: listingId,
      session_id: sessionId,
      eval_type: 'custom',
    });
    mergeRuns(runs);
    syncFailCountRef.current = 0; // Reset on success
  } catch (err) {
    syncFailCountRef.current += 1;
    if (syncFailCountRef.current === 3) {
      // Log once at 3 failures (not every time to avoid spam)
      console.warn(
        '[useEvaluatorRunner] eval_runs sync failed 3 times consecutively:',
        err instanceof Error ? err.message : err,
      );
    }
  }
}, [mergeRuns]);
```

Design reasoning:
- Log at 3 failures (not 1) to avoid noise from transient network blips
- Log only once at threshold (not every time after) to avoid console spam
- Reset counter on success so intermittent failures don't accumulate
- Keep non-blocking (no toast to user — this is a background sync)

### Files Changed
- `src/features/evals/hooks/useEvaluatorRunner.ts` — lines 102-120

### Test Plan

**Test F3-1: Successful sync resets counter**
1. Open evaluators view, verify initial sync works
2. Check browser console: no warnings

**Test F3-2: Three consecutive failures log once**
1. Disconnect network (or mock API to fail)
2. Wait for 3 sync intervals (18 seconds)
3. **Assert:** Console shows warning with "[useEvaluatorRunner] eval_runs sync failed 3 times"
4. Wait for more intervals
5. **Assert:** Warning NOT repeated (logged only once at threshold)

**Test F3-3: Recovery after failures**
1. Disconnect network, wait for 3 failures
2. Reconnect network
3. **Assert:** Next sync succeeds, counter resets
4. Disconnect again → would need 3 more failures to log again

---

## F4: Implicit ternary for listingId/sessionId fallback

### Problem

`useEvaluatorRunner.ts:105-106`:

```typescript
const listingId = t.listingId || (t.appId !== 'kaira-bot' ? t.entityId : undefined);
const sessionId = t.sessionId || (t.appId === 'kaira-bot' ? t.entityId : undefined);
```

If `appId` is neither `'voice-rx'` nor `'kaira-bot'`, both listingId and sessionId
resolve to undefined (or entityId for neither case depending on the ternary).
This implicit fallback is fragile if new app types are added.

### Fix

Replace with explicit mapping:

```typescript
const syncRuns = useCallback(async () => {
  const t = targetRef.current;

  // Explicit entity resolution — no implicit ternary fallback
  let listingId = t.listingId;
  let sessionId = t.sessionId;

  if (!listingId && !sessionId) {
    // Fallback: use entityId based on known app types
    if (t.appId === 'kaira-bot') {
      sessionId = t.entityId;
    } else {
      // voice-rx and any future listing-based apps
      listingId = t.entityId;
    }
  }

  if (!listingId && !sessionId) return;

  // ... rest unchanged
```

Apply the same pattern to the duplicate at line 184-185 (inside `handleRun`):

```typescript
const listingId = t.listingId || (t.appId === 'kaira-bot' ? undefined : t.entityId);
const sessionId = t.sessionId || (t.appId === 'kaira-bot' ? t.entityId : undefined);
```

Replace with the same explicit pattern.

### Files Changed
- `src/features/evals/hooks/useEvaluatorRunner.ts` — lines 104-106 and 184-185

### Test Plan

**Test F4-1: Voice-rx resolves to listingId**
1. Open a voice-rx listing's evaluators tab
2. **Assert:** Network requests use `listing_id={id}` param (not session_id)

**Test F4-2: Kaira-bot resolves to sessionId**
1. Open kaira-bot evaluators with an active session
2. **Assert:** Network requests use `session_id={id}` param (not listing_id)

**Test F4-3: TypeScript compiles**
1. Run `npx tsc -b`
2. **Assert:** No type errors

---

## F5: Fork passes empty string instead of null for listing ID

### Problem

`KairaBotEvaluatorsView.tsx:112`:

```typescript
const forked = await forkEvaluator(sourceId, '');
```

For kaira-bot, there's no listing — evaluators are app-level. Passing `''`
(empty string) as listing ID is semantically wrong. The backend handles it
(`UUID(listing_id) if listing_id else None`), but an empty string is truthy
in most languages and could cause issues if the backend validation changes.

### Fix

Pass `undefined` instead of empty string:

```typescript
const forked = await forkEvaluator(sourceId, undefined);
```

Check the `forkEvaluator` function signature in `evaluatorsStore.ts:113-117`:

```typescript
forkEvaluator: async (sourceId: string, targetListingId: string) => {
```

The parameter type is `string`, not `string | undefined`. Update the type:

```typescript
forkEvaluator: async (sourceId: string, targetListingId?: string) => {
```

And in the repository call, pass undefined through:

```typescript
const forked = await evaluatorsRepository.fork(sourceId, targetListingId);
```

Check `evaluatorsRepository.fork()` in the API layer to ensure it handles
undefined correctly (doesn't send `listing_id=` in the request body when undefined).

In `src/services/api/evaluatorsApi.ts`, the fork endpoint:
```typescript
fork: async (sourceId: string, targetListingId: string): Promise<EvaluatorDefinition> => {
    return apiRequest(`/api/evaluators/${sourceId}/fork`, {
      method: 'POST',
      body: JSON.stringify({ listing_id: targetListingId }),
    });
```

Update to conditionally include listing_id:

```typescript
fork: async (sourceId: string, targetListingId?: string): Promise<EvaluatorDefinition> => {
    const body: Record<string, unknown> = {};
    if (targetListingId) {
      body.listing_id = targetListingId;
    }
    return apiRequest(`/api/evaluators/${sourceId}/fork`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
```

### Files Changed
- `src/features/kaira/components/KairaBotEvaluatorsView.tsx` — line 112
- `src/stores/evaluatorsStore.ts` — `forkEvaluator` signature (line 113)
- `src/services/api/evaluatorsApi.ts` — `fork()` method

### Test Plan

**Test F5-1: Kaira-bot fork creates app-level evaluator**
1. In kaira-bot, add an evaluator to Registry
2. Fork it from Registry picker
3. **Assert:** Forked evaluator has `listingId: null` (not empty string)
4. **Assert:** Forked evaluator appears in kaira-bot evaluators list

**Test F5-2: Voice-rx fork still passes listing ID**
1. In voice-rx, fork an evaluator from Registry
2. **Assert:** Forked evaluator has `listingId: {listing.id}` (UUID)

**Test F5-3: TypeScript compiles**
1. Run `npx tsc -b`
2. **Assert:** No type errors from optional parameter change

---

## F1: RunAllOverlay shows only 100-char prompt truncation

### Problem

`RunAllOverlay.tsx:160-161`:

```tsx
<p className="text-xs text-[var(--text-muted)] truncate mt-0.5">
  {ev.prompt.slice(0, 100)}{ev.prompt.length > 100 ? '...' : ''}
</p>
```

Before running all evaluators, users can only see the evaluator name and a tiny
prompt snippet. No visibility into model, schema, or output fields configured.

### Fix

Expand the evaluator info card to show:
1. Name (already shown)
2. Prompt snippet (already shown, keep truncation)
3. Output field count (already shown on line 163-165)
4. **Add:** Model name if configured on the evaluator
5. **Add:** Output field keys as tags

```tsx
<div className="flex-1 min-w-0">
  <p className="text-sm font-medium text-[var(--text-primary)]">{ev.name}</p>
  <p className="text-xs text-[var(--text-muted)] truncate mt-0.5">
    {ev.prompt.slice(0, 100)}{ev.prompt.length > 100 ? '...' : ''}
  </p>
  <div className="flex items-center gap-1.5 mt-1 flex-wrap">
    <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--bg-tertiary)] text-[var(--text-muted)]">
      {ev.outputSchema?.length ?? 0} field{(ev.outputSchema?.length ?? 0) !== 1 ? 's' : ''}
    </span>
    {ev.outputSchema?.slice(0, 3).map(f => (
      <span
        key={f.key}
        className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--bg-tertiary)] text-[var(--text-muted)]"
      >
        {f.key}
      </span>
    ))}
    {(ev.outputSchema?.length ?? 0) > 3 && (
      <span className="text-[10px] text-[var(--text-muted)]">
        +{(ev.outputSchema?.length ?? 0) - 3}
      </span>
    )}
  </div>
</div>
```

This replaces the existing `<p>` for output field count (lines 163-165) with
tag-style display showing the first 3 field keys plus overflow count.

Design reasoning:
- Shows concrete field names (e.g., `accuracy_score`, `reasoning`) not just count
- Max 3 tags to avoid overflow in the overlay
- Tiny chip styling consistent with design system
- No model display (evaluators don't store model — model comes from global settings)

### Files Changed
- `src/features/voiceRx/components/RunAllOverlay.tsx` — lines 158-166

### Test Plan

**Test F1-1: Output field tags visible**
1. Create an evaluator with 5 output fields
2. Open RunAllOverlay
3. **Assert:** See evaluator name, prompt snippet, first 3 field keys as tags, "+2" overflow

**Test F1-2: Zero output fields**
1. Create evaluator with no output fields
2. Open RunAllOverlay
3. **Assert:** Shows "0 fields" tag, no field key tags

**Test F1-3: Exactly 3 fields**
1. Create evaluator with 3 output fields
2. Open RunAllOverlay
3. **Assert:** All 3 field keys shown, no "+N" overflow

---

## Phase 4 Completion Checklist

- [ ] F2 cancelled badge added and tested
- [ ] F3 sync failure logging added and tested
- [ ] F4 explicit entity resolution and tested
- [ ] F5 fork null handling and tested
- [ ] F1 overlay info expanded and tested
- [ ] `npx tsc -b` passes
- [ ] `npm run lint` passes (or targeted lint on changed files)
- [ ] Evaluators tab loads correctly for voice-rx
- [ ] Evaluators tab loads correctly for kaira-bot
- [ ] RunAllOverlay opens, selects, and submits correctly
- [ ] Individual evaluator run works from card
- [ ] Merge to `main`

---

## Full Project Completion Checklist

After all 4 phases are merged:

- [ ] All 15 issues addressed (B1-B11, F1-F5, X2)
- [ ] `docker compose up --build` — full stack starts
- [ ] Voice-rx upload evaluation: end-to-end success
- [ ] Voice-rx API evaluation: end-to-end success
- [ ] Custom evaluator: run single, run all batch
- [ ] Cancel mid-evaluation: status correctly "cancelled"
- [ ] Kaira-bot evaluator: run single
- [ ] No console errors during all flows
- [ ] No TypeScript errors: `npx tsc -b`
- [ ] No lint errors: `npm run lint`

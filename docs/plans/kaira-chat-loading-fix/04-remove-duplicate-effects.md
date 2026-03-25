# Step 4: Remove Duplicate Auto-Select Effects

## Goal

Clean up redundant session-selection logic in `ChatView` that duplicates what
is now handled atomically in the store (step 2). Also update ChatView's own
loading guards to use the new granular flags.

## File: `src/features/kaira/components/ChatView.tsx`

### 4a. Remove the auto-select-first-session effect (~lines 134-138)

Delete this block:

```ts
useEffect(() => {
  if (!sessionId && userId && isSessionsLoaded && sessions.length > 0 && !currentSession && !isLoading) {
    selectSession(sessions[0].id);
  }
}, [/* deps */]);
```

This is now handled in `loadSessions` (step 2).

### 4b. Update the loading spinner gate (~lines 157-164)

Replace `isLoading` with the granular flags:

```ts
// Before:
if (!isSessionsLoaded || (isLoading && messages.length === 0 && !currentSession)) {
  return <Spinner size="lg" />;
}

// After:
if (!isSessionsLoaded || isLoadingSessions || (isLoadingMessages && messages.length === 0)) {
  return <Spinner size="lg" />;
}
```

This is now a safety net -- `KairaBotTabView`'s `isReady` gate (step 3)
should prevent ChatView from rendering in a loading state at all. But
defense-in-depth is good.

### 4c. Update destructured values from `useKairaChat`

Wherever ChatView pulls `isLoading` from the hook, replace with
`isLoadingSessions` and `isLoadingMessages`.

### 4d. Review the auto-create effect (~lines 92-124)

The auto-create effect (creates a new session when sessions list is empty)
should remain -- it handles the genuinely-empty-user case. But verify its
conditions still work with the new flags:

```ts
// This should still reference isSessionsLoaded and isCreatingSession.
// isLoading references need to change to isLoadingSessions.
```

### 4e. Review the existing-sessions tracking effect (~lines 85-90)

```ts
useEffect(() => {
  if (isSessionsLoaded && sessions.length > 0) {
    hasAutoCreatedRef.current = true;
  }
}, [isSessionsLoaded, sessions.length]);
```

This can stay as-is -- it only reads `isSessionsLoaded`.

## File: `src/features/kaira/components/TraceAnalysisView.tsx`

### 4f. No changes needed

TraceAnalysisView receives `messages` as props from `KairaBotTabView`.
With the tightened `isReady` gate (step 3), it will never receive an empty
messages array for a session that has messages. The existing
`if (messages.length === 0)` check correctly handles genuinely empty sessions.

## File: `src/features/kaira/components/KairaBotEvaluatorsView.tsx`

### 4g. Remove or guard the lazy evaluator-loading effect (~lines 91-95)

Since step 2d now pre-fetches evaluators in parallel during `loadSessions`,
the `useEffect` in `KairaBotEvaluatorsView` that calls `loadAppEvaluators`
is now a redundant backup:

```ts
// Current (lines 91-95):
useEffect(() => {
  if (!isLoaded || currentAppId !== 'kaira-bot') {
    loadAppEvaluators('kaira-bot');
  }
}, [isLoaded, currentAppId, loadAppEvaluators]);
```

**Option A (recommended):** Keep it as a safety net but it will be a no-op
because `loadAppEvaluators` checks `isLoaded` internally. No code change
needed -- it just won't trigger a redundant fetch anymore.

**Option B:** Remove it entirely and rely on the pre-fetch from step 2d.
Simpler but less defensive.

Either way, the flash on first Evaluators tab click is eliminated because
evaluator data arrives before the tab renders.

## Verification

- `npx tsc -b` should pass with no errors.
- `npm run lint` should pass.
- Load all 3 tab URLs:
  - `http://localhost:5173/kaira/chat?tab=chat` -- no flash
  - `http://localhost:5173/kaira/chat?tab=traces` -- no flash
  - `http://localhost:5173/kaira/chat?tab=evaluators` -- no flash
- Test edge cases:
  - Delete all sessions, refresh -- should show auto-create flow cleanly.
  - Click "New" in sidebar -- should create session without flash.

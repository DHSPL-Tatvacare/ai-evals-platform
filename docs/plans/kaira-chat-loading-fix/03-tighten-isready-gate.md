# Step 3: Tighten the `isReady` Gate in KairaBotTabView

## Goal

Update the `isReady` check to use the new granular loading flags so the
spinner stays visible until data is fully settled. No tab content should
render until sessions are loaded, a session is selected (if any exist),
and its messages are loaded.

## File: `src/app/pages/kaira/KairaBotTabView.tsx`

### 3a. Update destructured values from `useKairaChat`

Replace:

```ts
const {
  currentSession,
  messages,
  isSessionsLoaded,
  isLoading,
  sessions,
  selectSession,
} = useKairaChat();
```

With:

```ts
const {
  currentSession,
  messages,
  isSessionsLoaded,
  isLoadingSessions,
  isLoadingMessages,
  sessions,
  selectSession,
} = useKairaChat();
```

### 3b. Update the `isReady` computation

Replace:

```ts
const isReady =
  isSessionsLoaded &&
  !isLoading &&
  (sessions.length === 0 || currentSession !== null);
```

With:

```ts
const isReady =
  isSessionsLoaded &&
  !isLoadingSessions &&
  !isLoadingMessages &&
  (sessions.length === 0 || currentSession !== null);
```

This ensures:
- We wait for session fetch to complete (`isSessionsLoaded && !isLoadingSessions`).
- We wait for message fetch to complete (`!isLoadingMessages`).
- We wait for a session to be selected if sessions exist (`currentSession !== null`).

After step 2, the auto-select happens inline during `loadSessions`, so
`isLoadingSessions` stays true until both sessions and messages are loaded.
The `!isLoadingMessages` is a safety net for manual `selectSession` calls.

### 3c. Remove the auto-select useEffect (lines 31-48)

Delete this entire block:

```ts
useEffect(() => {
  if (
    userId &&
    isSessionsLoaded &&
    !isLoading &&
    sessions.length > 0 &&
    !currentSession
  ) {
    selectSession(sessions[0].id);
  }
}, [
  userId,
  isSessionsLoaded,
  isLoading,
  sessions,
  currentSession,
  selectSession,
]);
```

This is now handled atomically in `loadSessions` (step 2). The `selectSession`
import can also be removed if no longer used elsewhere in this file.

### 3d. Clean up unused imports

If `useEffect` is no longer used in this file (only `useCallback` remains),
update the import accordingly. Same for `selectSession` from the hook.

## Verification

- Load all 3 tab URLs. Spinner should display until content is ready.
- No flash of empty state on any tab.
- `npx tsc -b` should pass (or only show errors from step 4 files).

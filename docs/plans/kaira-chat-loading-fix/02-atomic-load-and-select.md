# Step 2: Atomic Load-and-Select in `loadSessions`

## Goal

Eliminate the intermediate render between "sessions loaded" and "first session
selected". After fetching sessions, if no session is currently selected and
sessions exist, immediately select the first one and load its messages -- all
within the same async call, before returning control to React.

## File: `src/stores/chatStore.ts`

### 2a. Extend `loadSessions` to accept an optional auto-select hint

```ts
loadSessions: async (appId: AppId, opts?: { userId?: string }) => {
```

The `userId` is needed to know whether auto-select should happen (mirrors the
condition currently in KairaBotTabView's useEffect).

### 2b. After fetching sessions, auto-select inline

At the end of the `try` block in `loadSessions`, after setting sessions and
`isSessionsLoaded`, add:

```ts
// Auto-select first session if none selected and sessions exist
const updatedState = get();
if (
  opts?.userId &&
  updatedState.sessions[appId].length > 0 &&
  !updatedState.currentSessionId
) {
  const firstSessionId = updatedState.sessions[appId][0].id;
  // Inline message loading -- no intermediate render
  set({ currentSessionId: firstSessionId, isLoadingMessages: true });
  try {
    const messages = await chatMessagesRepository.getBySession(firstSessionId);
    set({ messages, isLoadingMessages: false });
  } catch {
    set({ messages: [], isLoadingMessages: false });
  }
}
```

Key point: this happens in the same async function, so React only sees the
final state (sessions loaded + first session selected + messages loaded) in
one batched update.

### 2c. Set `isLoadingSessions: false` AFTER the auto-select block

Move the `isLoadingSessions: false` set call to after the auto-select logic,
so the loading spinner stays visible until everything is truly ready:

```ts
// Final state -- everything is settled
set({ isLoadingSessions: false });
```

### 2d. Pre-fetch evaluators in parallel (fire-and-forget)

Voice Rx pre-fetches evaluators in parallel with listing data on mount
(`ListingPage.tsx:63`). Kaira currently doesn't -- evaluators are only
fetched when the Evaluators tab mounts, causing a flash on first tab click.

At the top of the `loadSessions` function (before the sessions fetch), add:

```ts
// Pre-fetch app-level evaluators in parallel — fire and forget.
// Mirrors Voice Rx pattern (ListingPage.tsx:63) so evaluator data
// is ready before the user clicks the Evaluators tab.
if (appId === 'kaira-bot') {
  import('@/stores/evaluatorsStore').then(({ useEvaluatorsStore }) => {
    useEvaluatorsStore.getState().loadAppEvaluators(appId);
  });
}
```

Or more directly (if circular imports aren't an issue):

```ts
import { useEvaluatorsStore } from '@/stores/evaluatorsStore';

// Inside loadSessions, before the sessions fetch:
useEvaluatorsStore.getState().loadAppEvaluators(appId);
```

This runs in parallel with the session fetch. The evaluators store has its
own `isLoaded` guard so duplicate calls are safe. By the time the user clicks
the Evaluators tab, data is already there.

---

## File: `src/hooks/useKairaChat.ts`

### 2e. Pass userId to loadSessions

Update the auto-load effect to pass the userId:

```ts
useEffect(() => {
  if (appId === 'kaira-bot') {
    storeLoadSessions(appId, { userId });
  }
}, [appId, userId, storeLoadSessions]);
```

Where `userId` comes from `useKairaBotSettings` (already available in the
component tree -- but the hook needs to receive or import it). The cleanest
approach: have `useKairaChat` accept an optional `userId` param, or read it
from the settings store directly inside the hook.

---

## What this replaces

This replaces the separate `useEffect` in `KairaBotTabView` (lines 31-48)
that currently does:

```ts
useEffect(() => {
  if (userId && isSessionsLoaded && !isLoading && sessions.length > 0 && !currentSession) {
    selectSession(sessions[0].id);
  }
}, [userId, isSessionsLoaded, isLoading, sessions, currentSession, selectSession]);
```

That effect fires one render cycle too late -- sessions are loaded, React
renders with `currentSession=null`, then the effect fires and triggers
selectSession. The new approach avoids this entirely.

## Verification

- Load `http://localhost:5173/kaira/chat?tab=chat` -- spinner should show
  until both sessions AND first session's messages are loaded, then content
  appears with no flash.
- Console should show `loadSessions` completing with auto-select inline.

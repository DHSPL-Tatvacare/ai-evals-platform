# Step 5: Add `chatId` Route Path Param to the URL

## Goal

Reflect the selected chat session in the URL as a route path param, consistent
with how Voice Rx listings (`/listing/:id`), runs (`/runs/:runId`), and
threads (`/kaira/threads/:threadId`) work across the codebase.

**Before:** `/kaira/chat?tab=chat` (same URL for all sessions)
**After:** `/kaira/chat/abc-123?tab=chat` (unique URL per session)

---

## File: `src/config/routes.ts`

### 5a. Add a chat session route builder

Update the `kaira` block:

```ts
kaira: {
  home: '/kaira',
  chat: '/kaira/chat',                              // keep for base/no-session URL
  chatSession: (chatId: string) => `/kaira/chat/${chatId}`,  // new
  // ... rest unchanged
},
```

This mirrors the existing pattern: `listing: (id: string) => /listing/${id}`.

---

## File: `src/app/Router.tsx`

### 5b. Add a parameterized route

Add a new route alongside the existing static one:

```tsx
{/* Kaira Bot routes */}
<Route path={routes.kaira.home} element={<Navigate to={routes.kaira.dashboard} replace />} />
<Route path="/kaira/chat/:chatId" element={<KairaBotHomePage />} />   {/* NEW -- must be before the static route */}
<Route path={routes.kaira.chat} element={<KairaBotHomePage />} />     {/* existing -- handles /kaira/chat with no session */}
```

Both routes render the same `KairaBotHomePage`. The parameterized route
matches when a chatId is present; the static route matches when there's
no chatId (new user, or navigating to chat without a specific session).

---

## File: `src/app/pages/kaira/KairaBotTabView.tsx`

### 5c. Read `chatId` from route params

```ts
import { useParams, useSearchParams, useNavigate } from 'react-router-dom';

// Inside the component:
const { chatId: chatIdFromUrl } = useParams<{ chatId?: string }>();
const navigate = useNavigate();
```

### 5d. Pass `chatIdFromUrl` to the hook

```ts
const { ... } = useKairaChat({ chatIdHint: chatIdFromUrl });
```

### 5e. Sync URL when session changes

When `currentSession` changes (user clicks sidebar, auto-select, etc.),
navigate to the correct URL:

```ts
useEffect(() => {
  if (currentSession && currentSession.id !== chatIdFromUrl) {
    const tab = searchParams.get('tab') || 'chat';
    navigate(
      `${routes.kaira.chatSession(currentSession.id)}?tab=${tab}`,
      { replace: !chatIdFromUrl }  // replace on initial auto-select, push on explicit nav
    );
  }
}, [currentSession, chatIdFromUrl, searchParams, navigate]);
```

- `replace: true` when there's no `chatIdFromUrl` (initial load auto-selected
  first session -- don't add a back-history entry).
- `replace: false` (push) when user explicitly switches sessions via sidebar
  (so back button works).

### 5f. Update `handleTabChange` to use navigate

```ts
const handleTabChange = useCallback(
  (tabId: string) => {
    if (currentSession) {
      navigate(`${routes.kaira.chatSession(currentSession.id)}?tab=${tabId}`);
    } else {
      navigate(`${routes.kaira.chat}?tab=${tabId}`);
    }
  },
  [currentSession, navigate],
);
```

### 5g. Remove `setSearchParams` usage

Since navigation is now handled by `navigate()` with full paths,
`useSearchParams` is only needed for reading `tab`. The setter can be removed
if no other usage remains.

---

## File: `src/hooks/useKairaChat.ts`

### 5h. Accept `chatIdHint` option

```ts
export function useKairaChat(opts?: { chatIdHint?: string }): UseKairaChatReturn {
```

### 5i. Pass `chatIdHint` to store's `loadSessions`

```ts
useEffect(() => {
  if (appId === 'kaira-bot') {
    storeLoadSessions(appId, { userId, chatIdHint: opts?.chatIdHint });
  }
}, [appId, userId, opts?.chatIdHint, storeLoadSessions]);
```

---

## File: `src/stores/chatStore.ts`

### 5j. Accept `chatIdHint` in `loadSessions` options

Extend from step 2:

```ts
loadSessions: async (appId: AppId, opts?: { userId?: string; chatIdHint?: string }) => {
```

### 5k. Prefer `chatIdHint` over `sessions[0]` in auto-select

In the auto-select block added in step 2:

```ts
const targetSessionId = opts?.chatIdHint
  ? (updatedState.sessions[appId].find(s => s.id === opts.chatIdHint)?.id
     ?? updatedState.sessions[appId][0]?.id)
  : updatedState.sessions[appId][0]?.id;
```

If `chatIdHint` matches an existing session, select it. Otherwise fall back
to `sessions[0]`.

---

## Sidebar session click handler

### 5l. Update session click to use `navigate`

Find the sidebar component that renders the session list buttons. Update the
click handler to navigate to the session URL instead of (or in addition to)
calling `selectSession` directly:

```ts
import { useNavigate } from 'react-router-dom';
import { routes } from '@/config/routes';

const navigate = useNavigate();

const handleSessionClick = (sessionId: string) => {
  navigate(routes.kaira.chatSession(sessionId));
};
```

The URL change triggers `KairaBotTabView` to re-read `chatIdFromUrl` from
`useParams`, which flows through to `selectSession`. This keeps the URL as
the single source of truth.

Alternatively, if the sidebar already calls `selectSession` directly, the
URL-sync effect in 5e will update the URL reactively. Either approach works,
but navigate-first is cleaner.

---

## Edge cases to handle

1. **`/kaira/chat` with no chatId**: Auto-select first session (step 2),
   then redirect to `/kaira/chat/<first-session-id>?tab=chat` via effect 5e.

2. **`/kaira/chat/nonexistent-id`**: Store's `loadSessions` can't find the
   hinted session, falls back to `sessions[0]`, URL is corrected via effect 5e.

3. **No sessions at all (new user)**: Route stays at `/kaira/chat`, ChatView
   auto-creates a session, then URL updates to the new session ID.

4. **"New" button in sidebar**: Creates a session, sets it as current, URL
   updates via effect 5e.

5. **Delete current session**: After deletion, if another session exists,
   select it and update URL. If no sessions remain, navigate to `/kaira/chat`.

---

## Verification

- Load `http://localhost:5173/kaira/chat` -- should redirect to
  `/kaira/chat/<first-session-id>?tab=chat`.
- Click a different session in sidebar -- URL path changes to new session ID.
- Copy the URL with session ID, open in new tab -- same session loads.
- Refresh the page -- same session is restored (not falling back to first).
- Browser back button -- navigates to the previously viewed session.
- Load `/kaira/chat/nonexistent-id` -- gracefully falls back to first session.
- Switch tabs -- URL changes to `?tab=traces` etc. while keeping the chatId
  in the path.
- Consistent with existing patterns: `/listing/:id`, `/runs/:runId`,
  `/kaira/threads/:threadId`.

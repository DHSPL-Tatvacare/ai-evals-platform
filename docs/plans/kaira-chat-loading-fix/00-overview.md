# Kaira Chat Loading Fix -- Plan Overview

## Issues

1. **Flash of empty state** on all 3 tabs (Chat / Traces / Evaluators) during initial mount.
   Users see the empty/placeholder state for a sub-second flicker before real data renders.

2. **No chatID in the URL** -- all chat sessions share `/kaira/chat?tab=<tab>`.
   Cannot bookmark, share, or refresh to a specific session.
   Fix uses a route path param (`/kaira/chat/:chatId`) consistent with
   Voice Rx listings (`/listing/:id`), runs (`/runs/:runId`), and
   threads (`/kaira/threads/:threadId`).

## Root Causes

- A 3-phase loading waterfall exposes intermediate states to React renders:
  `loadSessions` -> auto-select effect -> `selectSession` (fetches messages).
  Each phase triggers a re-render with partial data visible to tab components.
- `isLoading` is a single shared boolean for both session loading AND message loading,
  causing ambiguous readiness checks.
- Duplicate auto-select-first-session effects in `KairaBotTabView` and `ChatView`.
- Route `/kaira/chat` has no dynamic segment or query param for session identity.

## Files Affected

| File | Role |
|------|------|
| `src/stores/chatStore.ts` | Zustand store -- loading flags, loadSessions, selectSession |
| `src/hooks/useKairaChat.ts` | Hook -- effect triggers, derived state |
| `src/app/pages/kaira/KairaBotTabView.tsx` | Tab orchestrator -- isReady gate, auto-select effect |
| `src/features/kaira/components/ChatView.tsx` | Chat tab -- own loading gates, duplicate auto-select |
| `src/features/kaira/components/TraceAnalysisView.tsx` | Traces tab -- empty-state check |
| `src/features/kaira/components/KairaBotEvaluatorsView.tsx` | Evaluators tab -- own evaluator loading |
| `src/config/routes.ts` | Route definitions |
| `src/app/Router.tsx` | Route registration -- new `/kaira/chat/:chatId` route |

## Execution Sequence

Execute the steps in order. Each step has its own file:

| Step | File | Description |
|------|------|-------------|
| 1 | `01-split-isloading.md` | Split `isLoading` into granular flags |
| 2 | `02-atomic-load-and-select.md` | Move auto-select into loadSessions (same async tick) |
| 3 | `03-tighten-isready-gate.md` | Fix the isReady gate in KairaBotTabView |
| 4 | `04-remove-duplicate-effects.md` | Remove redundant auto-select effects |
| 5 | `05-add-chatid-to-url.md` | Add chatId as route path param (`/kaira/chat/:chatId`) |
| 6 | `06-cleanup-console-logs.md` | Remove debug console.log statements |

## Verification

After each step, load the following URLs and confirm no flash of empty state:
- `http://localhost:5173/kaira/chat?tab=chat`
- `http://localhost:5173/kaira/chat?tab=traces`
- `http://localhost:5173/kaira/chat?tab=evaluators`

After step 5, also verify:
- Navigating to `/kaira/chat` redirects to `/kaira/chat/<session-id>?tab=chat`.
- URL path updates with chatId when selecting a session from sidebar.
- Refreshing the page restores the correct session.
- Browser back/forward navigates between sessions.
- `/kaira/chat/nonexistent-id` falls back gracefully to first session.

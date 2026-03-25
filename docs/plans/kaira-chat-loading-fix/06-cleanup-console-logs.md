# Step 6: Clean Up Debug Console Logs

## Goal

Remove verbose debug `console.log` statements that were added during
development. These pollute the browser console and are no longer needed
once the loading flow is stabilized.

## Files and lines to clean

### `src/stores/chatStore.ts`

Remove or convert to `logger.debug(...)` (from `@/utils/logger`):

- Line ~70: `console.log('[chatStore] loadSessions called for appId:', appId);`
- Line ~74: `console.log('[chatStore] Sessions already loaded for', appId);`
- Line ~79: `console.log('[chatStore] Setting isLoading: true');`
- Line ~82: `console.log('[chatStore] Fetching sessions from repository...');`
- Line ~86: `console.log('[chatStore] Fetched sessions:', sessions.length, 'sessions');`
- Line ~99: `console.log('[chatStore] loadSessions completed successfully');`
- Line ~140: `console.log('[chatStore] createSession called - ...');`
- Line ~145: `console.log('[chatStore] Session creation already in progress, skipping');`
- Line ~149: `console.log('[chatStore] Setting isCreatingSession: true');`
- Line ~154: `console.log('[chatStore] Creating session in repository...');`
- Line ~161: `console.log('[chatStore] Session created with id:', session.id);`

### `src/hooks/useKairaChat.ts`

- Line ~69: `console.log('[useKairaChat] Effect triggered - appId:', appId);`
- Line ~71: `console.log('[useKairaChat] Calling loadSessions for kaira-bot');`

### `src/features/kaira/components/ChatView.tsx`

- Line ~62: `console.log('[ChatView] Auto-create check:', ...);`
- Line ~100: `console.log('[ChatView] Render state:', ...);`

### `src/stores/promptsStore.ts`

- Line ~10: `console.log('[PromptsStore] Loading prompts for ...');`
- Line ~14: `console.log('[PromptsStore] Loaded N prompts:', ...);`

### `src/app/Router.tsx`

- Line ~22: `console.log('[Router] Current path:', ...);`

## Approach

- **Keep** `console.error(...)` calls -- those are useful for diagnosing failures.
- **Remove** all `console.log(...)` debug statements listed above.
- If you want to retain any for diagnostics, convert them to use the project's
  `logger` utility (`import { logger } from '@/utils/logger'`) with `logger.debug(...)`.
  These are stripped in production builds.

## Verification

- `npm run lint` -- should pass.
- `npx tsc -b` -- should pass.
- Open browser console on `http://localhost:5173/kaira/chat` -- should be
  clean, no noisy `[chatStore]` / `[useKairaChat]` / `[ChatView]` logs.
- Error logging should still work (simulate a network failure and verify
  errors appear in console).

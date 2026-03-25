# Phase 6 — Frontend Data Scoping

All stores and API modules are updated to work within the authenticated user's context. The backend enforces scoping — the frontend doesn't need to pass `tenant_id` or `user_id` as query params because the backend reads them from the JWT. This phase is mostly about removing stale patterns and ensuring stores initialize correctly after auth.

## Key Principle

**The backend reads `tenant_id` and `user_id` from the JWT token.** The frontend does NOT pass these as query parameters. The `Authorization: Bearer` header (added in Phase 5) is sufficient. This means most API modules need zero changes to their URL construction — the backend middleware handles scoping.

---

## 6.1 Stores — Initialization Order

### Current Problem

Stores call `loadSettings()` in `Providers.tsx` on mount, before auth is resolved.

### Solution

All store `load*()` methods are called ONLY after auth resolves:

```typescript
// Providers.tsx
useEffect(() => {
  useAuthStore.getState().loadUser().then(() => {
    if (!useAuthStore.getState().isAuthenticated) return;
    // Now safe to load stores — all API calls will have auth headers
    useLLMSettingsStore.getState().loadSettings();
    useAppSettingsStore.getState().loadSettings();
    // etc.
  });
}, []);
```

### Store Reset on Logout

When the user logs out, all stores must be reset to prevent data leakage:

```typescript
// authStore.ts logout()
logout: async () => {
  await authApi.logout();
  localStorage.removeItem('accessToken');

  // Reset all stores
  useListingsStore.getState().reset();
  useSchemasStore.getState().reset();
  usePromptsStore.getState().reset();
  useEvaluatorsStore.getState().reset();
  useChatStore.getState().reset();
  useLLMSettingsStore.getState().reset();
  useAppSettingsStore.getState().reset();
  useJobTrackerStore.getState().reset();
  useCrossRunStore.getState().reset();

  set({ user: null, accessToken: null, isAuthenticated: false });
}
```

Each store needs a `reset()` action that returns state to initial values.

---

## 6.2 Store-by-Store Analysis

### `appStore.ts` — Minor Change

- **Current:** Stores `currentApp` (voice-rx/kaira-bot)
- **Change:** Add `reset()` method. No other changes — app selection is independent of auth.

### `llmSettingsStore.ts` — No API Changes

- **Current:** Calls `settingsRepository.get('', 'llm-settings')` and `settingsRepository.set('', 'llm-settings', value)`
- **Change:** No URL changes needed. Backend now scopes the `settings` table by JWT tenant/user. The store continues to call the same endpoints — the backend filters differently.
- **Add:** `reset()` method.

### `appSettingsStore.ts` — No API Changes

- **Current:** Calls `settingsRepository.get(appId, 'api-credentials')`
- **Change:** Same — backend scopes by JWT. No frontend changes to API calls.
- **Add:** `reset()` method.

### `listingsStore.ts` — No API Changes

- **Current:** Calls `listingsRepository.getAll(appId)`
- **Change:** Backend filters by tenant/user from JWT. Frontend unchanged.
- **Add:** `reset()` method.

### `schemasStore.ts` — No API Changes

- **Add:** `reset()` method.

### `promptsStore.ts` — No API Changes

- **Add:** `reset()` method.

### `evaluatorsStore.ts` — No API Changes

- **Add:** `reset()` method.

### `chatStore.ts` — No API Changes

- **Current:** Passes `appId` to chatApi calls
- **Change:** Backend scopes by JWT. The `externalUserId` field in chat sessions is for the Kaira test user, NOT the authenticated user — keep it as-is.
- **Add:** `reset()` method.

### `crossRunStore.ts` — No API Changes

- **Add:** `reset()` method.

### `jobTrackerStore.ts` — No API Changes

- **Add:** `reset()` method (clear tracked jobs).

### `globalSettingsStore.ts` — No Change

- **Current:** Frontend-only (localStorage). Theme, timeouts.
- **Change:** None — not backed by API.

### `uiStore.ts` — No Change

- **Change:** None — UI-only state.

### `miniPlayerStore.ts` — No Change

- **Change:** None — UI-only state.

### `taskQueueStore.ts` — No Change

- **Change:** None — in-memory task queue.

---

## 6.3 API Modules — Analysis

Since the backend reads auth from the JWT header, most API modules need NO changes to their URL patterns. The key change was in `client.ts` (Phase 5).

### Modules Requiring NO Changes

| Module | Reason |
|--------|--------|
| `listingsApi.ts` | Already passes `app_id`; backend adds tenant/user filter |
| `filesApi.ts` | Already passes file ID; backend checks ownership |
| `promptsApi.ts` | Already passes `app_id`; backend adds tenant/user filter |
| `schemasApi.ts` | Same |
| `evaluatorsApi.ts` | Same |
| `chatApi.ts` | Already passes `app_id`; backend adds tenant/user filter |
| `jobsApi.ts` | Backend injects tenant/user into job params |
| `evalRunsApi.ts` | Already passes `app_id`; backend adds tenant/user filter |
| `settingsApi.ts` | Already passes `app_id + key`; backend adds tenant/user filter |
| `tagsApi.ts` | Already passes `app_id`; backend adds tenant/user filter |
| `historyApi.ts` | Already passes `app_id`; backend adds tenant/user filter |
| `reportsApi.ts` | Already passes `app_id`; backend adds tenant/user filter |
| `adversarialConfigApi.ts` | Backend scopes config by JWT |

### One Module Requiring Change

**`jobsApi.ts`** — Remove any client-side `user_id` injection:

```typescript
// Old (if any frontend code manually sets user_id in params):
params: { ...jobParams, user_id: 'default' }

// New: Don't pass user_id — backend injects from JWT
params: { ...jobParams }
```

---

## 6.4 Type Changes

### Remove `user_id: string = "default"` from Types

Every type that has `userId?: string` should keep the field but remove the default:

```typescript
// Old
export interface Listing {
  // ...
  userId?: string;
}

// New
export interface Listing {
  // ...
  userId: string;    // Always present — UUID string
  tenantId: string;  // Always present — UUID string
}
```

### Files to Modify

- `src/types/listing.types.ts` — add `tenantId`
- `src/types/evalRuns.ts` — add `tenantId`
- `src/types/chat.types.ts` — add `tenantId` to session/message
- `src/types/evaluator.types.ts` — add `tenantId`
- `src/types/settings.types.ts` — add `tenantId`
- Any other type files with `userId`

**Note:** These type changes are cosmetic — the backend already returns these fields. The frontend just needs to type them correctly.

---

## 6.5 Component Changes

### Components That Display `userId` — Update

If any component shows the user_id (e.g., in eval run details, history), it now shows a UUID instead of "default". Consider showing the user's display name instead:

```typescript
// If needed, create a user display helper
function useUserDisplayName(userId: string): string {
  const currentUser = useAuthStore((s) => s.user);
  if (currentUser?.id === userId) return currentUser.displayName;
  return userId; // For other users, show ID (or fetch name via admin API)
}
```

### Components That Pass `user_id` in Job Params — Remove

Check all components that submit jobs (evaluation overlays, batch runners). Remove any manual `user_id` injection — the backend handles it.

Search pattern: `user_id` in component files that call `jobsApi.submit()` or `submitAndPollJob()`.

---

## 6.6 Job Polling (`src/services/api/jobPolling.ts`)

### No Changes Needed

`submitAndPollJob()` calls `jobsApi.submit()` and `jobsApi.get()`. Both now include auth headers via `client.ts`. The backend filters by JWT.

---

## 6.7 Files Summary

| File | Action | Changes |
|------|--------|---------|
| `src/stores/authStore.ts` | CREATED (Phase 5) | Reset logic for all stores |
| `src/stores/appStore.ts` | MODIFY | Add `reset()` |
| `src/stores/llmSettingsStore.ts` | MODIFY | Add `reset()` |
| `src/stores/appSettingsStore.ts` | MODIFY | Add `reset()` |
| `src/stores/listingsStore.ts` | MODIFY | Add `reset()` |
| `src/stores/schemasStore.ts` | MODIFY | Add `reset()` |
| `src/stores/promptsStore.ts` | MODIFY | Add `reset()` |
| `src/stores/evaluatorsStore.ts` | MODIFY | Add `reset()` |
| `src/stores/chatStore.ts` | MODIFY | Add `reset()` |
| `src/stores/crossRunStore.ts` | MODIFY | Add `reset()` |
| `src/stores/jobTrackerStore.ts` | MODIFY | Add `reset()` |
| `src/app/Providers.tsx` | MODIFY | Auth-first initialization |
| `src/types/*.ts` | MODIFY | Add `tenantId`, make `userId` required |
| Job-submitting components | MODIFY | Remove manual user_id in params |

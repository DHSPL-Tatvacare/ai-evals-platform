# Phase 4: Frontend Auth

## Goal

Add login/register UI, protect all routes, inject cookies in API calls, and gate store hydration on authentication. After this phase, the frontend is fully auth-aware.

**Prerequisite:** Phase 1 complete (auth endpoints available). Can proceed in parallel with Phases 2-3.

---

## 4.1 — API Client: Cookie Credentials

**File:** `src/services/api/client.ts`

### Change

Add `credentials: 'include'` to all fetch calls. This tells the browser to send httpOnly cookies with every request.

```typescript
// In apiRequest:
const response = await fetch(`${path}`, {
  ...options,
  credentials: 'include',   // ADD THIS
  headers: { 'Content-Type': 'application/json', ...options?.headers },
});

// In apiUpload:
const response = await fetch(path, {
  method: 'POST',
  credentials: 'include',   // ADD THIS
  body: formData,
});

// In apiDownload:
const response = await fetch(path, {
  credentials: 'include',   // ADD THIS
});
```

### 401 Interception

Add a response interceptor pattern in `apiRequest`:

```typescript
if (response.status === 401) {
  // Try token refresh
  const refreshed = await attemptTokenRefresh();
  if (refreshed) {
    // Retry original request once
    return fetch(path, { ...options, credentials: 'include' });
  }
  // Refresh failed — redirect to login
  useAuthStore.getState().handleSessionExpired();
  throw new ApiError('Session expired', 401, {});
}
```

The `attemptTokenRefresh` function calls `POST /api/auth/refresh` — since the refresh token is also in a httpOnly cookie, the browser sends it automatically.

---

## 4.2 — Auth API Repository

**File:** `src/services/api/authApi.ts` (new)

```typescript
export const authApi = {
  async register(email: string, password: string, name: string): Promise<User> {
    return apiRequest('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password, name }),
    });
  },

  async login(email: string, password: string): Promise<User> {
    return apiRequest('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
  },

  async logout(): Promise<void> {
    await apiRequest('/api/auth/logout', { method: 'POST' });
  },

  async getMe(): Promise<User> {
    return apiRequest('/api/auth/me');
  },

  async updateProfile(data: { name?: string; currentPassword?: string; newPassword?: string }): Promise<User> {
    return apiRequest('/api/auth/me', {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  async refreshToken(): Promise<User> {
    return apiRequest('/api/auth/refresh', { method: 'POST' });
  },
};
```

**Export from `src/services/api/index.ts`** barrel.

---

## 4.3 — Auth Store

**File:** `src/stores/authStore.ts` (new)

```typescript
interface AuthState {
  currentUser: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;          // True during initial auth check
  authError: string | null;

  // Actions
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name: string) => Promise<void>;
  logout: () => Promise<void>;
  checkAuth: () => Promise<void>;     // Called on app load
  handleSessionExpired: () => void;   // Called by 401 interceptor
  updateProfile: (data: ProfileUpdate) => Promise<void>;
  clearError: () => void;
}
```

### Key Behaviors

- **No persistence middleware.** The httpOnly cookie is the persistence layer. Store is hydrated from `/api/auth/me` on every app load.
- `checkAuth()`:
  1. Set `isLoading = true`.
  2. Call `authApi.getMe()`.
  3. On success: set `currentUser`, `isAuthenticated = true`.
  4. On 401: set `currentUser = null`, `isAuthenticated = false` (not logged in, not an error).
  5. Set `isLoading = false`.
- `login()` / `register()`:
  1. Call API.
  2. On success: set `currentUser`, `isAuthenticated = true`.
  3. On error: set `authError` with message.
- `logout()`:
  1. Call `authApi.logout()`.
  2. Clear `currentUser`, `isAuthenticated = false`.
  3. Clear all other stores (see 4.7).
  4. Navigate to `/login`.
- `handleSessionExpired()`:
  1. Clear `currentUser`, `isAuthenticated = false`.
  2. Set `authError = 'Session expired. Please log in again.'`.
  3. Navigate to `/login`.

---

## 4.4 — Login & Register Pages

### File Structure

```
src/features/auth/
  LoginPage.tsx
  RegisterPage.tsx
  AuthLayout.tsx       — Centered card layout for auth pages
```

### Login Page (`/login`)

- Email + password form.
- Submit calls `authStore.login()`.
- On success, redirect to `/` (or the page they were trying to access).
- Link to register page.
- Display `authError` from store.

### Register Page (`/register`)

- Name + email + password + confirm password form.
- Client-side validation: email format, password min 8 chars, passwords match.
- Submit calls `authStore.register()`.
- On success, redirect to `/` (user is auto-logged-in after register).
- Link to login page.

### Auth Layout

- Minimal centered layout — no sidebar, no top nav.
- App logo/name at top.
- Uses existing design tokens (`var(--bg-primary)`, `var(--text-primary)`, etc.).

---

## 4.5 — Protected Route Component

**File:** `src/features/auth/ProtectedRoute.tsx`

```typescript
function ProtectedRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, isLoading } = useAuthStore((s) => ({
    isAuthenticated: s.isAuthenticated,
    isLoading: s.isLoading,
  }));

  if (isLoading) {
    return <FullPageSpinner />;   // Or skeleton — avoid flash of login page
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}
```

### Admin Route Guard (optional sub-component)

```typescript
function AdminRoute({ children }: { children: ReactNode }) {
  const role = useAuthStore((s) => s.currentUser?.role);
  if (role !== 'admin') {
    return <Navigate to="/" replace />;
  }
  return <>{children}</>;
}
```

---

## 4.6 — Router Updates

**File:** `src/app/Router.tsx`

### New Routes

```typescript
<Route path="/login" element={<LoginPage />} />
<Route path="/register" element={<RegisterPage />} />
```

### Protected Routes

Wrap all existing route groups:

```typescript
<Route element={<ProtectedRoute><MainLayout /></ProtectedRoute>}>
  {/* All existing Voice Rx and Kaira routes */}
</Route>

{/* Auth routes — outside ProtectedRoute */}
<Route element={<AuthLayout />}>
  <Route path="/login" element={<LoginPage />} />
  <Route path="/register" element={<RegisterPage />} />
</Route>
```

### Redirect Authenticated Users Away from Auth Pages

If user is already authenticated and navigates to `/login` or `/register`, redirect to `/`.

---

## 4.7 — App Initialization Flow

**File:** `src/app/Providers.tsx`

### Current Flow

```
App mounts → Providers runs useEffect →
  loadLLMSettings()
  loadCredentials('voice-rx')
  loadCredentials('kaira-bot')
  loadPrompts('voice-rx')
  loadPrompts('kaira-bot')
```

### New Flow

```
App mounts → Providers runs useEffect →
  1. authStore.checkAuth()           ← NEW: first thing
  2. IF authenticated:
       loadLLMSettings()             ← Same as before, but now user-scoped
       loadCredentials('voice-rx')
       loadCredentials('kaira-bot')
       loadPrompts('voice-rx')
       loadPrompts('kaira-bot')
  3. IF not authenticated:
       Do nothing. ProtectedRoute will redirect to /login.
```

### Implementation

```typescript
useEffect(() => {
  const init = async () => {
    await useAuthStore.getState().checkAuth();

    // Only load app data if authenticated
    if (useAuthStore.getState().isAuthenticated) {
      await loadAppData();
    }
  };
  init();
}, []);

// Subscribe to auth changes — reload data on login
useEffect(() => {
  const unsub = useAuthStore.subscribe(
    (state) => state.isAuthenticated,
    async (isAuth) => {
      if (isAuth) await loadAppData();
    }
  );
  return unsub;
}, []);
```

---

## 4.8 — Logout: Store Cleanup

On logout, clear all user-specific state from Zustand stores:

```typescript
// In authStore.logout():
async logout() {
  await authApi.logout();

  // Clear all stores
  useListingsStore.getState().reset();
  usePromptsStore.getState().reset();
  useSchemasStore.getState().reset();
  useEvaluatorsStore.getState().reset();
  useChatStore.getState().reset();
  useLLMSettingsStore.getState().reset();
  useAppSettingsStore.getState().reset();
  useJobTrackerStore.getState().reset();

  // Clear auth
  set({ currentUser: null, isAuthenticated: false });
}
```

Each store needs a `reset()` action that restores initial state. Add where missing.

**Do NOT clear:** `globalSettingsStore` (theme is device-local, not user-specific), `appStore` (app selection is device-local).

---

## 4.9 — User Context in UI

### Display Current User

Add user info to the sidebar or top nav:
- Show user name/email.
- Logout button.
- Link to profile/settings page.

### Profile Page (lightweight)

Either a dedicated page or a modal in Settings:
- Show name, email.
- Change name.
- Change password (current + new).
- Uses `authStore.updateProfile()`.

---

## 4.10 — Error Handling Edge Cases

### Session Expiry During Active Use

The 401 interceptor (4.1) handles this:
1. Access token expires (15 min).
2. Next API call returns 401.
3. Interceptor tries refresh.
4. If refresh succeeds → retry request transparently.
5. If refresh fails (7-day refresh token expired) → redirect to login.

### Concurrent Refresh Race

If multiple API calls fail simultaneously with 401:
- Only ONE refresh call should fire.
- Use a promise-based lock:

```typescript
let refreshPromise: Promise<boolean> | null = null;

async function attemptTokenRefresh(): Promise<boolean> {
  if (refreshPromise) return refreshPromise;

  refreshPromise = authApi.refreshToken()
    .then(() => true)
    .catch(() => false)
    .finally(() => { refreshPromise = null; });

  return refreshPromise;
}
```

### Tab Visibility

When the user returns to a background tab after a long time:
- The next API call may get 401 → interceptor handles it.
- No special tab-visibility logic needed.

---

## Verification Checklist

- [ ] Unauthenticated user is redirected to `/login` on any protected route.
- [ ] Login form authenticates and redirects to `/`.
- [ ] Register form creates user and auto-logs in.
- [ ] `apiRequest` sends cookies with every request (`credentials: 'include'`).
- [ ] 401 response triggers automatic token refresh.
- [ ] If refresh fails, user is redirected to login with "session expired" message.
- [ ] Concurrent 401s don't trigger multiple refresh calls.
- [ ] Logout clears all user stores and redirects to `/login`.
- [ ] Already-authenticated users accessing `/login` are redirected to `/`.
- [ ] App data loads only after auth check succeeds.
- [ ] Theme preference (globalSettingsStore) survives logout (device-local).
- [ ] User name appears in sidebar/nav.

# Phase 5 — Frontend Authentication

## 5.1 Auth Types (`src/types/auth.types.ts`) — NEW FILE

```typescript
export interface User {
  id: string;
  email: string;
  displayName: string;
  role: 'owner' | 'admin' | 'member';
  tenantId: string;
  tenantName: string;
}

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface AuthState {
  user: User | null;
  accessToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
}
```

---

## 5.2 Auth Store (`src/stores/authStore.ts`) — NEW FILE

```typescript
import { create } from 'zustand';
import type { User, LoginCredentials } from '@/types/auth.types';

interface AuthStore {
  user: User | null;
  accessToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;

  login: (credentials: LoginCredentials) => Promise<void>;
  logout: () => Promise<void>;
  refreshToken: () => Promise<boolean>;
  loadUser: () => Promise<void>;
  setAccessToken: (token: string) => void;
}

export const useAuthStore = create<AuthStore>((set, get) => ({
  user: null,
  accessToken: localStorage.getItem('accessToken'),
  isAuthenticated: false,
  isLoading: true,

  login: async (credentials) => { ... },
  logout: async () => { ... },
  refreshToken: async () => { ... },
  loadUser: async () => { ... },
  setAccessToken: (token) => { ... },
}));
```

### Token Storage Strategy

- **Access token:** `localStorage` + Zustand state. Short-lived (15m). Sent as `Authorization: Bearer` header.
- **Refresh token:** httpOnly cookie. Set by backend. Sent automatically to `/api/auth/refresh` only.

### `login()` Flow

```
1. POST /api/auth/login { email, password }
2. Response: { accessToken, user }
3. Store accessToken in localStorage + Zustand
4. Store user in Zustand
5. Set isAuthenticated = true
6. Redirect to app home
```

### `refreshToken()` Flow

```
1. POST /api/auth/refresh (cookie sent automatically)
2. Response: { accessToken }
3. Update accessToken in localStorage + Zustand
4. Return true (success) or false (expired — redirect to login)
```

### `loadUser()` — Called on App Mount

```
1. If accessToken exists in localStorage:
   a. Try GET /api/auth/me
   b. If 401: try refreshToken()
   c. If refresh succeeds: retry GET /api/auth/me
   d. If refresh fails: clear state, redirect to login
2. If no token: isLoading = false, isAuthenticated = false
```

### `logout()` Flow

```
1. POST /api/auth/logout (clears cookie server-side)
2. Remove accessToken from localStorage
3. Clear Zustand state (user = null, isAuthenticated = false)
4. Redirect to /login
```

---

## 5.3 API Client Modification (`src/services/api/client.ts`)

### Current State

```typescript
const headers: Record<string, string> = {
  'Content-Type': 'application/json',
};
```

### Modified

```typescript
import { useAuthStore } from '@/stores/authStore';

function getAuthHeaders(): Record<string, string> {
  const token = useAuthStore.getState().accessToken;
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}
```

### 401 Interceptor

Add to `apiRequest`:

```typescript
export async function apiRequest<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...options,
    headers: { ...getAuthHeaders(), ...options?.headers },
    credentials: 'include',  // For refresh token cookie
  });

  if (response.status === 401) {
    // Try refresh
    const refreshed = await useAuthStore.getState().refreshToken();
    if (refreshed) {
      // Retry original request with new token
      const retryResponse = await fetch(url, {
        ...options,
        headers: { ...getAuthHeaders(), ...options?.headers },
        credentials: 'include',
      });
      if (retryResponse.ok) {
        return retryResponse.json();
      }
    }
    // Refresh failed — logout
    useAuthStore.getState().logout();
    throw new Error('Session expired');
  }

  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}
```

Same pattern for `apiUpload` and `apiDownload` — add auth headers and 401 handling.

---

## 5.4 Auth API Module (`src/services/api/authApi.ts`) — NEW FILE

```typescript
import { apiRequest } from './client';
import type { User, LoginCredentials } from '@/types/auth.types';

interface LoginResponse {
  accessToken: string;
  user: User;
}

interface RefreshResponse {
  accessToken: string;
}

export const authApi = {
  login: (credentials: LoginCredentials): Promise<LoginResponse> =>
    apiRequest('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify(credentials),
    }),

  refresh: (): Promise<RefreshResponse> =>
    fetch('/api/auth/refresh', {
      method: 'POST',
      credentials: 'include',
    }).then(r => {
      if (!r.ok) throw new Error('Refresh failed');
      return r.json();
    }),

  logout: (): Promise<void> =>
    fetch('/api/auth/logout', {
      method: 'POST',
      credentials: 'include',
    }).then(() => {}),

  getMe: (): Promise<User> =>
    apiRequest('/api/auth/me'),

  changePassword: (currentPassword: string, newPassword: string): Promise<void> =>
    apiRequest('/api/auth/me/password', {
      method: 'PUT',
      body: JSON.stringify({ currentPassword, newPassword }),
    }),
};
```

**Note:** `refresh` and `logout` use raw `fetch` (not `apiRequest`) to avoid circular 401 handling.

---

## 5.5 Login Page (`src/features/auth/LoginPage.tsx`) — NEW FILE

### Design Requirements

- Clean, centered card layout
- Email + password fields
- Submit button with loading state
- Error message display
- No "sign up" link (admin-onboarded only)
- Redirect to app home on success

### Component Structure

```typescript
export function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const login = useAuthStore((s) => s.login);
  const navigate = useNavigate();

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');
    try {
      await login({ email, password });
      navigate(ROUTES.HOME);
    } catch (err) {
      setError('Invalid email or password');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    // Centered card with form
  );
}
```

---

## 5.6 Auth Guard (`src/features/auth/AuthGuard.tsx`) — NEW FILE

```typescript
export function AuthGuard({ children }: { children: ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const isLoading = useAuthStore((s) => s.isLoading);

  if (isLoading) {
    return <LoadingSpinner />;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}
```

---

## 5.7 Router Changes (`src/app/Router.tsx`)

### Add Login Route (Unprotected)

```typescript
<Route path="/login" element={<LoginPage />} />
```

### Wrap All App Routes with AuthGuard

```typescript
<Route element={<AuthGuard><MainLayout /></AuthGuard>}>
  {/* All existing app routes */}
</Route>
```

### Add Admin Route

```typescript
<Route path="/admin/users" element={<AdminGuard><AdminUsersPage /></AdminGuard>} />
```

### Route Constants (`src/config/routes.ts`)

Add:
```typescript
LOGIN: '/login',
ADMIN_USERS: '/admin/users',
PROFILE: '/profile',
```

---

## 5.8 Providers Changes (`src/app/Providers.tsx`)

### Current

Calls `loadSettings()` on mount for all stores.

### Modified

```typescript
export function Providers({ children }: { children: ReactNode }) {
  useEffect(() => {
    // 1. Load auth first
    useAuthStore.getState().loadUser().then(() => {
      const isAuth = useAuthStore.getState().isAuthenticated;
      if (!isAuth) return; // Don't load app data if not authenticated

      // 2. Then load app data
      loadAllStores();
    });
  }, []);

  return <>{children}</>;
}
```

Auth must resolve before any store attempts API calls. Otherwise stores will get 401s on page load.

---

## 5.9 Layout Changes

### Sidebar (`src/components/layout/Sidebar.tsx`)

Add at bottom of sidebar:
- User avatar/initials + display name
- Role badge (admin/owner)
- Tenant name
- Settings/profile link
- Logout button

```typescript
// Read from auth store
const user = useAuthStore((s) => s.user);
const logout = useAuthStore((s) => s.logout);
```

### Header / MainLayout (`src/components/layout/MainLayout.tsx`)

- Show tenant name in header (optional — depends on design)
- Admin link visible only for admin/owner roles

---

## 5.10 Admin Guard (`src/features/auth/AdminGuard.tsx`) — NEW FILE

```typescript
export function AdminGuard({ children }: { children: ReactNode }) {
  const user = useAuthStore((s) => s.user);

  if (!user || (user.role !== 'admin' && user.role !== 'owner')) {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}
```

---

## 5.11 Files Summary

| File | Action | Purpose |
|------|--------|---------|
| `src/types/auth.types.ts` | CREATE | User, LoginCredentials, AuthState types |
| `src/stores/authStore.ts` | CREATE | Auth state management |
| `src/services/api/authApi.ts` | CREATE | Auth API calls |
| `src/services/api/client.ts` | MODIFY | Add auth headers, 401 interceptor |
| `src/features/auth/LoginPage.tsx` | CREATE | Login form |
| `src/features/auth/AuthGuard.tsx` | CREATE | Route protection |
| `src/features/auth/AdminGuard.tsx` | CREATE | Admin route protection |
| `src/app/Router.tsx` | MODIFY | Add login route, wrap with AuthGuard |
| `src/app/Providers.tsx` | MODIFY | Auth-first initialization |
| `src/config/routes.ts` | MODIFY | Add LOGIN, ADMIN_USERS routes |
| `src/components/layout/Sidebar.tsx` | MODIFY | User profile + logout in sidebar |
| `src/components/layout/MainLayout.tsx` | MODIFY | Tenant context display |
| `src/services/storage/index.ts` | MODIFY | Add authApi export |

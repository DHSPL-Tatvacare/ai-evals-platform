# User Authentication & User-Level Data Isolation — Overview

## Scope

Add JWT-based authentication with httpOnly cookies, role-based access (admin + users), per-user API keys/settings, and user-scoped data isolation across the entire platform.

## Assumptions

- **All existing data will be deleted.** No migration or backfill of existing rows.
- **JWT + httpOnly cookie** for auth. No OAuth/social login in initial scope.
- **User-level tenancy only.** No org/team abstractions.
- **Per-user API keys and settings.** Each user manages their own LLM credentials.
- **Seed data** (default prompts, schemas, evaluators) is system-owned and shared across all users (read-only for non-admins).
- **Existing abstractions preserved.** `UserMixin`, `CamelModel`, `get_db`, `apiRequest`, Zustand stores — all extended, not replaced.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Auth mechanism | JWT in httpOnly cookie | Immune to XSS token theft; no localStorage tokens |
| Token refresh | Short-lived access (15min) + long-lived refresh (7d) cookie pair | Balance security with UX |
| Password hashing | `bcrypt` via `passlib` | Industry standard, slow-by-design |
| JWT library | `python-jose[cryptography]` | Async-compatible, well-maintained |
| User ID type | UUID | Matches existing PK pattern for most tables |
| Roles | `admin`, `user` | Admin can manage users + see all data; user sees own data only |
| Seed data ownership | `user_id = NULL` (system-owned) | Distinguishes from any real user; queries use `WHERE user_id = :uid OR user_id IS NULL` for shared data |
| Frontend auth state | Zustand `authStore` with no persistence | Cookie handles persistence; store is hydrated from `/api/auth/me` on load |

## Phase Map

| Phase | Name | Depends On | Summary |
|-------|------|------------|---------|
| 1 | [Backend Auth Core](./PHASE_1_AUTH_CORE.md) | — | Users table, JWT, cookies, auth dependency, auth router |
| 2 | [Data Model & Route Scoping](./PHASE_2_DATA_SCOPING.md) | Phase 1 | UserMixin → UUID FK, all 15 routers scoped by user_id |
| 3 | [Per-User Settings & Keys](./PHASE_3_USER_SETTINGS.md) | Phase 2 | User-scoped settings, per-user LLM keys, profile management |
| 4 | [Frontend Auth](./PHASE_4_FRONTEND_AUTH.md) | Phase 1 | Auth store, login/register UI, protected routes, cookie flow |
| 5 | [Job Worker & Session Integrity](./PHASE_5_JOBS_AND_SESSIONS.md) | Phase 2, 3 | User-owned jobs, worker auth context, background task scoping |

**Phases 1-3 are backend-only. Phase 4 is frontend-only. Phase 5 ties them together.**

Phases 2 and 4 can proceed in parallel after Phase 1 is complete.

## New Dependencies

### Backend (`requirements.txt`)
```
python-jose[cryptography]>=3.3.0
passlib[bcrypt]>=1.7.4
```

### Frontend
No new npm packages needed. httpOnly cookies are handled natively by the browser.

## New Files (Planned)

### Backend
```
backend/app/models/user.py          — User ORM model
backend/app/schemas/auth.py         — Register/Login/UserResponse schemas
backend/app/routes/auth.py          — /api/auth/* endpoints
backend/app/auth.py                 — JWT encode/decode, cookie helpers, get_current_user dependency
```

### Frontend
```
src/stores/authStore.ts             — Auth state (currentUser, isAuthenticated)
src/features/auth/LoginPage.tsx     — Login form
src/features/auth/RegisterPage.tsx  — Registration form
src/features/auth/ProtectedRoute.tsx — Route guard component
src/services/api/authApi.ts         — Auth API calls
```

## Files Modified (All Phases Combined)

### Backend — Models
- `backend/app/models/base.py` — Change `UserMixin.user_id` from `String(100)` to `UUID FK → users.id`, nullable
- `backend/app/models/__init__.py` — Export `User` model

### Backend — Routes (all 15)
- Every router file in `backend/app/routes/` — Add `current_user` dependency, filter queries by `user_id`

### Backend — Services
- `backend/app/services/job_worker.py` — Pass user_id through job lifecycle
- `backend/app/services/evaluators/llm_base.py` — Accept user-specific credentials
- `backend/app/services/seed_defaults.py` (or equivalent) — Seed data with `user_id=NULL`

### Backend — Config
- `backend/app/main.py` — Register auth router, update lifespan for user table creation
- `backend/app/config.py` — Add `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`

### Frontend — Core
- `src/services/api/client.ts` — Add `credentials: 'include'` to all fetch calls
- `src/app/Router.tsx` — Wrap routes in `<ProtectedRoute>`
- `src/app/Providers.tsx` — Gate store hydration on auth check
- `src/app/App.tsx` — Add auth initialization

### Frontend — Stores
- `src/stores/appSettingsStore.ts` — Remove localStorage persistence (now server-scoped per user)
- `src/stores/llmSettingsStore.ts` — Load from user-scoped backend settings
- `src/stores/globalSettingsStore.ts` — Keep localStorage for theme (device-local preference)

# Complete File Touchpoint Reference

Every file that needs to be created or modified, organized by phase.

## Legend

- **C** = Create new file
- **M** = Modify existing file
- **D** = Delete (remove dead code from file)

---

## Phase 1 — Data Model (18 files)

| # | Action | File | Changes |
|---|--------|------|---------|
| 1 | C | `backend/app/models/tenant.py` | Tenant model |
| 2 | C | `backend/app/models/user.py` | User, UserRole, RefreshToken models |
| 3 | C | `backend/app/constants.py` | SYSTEM_TENANT_ID, SYSTEM_USER_ID |
| 4 | M | `backend/app/models/base.py` | Replace UserMixin → TenantUserMixin |
| 5 | M | `backend/app/models/__init__.py` | Import new models |
| 6 | M | `backend/app/models/eval_run.py` | TenantUserMixin, indexes |
| 7 | M | `backend/app/models/listing.py` | TenantUserMixin, indexes |
| 8 | M | `backend/app/models/chat.py` | TenantUserMixin on Session + Message |
| 9 | M | `backend/app/models/prompt.py` | TenantUserMixin, constraint |
| 10 | M | `backend/app/models/schema.py` | TenantUserMixin, constraint |
| 11 | M | `backend/app/models/evaluator.py` | TenantUserMixin, indexes |
| 12 | M | `backend/app/models/job.py` | TenantUserMixin |
| 13 | M | `backend/app/models/file_record.py` | TenantUserMixin |
| 14 | M | `backend/app/models/tag.py` | TenantUserMixin, constraint |
| 15 | M | `backend/app/models/history.py` | TenantUserMixin |
| 16 | M | `backend/app/models/setting.py` | TenantUserMixin, constraint |
| 17 | M | `backend/app/models/evaluation_analytics.py` | Add tenant_id FK, constraints |
| 18 | M | `backend/app/database.py` | No structural change (verify create_all picks up new models) |

---

## Phase 2 — Auth Backend (10 files)

| # | Action | File | Changes |
|---|--------|------|---------|
| 19 | C | `backend/app/auth/__init__.py` | Package init |
| 20 | C | `backend/app/auth/utils.py` | Password hashing, JWT encode/decode |
| 21 | C | `backend/app/auth/context.py` | AuthContext, get_auth_context, require_admin, require_owner |
| 22 | C | `backend/app/routes/auth.py` | Login, refresh, logout, me, password change |
| 23 | C | `backend/app/schemas/auth.py` | Auth request/response schemas |
| 24 | M | `backend/app/config.py` | JWT_SECRET, token expiry, admin bootstrap vars |
| 25 | M | `backend/app/main.py` | Register auth router |
| 26 | M | `backend/app/services/seed_defaults.py` | Bootstrap admin + system tenant/user seed |
| 27 | M | `.env.backend` | JWT_SECRET, ADMIN_EMAIL/PASSWORD/TENANT |
| 28 | M | `.env.backend.example` | Document new vars |

---

## Phase 3 — Route Scoping (27 files)

### Route Files (16)

| # | Action | File | Endpoints Modified |
|---|--------|------|--------------------|
| 29 | M | `backend/app/routes/listings.py` | 6 endpoints |
| 30 | M | `backend/app/routes/files.py` | 4 endpoints |
| 31 | M | `backend/app/routes/prompts.py` | 6 endpoints |
| 32 | M | `backend/app/routes/schemas.py` | 7 endpoints |
| 33 | M | `backend/app/routes/evaluators.py` | 12 endpoints |
| 34 | M | `backend/app/routes/chat.py` | 12 endpoints |
| 35 | M | `backend/app/routes/jobs.py` | 4 endpoints |
| 36 | M | `backend/app/routes/eval_runs.py` | 11 endpoints |
| 37 | M | `backend/app/routes/settings.py` | 5 endpoints |
| 38 | M | `backend/app/routes/tags.py` | 7 endpoints |
| 39 | M | `backend/app/routes/history.py` | 5 endpoints |
| 40 | M | `backend/app/routes/llm.py` | 3 endpoints |
| 41 | M | `backend/app/routes/adversarial_config.py` | 5 endpoints |
| 42 | M | `backend/app/routes/reports.py` | 5 endpoints |
| 43 | M | `backend/app/routes/admin.py` | 2 existing + 6 new endpoints |
| 44 | C | `backend/app/schemas/admin.py` | Admin request/response schemas |

### Schema Files (11)

| # | Action | File | Changes |
|---|--------|------|---------|
| 45 | M | `backend/app/schemas/listing.py` | Add tenant_id, remove user_id default |
| 46 | M | `backend/app/schemas/eval_run.py` | Add tenant_id, remove user_id default |
| 47 | M | `backend/app/schemas/chat.py` | Add tenant_id, remove user_id default |
| 48 | M | `backend/app/schemas/prompt.py` | Add tenant_id, remove user_id default |
| 49 | M | `backend/app/schemas/schema.py` | Add tenant_id, remove user_id default |
| 50 | M | `backend/app/schemas/evaluator.py` | Add tenant_id, remove user_id default |
| 51 | M | `backend/app/schemas/job.py` | Add tenant_id, remove user_id default |
| 52 | M | `backend/app/schemas/file.py` | Add tenant_id, remove user_id default |
| 53 | M | `backend/app/schemas/tag.py` | Add tenant_id, remove user_id default |
| 54 | M | `backend/app/schemas/history.py` | Add tenant_id, remove user_id default |
| 55 | M | `backend/app/schemas/setting.py` | Add tenant_id, remove user_id default |

---

## Phase 4 — Services (10 files)

| # | Action | File | Changes |
|---|--------|------|---------|
| 56 | M | `backend/app/services/job_worker.py` | Extract tenant/user from params; pass to handlers |
| 57 | M | `backend/app/services/evaluators/runner_utils.py` | Add tenant_id/user_id to create/finalize |
| 58 | M | `backend/app/services/evaluators/batch_runner.py` | Accept tenant_id/user_id; ownership checks |
| 59 | M | `backend/app/services/evaluators/voice_rx_runner.py` | Accept tenant_id/user_id; system tenant for defaults |
| 60 | M | `backend/app/services/evaluators/custom_evaluator_runner.py` | Accept tenant_id/user_id; ownership checks |
| 61 | M | `backend/app/services/evaluators/adversarial_runner.py` | Accept tenant_id/user_id; scoped config |
| 62 | M | `backend/app/services/evaluators/adversarial_config.py` | Add tenant_id/user_id to load/save |
| 63 | M | `backend/app/services/evaluators/settings_helper.py` | Add tenant_id/user_id params; no fallbacks |
| 64 | M | `backend/app/services/reports/report_service.py` | Accept tenant_id/user_id; ownership checks |
| 65 | M | `backend/app/services/seed_defaults.py` | SYSTEM_TENANT_ID/SYSTEM_USER_ID everywhere |

---

## Phase 5 — Frontend Auth (13 files)

| # | Action | File | Changes |
|---|--------|------|---------|
| 66 | C | `src/types/auth.types.ts` | User, LoginCredentials, AuthState |
| 67 | C | `src/stores/authStore.ts` | Auth state management |
| 68 | C | `src/services/api/authApi.ts` | Auth API calls |
| 69 | M | `src/services/api/client.ts` | Auth headers, 401 interceptor |
| 70 | C | `src/features/auth/LoginPage.tsx` | Login form |
| 71 | C | `src/features/auth/AuthGuard.tsx` | Route protection |
| 72 | C | `src/features/auth/AdminGuard.tsx` | Admin route protection |
| 73 | M | `src/app/Router.tsx` | Login route, AuthGuard wrapper |
| 74 | M | `src/app/Providers.tsx` | Auth-first initialization |
| 75 | M | `src/config/routes.ts` | LOGIN, ADMIN_USERS constants |
| 76 | M | `src/components/layout/Sidebar.tsx` | User profile, logout, admin link |
| 77 | M | `src/components/layout/MainLayout.tsx` | Tenant context |
| 78 | M | `src/services/storage/index.ts` | Export authApi |

---

## Phase 6 — Frontend Scoping (15 files)

| # | Action | File | Changes |
|---|--------|------|---------|
| 79 | M | `src/stores/appStore.ts` | Add reset() |
| 80 | M | `src/stores/llmSettingsStore.ts` | Add reset() |
| 81 | M | `src/stores/appSettingsStore.ts` | Add reset() |
| 82 | M | `src/stores/listingsStore.ts` | Add reset() |
| 83 | M | `src/stores/schemasStore.ts` | Add reset() |
| 84 | M | `src/stores/promptsStore.ts` | Add reset() |
| 85 | M | `src/stores/evaluatorsStore.ts` | Add reset() |
| 86 | M | `src/stores/chatStore.ts` | Add reset() |
| 87 | M | `src/stores/crossRunStore.ts` | Add reset() |
| 88 | M | `src/stores/jobTrackerStore.ts` | Add reset() |
| 89 | M | `src/types/listing.types.ts` | Add tenantId |
| 90 | M | `src/types/evalRuns.ts` | Add tenantId |
| 91 | M | `src/types/chat.types.ts` | Add tenantId |
| 92 | M | `src/types/evaluator.types.ts` | Add tenantId |
| 93 | M | `src/types/settings.types.ts` | Add tenantId |

---

## Phase 7 — Admin UI (9 files)

| # | Action | File | Changes |
|---|--------|------|---------|
| 94 | C | `src/services/api/adminApi.ts` | Admin API calls |
| 95 | C | `src/features/admin/AdminUsersPage.tsx` | User management page |
| 96 | C | `src/features/admin/CreateUserDialog.tsx` | Create user modal |
| 97 | C | `src/features/admin/EditUserDialog.tsx` | Edit user modal |
| 98 | C | `backend/app/schemas/admin.py` | Already counted in Phase 3 |
| 99 | M | `backend/app/routes/admin.py` | Already counted in Phase 3 |
| 100 | M | `src/components/layout/Sidebar.tsx` | Already counted in Phase 5 |
| 101 | M | `src/app/Router.tsx` | Already counted in Phase 5 |
| 102 | M | `src/config/routes.ts` | Already counted in Phase 5 |

---

## Phase 8 — Cleanup (5 files)

| # | Action | File | Changes |
|---|--------|------|---------|
| 103 | M | `backend/app/models/base.py` | Delete old UserMixin class |
| 104 | M | `CLAUDE.md` | Update registry, invariants, coding rules |
| 105 | M | `docker-compose.yml` | Pass auth env vars |
| 106 | M | `.env.backend` | Already counted in Phase 2 |
| 107 | M | `.env.backend.example` | Already counted in Phase 2 |

---

## Totals

| Category | Create | Modify | Total Unique Files |
|----------|--------|--------|--------------------|
| Backend models | 3 | 14 | 17 |
| Backend auth | 3 | 0 | 3 |
| Backend routes | 1 | 16 | 17 |
| Backend schemas | 2 | 11 | 13 |
| Backend services | 0 | 10 | 10 |
| Backend config | 0 | 4 | 4 |
| Frontend auth | 4 | 5 | 9 |
| Frontend stores | 0 | 10 | 10 |
| Frontend types | 1 | 5 | 6 |
| Frontend admin | 3 | 0 | 3 |
| Frontend API | 1 | 1 | 2 |
| Docs | 0 | 1 | 1 |
| **Total** | **18** | **77** | **~95** |

---

## Implementation Order (Critical Path)

```
Phase 1 (Data Model)     ─── Must be first (all other phases depend on schema)
    │
    ├── Phase 2 (Auth Backend)     ─── Depends on Phase 1 (User, Tenant models)
    │       │
    │       ├── Phase 3 (Routes)   ─── Depends on Phase 2 (AuthContext dependency)
    │       │
    │       └── Phase 4 (Services) ─── Depends on Phase 2 (tenant_id/user_id types)
    │
    ├── Phase 5 (Frontend Auth)    ─── Can start after Phase 2 (needs auth API)
    │       │
    │       └── Phase 6 (Frontend Scoping) ─── Depends on Phase 5 (auth store)
    │
    ├── Phase 7 (Admin UI)         ─── Depends on Phase 3 (admin routes) + Phase 5 (auth)
    │
    └── Phase 8 (Cleanup)          ─── After all other phases
```

### Parallelizable Work

- Phase 3 (Routes) and Phase 4 (Services) can be done in parallel after Phase 2
- Phase 5 (Frontend Auth) can start as soon as Phase 2 auth routes are done
- Phase 6 and Phase 7 can be done in parallel after Phase 5

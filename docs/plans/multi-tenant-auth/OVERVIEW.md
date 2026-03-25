# Multi-Tenant Authentication Plan — Overview

## Goal

Transform the AI Evals Platform from a single-user dev tool into a multi-tenant, authenticated platform ready for internal team use and eventual SaaS deployment.

## Design Principles

1. **No legacy handling.** Existing data will be wiped. No migration logic, no fallback chains, no "default" user compatibility.
2. **Tenant-first.** Every data row belongs to a tenant. Every query filters by `tenant_id`. No exceptions.
3. **User-scoped within tenant.** Within a tenant, each user sees only their own data. Admins can see all data within their tenant.
4. **Industry-standard auth.** bcrypt password hashing, JWT access + refresh tokens, httpOnly cookies for refresh, Bearer header for access.
5. **No hardcoding.** Secrets from env vars. Roles from enum. Scoping from auth context dependency injection.
6. **Clean abstractions.** Auth context flows through a single FastAPI dependency. Frontend injects auth via the existing `apiRequest` abstraction.

## Architecture After Implementation

```
                          ┌─────────────────────┐
                          │   Azure Front Door   │
                          │   (TLS termination)  │
                          └──────────┬──────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    │                │                 │
              ┌─────▼─────┐   ┌─────▼─────┐   ┌──────▼──────┐
              │  Frontend  │   │  Backend   │   │ PostgreSQL  │
              │  (nginx)   │   │  (FastAPI) │   │ (Flex Srv)  │
              │  Container │   │  Container │   │  Azure DB   │
              └───────────┘   └───────────┘   └─────────────┘
```

## Data Model Summary

### New Tables

| Table | Purpose |
|-------|---------|
| `tenants` | Organization/account. Every data row belongs to one tenant. |
| `users` | Authenticated user. Belongs to one tenant. Has a role. |

### Modified Tables (All Existing)

Every table with `UserMixin` gets:
- `tenant_id` column (UUID FK to `tenants`, NOT NULL)
- `user_id` column changes from `String(100) default="default"` to `UUID FK to users, NOT NULL`

Tables without `UserMixin` that need `tenant_id`:
- `evaluation_analytics` — add `tenant_id`
- `thread_evaluations`, `adversarial_evaluations`, `api_logs` — inherit tenant/user from parent `eval_run` (no direct column needed; access controlled via eval_run ownership)

### Scoping Model

```
tenants
  └── users (role: owner | admin | member)
  └── listings (tenant_id + user_id)
  └── eval_runs (tenant_id + user_id)
  └── chat_sessions (tenant_id + user_id)
  └── chat_messages (tenant_id + user_id)
  └── prompts (tenant_id + user_id)
  └── schemas (tenant_id + user_id)
  └── evaluators (tenant_id + user_id)
  └── jobs (tenant_id + user_id)
  └── files (tenant_id + user_id)
  └── tags (tenant_id + user_id)
  └── history (tenant_id + user_id)
  └── settings (tenant_id + user_id)
  └── evaluation_analytics (tenant_id)

Seed data: tenant_id = SYSTEM_TENANT_ID (well-known UUID), user_id = SYSTEM_USER_ID
  - System prompts, system schemas, global evaluators
  - Visible to all tenants (read-only)
  - Queries: WHERE tenant_id = :current OR tenant_id = SYSTEM_TENANT_ID
```

## Auth Flow

```
1. POST /api/auth/login { email, password }
   → Validate credentials
   → Return { accessToken (JWT, 15m), user profile }
   → Set refreshToken as httpOnly cookie (7d)

2. Every API request:
   → Authorization: Bearer <accessToken>
   → Backend extracts tenant_id + user_id from JWT claims
   → Injects AuthContext into route via Depends(get_auth_context)

3. POST /api/auth/refresh
   → Read refreshToken from httpOnly cookie
   → Validate, issue new accessToken
   → Rotate refreshToken (token rotation)

4. POST /api/auth/logout
   → Clear refreshToken cookie
   → Blacklist refresh token in DB (optional, or rely on rotation)
```

## JWT Claims

```json
{
  "sub": "<user_id UUID>",
  "tid": "<tenant_id UUID>",
  "email": "<user email>",
  "role": "owner|admin|member",
  "iat": 1710000000,
  "exp": 1710000900
}
```

## Phase Summary

| Phase | Scope | Files Changed |
|-------|-------|---------------|
| 1 — Data Model | New tables, modify all models, drop/recreate DB | ~16 model files, base.py, database.py |
| 2 — Auth Backend | JWT utils, auth deps, auth routes, middleware | ~6 new files, main.py, config.py |
| 3 — Route Scoping | Every route gets `AuthContext` dependency, all queries filter by tenant_id + user_id | 16 route files |
| 4 — Services | Job worker, runners, settings helper, seed defaults, report service | ~12 service files |
| 5 — Frontend Auth | Auth store, login page, route guard, API client headers, token refresh | ~15 files |
| 6 — Frontend Scoping | All stores pass user context, all API calls include auth | ~14 stores, ~15 API modules |
| 7 — Admin UI | Tenant management, user management, admin routes + pages | ~4 new files |
| 8 — Cleanup | Remove UserMixin default, delete dead code, update CLAUDE.md | ~10 files |

## Environment Variables (New)

```bash
# Auth
JWT_SECRET=<random 64-char hex>
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# First admin (seed on startup if no users exist)
ADMIN_EMAIL=<admin email>
ADMIN_PASSWORD=<admin password>
ADMIN_TENANT_NAME=<tenant name>
```

## What Gets Deleted

- All existing data in all tables (clean sweep via `docker compose down -v`)
- `UserMixin` default value of `"default"` — replaced with proper FK
- All hardcoded `user_id="default"` in routes, services, seeds
- No fallback chains in settings lookup
- No backward-compatible response schemas

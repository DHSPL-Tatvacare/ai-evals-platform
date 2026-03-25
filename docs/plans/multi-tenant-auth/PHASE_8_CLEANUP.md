# Phase 8 — Cleanup and Validation

## 8.1 Dead Code Removal

### Delete `UserMixin` Class

Remove from `backend/app/models/base.py`. Replace with `TenantUserMixin` (done in Phase 1). Verify no imports remain.

### Remove All `user_id="default"` Strings

Global search-and-destroy:

```bash
grep -rn '"default"' backend/app/ --include="*.py" | grep user_id
```

Every hit must be replaced with proper tenant/user from auth context or `SYSTEM_TENANT_ID`/`SYSTEM_USER_ID`.

### Remove `is_default` Field Usage for Auth Checks

The old pattern `Prompt.is_default == True and Prompt.user_id == "default"` to identify system data is replaced by `Prompt.tenant_id == SYSTEM_TENANT_ID`. Review and remove any remaining `is_default`-based auth checks.

**Note:** `is_default` as a boolean field on Prompt/Schema can remain — it still serves a UI purpose (marking system-provided templates). But it's no longer used for access control.

### Remove `ensure-defaults` Endpoints

`POST /api/prompts/ensure-defaults` and `POST /api/schemas/ensure-defaults` and `POST /api/evaluators/seed-defaults` — these are startup-only operations. Remove the routes. Seeding happens in `lifespan`.

---

## 8.2 Environment File Updates

### `.env.backend`

```bash
# Auth (NEW)
JWT_SECRET=<generate with: python -c "import secrets; print(secrets.token_hex(32))">
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# Bootstrap admin (NEW)
ADMIN_EMAIL=admin@yourcompany.com
ADMIN_PASSWORD=<strong-initial-password>
ADMIN_TENANT_NAME=Your Company Name
```

### `.env.backend.example`

Document all new variables with descriptions.

### `docker-compose.yml`

Pass new env vars to backend container:

```yaml
backend:
  environment:
    - JWT_SECRET=${JWT_SECRET}
    - JWT_ACCESS_TOKEN_EXPIRE_MINUTES=${JWT_ACCESS_TOKEN_EXPIRE_MINUTES:-15}
    - JWT_REFRESH_TOKEN_EXPIRE_DAYS=${JWT_REFRESH_TOKEN_EXPIRE_DAYS:-7}
    - ADMIN_EMAIL=${ADMIN_EMAIL}
    - ADMIN_PASSWORD=${ADMIN_PASSWORD}
    - ADMIN_TENANT_NAME=${ADMIN_TENANT_NAME}
```

---

## 8.3 CLAUDE.md Updates

### Update Current Registry

```markdown
- ORM tables (19): tenants, users, refresh_tokens, eval_runs, jobs, listings, files, prompts, schemas, evaluators, chat_sessions, chat_messages, history, settings, tags, thread_evaluations, adversarial_evaluations, api_logs, evaluation_analytics
- Routers (17): auth, listings, files, prompts, schemas, evaluators, chat, history, settings, tags, jobs, eval_runs, threads, llm, adversarial_config, admin, reports
```

### Update Invariants

```markdown
- Every data row belongs to a tenant. Every query filters by `tenant_id` from `AuthContext`.
- `SYSTEM_TENANT_ID` and `SYSTEM_USER_ID` are well-known UUIDs for seed data.
- `UserMixin` is replaced by `TenantUserMixin`. No defaults. Both fields are required FK references.
- LLM settings are per-user-per-tenant, stored at `(tenant_id, user_id, app_id="")`.
- Auth routes (`/api/auth/*`) are the only public routes. All others require Bearer token.
```

### Update Coding Rules

```markdown
- Auth context: `auth: AuthContext = Depends(get_auth_context)` on every route.
- Never use `db.get(Model, id)` for user data — always `select().where()` with tenant/user filters.
- Job params: `tenant_id` and `user_id` are injected by the job submission route. Runners read from params.
- System data: Query with `tenant_id == SYSTEM_TENANT_ID`, not `is_default == True and user_id == "default"`.
```

### Remove

- All references to `user_id="default"` pattern
- `UserMixin` documentation
- Global settings scope description (now per-user)

---

## 8.4 Validation Checklist

### Backend

- [ ] All 16 route files have `Depends(get_auth_context)` or `Depends(require_admin)` on every endpoint
- [ ] No route uses `db.get(Model, id)` without ownership check
- [ ] All model creates set `tenant_id` and `user_id` from auth context
- [ ] `settings_helper.get_llm_settings_from_db()` requires `tenant_id, user_id`
- [ ] All runners accept and propagate `tenant_id, user_id`
- [ ] `seed_defaults.py` uses `SYSTEM_TENANT_ID, SYSTEM_USER_ID` exclusively
- [ ] No string `"default"` appears as a user_id in any Python file
- [ ] `JWT_SECRET` is required in config — app fails to start without it
- [ ] Refresh token rotation works (old token invalidated after use)
- [ ] Expired refresh tokens are cleaned up periodically

### Frontend

- [ ] `client.ts` adds `Authorization: Bearer` header to all requests
- [ ] `client.ts` handles 401 → refresh → retry → logout
- [ ] `authStore` initializes on app mount
- [ ] All stores have `reset()` and are reset on logout
- [ ] Login page renders when unauthenticated
- [ ] AuthGuard redirects to `/login` when not authenticated
- [ ] AdminGuard blocks non-admin users from admin routes
- [ ] No hardcoded `user_id` in any frontend file
- [ ] No manual `user_id` in job submission params

### Data Isolation

- [ ] User A cannot see User B's listings, eval runs, sessions, etc.
- [ ] User A cannot access User B's records by ID
- [ ] System prompts/schemas/evaluators visible to all users (read-only)
- [ ] Users cannot edit or delete system data
- [ ] Admin can see user list within own tenant
- [ ] Admin cannot see other tenants' users

---

## 8.5 Database Wipe

Before first deployment:

```bash
docker compose down -v   # Wipe volumes
docker compose up --build
```

The `lifespan` startup will:
1. `metadata.create_all()` — create all 19 tables
2. `seed_bootstrap_admin()` — create system tenant, system user, admin tenant, admin user
3. `seed_all_defaults()` — create system prompts, schemas, evaluators

---

## 8.6 Files Summary

| File | Action | Purpose |
|------|--------|---------|
| `backend/app/models/base.py` | MODIFY | Remove old `UserMixin` |
| `.env.backend` | MODIFY | Add auth env vars |
| `.env.backend.example` | MODIFY | Document auth env vars |
| `docker-compose.yml` | MODIFY | Pass auth env vars |
| `CLAUDE.md` | MODIFY | Update registry, invariants, coding rules |
| All route files | VERIFY | Ensure auth dependency on every endpoint |
| All runner files | VERIFY | Ensure tenant/user propagation |
| All frontend stores | VERIFY | Ensure `reset()` method exists |

# Phase 3 — Route Scoping

Every route gets `auth: AuthContext = Depends(get_auth_context)` and filters all queries by `tenant_id` + `user_id`.

## Universal Pattern

### Before (current)
```python
@router.get("")
async def list_items(
    app_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Model).where(Model.app_id == app_id)
    )
    return result.scalars().all()
```

### After
```python
@router.get("")
async def list_items(
    app_id: str = Query(...),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Model).where(
            Model.tenant_id == auth.tenant_id,
            Model.user_id == auth.user_id,
            Model.app_id == app_id,
        )
    )
    return result.scalars().all()
```

### Create Pattern
```python
@router.post("", status_code=201)
async def create_item(
    body: ItemCreate,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    item = Model(
        **body.model_dump(),
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item
```

### Get-by-ID Pattern (Ownership Check)
```python
@router.get("/{item_id}")
async def get_item(
    item_id: str,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    item = await db.scalar(
        select(Model).where(
            Model.id == item_id,
            Model.tenant_id == auth.tenant_id,
            Model.user_id == auth.user_id,
        )
    )
    if not item:
        raise HTTPException(404, detail="Not found")
    return item
```

**Never use `db.get(Model, id)` for user data** — it bypasses tenant/user filtering. Always use `select().where()` with ownership clauses.

---

## 3.1 Listings Router (`/api/listings`) — 6 endpoints

| Endpoint | Auth | Query Changes |
|----------|------|---------------|
| `GET /` | `get_auth_context` | Add `tenant_id == auth.tenant_id, user_id == auth.user_id` |
| `GET /search` | `get_auth_context` | Add `tenant_id, user_id` to search filter |
| `GET /{id}` | `get_auth_context` | Replace `db.get()` with `select().where(id, tenant_id, user_id)` |
| `POST /` | `get_auth_context` | Set `tenant_id=auth.tenant_id, user_id=auth.user_id` on create |
| `PUT /{id}` | `get_auth_context` | Fetch with ownership check before update |
| `DELETE /{id}` | `get_auth_context` | Fetch with ownership check before delete |

---

## 3.2 Files Router (`/api/files`) — 4 endpoints

| Endpoint | Auth | Query Changes |
|----------|------|---------------|
| `POST /upload` | `get_auth_context` | Set `tenant_id, user_id` on FileRecord |
| `GET /{id}` | `get_auth_context` | Ownership check on FileRecord |
| `GET /{id}/download` | `get_auth_context` | Ownership check before streaming |
| `DELETE /{id}` | `get_auth_context` | Ownership check before delete |

---

## 3.3 Prompts Router (`/api/prompts`) — 6 endpoints

| Endpoint | Auth | Special Handling |
|----------|------|-----------------|
| `GET /` | `get_auth_context` | Return user's prompts PLUS system prompts (`tenant_id == SYSTEM_TENANT_ID`) |
| `GET /{id}` | `get_auth_context` | Allow access to own prompts + system prompts |
| `POST /` | `get_auth_context` | Set `tenant_id, user_id`; version auto-increment scoped to `(tenant_id, user_id, app_id, prompt_type)` |
| `PUT /{id}` | `get_auth_context` | Ownership check; block editing system prompts |
| `DELETE /{id}` | `get_auth_context` | Ownership check; block deleting system prompts |
| `POST /ensure-defaults` | `get_auth_context` | No-op or remove entirely — seeds are system-level |

### System Prompt Visibility Query

```python
# User sees: their own prompts + system defaults
select(Prompt).where(
    or_(
        and_(Prompt.tenant_id == auth.tenant_id, Prompt.user_id == auth.user_id),
        Prompt.tenant_id == SYSTEM_TENANT_ID,
    ),
    Prompt.app_id == app_id,
)
```

---

## 3.4 Schemas Router (`/api/schemas`) — 7 endpoints

Same pattern as Prompts:

| Endpoint | Auth | Special Handling |
|----------|------|-----------------|
| `GET /` | `get_auth_context` | User's schemas + system schemas |
| `GET /{id}` | `get_auth_context` | Own + system access |
| `POST /` | `get_auth_context` | Set `tenant_id, user_id` |
| `PUT /{id}` | `get_auth_context` | Ownership check; block system |
| `DELETE /{id}` | `get_auth_context` | Ownership check; block system |
| `POST /ensure-defaults` | `get_auth_context` | Remove or no-op |
| `POST /sync-from-listing` | `get_auth_context` | Verify listing ownership before syncing |

---

## 3.5 Evaluators Router (`/api/evaluators`) — 12 endpoints

| Endpoint | Auth | Special Handling |
|----------|------|-----------------|
| `GET /` | `get_auth_context` | User's evaluators + system globals (`tenant_id == SYSTEM_TENANT_ID`) |
| `GET /registry` | `get_auth_context` | System globals + user's globals |
| `GET /variables` | `get_auth_context` | Read-only, no DB — no change needed beyond auth |
| `POST /validate-prompt` | `get_auth_context` | Validation only — auth required but no DB scoping |
| `POST /seed-defaults` | `get_auth_context` | Remove — system seeds happen at startup |
| `GET /variables/api-paths` | `get_auth_context` | Verify listing ownership |
| `GET /{id}` | `get_auth_context` | Own + system access |
| `POST /` | `get_auth_context` | Set `tenant_id, user_id` |
| `PUT /{id}` | `get_auth_context` | Ownership check; block system |
| `DELETE /{id}` | `get_auth_context` | Ownership check; block system |
| `POST /{id}/fork` | `get_auth_context` | Source can be system or own; fork sets `tenant_id, user_id` to current user |
| `PUT /{id}/global` | `get_auth_context` | Ownership check — only owner can toggle global |

---

## 3.6 Chat Router (`/api/chat`) — 12 endpoints

| Endpoint | Auth | Notes |
|----------|------|-------|
| `GET /sessions` | `get_auth_context` | Filter by `tenant_id, user_id, app_id` |
| `GET /sessions/{id}` | `get_auth_context` | Ownership check |
| `POST /sessions` | `get_auth_context` | Set `tenant_id, user_id` |
| `PUT /sessions/{id}` | `get_auth_context` | Ownership check |
| `DELETE /sessions/{id}` | `get_auth_context` | Ownership check (cascades to messages) |
| `GET /sessions/{id}/messages` | `get_auth_context` | Verify session ownership first, then return messages |
| `GET /messages/{id}` | `get_auth_context` | Ownership check via `tenant_id, user_id` |
| `POST /messages` | `get_auth_context` | Verify session ownership, set `tenant_id, user_id` on message |
| `PUT /messages/{id}` | `get_auth_context` | Ownership check |
| `DELETE /messages/{id}` | `get_auth_context` | Ownership check |
| `PUT /messages/tags/rename` | `get_auth_context` | Scope rename to `tenant_id, user_id` (currently global — **bug fix**) |
| `POST /messages/tags/delete` | `get_auth_context` | Scope delete to `tenant_id, user_id` (currently global — **bug fix**) |

---

## 3.7 Jobs Router (`/api/jobs`) — 4 endpoints

| Endpoint | Auth | Notes |
|----------|------|-------|
| `POST /` | `get_auth_context` | Set `tenant_id, user_id` on Job; inject `tenant_id, user_id` into `params` dict for downstream runners |
| `GET /` | `get_auth_context` | Filter by `tenant_id, user_id` |
| `GET /{id}` | `get_auth_context` | Ownership check |
| `POST /{id}/cancel` | `get_auth_context` | Ownership check before cancel |

### Critical: Job Params Injection

When creating a job, the route must inject auth context into `params` so downstream runners have it:

```python
@router.post("", status_code=201)
async def submit_job(body: JobCreate, auth: AuthContext = Depends(get_auth_context), db = Depends(get_db)):
    job_data = body.model_dump()
    # Inject auth context into params — runners read this
    job_data["params"]["tenant_id"] = str(auth.tenant_id)
    job_data["params"]["user_id"] = str(auth.user_id)
    job = Job(**job_data, tenant_id=auth.tenant_id, user_id=auth.user_id)
    db.add(job)
    await db.commit()
    return job
```

---

## 3.8 EvalRuns Router (`/api/eval-runs`) — 11 endpoints

| Endpoint | Auth | Notes |
|----------|------|-------|
| `GET /` | `get_auth_context` | Add `tenant_id, user_id` filter |
| `POST /preview` | `get_auth_context` | Auth required (no DB write — file parse) |
| `GET /stats/summary` | `get_auth_context` | Scope counts to `tenant_id, user_id` |
| `GET /trends` | `get_auth_context` | Scope to `tenant_id, user_id` |
| `GET /logs` | `get_auth_context` | Filter logs via `run_id` owned by user |
| `DELETE /logs` | `get_auth_context` | Same ownership check |
| `PUT /{id}/human-review` | `get_auth_context` | Verify AI run ownership; create human run with same `tenant_id, user_id` |
| `GET /{id}/human-review` | `get_auth_context` | Ownership check on AI run |
| `GET /{id}` | `get_auth_context` | Ownership check |
| `DELETE /{id}` | `get_auth_context` | Ownership check |
| `GET /{id}/threads` | `get_auth_context` | Verify run ownership, return child thread_evaluations |
| `GET /{id}/adversarial` | `get_auth_context` | Verify run ownership, return child adversarial_evaluations |
| `GET /{id}/logs` | `get_auth_context` | Verify run ownership, return child api_logs |

### Thread History
| Endpoint | Auth | Notes |
|----------|------|-------|
| `GET /threads/{thread_id}/history` | `get_auth_context` | Filter ThreadEvaluation via `run_id` → verify EvalRun ownership |

---

## 3.9 Settings Router (`/api/settings`) — 5 endpoints

| Endpoint | Auth | Notes |
|----------|------|-------|
| `GET /` | `get_auth_context` | Filter by `tenant_id, user_id, app_id, key` |
| `GET /{id}` | `get_auth_context` | Ownership check |
| `PUT /` | `get_auth_context` | UPSERT with `tenant_id, user_id` — remove hardcoded `"default"` |
| `DELETE /` | `get_auth_context` | Filter by `tenant_id, user_id, app_id, key` |
| `DELETE /{id}` | `get_auth_context` | Ownership check |

### LLM Settings Scoping Change

**Old:** Global singleton at `(app_id="", user_id="default")`
**New:** Per-user at `(tenant_id=auth.tenant_id, user_id=auth.user_id, app_id="")`

Each user stores their own LLM API keys. No sharing between users.

---

## 3.10 Tags Router (`/api/tags`) — 7 endpoints

| Endpoint | Auth | Notes |
|----------|------|-------|
| `GET /` | `get_auth_context` | Filter by `tenant_id, user_id, app_id` |
| `GET /{id}` | `get_auth_context` | Ownership check |
| `POST /` | `get_auth_context` | Set `tenant_id, user_id` |
| `PUT /{id}` | `get_auth_context` | Ownership check |
| `DELETE /{id}` | `get_auth_context` | Ownership check |
| `POST /{id}/increment` | `get_auth_context` | Ownership check |
| `POST /{id}/decrement` | `get_auth_context` | Ownership check |

---

## 3.11 History Router (`/api/history`) — 5 endpoints

| Endpoint | Auth | Notes |
|----------|------|-------|
| `GET /` | `get_auth_context` | Add `tenant_id, user_id` filter |
| `GET /{id}` | `get_auth_context` | Ownership check |
| `POST /` | `get_auth_context` | Set `tenant_id, user_id` |
| `PUT /{id}` | `get_auth_context` | Ownership check |
| `DELETE /{id}` | `get_auth_context` | Ownership check |

---

## 3.12 LLM Router (`/api/llm`) — 3 endpoints

| Endpoint | Auth | Notes |
|----------|------|-------|
| `GET /auth-status` | `get_auth_context` | Check env vars — no DB. Auth just for gating. |
| `POST /discover-models` | `get_auth_context` | Pass `tenant_id, user_id` to `get_llm_settings_from_db()` |
| `GET /models` | `get_auth_context` | Same — pass auth context to settings lookup |

---

## 3.13 Adversarial Config Router (`/api/adversarial-config`) — 5 endpoints

| Endpoint | Auth | Notes |
|----------|------|-------|
| `GET /` | `get_auth_context` | Load config scoped to `tenant_id, user_id` |
| `PUT /` | `get_auth_context` | Save config scoped to `tenant_id, user_id` |
| `POST /reset` | `get_auth_context` | Reset user's config to system default |
| `GET /export` | `get_auth_context` | Export user's config |
| `POST /import` | `get_auth_context` | Import into user's config |

Adversarial config moves from global to per-user-per-tenant. System defaults provide the reset target.

---

## 3.14 Reports Router (`/api/reports`) — 5 endpoints

| Endpoint | Auth | Notes |
|----------|------|-------|
| `GET /cross-run-analytics` | `get_auth_context` | Scope `evaluation_analytics` by `tenant_id` + `app_id` |
| `POST /cross-run-analytics/refresh` | `get_auth_context` | Recompute for user's runs within tenant |
| `GET /{run_id}/export-pdf` | `get_auth_context` | Verify run ownership before export |
| `GET /{run_id}` | `get_auth_context` | Verify run ownership before generating report |
| `POST /cross-run-ai-summary` | `get_auth_context` | Pass auth to settings lookup + scope to user's runs |

---

## 3.15 Admin Router (`/api/admin`) — 2 existing + new user management

### Existing Endpoints (Modified)

| Endpoint | Auth | Notes |
|----------|------|-------|
| `GET /stats` | `require_admin` | Scope counts to `tenant_id` (admin sees all users' data within tenant) |
| `POST /erase` | `require_owner` | Scope erasure to `tenant_id`; only owner can erase |

### New User Management Endpoints

| Endpoint | Auth | Purpose |
|----------|------|---------|
| `GET /admin/users` | `require_admin` | List users in tenant |
| `POST /admin/users` | `require_admin` | Create user in tenant |
| `PATCH /admin/users/{id}` | `require_admin` | Update user (name, role, is_active) |
| `DELETE /admin/users/{id}` | `require_owner` | Deactivate user |

### New Tenant Management (Owner Only)

| Endpoint | Auth | Purpose |
|----------|------|---------|
| `GET /admin/tenant` | `require_owner` | Get tenant details |
| `PATCH /admin/tenant` | `require_owner` | Update tenant name |

---

## 3.16 Pydantic Schema Updates

Every response schema that currently has `user_id: str = "default"` changes to:

```python
class ListingResponse(CamelORMModel):
    # ... existing fields ...
    tenant_id: str     # UUID as string
    user_id: str       # UUID as string
```

Remove all `= "default"` defaults from response schemas. These are always populated from the database.

### Files to Modify

All schema files in `backend/app/schemas/`:
- `listing.py` — add `tenant_id` to Create/Response
- `eval_run.py` — add `tenant_id` to Create/Response
- `chat.py` — add `tenant_id` to Session/Message Create/Response
- `prompt.py` — add `tenant_id` to Create/Response
- `schema.py` — add `tenant_id` to Create/Response
- `evaluator.py` — add `tenant_id` to Create/Response
- `job.py` — add `tenant_id` to Create/Response
- `file.py` — add `tenant_id` to Response
- `tag.py` — add `tenant_id` to Create/Response
- `history.py` — add `tenant_id` to Create/Response
- `setting.py` — add `tenant_id` to Create/Response

**Note:** `tenant_id` and `user_id` are NOT accepted in Create schemas from the client. They are injected server-side from `AuthContext`. The Create schemas should NOT include these fields — the route handler adds them.

---

## 3.17 Summary: Route File Changes

| File | Endpoints | Auth Dependency | Key Notes |
|------|-----------|-----------------|-----------|
| `routes/auth.py` | 5 | None (public) | New file |
| `routes/listings.py` | 6 | `get_auth_context` | Standard scoping |
| `routes/files.py` | 4 | `get_auth_context` | Standard scoping |
| `routes/prompts.py` | 6 | `get_auth_context` | System prompts visibility |
| `routes/schemas.py` | 7 | `get_auth_context` | System schemas visibility |
| `routes/evaluators.py` | 12 | `get_auth_context` | System evaluators visibility; fork copies |
| `routes/chat.py` | 12 | `get_auth_context` | Session→message ownership chain |
| `routes/jobs.py` | 4 | `get_auth_context` | Inject auth into job params |
| `routes/eval_runs.py` | 11 | `get_auth_context` | Run→children ownership chain |
| `routes/settings.py` | 5 | `get_auth_context` | Per-user settings; no more "default" |
| `routes/tags.py` | 7 | `get_auth_context` | Standard scoping |
| `routes/history.py` | 5 | `get_auth_context` | Standard scoping |
| `routes/llm.py` | 3 | `get_auth_context` | Pass auth to settings helper |
| `routes/adversarial_config.py` | 5 | `get_auth_context` | Per-user config |
| `routes/reports.py` | 5 | `get_auth_context` | Run ownership + tenant analytics |
| `routes/admin.py` | 6+ | `require_admin`/`require_owner` | User mgmt + tenant mgmt |

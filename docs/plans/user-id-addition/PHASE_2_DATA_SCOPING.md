# Phase 2: Data Model & Route Scoping

## Goal

Every piece of user-created data is owned by a user. All existing routes enforce `user_id` filtering. Seed/system data remains accessible to all users. After this phase, the backend is fully user-scoped.

**Prerequisite:** Phase 1 complete (User model + `get_current_user` dependency available).

---

## 2.1 — Update `UserMixin` in `base.py`

**File:** `backend/app/models/base.py`

### Current

```python
class UserMixin:
    user_id: Mapped[str] = mapped_column(String(100), default="default")
```

### Target

```python
class UserMixin:
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,   # NULL = system-owned / seed data
        index=True,
    )
```

### Implications

- **All 14 tables** using UserMixin get a UUID FK column instead of a string.
- `nullable=True` allows seed data to have `user_id = NULL`.
- `ondelete="CASCADE"` — deleting a user deletes all their data (clean teardown).
- Index on `user_id` for performant filtered queries.
- **Since all existing data is being deleted**, this is a clean schema change — no migration needed, just drop and recreate tables.

---

## 2.2 — Seed Data Strategy

Seed data (default prompts, schemas, global evaluators) must be accessible to all users without duplication.

### Rules

| Data Type | Ownership | Query Pattern |
|-----------|-----------|--------------|
| Default prompts (`is_default=True`) | `user_id = NULL` | `WHERE (user_id = :uid OR user_id IS NULL)` |
| Default schemas (`is_default=True`) | `user_id = NULL` | `WHERE (user_id = :uid OR user_id IS NULL)` |
| Global evaluators (`is_global=True`) | `user_id = NULL` | `WHERE (user_id = :uid OR user_id IS NULL)` |
| User-created prompts | `user_id = <user_uuid>` | `WHERE user_id = :uid` |
| User-created listings | `user_id = <user_uuid>` | `WHERE user_id = :uid` |
| All other user data | `user_id = <user_uuid>` | `WHERE user_id = :uid` |

### Update Seed Functions

In `seed_defaults.py` (or wherever seeding happens in lifespan):
- Change `user_id="default"` → `user_id=None` for all seed inserts.
- Ensure seed upsert logic uses `(app_id, key, user_id IS NULL)` for conflict detection.

---

## 2.3 — Composite Query Helper

Create a reusable SQLAlchemy helper to avoid duplicating the `user_id` filter logic across all 15 routers.

**File:** `backend/app/auth.py` (extend, or new `backend/app/utils/query_scope.py`)

```python
from sqlalchemy import or_

def user_scope(model, user_id: uuid.UUID, *, include_system: bool = False):
    """Return a WHERE clause that scopes a query to the given user.

    If include_system=True, also includes rows with user_id=NULL (seed/system data).
    """
    if include_system:
        return or_(model.user_id == user_id, model.user_id.is_(None))
    return model.user_id == user_id
```

Usage in routes:
```python
query = select(Prompt).where(
    Prompt.app_id == app_id,
    user_scope(Prompt, current_user.id, include_system=True),
)
```

---

## 2.4 — Route-by-Route Scoping

Every router gets `current_user: User = Depends(get_current_user)` added as a parameter. Below is the scoping strategy per router.

### Pattern A: User-only data (no system rows)

Used by: `listings`, `files`, `chat`, `history`, `tags`, `eval_runs`, `threads`, `jobs`

```python
# LIST: filter by user
.where(Model.app_id == app_id, Model.user_id == current_user.id)

# CREATE: set user_id from auth
new_row = Model(**body.model_dump(), user_id=current_user.id)

# GET/UPDATE/DELETE: verify ownership
.where(Model.id == item_id, Model.user_id == current_user.id)
```

### Pattern B: User data + system seed (read-only system rows)

Used by: `prompts`, `schemas`, `evaluators`

```python
# LIST: include system rows
.where(Model.app_id == app_id, user_scope(Model, current_user.id, include_system=True))

# CREATE: set user_id from auth
new_row = Model(**body.model_dump(), user_id=current_user.id)

# UPDATE/DELETE: user-owned only (block modification of system rows)
.where(Model.id == item_id, Model.user_id == current_user.id)
# If not found → 404. System rows are implicitly protected.
```

### Pattern C: Settings (user-scoped with global fallback)

Used by: `settings`

```python
# GET: user's setting, or fall back to system default
.where(Setting.app_id == resolved_app_id, Setting.key == key, Setting.user_id == current_user.id)
# If not found → try user_id IS NULL for system defaults

# UPSERT: always write to user's row
upsert with (app_id, key, user_id=current_user.id)
```

### Pattern D: Admin-only

Used by: `admin`

```python
# All endpoints: require_admin(current_user)
# Stats/erase can operate across users (admin privilege)
```

### Pattern E: Read-only / informational

Used by: `llm` (auth-status, model discovery)

```python
# These endpoints just need authentication, no user_id filtering.
# Add get_current_user dependency for access control but no data scoping.
```

### Pattern F: Adversarial config

Used by: `adversarial_config`

```python
# Scoped like Pattern A — user-owned adversarial configurations.
```

---

## 2.5 — Router Change Matrix

| Router File | Pattern | `include_system` | Notes |
|-------------|---------|-------------------|-------|
| `listings.py` | A | No | Listings are always user-owned |
| `files.py` | A | No | Files belong to listings (user-owned) |
| `prompts.py` | B | Yes | System defaults visible to all |
| `schemas.py` | B | Yes | System defaults visible to all |
| `evaluators.py` | B | Yes | Global evaluators visible to all |
| `chat.py` | A | No | Chat sessions are user-owned |
| `history.py` | A | No | History entries are user-owned |
| `settings.py` | C | Special | User override + system fallback |
| `tags.py` | A | No | Tags are user-owned |
| `jobs.py` | A | No | Jobs are user-owned |
| `eval_runs.py` | A | No | Eval runs are user-owned |
| `threads.py` | A | No | Thread evaluations inherit from eval_run |
| `llm.py` | E | N/A | Auth required, no data scoping |
| `adversarial_config.py` | F | No | User-owned configs |
| `admin.py` | D | N/A | Admin-only, cross-user access |

---

## 2.6 — FK Cascade Implications

Current cascade chain: `Listing → EvalRun → ThreadEvaluation / AdversarialEvaluation / ApiLog`

With `User → (all tables via UserMixin)` cascade:
- Deleting a user cascades to ALL their data across all tables.
- This is the desired behavior for account deletion.
- **No additional FK changes needed** — the existing inter-table cascades remain intact. The new `users.id` FK is additive.

---

## 2.7 — Schema Changes (Pydantic)

All `*Response` schemas currently have:
```python
user_id: str = "default"
```

Change to:
```python
user_id: uuid.UUID | None = None
```

All `*Create` schemas: **Remove `user_id` field entirely** — it's set server-side from `current_user.id`, never accepted from the client.

---

## 2.8 — Unique Constraint Updates

### Settings Table

Current constraint: `UniqueConstraint("app_id", "key", "user_id", name="uq_setting")`

This still works — now `user_id` is a UUID instead of a string. The same `(app_id, key, user_id)` tuple ensures one setting per user per key per app.

Update the upsert in `settings.py` route:
```python
pg_insert(Setting).values(
    app_id=app_id,
    key=body.key,
    value=body.value,
    user_id=current_user.id,  # was "default"
)
```

### Other Tables

Check for any other unique constraints involving `user_id` and ensure they still hold with UUID type.

---

## 2.9 — Admin Stats Update

The admin `/stats` endpoint currently distinguishes seed vs user data by checking `user_id == "default"`. Update to:
- Seed data: `user_id IS NULL`
- User data: `user_id IS NOT NULL`
- Per-user breakdown: `GROUP BY user_id`

---

## Verification Checklist

- [ ] All 14 existing tables have `user_id` as UUID FK → `users.id` (nullable).
- [ ] Seed data rows have `user_id = NULL`.
- [ ] `GET /api/listings?app_id=voice-rx` returns only current user's listings.
- [ ] `GET /api/prompts?app_id=voice-rx` returns user's + system prompts.
- [ ] `DELETE` on a system prompt returns 404 (not owned by user).
- [ ] `POST` to create any resource sets `user_id` from auth, ignoring any client-sent value.
- [ ] Settings upsert writes to user's row, not system row.
- [ ] Admin endpoints require admin role, return 403 for regular users.
- [ ] Deleting a user cascades all their data.
- [ ] Job listing shows only current user's jobs.
- [ ] Eval runs listing shows only current user's runs.

# Phase 3: Per-User Settings & API Keys

## Goal

Each user has their own LLM API keys, app-specific settings, and profile. The settings system (already column-ready from Phase 2) is fully user-scoped. LLM provider factory resolves credentials per-user.

**Prerequisite:** Phase 2 complete (user_id FK on all tables, routes scoped).

---

## 3.1 — Settings Scoping (Backend)

### Current Settings Keys (from `settingsRepository` usage)

| `app_id` | `key` | Contains |
|----------|-------|----------|
| `''` (global) | `llm-settings` | Provider, model, API keys, auth method, step models |
| `''` (global) | `timeouts` | LLM timeout values |
| `'voice-rx'` | `api-credentials` | Voice Rx API URL + key |
| `'kaira-bot'` | `api-credentials` | Kaira API URL + auth token + user ID |

### New Behavior

All of the above become **per-user**. The `(app_id, key, user_id)` unique constraint (already exists) naturally handles this.

- User A's LLM keys: `('', 'llm-settings', user_a_uuid)`
- User B's LLM keys: `('', 'llm-settings', user_b_uuid)`

### System-Default Settings

For settings where a sensible default exists (e.g., timeouts), seed a system row:
```
('', 'timeouts', NULL)  →  { textOnly: 60, withSchema: 90, ... }
```

Settings GET logic (Phase 2, Pattern C) already falls back to `user_id IS NULL` when the user has no override. No additional backend changes needed beyond what Phase 2 established.

---

## 3.2 — LLM Credential Resolution

### Current Flow

```
Frontend Settings page → saves to backend settings API →
Job worker reads settings from DB → creates LLM provider
```

The credential resolution happens in the evaluator runners (e.g., `voice_rx_runner.py`, `batch_runner.py`) which read settings from the DB.

### Required Change: `settings_helper.py`

**File:** `backend/app/services/evaluators/settings_helper.py` (or wherever LLM settings are resolved)

Current pattern (conceptual):
```python
async def get_llm_settings(db, app_id):
    setting = await db.execute(
        select(Setting).where(Setting.app_id == "", Setting.key == "llm-settings")
    )
    return setting.scalar_one_or_none()
```

New pattern — **accept `user_id` parameter**:
```python
async def get_llm_settings(db, app_id, user_id: uuid.UUID):
    # Try user-specific settings first
    setting = await db.execute(
        select(Setting).where(
            Setting.app_id == "",
            Setting.key == "llm-settings",
            Setting.user_id == user_id,
        )
    )
    result = setting.scalar_one_or_none()
    if result:
        return result.value

    # Fall back to system defaults (user_id IS NULL)
    setting = await db.execute(
        select(Setting).where(
            Setting.app_id == "",
            Setting.key == "llm-settings",
            Setting.user_id.is_(None),
        )
    )
    result = setting.scalar_one_or_none()
    return result.value if result else None
```

### Provider Factory Update

**File:** `backend/app/services/evaluators/llm_base.py`

`create_llm_provider()` is a dumb constructor — it doesn't know about users. Keep it that way.

The **callers** (runners) are responsible for resolving the user's credentials and passing them in. The user_id flows through the job params (Phase 5) → runner reads user's settings → passes API key to `create_llm_provider()`.

### Service Account Override

For the Gemini service account (Vertex AI), this is a **server-level** credential, not per-user. The service account file is on the server filesystem.

Decision: **Service account remains shared.** Per-user scoping applies to:
- `geminiApiKey` — user's own API key for the Developer API
- `openaiApiKey` — user's own OpenAI key
- `provider` / `selectedModel` — user's preference

The `geminiAuthMethod` and `serviceAccountPath` remain server-level config in `.env.backend`.

---

## 3.3 — Per-User API Keys Security

### Storage

API keys are stored in the `settings.value` JSONB column. Currently in plaintext.

### Recommendation (keep simple for now)

- Store API keys as-is in JSONB (same as current behavior).
- The `settings` table is already behind auth. Users can only read their own keys.
- **Future enhancement:** Encrypt `value` column at rest using a server-side key (AES-256). Out of scope for this phase.

### API Response Masking

When returning settings that contain API keys via `GET /api/settings`:
- Return masked values for `apiKey`, `geminiApiKey`, `openaiApiKey` fields.
- Example: `"sk-...abc123"` → `"sk-...c123"` (last 4 chars).
- The frontend only needs masked display. Full key is only used server-side.
- Add a `maskSensitiveFields(value: dict) -> dict` utility.

**Exception:** `PUT /api/settings` accepts the full key. If the client sends a masked value (contains `...`), preserve the existing DB value for that field.

---

## 3.4 — User Profile Endpoint

Already defined in Phase 1 (`PUT /api/auth/me`). This phase adds:

### `GET /api/auth/me` — Extended Response

Add to `UserResponse`:
```python
class UserResponse(CamelORMModel):
    id: uuid.UUID
    email: str
    name: str
    role: str
    is_active: bool
    created_at: datetime
    # Phase 3 additions:
    has_llm_keys: bool      # Whether user has LLM settings configured
    app_ids: list[str]       # Apps the user has data in
```

These are computed fields, not stored:
- `has_llm_keys`: Check if a `('', 'llm-settings', user_id)` setting exists with a non-empty API key.
- `app_ids`: `SELECT DISTINCT app_id FROM listings WHERE user_id = :uid`

---

## 3.5 — Admin User Management

### New Endpoints in `admin.py`

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/admin/users` | GET | List all users (admin only) |
| `/api/admin/users/{user_id}` | GET | Get user details (admin only) |
| `/api/admin/users/{user_id}` | PUT | Update user role/active status (admin only) |
| `/api/admin/users/{user_id}` | DELETE | Delete user + cascade all data (admin only) |

### User Listing Response

```python
class AdminUserResponse(CamelORMModel):
    id: uuid.UUID
    email: str
    name: str
    role: str
    is_active: bool
    created_at: datetime
    data_counts: dict    # { listings: 5, evalRuns: 12, ... }
```

`data_counts` is computed by counting rows per table for that user_id. Reuse the existing admin stats logic.

---

## 3.6 — Initialization Flow for New Users

When a new user registers (Phase 1's `/api/auth/register`):

1. Create `User` row.
2. **Do NOT auto-create settings rows.** The system defaults (`user_id = NULL`) serve as fallback.
3. User sees default prompts, schemas, evaluators (system-owned).
4. When user first saves LLM settings, their personal row is created.

This keeps the DB clean — no eager row creation.

---

## Verification Checklist

- [ ] User A's LLM API key is not visible to User B.
- [ ] User A changing their model selection doesn't affect User B.
- [ ] Voice Rx API credentials are per-user.
- [ ] Kaira Bot credentials are per-user.
- [ ] Timeout settings fall back to system defaults when user hasn't customized.
- [ ] API key values are masked in GET responses.
- [ ] Admin can list all users with data counts.
- [ ] Admin can deactivate a user (sets `is_active=False`).
- [ ] Admin can delete a user (cascades all data).
- [ ] New user registration doesn't create any settings rows.
- [ ] New user can immediately see system default prompts/schemas.

# Phase 1 — Data Model

## Prerequisites

- `docker compose down -v` to wipe all data and volumes
- No migration scripts needed — clean `metadata.create_all()` on startup

## 1.1 New Table: `tenants`

```python
# backend/app/models/tenant.py

class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    users: Mapped[list["User"]] = relationship(back_populates="tenant", cascade="all, delete-orphan")
```

### Fields

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| `id` | UUID | PK, default uuid4 | Unique tenant identifier |
| `name` | String(255) | NOT NULL | Display name (e.g., "AI Tatva") |
| `slug` | String(100) | UNIQUE, NOT NULL | URL-safe identifier (e.g., "ai-tatva") |
| `is_active` | Boolean | NOT NULL, default True | Soft-disable tenant |
| `created_at` | DateTime(tz) | server_default now() | Creation timestamp |
| `updated_at` | DateTime(tz) | server_default now(), onupdate | Last modification |

### Indexes

- `uq_tenants_slug` — UNIQUE on `slug`

---

## 1.2 New Table: `users`

```python
# backend/app/models/user.py

class UserRole(str, enum.Enum):
    OWNER = "owner"      # Full control, can manage tenant settings
    ADMIN = "admin"      # Can manage users within tenant
    MEMBER = "member"    # Standard user, sees only own data

class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SQLEnum(UserRole), nullable=False, default=UserRole.MEMBER
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship(back_populates="users")

    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_user_email_per_tenant"),
    )
```

### Fields

| Column | Type | Constraints | Purpose |
|--------|------|-------------|---------|
| `id` | UUID | PK | User identifier, used in JWT `sub` claim |
| `tenant_id` | UUID | FK → tenants.id CASCADE, NOT NULL | Owning tenant |
| `email` | String(255) | NOT NULL | Login identifier |
| `password_hash` | String(255) | NOT NULL | bcrypt hash |
| `display_name` | String(255) | NOT NULL | Human-readable name |
| `role` | Enum(owner/admin/member) | NOT NULL, default member | Permission level |
| `is_active` | Boolean | NOT NULL, default True | Soft-disable user |
| `created_at` | DateTime(tz) | server_default now() | Account creation |
| `updated_at` | DateTime(tz) | server_default now(), onupdate | Last modification |

### Indexes

- `uq_user_email_per_tenant` — UNIQUE on `(tenant_id, email)` — same email can exist in different tenants

### Design Decision: Email Uniqueness

Email is unique **per tenant**, not globally. This supports SaaS where the same person could belong to multiple organizations. If global uniqueness is later needed, add a cross-tenant lookup table.

---

## 1.3 New Table: `refresh_tokens`

```python
# backend/app/models/user.py (same file)

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("idx_refresh_tokens_user", "user_id"),
        Index("idx_refresh_tokens_expires", "expires_at"),
    )
```

### Purpose

- Enables token rotation (each refresh issues a new refresh token)
- Allows server-side revocation (logout, password change)
- `token_hash` stores SHA-256 of the actual token (never store raw tokens)
- Expired tokens cleaned up periodically

---

## 1.4 Modify `UserMixin` → `TenantUserMixin`

### Current (`backend/app/models/base.py`)

```python
class UserMixin:
    user_id: Mapped[str] = mapped_column(String(100), default="default")
```

### New

```python
class TenantUserMixin:
    """Adds tenant_id and user_id columns. Both are required FK references."""
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
```

**No defaults.** Every record must be explicitly created with tenant_id and user_id from the auth context.

### Impact

All 12 models currently using `UserMixin` switch to `TenantUserMixin`:
1. `EvalRun`
2. `Listing`
3. `ChatSession`
4. `ChatMessage`
5. `Prompt`
6. `Schema`
7. `Evaluator`
8. `Job`
9. `FileRecord`
10. `Tag`
11. `History`
12. `Setting`

---

## 1.5 Modify Existing Models

### Changes Per Model

Every model using the new `TenantUserMixin` needs:

1. **Replace `UserMixin`** with `TenantUserMixin` in class inheritance
2. **Update unique constraints** to include `tenant_id`
3. **Add composite indexes** on `(tenant_id, user_id)` for query performance

### Constraint Changes

| Model | Old Constraint | New Constraint |
|-------|---------------|----------------|
| `Prompt` | `uq_prompt_version(app_id, prompt_type, version, user_id)` | `uq_prompt_version(tenant_id, app_id, prompt_type, version, user_id)` |
| `Schema` | `uq_schema_version(app_id, prompt_type, version, user_id)` | `uq_schema_version(tenant_id, app_id, prompt_type, version, user_id)` |
| `Tag` | `uq_tag(app_id, name, user_id)` | `uq_tag(tenant_id, app_id, name, user_id)` |
| `Setting` | `uq_setting(app_id, key, user_id)` | `uq_setting(tenant_id, app_id, key, user_id)` |

### New Indexes (All Models with TenantUserMixin)

```python
# On every table using TenantUserMixin:
Index("idx_{table}_tenant", "tenant_id")
Index("idx_{table}_tenant_user", "tenant_id", "user_id")

# On tables with app_id:
Index("idx_{table}_tenant_app", "tenant_id", "app_id")
```

### Specific Model Changes

#### `EvalRun`
```python
class EvalRun(Base, TenantUserMixin):
    # existing columns unchanged
    __table_args__ = (
        Index("idx_eval_runs_tenant_app", "tenant_id", "app_id", "created_at"),
        Index("idx_eval_runs_tenant_user", "tenant_id", "user_id", "created_at"),
        # keep existing indexes
    )
```

#### `Setting`
```python
class Setting(Base, TenantUserMixin):
    # existing columns unchanged
    __table_args__ = (
        UniqueConstraint("tenant_id", "app_id", "key", "user_id", name="uq_setting"),
    )
```

LLM settings scoping changes:
- **Old:** `app_id=""`, `user_id="default"` (global singleton)
- **New:** `tenant_id=<tenant>`, `app_id=""`, `user_id=<user>` (per-user within tenant)
- **Tenant-wide settings:** `user_id = SYSTEM_USER_ID` for settings shared across all users in a tenant

#### `EvaluationAnalytics`
```python
class EvaluationAnalytics(Base):
    # Add tenant_id (no UserMixin — analytics are tenant-scoped, not user-scoped)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    __table_args__ = (
        UniqueConstraint("tenant_id", "app_id", "scope", "run_id", name="uq_analytics_app_scope_run"),
        Index("idx_analytics_tenant_app", "tenant_id", "app_id"),
    )
```

#### Child Tables (No Direct Tenant Column)

`ThreadEvaluation`, `AdversarialEvaluation`, `ApiLog` — these are always accessed via their parent `EvalRun` (FK cascade). No `tenant_id` or `user_id` column needed. Access control enforced at the `EvalRun` level.

---

## 1.6 System Tenant and System User

For seed data (system prompts, system schemas, global evaluators), use well-known UUIDs:

```python
# backend/app/constants.py (new file)
import uuid

SYSTEM_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
SYSTEM_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
```

### Seed Logic

On startup:
1. Ensure system tenant exists (`id=SYSTEM_TENANT_ID, name="System", slug="system"`)
2. Ensure system user exists (`id=SYSTEM_USER_ID, tenant_id=SYSTEM_TENANT_ID, email="system@internal", role=owner`)
3. Seed prompts/schemas/evaluators with `tenant_id=SYSTEM_TENANT_ID, user_id=SYSTEM_USER_ID`

### Query Pattern for Shared Data

```python
# User sees their own prompts + system defaults
select(Prompt).where(
    or_(
        and_(Prompt.tenant_id == auth.tenant_id, Prompt.user_id == auth.user_id),
        Prompt.tenant_id == SYSTEM_TENANT_ID,
    ),
    Prompt.app_id == app_id,
)
```

This replaces the old `is_default=True` + `user_id="default"` pattern.

---

## 1.7 Model Registration

### `backend/app/models/__init__.py`

Add new imports:
```python
from .tenant import Tenant
from .user import User, UserRole, RefreshToken
```

Ensure all models are imported so `metadata.create_all()` picks them up.

---

## 1.8 Complete Schema of All Tables (Post-Change)

```
tenants
├── id (UUID PK)
├── name (String)
├── slug (String UNIQUE)
├── is_active (Boolean)
├── created_at, updated_at

users
├── id (UUID PK)
├── tenant_id (FK → tenants.id CASCADE)
├── email (String)
├── password_hash (String)
├── display_name (String)
├── role (Enum: owner/admin/member)
├── is_active (Boolean)
├── created_at, updated_at
├── UNIQUE(tenant_id, email)

refresh_tokens
├── id (UUID PK)
├── user_id (FK → users.id CASCADE)
├── token_hash (String UNIQUE)
├── expires_at (DateTime)
├── created_at

listings
├── id (UUID PK)
├── tenant_id (FK → tenants.id CASCADE)    ← NEW
├── user_id (FK → users.id CASCADE)         ← CHANGED from String to UUID FK
├── app_id, title, status, source_type, ...

eval_runs
├── id (UUID PK)
├── tenant_id (FK → tenants.id CASCADE)    ← NEW
├── user_id (FK → users.id CASCADE)         ← CHANGED
├── app_id, eval_type, listing_id, session_id, ...

chat_sessions
├── id (UUID PK)
├── tenant_id (FK → tenants.id CASCADE)    ← NEW
├── user_id (FK → users.id CASCADE)         ← CHANGED
├── app_id, external_user_id, thread_id, ...

chat_messages
├── id (UUID PK)
├── tenant_id (FK → tenants.id CASCADE)    ← NEW
├── user_id (FK → users.id CASCADE)         ← CHANGED
├── session_id (FK), role, content, ...

prompts
├── id (Integer PK)
├── tenant_id (FK → tenants.id CASCADE)    ← NEW
├── user_id (FK → users.id CASCADE)         ← CHANGED
├── app_id, prompt_type, version, ...
├── UNIQUE(tenant_id, app_id, prompt_type, version, user_id)

schemas
├── id (Integer PK)
├── tenant_id (FK → tenants.id CASCADE)    ← NEW
├── user_id (FK → users.id CASCADE)         ← CHANGED
├── app_id, prompt_type, version, ...
├── UNIQUE(tenant_id, app_id, prompt_type, version, user_id)

evaluators
├── id (UUID PK)
├── tenant_id (FK → tenants.id CASCADE)    ← NEW
├── user_id (FK → users.id CASCADE)         ← CHANGED
├── app_id, name, prompt, model_id, ...

jobs
├── id (UUID PK)
├── tenant_id (FK → tenants.id CASCADE)    ← NEW
├── user_id (FK → users.id CASCADE)         ← CHANGED
├── job_type, status, params, ...

files
├── id (UUID PK)
├── tenant_id (FK → tenants.id CASCADE)    ← NEW
├── user_id (FK → users.id CASCADE)         ← CHANGED
├── original_name, mime_type, ...

tags
├── id (Integer PK)
├── tenant_id (FK → tenants.id CASCADE)    ← NEW
├── user_id (FK → users.id CASCADE)         ← CHANGED
├── app_id, name, count, ...
├── UNIQUE(tenant_id, app_id, name, user_id)

history
├── id (UUID PK)
├── tenant_id (FK → tenants.id CASCADE)    ← NEW
├── user_id (FK → users.id CASCADE)         ← CHANGED
├── app_id, entity_type, ...

settings
├── id (Integer PK)
├── tenant_id (FK → tenants.id CASCADE)    ← NEW
├── user_id (FK → users.id CASCADE)         ← CHANGED
├── app_id, key, value, ...
├── UNIQUE(tenant_id, app_id, key, user_id)

evaluation_analytics
├── id (UUID PK)
├── tenant_id (FK → tenants.id CASCADE)    ← NEW
├── app_id, scope, run_id, ...
├── UNIQUE(tenant_id, app_id, scope, run_id)

thread_evaluations    ← UNCHANGED (access via eval_run FK)
adversarial_evaluations ← UNCHANGED
api_logs              ← UNCHANGED
```

---

## 1.9 Files to Create/Modify

| File | Action | Changes |
|------|--------|---------|
| `backend/app/models/tenant.py` | CREATE | Tenant model |
| `backend/app/models/user.py` | CREATE | User, UserRole, RefreshToken models |
| `backend/app/constants.py` | CREATE | SYSTEM_TENANT_ID, SYSTEM_USER_ID |
| `backend/app/models/base.py` | MODIFY | Replace `UserMixin` with `TenantUserMixin` |
| `backend/app/models/__init__.py` | MODIFY | Add Tenant, User, RefreshToken imports |
| `backend/app/models/eval_run.py` | MODIFY | TenantUserMixin, updated indexes |
| `backend/app/models/listing.py` | MODIFY | TenantUserMixin, updated indexes |
| `backend/app/models/chat.py` | MODIFY | TenantUserMixin on ChatSession + ChatMessage |
| `backend/app/models/prompt.py` | MODIFY | TenantUserMixin, updated unique constraint |
| `backend/app/models/schema.py` | MODIFY | TenantUserMixin, updated unique constraint |
| `backend/app/models/evaluator.py` | MODIFY | TenantUserMixin, updated indexes |
| `backend/app/models/job.py` | MODIFY | TenantUserMixin |
| `backend/app/models/file_record.py` | MODIFY | TenantUserMixin |
| `backend/app/models/tag.py` | MODIFY | TenantUserMixin, updated unique constraint |
| `backend/app/models/history.py` | MODIFY | TenantUserMixin |
| `backend/app/models/setting.py` | MODIFY | TenantUserMixin, updated unique constraint |
| `backend/app/models/evaluation_analytics.py` | MODIFY | Add tenant_id FK, updated constraints |

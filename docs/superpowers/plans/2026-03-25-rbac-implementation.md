# RBAC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement role-based access control with custom roles, app-level access gates, action-level permissions, audit logging, and a frontend permission system.

**Architecture:** Single system role (Owner) with implicit wildcard. Custom roles per tenant with two permission layers: app access (which apps) and action permissions (which operations). Backend enforces via FastAPI dependencies; frontend enforces via `<PermissionGate>` component reading permissions from auth store.

**Tech Stack:** FastAPI, SQLAlchemy async, PostgreSQL, React, TypeScript, Zustand

**Spec:** `docs/superpowers/specs/2026-03-25-rbac-design.md`

---

## File Map

### New Backend Files
| File | Responsibility |
|---|---|
| `backend/app/models/app.py` | `App` ORM model |
| `backend/app/models/role.py` | `Role`, `RoleAppAccess`, `RolePermission` ORM models |
| `backend/app/models/audit_log.py` | `AuditLog` ORM model |
| `backend/app/auth/permissions.py` | `Permission` enum, `load_role_permissions()`, `require_permission()`, `require_app_access()` |
| `backend/app/services/audit.py` | `write_audit_log()` helper |
| `backend/app/routes/apps.py` | `GET /api/apps` route |
| `backend/app/routes/roles.py` | Role CRUD routes (Owner only) |
| `backend/app/schemas/role.py` | Pydantic schemas for roles API |
| `backend/app/schemas/audit.py` | Pydantic schemas for audit log API |
| `backend/tests/test_permissions.py` | Unit tests for permission logic |

### New Frontend Files
| File | Responsibility |
|---|---|
| `src/components/auth/PermissionGate.tsx` | `<PermissionGate>` + `<AppAccessGuard>` |
| `src/utils/permissions.ts` | `hasPermission()`, `hasAppAccess()`, `usePermission()` hook |
| `src/services/api/rolesApi.ts` | Roles + apps API client |
| `src/features/admin/RolesTab.tsx` | Roles list + create/edit |
| `src/features/admin/RoleEditorDialog.tsx` | Role editor (app access + permission grid) |
| `src/features/admin/AuditLogTab.tsx` | Audit log viewer |

### Modified Backend Files
| File | Change |
|---|---|
| `backend/app/models/user.py` | Drop `UserRole` enum + `role` column, add `role_id` FK |
| `backend/app/models/invite_link.py` | Drop `default_role`, add `role_id` FK |
| `backend/app/models/__init__.py` | Register new models |
| `backend/app/auth/context.py` | New `AuthContext` with `role_id`, `is_owner`, `permissions`, `app_access` |
| `backend/app/auth/utils.py` | JWT `role` → `rid` (role_id) |
| `backend/app/services/seed_defaults.py` | Seed apps table + Owner role per tenant |
| `backend/app/routes/auth.py` | Update `/me`, login, signup for new role model |
| `backend/app/routes/admin.py` | Replace `require_admin`/`require_owner` with `require_permission()` |
| `backend/app/routes/listings.py` | Add `require_permission()` + `require_app_access()` |
| `backend/app/routes/eval_runs.py` | Add `require_permission()` + `require_app_access()` |
| `backend/app/routes/jobs.py` | Add `require_permission()` + `require_app_access()` |
| `backend/app/routes/prompts.py` | Add `require_permission()` + `require_app_access()` |
| `backend/app/routes/schemas.py` | Add `require_permission()` + `require_app_access()` |
| `backend/app/routes/evaluators.py` | Add `require_permission()` + `require_app_access()` |
| `backend/app/routes/chat.py` | Add `require_permission()` + `require_app_access()` |
| `backend/app/routes/files.py` | Add `require_permission()` + `require_app_access()` |
| `backend/app/routes/tags.py` | Add `require_permission()` + `require_app_access()` |
| `backend/app/routes/history.py` | Add `require_permission()` + `require_app_access()` |
| `backend/app/routes/settings.py` | Add `require_permission()` |
| `backend/app/routes/reports.py` | Add `require_permission()` + `require_app_access()` |
| `backend/app/routes/adversarial_config.py` | Add `require_permission()` + `require_app_access()` |
| `backend/app/routes/inside_sales.py` | Add `require_app_access()` |
| `backend/app/main.py` | Register new routers (apps, roles) |

### Modified Frontend Files
| File | Change |
|---|---|
| `src/types/auth.types.ts` | New `User` shape with `roleId`, `roleName`, `isOwner`, `permissions`, `appAccess` |
| `src/stores/authStore.ts` | Handle new user shape |
| `src/services/api/authApi.ts` | Handle new `/me` response |
| `src/services/api/adminApi.ts` | Add roles + audit log endpoints |
| `src/components/layout/AppSwitcher.tsx` | Filter by app access |
| `src/features/auth/AdminGuard.tsx` | Replace role check with permission check |
| `src/app/Router.tsx` | Add `AppAccessGuard` wrapping per-app routes |
| `src/features/admin/AdminUsersPage.tsx` | Wire Roles tab + Security tab, PermissionGate on buttons |
| `src/features/admin/InviteLinksSection.tsx` | Role dropdown instead of enum, PermissionGate |
| `src/features/admin/CreateUserDialog.tsx` | Role dropdown from API |
| `src/features/admin/EditUserDialog.tsx` | Role dropdown from API, PermissionGate |
| ~30 feature components | Wrap action buttons with `<PermissionGate>` (see Section 7 of spec) |

---

## Task 1: Backend Models — App, Role, RoleAppAccess, RolePermission, AuditLog

**Files:**
- Create: `backend/app/models/app.py`
- Create: `backend/app/models/role.py`
- Create: `backend/app/models/audit_log.py`

- [ ] **Step 1: Create App model**

```python
# backend/app/models/app.py
"""App model — registered applications available platform-wide."""
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class App(Base):
    __tablename__ = "apps"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    slug: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    icon_url: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

- [ ] **Step 2: Create Role, RoleAppAccess, RolePermission models**

```python
# backend/app/models/role.py
"""Role models — RBAC roles, app access grants, and action permissions."""
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, ForeignKey, DateTime, Index, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    app_access: Mapped[list["RoleAppAccess"]] = relationship(
        "RoleAppAccess", back_populates="role", cascade="all, delete-orphan"
    )
    permissions: Mapped[list["RolePermission"]] = relationship(
        "RolePermission", back_populates="role", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_role_name_per_tenant"),
    )


class RoleAppAccess(Base):
    __tablename__ = "role_app_access"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
    )
    app_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("apps.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    role: Mapped["Role"] = relationship("Role", back_populates="app_access")
    app: Mapped["App"] = relationship("App")

    __table_args__ = (
        UniqueConstraint("role_id", "app_id", name="uq_role_app_access"),
    )


class RolePermission(Base):
    __tablename__ = "role_permissions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
    )
    permission: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    role: Mapped["Role"] = relationship("Role", back_populates="permissions")

    __table_args__ = (
        UniqueConstraint("role_id", "permission", name="uq_role_permission"),
    )
```

- [ ] **Step 3: Create AuditLog model**

```python
# backend/app/models/audit_log.py
"""AuditLog model — immutable record of RBAC and user-management changes."""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, ForeignKey, DateTime, Index, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    before_state: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    after_state: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("idx_audit_log_tenant_created", "tenant_id", "created_at"),
        Index("idx_audit_log_entity", "entity_type", "entity_id"),
    )
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/app.py backend/app/models/role.py backend/app/models/audit_log.py
git commit -m "feat(rbac): add App, Role, RoleAppAccess, RolePermission, AuditLog models"
```

---

## Task 2: Modify User + InviteLink Models, Update Registry

**Files:**
- Modify: `backend/app/models/user.py`
- Modify: `backend/app/models/invite_link.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Rewrite User model — drop UserRole enum, add role_id FK**

In `backend/app/models/user.py`:
- Delete the `UserRole` enum class entirely
- Replace `role: Mapped[UserRole]` with `role_id: Mapped[uuid.UUID]` FK → `roles.id`
- Add `role` relationship to Role model

```python
# backend/app/models/user.py
"""User and RefreshToken models — authenticated users within a tenant."""
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, ForeignKey, DateTime, Index, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


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
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="users")
    role: Mapped["Role"] = relationship("Role", lazy="joined")

    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_user_email_per_tenant"),
    )


# RefreshToken stays unchanged (keep existing code)
```

- [ ] **Step 2: Rewrite InviteLink — drop default_role, add role_id FK**

In `backend/app/models/invite_link.py`:
- Remove import of `UserRole`
- Replace `default_role` with `role_id` FK → `roles.id`

Replace the `default_role` field with:
```python
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False
    )
```

Remove the `from app.models.user import UserRole` import and the `SQLEnum` import.

- [ ] **Step 3: Update models/__init__.py**

Add new model imports:
```python
from app.models.app import App
from app.models.role import Role, RoleAppAccess, RolePermission
from app.models.audit_log import AuditLog
```

Update `__all__` — remove `UserRole`, add `App`, `Role`, `RoleAppAccess`, `RolePermission`, `AuditLog`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/user.py backend/app/models/invite_link.py backend/app/models/__init__.py
git commit -m "feat(rbac): replace UserRole enum with role_id FK, register new models"
```

---

## Task 3: Permission Enum + Auth Dependencies

**Files:**
- Create: `backend/app/auth/permissions.py`
- Modify: `backend/app/auth/context.py`
- Modify: `backend/app/auth/utils.py`

- [ ] **Step 1: Create Permission enum and auth dependencies**

```python
# backend/app/auth/permissions.py
"""Permission constants and RBAC dependency functions."""
import enum
import uuid
from functools import lru_cache

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.role import Role, RoleAppAccess, RolePermission
from app.models.app import App


class Permission(str, enum.Enum):
    """All grantable permission strings. Validated on write to role_permissions."""
    # Listings
    LISTING_CREATE = "listing:create"
    LISTING_DELETE = "listing:delete"
    # Evaluations
    EVAL_RUN = "eval:run"
    EVAL_DELETE = "eval:delete"
    EVAL_EXPORT = "eval:export"
    # Resources (prompts, schemas, evaluators, tags)
    RESOURCE_CREATE = "resource:create"
    RESOURCE_EDIT = "resource:edit"
    RESOURCE_DELETE = "resource:delete"
    # Reports & Analytics
    REPORT_GENERATE = "report:generate"
    ANALYTICS_VIEW = "analytics:view"
    # Settings
    SETTINGS_EDIT = "settings:edit"
    # User Management
    USER_CREATE = "user:create"
    USER_INVITE = "user:invite"
    USER_EDIT = "user:edit"
    USER_DEACTIVATE = "user:deactivate"
    USER_RESET_PASSWORD = "user:reset_password"
    ROLE_ASSIGN = "role:assign"
    # Tenant
    TENANT_SETTINGS = "tenant:settings"


# Set of all valid permission strings for validation
VALID_PERMISSIONS: frozenset[str] = frozenset(p.value for p in Permission)


async def load_role_permissions(
    db: AsyncSession, role_id: uuid.UUID
) -> tuple["Role", list[str], list[str]]:
    """Load a role with its permissions and app access slugs in one query.

    Returns: (role, permission_strings, app_slugs)
    """
    stmt = (
        select(Role)
        .options(
            selectinload(Role.permissions),
            selectinload(Role.app_access).selectinload(RoleAppAccess.app),
        )
        .where(Role.id == role_id)
    )
    result = await db.execute(stmt)
    role = result.scalar_one_or_none()
    if role is None:
        raise HTTPException(401, "Role not found — token may be stale")

    perm_strings = [rp.permission for rp in role.permissions]
    app_slugs = [ra.app.slug for ra in role.app_access]
    return role, perm_strings, app_slugs


def require_permission(*perms: str):
    """FastAPI dependency: require one or more permissions. Owner bypasses."""
    from app.auth.context import get_auth_context, AuthContext

    async def _checker(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
        if auth.is_owner:
            return auth
        missing = set(perms) - auth.permissions
        if missing:
            raise HTTPException(403, f"Missing permissions: {', '.join(sorted(missing))}")
        return auth

    return Depends(_checker)


def require_app_access(app_id_param: str = "app_id"):
    """FastAPI dependency: require access to the app in query/path param.

    Missing app_id → 400. No access → 403. Owner bypasses.
    app_access contains slugs (e.g., 'voice-rx'), not UUIDs.
    """
    from app.auth.context import get_auth_context, AuthContext

    async def _checker(
        request: Request, auth: AuthContext = Depends(get_auth_context)
    ) -> AuthContext:
        if auth.is_owner:
            return auth
        app_slug = (
            request.query_params.get(app_id_param)
            or request.path_params.get(app_id_param)
        )
        if not app_slug:
            raise HTTPException(400, f"Missing required parameter: {app_id_param}")
        if app_slug not in auth.app_access:
            raise HTTPException(403, f"No access to app: {app_slug}")
        return auth

    return Depends(_checker)
```

- [ ] **Step 2: Rewrite AuthContext**

Replace `backend/app/auth/context.py` entirely:

```python
# backend/app/auth/context.py
"""AuthContext dataclass and FastAPI dependencies for route-level auth."""
import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.utils import decode_access_token
from app.auth.permissions import load_role_permissions
from app.database import get_db


bearer_scheme = HTTPBearer()


@dataclass(frozen=True)
class AuthContext:
    """Injected into every authenticated route."""
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    role_id: uuid.UUID
    is_owner: bool
    permissions: frozenset[str]
    app_access: frozenset[str]


async def get_auth_context(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> AuthContext:
    """Extract and validate auth context from Bearer token, load permissions."""
    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    role_id = uuid.UUID(payload["rid"])
    role, permissions, app_slugs = await load_role_permissions(db, role_id)

    return AuthContext(
        user_id=uuid.UUID(payload["sub"]),
        tenant_id=uuid.UUID(payload["tid"]),
        email=payload["email"],
        role_id=role_id,
        is_owner=(role.is_system and role.name == "Owner"),
        permissions=frozenset(permissions),
        app_access=frozenset(app_slugs),
    )


async def require_owner(
    auth: AuthContext = Depends(get_auth_context),
) -> AuthContext:
    """Require Owner role."""
    if not auth.is_owner:
        raise HTTPException(status_code=403, detail="Owner access required")
    return auth
```

- [ ] **Step 3: Update JWT utils — role → rid**

In `backend/app/auth/utils.py`, change `create_access_token` signature:
- Parameter: `role: str` → `role_id: uuid.UUID`
- Payload: `"role": role` → `"rid": str(role_id)`

```python
def create_access_token(
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    email: str,
    role_id: uuid.UUID,
) -> str:
    """Create a short-lived JWT access token."""
    payload = {
        "sub": str(user_id),
        "tid": str(tenant_id),
        "email": email,
        "rid": str(role_id),
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
        "type": "access",
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/auth/permissions.py backend/app/auth/context.py backend/app/auth/utils.py
git commit -m "feat(rbac): Permission enum, AuthContext with permissions/app_access, JWT rid"
```

---

## Task 4: Seed Apps + Owner Role

**Files:**
- Modify: `backend/app/services/seed_defaults.py`
- Modify: `backend/app/constants.py` (if needed for well-known role UUIDs)

- [ ] **Step 1: Add app and role seeding to seed_defaults.py**

At the top of the file, add imports for new models and define seed data:

```python
from app.models.app import App
from app.models.role import Role
```

Add a new function `seed_apps()`:

```python
APP_SEEDS = [
    {"slug": "voice-rx", "display_name": "Voice Rx", "description": "Audio file evaluation tool", "icon_url": "/voice-rx-icon.jpeg"},
    {"slug": "kaira-bot", "display_name": "Kaira Bot", "description": "Health chat bot assistant", "icon_url": "/kaira-icon.svg"},
    {"slug": "inside-sales", "display_name": "Inside Sales", "description": "Inside sales call quality evaluation", "icon_url": "/inside-sales-icon.svg"},
]


async def seed_apps(session: AsyncSession) -> dict[str, uuid.UUID]:
    """Seed apps table. Returns {slug: id} mapping."""
    app_ids = {}
    for app_data in APP_SEEDS:
        existing = await session.execute(
            select(App).where(App.slug == app_data["slug"])
        )
        app = existing.scalar_one_or_none()
        if not app:
            app = App(**app_data)
            session.add(app)
            await session.flush()
            logger.info(f"Seeded app: {app_data['slug']}")
        app_ids[app.slug] = app.id
    return app_ids


async def seed_owner_role(session: AsyncSession, tenant_id: uuid.UUID) -> uuid.UUID:
    """Ensure Owner role exists for a tenant. Returns role_id."""
    existing = await session.execute(
        select(Role).where(
            Role.tenant_id == tenant_id,
            Role.is_system == True,
            Role.name == "Owner",
        )
    )
    role = existing.scalar_one_or_none()
    if not role:
        role = Role(tenant_id=tenant_id, name="Owner", description="Full access", is_system=True)
        session.add(role)
        await session.flush()
        logger.info(f"Seeded Owner role for tenant {tenant_id}")
    return role.id
```

Then update the main `seed_defaults()` function to call these first and assign the Owner role to the system user.

- [ ] **Step 2: Update the existing seeding flow**

In the main `seed_defaults()` function, add calls to `seed_apps()` and `seed_owner_role()` at the top, before seeding prompts/schemas. After seeding the owner role, update the system user's `role_id` if it's not set:

```python
# Inside seed_defaults():
app_ids = await seed_apps(session)
owner_role_id = await seed_owner_role(session, SYSTEM_TENANT_ID)

# Ensure system user has Owner role
system_user = await session.execute(
    select(User).where(User.id == SYSTEM_USER_ID)
)
user = system_user.scalar_one_or_none()
if user and user.role_id != owner_role_id:
    user.role_id = owner_role_id
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/seed_defaults.py
git commit -m "feat(rbac): seed apps table and Owner role per tenant"
```

---

## Task 5: Update Auth Routes (login, signup, /me)

**Files:**
- Modify: `backend/app/routes/auth.py`

- [ ] **Step 1: Read the full auth.py file**

Run: Read `backend/app/routes/auth.py` to understand all endpoints and the `_user_response` helper.

- [ ] **Step 2: Update _user_response helper**

The helper builds the user JSON for `/me` and login. Update it to include RBAC fields:

```python
async def _user_response(user: User, tenant: Tenant, db: AsyncSession) -> dict:
    """Build user response dict with RBAC fields."""
    from app.auth.permissions import load_role_permissions
    role, permissions, app_slugs = await load_role_permissions(db, user.role_id)
    return {
        "id": str(user.id),
        "email": user.email,
        "displayName": user.display_name,
        "tenantId": str(user.tenant_id),
        "tenantName": tenant.name,
        "roleId": str(user.role_id),
        "roleName": role.name,
        "isOwner": role.is_system and role.name == "Owner",
        "permissions": permissions,
        "appAccess": app_slugs,
    }
```

- [ ] **Step 3: Update login endpoint**

Change `create_access_token(user.id, user.tenant_id, user.email, user.role.value)` to:
```python
create_access_token(user.id, user.tenant_id, user.email, user.role_id)
```

Update the response to use `await _user_response(user, tenant, db)`.

- [ ] **Step 4: Update /me endpoint**

Change response to use `await _user_response(user, tenant, db)`.

- [ ] **Step 5: Update signup endpoint**

The signup endpoint creates a user from an invite link. Change:
- `role=invite_link.default_role` → `role_id=invite_link.role_id`
- Token creation: `create_access_token(..., user.role.value)` → `create_access_token(..., user.role_id)`

- [ ] **Step 6: Update refresh endpoint**

The refresh endpoint queries the user and creates a new access token. Update:
```python
create_access_token(user.id, user.tenant_id, user.email, user.role_id)
```

- [ ] **Step 7: Remove all UserRole imports from auth routes**

Search for `from app.models.user import UserRole` and remove it. Remove any `UserRole` references.

- [ ] **Step 8: Commit**

```bash
git add backend/app/routes/auth.py
git commit -m "feat(rbac): update auth routes for role_id, permissions in /me response"
```

---

## Task 6: Pydantic Schemas for Roles + Audit Log

**Files:**
- Create: `backend/app/schemas/role.py`
- Create: `backend/app/schemas/audit.py`

- [ ] **Step 1: Create role schemas**

```python
# backend/app/schemas/role.py
"""Pydantic schemas for role CRUD API."""
from pydantic import BaseModel, Field


class RoleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    app_access: list[str] = Field(default_factory=list)  # App slugs
    permissions: list[str] = Field(default_factory=list)  # Permission strings


class RoleUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    app_access: list[str] | None = None
    permissions: list[str] | None = None


class RoleResponse(BaseModel):
    id: str
    name: str
    description: str | None
    is_system: bool
    app_access: list[str]    # App slugs
    permissions: list[str]   # Permission strings
    user_count: int          # Number of users assigned this role
    created_at: str
    updated_at: str


class AppResponse(BaseModel):
    id: str
    slug: str
    display_name: str
    description: str
    icon_url: str
    is_active: bool
```

- [ ] **Step 2: Create audit log schemas**

```python
# backend/app/schemas/audit.py
"""Pydantic schemas for audit log API."""
from pydantic import BaseModel


class AuditLogEntry(BaseModel):
    id: str
    actor_id: str
    actor_email: str | None = None  # Joined from users table
    action: str
    entity_type: str
    entity_id: str
    before_state: dict | None
    after_state: dict | None
    ip_address: str | None
    created_at: str
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/role.py backend/app/schemas/audit.py
git commit -m "feat(rbac): add Pydantic schemas for roles and audit log API"
```

---

## Task 7: Audit Log Service

**Files:**
- Create: `backend/app/services/audit.py`

- [ ] **Step 1: Create audit log write helper**

```python
# backend/app/services/audit.py
"""Audit log service — writes immutable records of RBAC changes."""
import uuid
from typing import Optional

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


async def write_audit_log(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID,
    before_state: Optional[dict] = None,
    after_state: Optional[dict] = None,
    request: Optional[Request] = None,
) -> None:
    """Write an audit log entry. Call within the same transaction as the mutation."""
    ip_address = None
    user_agent = None
    if request:
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent", "")[:500]

    entry = AuditLog(
        tenant_id=tenant_id,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before_state=before_state,
        after_state=after_state,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(entry)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/audit.py
git commit -m "feat(rbac): add audit log write service"
```

---

## Task 8: Apps Route + Roles CRUD Routes + Audit Log Route

**Files:**
- Create: `backend/app/routes/apps.py`
- Create: `backend/app/routes/roles.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create apps route**

```python
# backend/app/routes/apps.py
"""Apps route — list registered applications."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import get_auth_context, AuthContext
from app.database import get_db
from app.models.app import App

router = APIRouter(prefix="/api/apps", tags=["apps"])


@router.get("")
async def list_apps(
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """List all registered apps."""
    result = await db.execute(select(App).where(App.is_active == True).order_by(App.slug))
    apps = result.scalars().all()
    return [
        {
            "id": str(a.id),
            "slug": a.slug,
            "displayName": a.display_name,
            "description": a.description,
            "iconUrl": a.icon_url,
            "isActive": a.is_active,
        }
        for a in apps
    ]
```

- [ ] **Step 2: Create roles CRUD route**

This is a larger file. Key endpoints:
- `GET /api/admin/roles` — list roles for tenant with user counts
- `POST /api/admin/roles` — create custom role (Owner only)
- `GET /api/admin/roles/{role_id}` — get role detail
- `PUT /api/admin/roles/{role_id}` — update role (Owner only)
- `DELETE /api/admin/roles/{role_id}` — delete role (Owner only, blocked if users/invites reference it)
- `GET /api/admin/audit-log` — paginated audit log (Owner only)

```python
# backend/app/routes/roles.py
"""Role management routes — Owner only for mutations."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.context import AuthContext, get_auth_context, require_owner
from app.auth.permissions import VALID_PERMISSIONS
from app.database import get_db
from app.models.app import App
from app.models.role import Role, RoleAppAccess, RolePermission
from app.models.user import User
from app.models.invite_link import InviteLink
from app.models.audit_log import AuditLog
from app.schemas.role import RoleCreate, RoleUpdate
from app.services.audit import write_audit_log

router = APIRouter(prefix="/api/admin", tags=["admin-rbac"])


def _role_response(role: Role, user_count: int = 0) -> dict:
    return {
        "id": str(role.id),
        "name": role.name,
        "description": role.description,
        "isSystem": role.is_system,
        "appAccess": [ra.app.slug for ra in role.app_access],
        "permissions": [rp.permission for rp in role.permissions],
        "userCount": user_count,
        "createdAt": role.created_at.isoformat() if role.created_at else None,
        "updatedAt": role.updated_at.isoformat() if role.updated_at else None,
    }


@router.get("/roles")
async def list_roles(
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """List all roles for the tenant with user counts."""
    # Subquery for user counts
    user_count_sq = (
        select(User.role_id, func.count(User.id).label("cnt"))
        .where(User.tenant_id == auth.tenant_id)
        .group_by(User.role_id)
        .subquery()
    )
    stmt = (
        select(Role, func.coalesce(user_count_sq.c.cnt, 0))
        .outerjoin(user_count_sq, Role.id == user_count_sq.c.role_id)
        .options(
            selectinload(Role.app_access).selectinload(RoleAppAccess.app),
            selectinload(Role.permissions),
        )
        .where(Role.tenant_id == auth.tenant_id)
        .order_by(Role.is_system.desc(), Role.name)
    )
    result = await db.execute(stmt)
    rows = result.all()
    return [_role_response(role, count) for role, count in rows]


@router.post("/roles", status_code=201)
async def create_role(
    body: RoleCreate,
    request: Request,
    auth: AuthContext = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    """Create a custom role. Owner only."""
    # Validate permission strings
    invalid = set(body.permissions) - VALID_PERMISSIONS
    if invalid:
        raise HTTPException(400, f"Invalid permissions: {', '.join(sorted(invalid))}")

    # Validate app slugs
    app_map = await _get_app_map(db)
    invalid_apps = set(body.app_access) - set(app_map.keys())
    if invalid_apps:
        raise HTTPException(400, f"Invalid app slugs: {', '.join(sorted(invalid_apps))}")

    # Check name uniqueness
    existing = await db.execute(
        select(Role).where(Role.tenant_id == auth.tenant_id, Role.name == body.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"Role '{body.name}' already exists")

    role = Role(tenant_id=auth.tenant_id, name=body.name, description=body.description)
    db.add(role)
    await db.flush()

    # Add app access
    for slug in body.app_access:
        db.add(RoleAppAccess(role_id=role.id, app_id=app_map[slug]))
    # Add permissions
    for perm in body.permissions:
        db.add(RolePermission(role_id=role.id, permission=perm))

    await write_audit_log(
        db, tenant_id=auth.tenant_id, actor_id=auth.user_id,
        action="role.created", entity_type="role", entity_id=role.id,
        after_state={"name": body.name, "permissions": body.permissions, "app_access": body.app_access},
        request=request,
    )
    await db.commit()

    # Reload with relationships
    return await _get_role_detail(db, role.id)


@router.get("/roles/{role_id}")
async def get_role(
    role_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """Get role detail with permissions and app access."""
    return await _get_role_detail(db, role_id, auth.tenant_id)


@router.put("/roles/{role_id}")
async def update_role(
    role_id: uuid.UUID,
    body: RoleUpdate,
    request: Request,
    auth: AuthContext = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    """Update a custom role. Owner only. Cannot update system roles."""
    role = await _get_role_or_404(db, role_id, auth.tenant_id)
    if role.is_system:
        raise HTTPException(403, "Cannot modify system roles")

    before = {"name": role.name, "permissions": [rp.permission for rp in role.permissions],
              "app_access": [ra.app.slug for ra in role.app_access]}

    if body.name is not None:
        # Check uniqueness
        existing = await db.execute(
            select(Role).where(Role.tenant_id == auth.tenant_id, Role.name == body.name, Role.id != role_id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(409, f"Role '{body.name}' already exists")
        role.name = body.name

    if body.description is not None:
        role.description = body.description

    app_map = await _get_app_map(db)

    if body.app_access is not None:
        invalid_apps = set(body.app_access) - set(app_map.keys())
        if invalid_apps:
            raise HTTPException(400, f"Invalid app slugs: {', '.join(sorted(invalid_apps))}")
        # Replace app access
        await db.execute(delete(RoleAppAccess).where(RoleAppAccess.role_id == role_id))
        for slug in body.app_access:
            db.add(RoleAppAccess(role_id=role_id, app_id=app_map[slug]))

    if body.permissions is not None:
        invalid = set(body.permissions) - VALID_PERMISSIONS
        if invalid:
            raise HTTPException(400, f"Invalid permissions: {', '.join(sorted(invalid))}")
        # Replace permissions
        await db.execute(delete(RolePermission).where(RolePermission.role_id == role_id))
        for perm in body.permissions:
            db.add(RolePermission(role_id=role_id, permission=perm))

    after = {"name": role.name, "permissions": body.permissions or before["permissions"],
             "app_access": body.app_access or before["app_access"]}

    await write_audit_log(
        db, tenant_id=auth.tenant_id, actor_id=auth.user_id,
        action="role.updated", entity_type="role", entity_id=role_id,
        before_state=before, after_state=after, request=request,
    )
    await db.commit()
    return await _get_role_detail(db, role_id)


@router.delete("/roles/{role_id}", status_code=204)
async def delete_role(
    role_id: uuid.UUID,
    request: Request,
    auth: AuthContext = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    """Delete a custom role. Blocked if users or invite links reference it."""
    role = await _get_role_or_404(db, role_id, auth.tenant_id)
    if role.is_system:
        raise HTTPException(403, "Cannot delete system roles")

    # Check for assigned users
    user_count = await db.execute(
        select(func.count(User.id)).where(User.role_id == role_id)
    )
    if user_count.scalar_one() > 0:
        raise HTTPException(409, "Cannot delete role — users are still assigned to it")

    # Check for invite links
    link_count = await db.execute(
        select(func.count(InviteLink.id)).where(InviteLink.role_id == role_id, InviteLink.is_active == True)
    )
    if link_count.scalar_one() > 0:
        raise HTTPException(409, "Cannot delete role — active invite links reference it")

    before = {"name": role.name, "permissions": [rp.permission for rp in role.permissions],
              "app_access": [ra.app.slug for ra in role.app_access]}

    await write_audit_log(
        db, tenant_id=auth.tenant_id, actor_id=auth.user_id,
        action="role.deleted", entity_type="role", entity_id=role_id,
        before_state=before, request=request,
    )
    await db.delete(role)
    await db.commit()


# ── Audit log endpoint ──────────────────────────────────────────────────

@router.get("/audit-log")
async def list_audit_log(
    auth: AuthContext = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    action_filter: str | None = Query(None, alias="action"),
):
    """Paginated audit log for the tenant. Owner only."""
    stmt = (
        select(AuditLog, User.email)
        .outerjoin(User, AuditLog.actor_id == User.id)
        .where(AuditLog.tenant_id == auth.tenant_id)
    )
    if action_filter:
        stmt = stmt.where(AuditLog.action.ilike(f"%{action_filter}%"))
    stmt = stmt.order_by(AuditLog.created_at.desc())

    # Count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    # Paginate
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    rows = result.all()

    return {
        "items": [
            {
                "id": str(entry.id),
                "actorId": str(entry.actor_id),
                "actorEmail": email,
                "action": entry.action,
                "entityType": entry.entity_type,
                "entityId": str(entry.entity_id),
                "beforeState": entry.before_state,
                "afterState": entry.after_state,
                "ipAddress": entry.ip_address,
                "createdAt": entry.created_at.isoformat() if entry.created_at else None,
            }
            for entry, email in rows
        ],
        "total": total,
        "page": page,
        "pageSize": page_size,
    }


# ── Helpers ──────────────────────────────────────────────────────────────

async def _get_app_map(db: AsyncSession) -> dict[str, uuid.UUID]:
    """Get {slug: id} mapping for all active apps."""
    result = await db.execute(select(App).where(App.is_active == True))
    return {a.slug: a.id for a in result.scalars().all()}


async def _get_role_or_404(db: AsyncSession, role_id: uuid.UUID, tenant_id: uuid.UUID | None = None) -> Role:
    stmt = (
        select(Role)
        .options(
            selectinload(Role.app_access).selectinload(RoleAppAccess.app),
            selectinload(Role.permissions),
        )
        .where(Role.id == role_id)
    )
    if tenant_id:
        stmt = stmt.where(Role.tenant_id == tenant_id)
    result = await db.execute(stmt)
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(404, "Role not found")
    return role


async def _get_role_detail(db: AsyncSession, role_id: uuid.UUID, tenant_id: uuid.UUID | None = None) -> dict:
    role = await _get_role_or_404(db, role_id, tenant_id)
    user_count = await db.execute(
        select(func.count(User.id)).where(User.role_id == role_id)
    )
    return _role_response(role, user_count.scalar_one())
```

- [ ] **Step 3: Register new routers in main.py**

Add to `backend/app/main.py`:
```python
from app.routes.apps import router as apps_router
from app.routes.roles import router as roles_router

app.include_router(apps_router)
app.include_router(roles_router)
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/routes/apps.py backend/app/routes/roles.py backend/app/schemas/role.py backend/app/schemas/audit.py backend/app/main.py
git commit -m "feat(rbac): add apps, roles CRUD, and audit log routes"
```

---

## Task 9: Migrate Admin Routes to Permission-Based Auth

**Files:**
- Modify: `backend/app/routes/admin.py`

- [ ] **Step 1: Read the full admin.py**

Run: Read `backend/app/routes/admin.py` to understand all endpoints.

- [ ] **Step 2: Replace auth imports and dependencies**

Remove:
```python
from app.auth.context import require_admin, require_owner
from app.models.user import UserRole
```

Add:
```python
from app.auth.context import get_auth_context, require_owner, AuthContext
from app.auth.permissions import require_permission
from app.services.audit import write_audit_log
```

- [ ] **Step 3: Replace each route's auth dependency**

Follow the mapping from spec section 5.4 "Admin — User Management":
- `GET /api/admin/stats` → `auth: AuthContext = require_permission('analytics:view')`
- `POST /api/admin/erase` → `auth: AuthContext = Depends(require_owner)` (unchanged)
- `GET /api/admin/users` → `auth: AuthContext = require_permission('user:edit')`
- `POST /api/admin/users` → `auth: AuthContext = require_permission('user:create')`
- `PATCH /api/admin/users/{id}` → dual check (see Step 4)
- `PUT /api/admin/users/{id}/password` → `auth: AuthContext = require_permission('user:reset_password')`
- `DELETE /api/admin/users/{id}` → `auth: AuthContext = require_permission('user:deactivate')`
- `POST /api/admin/invite-links` → `auth: AuthContext = require_permission('user:invite')`
- `GET /api/admin/invite-links` → `auth: AuthContext = require_permission('user:invite')`
- `DELETE /api/admin/invite-links/{id}` → `auth: AuthContext = require_permission('user:invite')`
- Tenant routes → `Depends(require_owner)` (unchanged)

- [ ] **Step 4: Implement dual permission check for PATCH users**

```python
@router.patch("/users/{user_id}")
async def update_user(
    user_id: uuid.UUID,
    body: UpdateUserRequest,
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    # Check permissions based on what's being changed
    if not auth.is_owner:
        if body.role_id is not None and "role:assign" not in auth.permissions:
            raise HTTPException(403, "Missing permission: role:assign")
        needs_edit = body.display_name is not None or body.is_active is not None
        if needs_edit and "user:edit" not in auth.permissions:
            raise HTTPException(403, "Missing permission: user:edit")
    # ... rest of the handler
```

- [ ] **Step 5: Update user creation to use role_id**

In `POST /api/admin/users`, change `role=UserRole(body.role)` to `role_id=body.role_id`. Update `CreateUserRequest` schema to accept `role_id: str` instead of `role: str`.

- [ ] **Step 6: Update invite link creation to use role_id**

In `POST /api/admin/invite-links`, change `default_role=UserRole(body.default_role)` to `role_id=uuid.UUID(body.role_id)`. Update `CreateInviteLinkRequest` schema.

- [ ] **Step 7: Add audit log writes to user management mutations**

Add `write_audit_log()` calls to: create user, update user, deactivate user, reset password, create/revoke invite link.

- [ ] **Step 8: Remove all UserRole references**

Search and replace any remaining `UserRole` references with the new role_id-based checks.

- [ ] **Step 9: Commit**

```bash
git add backend/app/routes/admin.py
git commit -m "feat(rbac): migrate admin routes to permission-based auth"
```

---

## Task 10: Migrate All Other Backend Routes

**Files:**
- Modify: All route files listed in the File Map under "Modified Backend Files"

This is mechanical. For each route file, add the appropriate `require_permission()` and/or `require_app_access()` dependencies per the spec's route mapping table (section 5.4).

- [ ] **Step 1: Migrate listings.py**

Add import:
```python
from app.auth.permissions import require_permission, require_app_access
```

Change mutating routes:
- `POST /api/listings` → `auth: AuthContext = require_permission('listing:create')`
- `PUT /api/listings/{id}` → `auth: AuthContext = require_permission('listing:create')`
- `DELETE /api/listings/{id}` → `auth: AuthContext = require_permission('listing:delete')`

Add `require_app_access()` to all routes — but since `app_id` is already a required query param that's used for filtering, `require_app_access()` can be added as a second dependency:
```python
@router.get("")
async def list_listings(
    app_id: str = Query(...),
    auth: AuthContext = Depends(get_auth_context),
    _app: AuthContext = require_app_access(),
    db: AsyncSession = Depends(get_db),
):
```

**Note:** Since `require_app_access()` internally depends on `get_auth_context`, FastAPI will reuse the same `AuthContext` instance (dependency caching). This means we don't double-query. The `_app` variable is unused — it's just for the side-effect of the access check.

- [ ] **Step 2: Migrate eval_runs.py**

Same pattern. Mutating routes get `require_permission()`. All routes get `require_app_access()`. Analytics/stats routes get `require_permission('analytics:view')`.

- [ ] **Step 3: Migrate jobs.py**

- `POST /api/jobs` → `require_permission('eval:run')`
- `POST /api/jobs/{id}/cancel` → `require_permission('eval:delete')`
- All routes: `require_app_access()`

- [ ] **Step 4: Migrate prompts.py, schemas.py, evaluators.py**

Same CRUD pattern:
- POST → `require_permission('resource:create')`
- PUT → `require_permission('resource:edit')`
- DELETE → `require_permission('resource:delete')`
- All: `require_app_access()`

- [ ] **Step 5: Migrate chat.py, files.py, tags.py, history.py**

Same CRUD pattern as Step 4.

- [ ] **Step 6: Migrate settings.py**

- `PUT /api/settings` → `require_permission('settings:edit')`
- `DELETE /api/settings` → `require_permission('settings:edit')`
- No `require_app_access()` (settings are global)

- [ ] **Step 7: Migrate reports.py**

- `GET /api/reports/{id}` → `require_permission('analytics:view')` + `require_app_access()`
- `GET /api/reports/{id}/export-pdf` → `require_permission('eval:export')` + `require_app_access()`
- `GET /api/reports/cross-run-analytics` → `require_permission('analytics:view')` + `require_app_access()`
- `POST /api/reports/cross-run-analytics/refresh` → `require_permission('report:generate')` + `require_app_access()`
- `POST /api/reports/cross-run-ai-summary` → `require_permission('report:generate')` + `require_app_access()`

- [ ] **Step 8: Migrate adversarial_config.py**

- GET/PUT/POST (config) → `require_permission('settings:edit')` + `require_app_access()`
- GET (export) → `require_permission('eval:export')` + `require_app_access()`
- POST (import) → `require_permission('settings:edit')` + `require_app_access()`

- [ ] **Step 9: Migrate inside_sales.py**

All routes: add `require_app_access()` only (read-only routes). The `app_id` for inside-sales is implicit (`"inside-sales"` slug). If routes don't have `app_id` as a query param, hardcode the check or add the param.

- [ ] **Step 10: Verify — start the backend**

Run: `PYTHONPATH=backend python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8721`
Expected: Server starts without import errors. Check logs for seed output.

- [ ] **Step 11: Commit**

```bash
git add backend/app/routes/
git commit -m "feat(rbac): migrate all routes to permission-based auth"
```

---

## Task 11: Backend Tests for Permission Logic

**Files:**
- Create: `backend/tests/test_permissions.py`

- [ ] **Step 1: Write permission tests**

```python
# backend/tests/test_permissions.py
"""Unit tests for RBAC permission logic."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.auth.permissions import Permission, VALID_PERMISSIONS


def test_permission_enum_has_all_expected_values():
    expected = {
        "listing:create", "listing:delete",
        "eval:run", "eval:delete", "eval:export",
        "resource:create", "resource:edit", "resource:delete",
        "report:generate", "analytics:view",
        "settings:edit",
        "user:create", "user:invite", "user:edit",
        "user:deactivate", "user:reset_password", "role:assign",
        "tenant:settings",
    }
    assert VALID_PERMISSIONS == expected


def test_permission_enum_values_match_resource_action_format():
    for p in Permission:
        assert ":" in p.value, f"Permission {p.name} missing colon separator"
        resource, action = p.value.split(":", 1)
        assert len(resource) > 0
        assert len(action) > 0


def test_valid_permissions_is_frozenset():
    assert isinstance(VALID_PERMISSIONS, frozenset)
```

- [ ] **Step 2: Run tests**

Run: `cd backend && python -m pytest tests/test_permissions.py -v`
Expected: 3 tests PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_permissions.py
git commit -m "test(rbac): add permission enum unit tests"
```

---

## Task 12: Frontend — Auth Types, Permission Utils, PermissionGate

**Files:**
- Modify: `src/types/auth.types.ts`
- Create: `src/utils/permissions.ts`
- Create: `src/components/auth/PermissionGate.tsx`

- [ ] **Step 1: Update auth types**

Replace `src/types/auth.types.ts`:

```typescript
export interface User {
  id: string;
  email: string;
  displayName: string;
  tenantId: string;
  tenantName: string;
  roleId: string;
  roleName: string;
  isOwner: boolean;
  permissions: string[];
  appAccess: string[];
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

export interface SignupCredentials {
  token: string;
  email: string;
  password: string;
  displayName: string;
}

export interface ValidateInviteResult {
  valid: boolean;
  tenantName?: string;
  roleId?: string;
  roleName?: string;
  expiresAt?: string;
  allowedDomains?: string[];
}
```

- [ ] **Step 2: Create permission utilities**

```typescript
// src/utils/permissions.ts
import { useAuthStore } from '@/stores/authStore';

/** Check permission from outside React (callbacks, services) */
export function hasPermission(permission: string): boolean {
  const user = useAuthStore.getState().user;
  if (!user) return false;
  if (user.isOwner) return true;
  return user.permissions.includes(permission);
}

/** Check app access from outside React */
export function hasAppAccess(appSlug: string): boolean {
  const user = useAuthStore.getState().user;
  if (!user) return false;
  if (user.isOwner) return true;
  return user.appAccess.includes(appSlug);
}

/** React hook for permission check (reactive) */
export function usePermission(permission: string): boolean {
  const user = useAuthStore((s) => s.user);
  if (!user) return false;
  if (user.isOwner) return true;
  return user.permissions.includes(permission);
}

/** React hook for app access check (reactive) */
export function useAppAccess(appSlug: string): boolean {
  const user = useAuthStore((s) => s.user);
  if (!user) return false;
  if (user.isOwner) return true;
  return user.appAccess.includes(appSlug);
}

/** All grantable permission IDs — keep in sync with backend Permission enum */
export const PERMISSIONS = {
  LISTING_CREATE: 'listing:create',
  LISTING_DELETE: 'listing:delete',
  EVAL_RUN: 'eval:run',
  EVAL_DELETE: 'eval:delete',
  EVAL_EXPORT: 'eval:export',
  RESOURCE_CREATE: 'resource:create',
  RESOURCE_EDIT: 'resource:edit',
  RESOURCE_DELETE: 'resource:delete',
  REPORT_GENERATE: 'report:generate',
  ANALYTICS_VIEW: 'analytics:view',
  SETTINGS_EDIT: 'settings:edit',
  USER_CREATE: 'user:create',
  USER_INVITE: 'user:invite',
  USER_EDIT: 'user:edit',
  USER_DEACTIVATE: 'user:deactivate',
  USER_RESET_PASSWORD: 'user:reset_password',
  ROLE_ASSIGN: 'role:assign',
  TENANT_SETTINGS: 'tenant:settings',
} as const;
```

- [ ] **Step 3: Create PermissionGate and AppAccessGuard components**

```tsx
// src/components/auth/PermissionGate.tsx
import type { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuthStore } from '@/stores/authStore';

interface PermissionGateProps {
  action: string;
  app?: string;
  fallback?: ReactNode;
  children: ReactNode;
}

/** Renders children only if the user has the required permission. */
export function PermissionGate({ action, app, fallback = null, children }: PermissionGateProps) {
  const user = useAuthStore((s) => s.user);
  if (!user) return null;
  if (user.isOwner) return <>{children}</>;
  if (app && !user.appAccess.includes(app)) return <>{fallback}</>;
  if (!user.permissions.includes(action)) return <>{fallback}</>;
  return <>{children}</>;
}

interface AppAccessGuardProps {
  app: string;
  children: ReactNode;
}

/** Route-level guard — redirects to first accessible app if no access. */
export function AppAccessGuard({ app, children }: AppAccessGuardProps) {
  const user = useAuthStore((s) => s.user);
  if (!user) return null;
  if (user.isOwner || user.appAccess.includes(app)) return <>{children}</>;

  // Redirect to first accessible app
  const firstApp = user.appAccess[0];
  const fallbackRoute = firstApp ? `/${firstApp}` : '/';
  return <Navigate to={fallbackRoute} replace />;
}
```

- [ ] **Step 4: Commit**

```bash
git add src/types/auth.types.ts src/utils/permissions.ts src/components/auth/PermissionGate.tsx
git commit -m "feat(rbac): add frontend auth types, permission utils, PermissionGate"
```

---

## Task 13: Frontend — Update Auth Store, Auth API, AdminGuard

**Files:**
- Modify: `src/stores/authStore.ts`
- Modify: `src/services/api/authApi.ts` (if it transforms the response)
- Modify: `src/features/auth/AdminGuard.tsx`

- [ ] **Step 1: Update authStore**

The store doesn't need structural changes — the `User` type it references from `auth.types.ts` is already updated. But verify that `loadUser` and `login` don't transform/destructure the `user` object in ways that break the new fields.

- [ ] **Step 2: Update AdminGuard**

Replace the role check with a permission-based check. Anyone with any `user:*` permission can access admin:

```tsx
// src/features/auth/AdminGuard.tsx
import type { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuthStore } from '@/stores/authStore';

const ADMIN_PERMISSIONS = ['user:create', 'user:edit', 'user:invite', 'user:deactivate', 'user:reset_password'];

export function AdminGuard({ children }: { children: ReactNode }) {
  const user = useAuthStore((s) => s.user);
  if (!user) return <Navigate to="/" replace />;
  if (user.isOwner) return <>{children}</>;
  const hasAdminAccess = ADMIN_PERMISSIONS.some((p) => user.permissions.includes(p));
  if (!hasAdminAccess) return <Navigate to="/" replace />;
  return <>{children}</>;
}
```

- [ ] **Step 3: Update AppSwitcher**

In `src/components/layout/AppSwitcher.tsx`, filter the `apps` array by user access:

Before the return, add:
```tsx
const user = useAuthStore((s) => s.user);
const accessibleApps = user
  ? apps.filter((app) => user.isOwner || user.appAccess.includes(app.id))
  : apps;
```

Replace `apps.map(...)` with `accessibleApps.map(...)` in the dropdown render.

- [ ] **Step 4: Add AppAccessGuard to Router.tsx**

In `src/app/Router.tsx`, wrap each app's routes with `<AppAccessGuard>`:

```tsx
import { AppAccessGuard } from '@/components/auth/PermissionGate';

// Wrap Voice Rx routes
<AppAccessGuard app="voice-rx">
  <Route ... />
</AppAccessGuard>

// Wrap Kaira Bot routes
<AppAccessGuard app="kaira-bot">
  <Route ... />
</AppAccessGuard>

// Wrap Inside Sales routes
<AppAccessGuard app="inside-sales">
  <Route ... />
</AppAccessGuard>
```

**Note:** Due to React Router v6 nesting constraints, the simplest approach is to create wrapper layout components (e.g., `VoiceRxGuard`, `KairaGuard`, `InsideSalesGuard`) that render `<AppAccessGuard app="..."><Outlet /></AppAccessGuard>` and use them as layout routes. Read `Router.tsx` carefully to find the best integration point.

- [ ] **Step 5: Commit**

```bash
git add src/stores/authStore.ts src/features/auth/AdminGuard.tsx src/components/layout/AppSwitcher.tsx src/app/Router.tsx
git commit -m "feat(rbac): update auth store, AdminGuard, AppSwitcher, route guards"
```

---

## Task 14: Frontend — Button Tagging (Admin + Listings + Eval Runs)

**Files:**
- Modify: `src/features/admin/AdminUsersPage.tsx`
- Modify: `src/features/admin/InviteLinksSection.tsx`
- Modify: Multiple listing and eval run components

- [ ] **Step 1: Tag admin buttons**

In `AdminUsersPage.tsx`, wrap each action button:
- Add User button → `<PermissionGate action="user:create">`
- Edit user (pencil) → `<PermissionGate action="user:edit">`
- Reset password (key) → `<PermissionGate action="user:reset_password">`
- Deactivate user (X) → `<PermissionGate action="user:deactivate">`

In `InviteLinksSection.tsx`:
- Generate Link → `<PermissionGate action="user:invite">`
- Revoke Link → `<PermissionGate action="user:invite">`

- [ ] **Step 2: Tag listing action buttons**

In `ListingActionMenu.tsx` (or wherever the listing action menu lives):
- Fetch from API → `<PermissionGate action="listing:create">`
- Run Evaluation → `<PermissionGate action="eval:run">`
- Export → `<PermissionGate action="eval:export">`

- [ ] **Step 3: Tag eval run action buttons**

Across `RunList.tsx`, `RunDetail.tsx`, `VoiceRxRunDetail.tsx`, `InsideSalesRunList.tsx`, `InsideSalesRunDetail.tsx`:
- Delete run → `<PermissionGate action="eval:delete">`
- Cancel job → `<PermissionGate action="eval:delete">`

In `ReportTab.tsx`:
- Generate Report → `<PermissionGate action="report:generate">`
- Refresh Report → `<PermissionGate action="report:generate">`

- [ ] **Step 4: Commit**

```bash
git add src/features/admin/ src/app/pages/ src/features/evalRuns/ src/features/voiceRx/ src/features/insideSales/
git commit -m "feat(rbac): tag admin, listing, and eval run buttons with PermissionGate"
```

---

## Task 15: Frontend — Button Tagging (Resources + Settings + Analytics)

**Files:**
- Modify: Settings/resource management components
- Modify: Evaluator components
- Modify: Inside Sales components

- [ ] **Step 1: Tag resource management buttons**

In `PromptsTab.tsx`:
- Create prompt → `<PermissionGate action="resource:create">`
- Edit (pencil) → `<PermissionGate action="resource:edit">`
- Set default → `<PermissionGate action="resource:edit">`
- Delete (trash) → `<PermissionGate action="resource:delete">`

Same pattern for `SchemasTab.tsx`.

In `EvaluatorsView.tsx`:
- Create evaluator → `<PermissionGate action="resource:create">`
- Edit → `<PermissionGate action="resource:edit">`
- Delete → `<PermissionGate action="resource:delete">`
- Run evaluator → `<PermissionGate action="eval:run">`
- Run All → `<PermissionGate action="eval:run">`

In `EvaluatorRegistryPicker.tsx`:
- Fork → `<PermissionGate action="resource:create">`

In `KairaBotEvaluatorsView.tsx`:
- Create/Edit/Delete → same permissions

- [ ] **Step 2: Tag settings buttons**

Across LLM settings, adversarial config components:
- Save/reset/import → `<PermissionGate action="settings:edit">`

- [ ] **Step 3: Tag Inside Sales specific buttons**

In `InsideSalesListing.tsx`:
- Evaluate Call → `<PermissionGate action="eval:run">`

- [ ] **Step 4: Commit**

```bash
git add src/features/settings/ src/features/evals/ src/features/kaira/ src/features/kairaBotSettings/ src/features/insideSales/
git commit -m "feat(rbac): tag resource, settings, and analytics buttons with PermissionGate"
```

---

## Task 16: Frontend — Roles API Client

**Files:**
- Create: `src/services/api/rolesApi.ts`
- Modify: `src/services/api/adminApi.ts`

- [ ] **Step 1: Create roles API client**

```typescript
// src/services/api/rolesApi.ts
import { apiRequest } from './client';

export interface RoleResponse {
  id: string;
  name: string;
  description: string | null;
  isSystem: boolean;
  appAccess: string[];
  permissions: string[];
  userCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface AppResponse {
  id: string;
  slug: string;
  displayName: string;
  description: string;
  iconUrl: string;
  isActive: boolean;
}

export interface CreateRoleRequest {
  name: string;
  description?: string;
  appAccess: string[];
  permissions: string[];
}

export interface UpdateRoleRequest {
  name?: string;
  description?: string;
  appAccess?: string[];
  permissions?: string[];
}

export interface AuditLogEntry {
  id: string;
  actorId: string;
  actorEmail: string | null;
  action: string;
  entityType: string;
  entityId: string;
  beforeState: Record<string, unknown> | null;
  afterState: Record<string, unknown> | null;
  ipAddress: string | null;
  createdAt: string;
}

export interface AuditLogResponse {
  items: AuditLogEntry[];
  total: number;
  page: number;
  pageSize: number;
}

export const rolesApi = {
  listApps: () => apiRequest<AppResponse[]>('/api/apps'),
  listRoles: () => apiRequest<RoleResponse[]>('/api/admin/roles'),
  getRole: (id: string) => apiRequest<RoleResponse>(`/api/admin/roles/${id}`),
  createRole: (data: CreateRoleRequest) =>
    apiRequest<RoleResponse>('/api/admin/roles', { method: 'POST', body: JSON.stringify(data) }),
  updateRole: (id: string, data: UpdateRoleRequest) =>
    apiRequest<RoleResponse>(`/api/admin/roles/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteRole: (id: string) =>
    apiRequest<void>(`/api/admin/roles/${id}`, { method: 'DELETE' }),
  getAuditLog: (page = 1, pageSize = 50, action?: string) => {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (action) params.set('action', action);
    return apiRequest<AuditLogResponse>(`/api/admin/audit-log?${params}`);
  },
};
```

- [ ] **Step 2: Update adminApi.ts**

Update `CreateUserRequest` and `CreateInviteLinkRequest` to use `roleId` instead of `role`/`defaultRole`:

```typescript
export interface CreateUserRequest {
  email: string;
  password: string;
  displayName: string;
  roleId: string;  // Changed from role: 'admin' | 'member'
}

export interface CreateInviteLinkRequest {
  label?: string;
  roleId: string;   // Changed from defaultRole
  maxUses?: number;
  expiresInHours?: number;
}
```

- [ ] **Step 3: Commit**

```bash
git add src/services/api/rolesApi.ts src/services/api/adminApi.ts
git commit -m "feat(rbac): add roles API client, update admin API types"
```

---

## Task 17: Frontend — Roles Tab (Admin Panel)

**Files:**
- Create: `src/features/admin/RolesTab.tsx`
- Create: `src/features/admin/RoleEditorDialog.tsx`
- Modify: `src/features/admin/AdminUsersPage.tsx`

- [ ] **Step 1: Create RolesTab component**

A table listing all roles with columns: Name, Description, Users, App Access (badges), System badge, Actions (edit/delete). Owner row is read-only. "Create Role" button at top.

- [ ] **Step 2: Create RoleEditorDialog**

A dialog/modal with:
- Name input, description textarea
- **App Access** section: toggle switches for each app (fetched from `/api/apps`)
- **Permissions** section: grouped checkboxes for each permission. Groups:
  - Listings: listing:create, listing:delete
  - Evaluations: eval:run, eval:delete, eval:export
  - Resources: resource:create, resource:edit, resource:delete
  - Reports & Analytics: report:generate, analytics:view
  - Settings: settings:edit
  - User Management: user:create, user:invite, user:edit, user:deactivate, user:reset_password, role:assign
  - Tenant: tenant:settings

When an app toggle is OFF, the entire permission section still shows (permissions are global). The app access section is independent of the permissions section.

Save calls `rolesApi.createRole()` or `rolesApi.updateRole()`.

- [ ] **Step 3: Wire RolesTab into AdminUsersPage**

Replace the "Roles" tab placeholder (lines ~261-271 in `AdminUsersPage.tsx`) with `<RolesTab />`. Import and render.

- [ ] **Step 4: Commit**

```bash
git add src/features/admin/RolesTab.tsx src/features/admin/RoleEditorDialog.tsx src/features/admin/AdminUsersPage.tsx
git commit -m "feat(rbac): add Roles tab with create/edit/delete role UI"
```

---

## Task 18: Frontend — Security Tab (Audit Log Viewer)

**Files:**
- Create: `src/features/admin/AuditLogTab.tsx`
- Modify: `src/features/admin/AdminUsersPage.tsx`

- [ ] **Step 1: Create AuditLogTab**

A paginated table showing audit log entries:
- Columns: Timestamp, Actor (email), Action, Entity Type, Details (expandable JSON)
- Filter by action string
- Pagination controls
- Fetches from `rolesApi.getAuditLog()`

- [ ] **Step 2: Wire into AdminUsersPage**

Replace the "Security" tab placeholder (lines ~274-284) with `<AuditLogTab />`. Only visible to Owner (`user.isOwner`).

- [ ] **Step 3: Commit**

```bash
git add src/features/admin/AuditLogTab.tsx src/features/admin/AdminUsersPage.tsx
git commit -m "feat(rbac): add Security tab with audit log viewer"
```

---

## Task 19: Frontend — Update Invite Link + User Creation Forms

**Files:**
- Modify: `src/features/admin/CreateUserDialog.tsx`
- Modify: `src/features/admin/EditUserDialog.tsx`
- Modify: `src/features/admin/InviteLinksSection.tsx`

- [ ] **Step 1: Update CreateUserDialog**

Replace the role dropdown (hardcoded `admin`/`member` options) with a role dropdown populated from `rolesApi.listRoles()`. Exclude the Owner system role from the dropdown. Submit sends `roleId` instead of `role`.

- [ ] **Step 2: Update EditUserDialog**

Replace role dropdown with roles from API. Gate the role dropdown behind `<PermissionGate action="role:assign">` — if the user doesn't have `role:assign`, show the current role as read-only text.

- [ ] **Step 3: Update InviteLinksSection**

Replace `defaultRole` dropdown with role dropdown from API. Submit sends `roleId`. Display invite links showing role name instead of enum string.

- [ ] **Step 4: Commit**

```bash
git add src/features/admin/CreateUserDialog.tsx src/features/admin/EditUserDialog.tsx src/features/admin/InviteLinksSection.tsx
git commit -m "feat(rbac): update user/invite forms with role dropdown from API"
```

---

## Task 20: Full Stack Verification

- [ ] **Step 1: Docker rebuild**

Run: `docker compose down -v && docker compose up --build`
Expected: Backend starts, seeds apps + Owner role, frontend builds, login works.

- [ ] **Step 2: Login as Owner, verify /me response**

Check browser DevTools → Network → `/api/auth/me` response includes `roleId`, `roleName`, `isOwner`, `permissions`, `appAccess`.

- [ ] **Step 3: Create a custom role via Roles tab**

Create "Analyst" role with voice-rx access only, eval:run + analytics:view permissions.

- [ ] **Step 4: Create a user with the custom role**

Create user, assign "Analyst" role. Login as that user. Verify:
- Only voice-rx visible in AppSwitcher
- Run Evaluation button visible, Delete button hidden
- Admin panel accessible only if user has user management permissions
- Navigating to `/kaira` or `/inside-sales` redirects to voice-rx

- [ ] **Step 5: Verify audit log**

Login as Owner → Security tab → verify role creation and user creation entries appear.

- [ ] **Step 6: Final commit (if any fixes needed)**

```bash
git add -A
git commit -m "fix(rbac): address issues found during full stack verification"
```

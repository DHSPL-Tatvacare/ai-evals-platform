# RBAC Design Spec — Role-Based Access Control

**Date:** 2026-03-25
**Status:** Draft — awaiting approval

---

## 1. Core Model

One system role. Everything else is custom.

- **Owner** — seeded when tenant is created. Implicit `*` (all permissions). Cannot be edited, deleted, or assigned to anyone else. Exactly 1 per tenant.
- **Custom roles** — created by Owner. Each role defines: which apps the role can access + which actions the role can perform within accessible apps.

There is no built-in "admin" or "member" role. If the Owner wants an admin-equivalent, they create a custom role with near-full permissions. The platform doesn't distinguish — it's just a custom role with a lot of checkboxes ticked.

### Permission Check Flow

```
Request arrives with JWT (contains user_id, tenant_id, role_id)
  │
  ├─ Is user the Owner? → ALLOW (implicit *, skip all checks)
  │
  ├─ Does the request target an app? (app_id in route/query)
  │   └─ Does role have access to this app? (role_app_access)
  │       ├─ NO  → 403
  │       └─ YES → continue
  │
  └─ Does the route require a permission? (e.g., eval:run)
      └─ Does role have this permission? (role_permissions)
          ├─ NO  → 403
          └─ YES → ALLOW
```

Frontend mirrors this: `<PermissionGate>` reads from `authStore.permissions` + `authStore.appAccess`.

---

## 2. Database Schema

### New Tables

#### `apps`

Registers available applications. Seeded on startup.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `slug` | VARCHAR(50) | Unique. `voice-rx`, `kaira-bot`, `inside-sales` |
| `display_name` | VARCHAR(100) | Human label |
| `description` | VARCHAR(255) | Short description |
| `icon_url` | VARCHAR(255) | Path to icon asset |
| `is_active` | BOOLEAN | Default true |
| `created_at` | TIMESTAMPTZ | Server default now() |

#### `roles`

One row per role per tenant.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `tenant_id` | UUID | FK → tenants.id, CASCADE |
| `name` | VARCHAR(100) | Display name (unique per tenant) |
| `description` | VARCHAR(500) | Optional |
| `is_system` | BOOLEAN | Default false. True only for `owner` |
| `created_at` | TIMESTAMPTZ | Server default now() |
| `updated_at` | TIMESTAMPTZ | Server default now(), onupdate |

**Constraints:**
- `UNIQUE(tenant_id, name)` — no duplicate role names within a tenant

#### `role_app_access`

Which apps a role can access.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `role_id` | UUID | FK → roles.id, CASCADE |
| `app_id` | UUID | FK → apps.id, CASCADE |
| `created_at` | TIMESTAMPTZ | Server default now() |

**Constraints:**
- `UNIQUE(role_id, app_id)` — no duplicate grants

#### `role_permissions`

Which actions a role can perform (global across all accessible apps).

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `role_id` | UUID | FK → roles.id, CASCADE |
| `permission` | VARCHAR(50) | e.g., `eval:run`, `listing:delete` |
| `created_at` | TIMESTAMPTZ | Server default now() |

**Constraints:**
- `UNIQUE(role_id, permission)` — no duplicate grants

#### `audit_log`

Records all RBAC and user-management changes.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `tenant_id` | UUID | FK → tenants.id |
| `actor_id` | UUID | Who performed the action (user_id) |
| `action` | VARCHAR(100) | e.g., `role.created`, `user.role_changed`, `role.permission_added` |
| `entity_type` | VARCHAR(50) | `role`, `user`, `role_permission`, `role_app_access` |
| `entity_id` | UUID | ID of affected entity |
| `before_state` | JSONB | Nullable. State before change |
| `after_state` | JSONB | Nullable. State after change |
| `created_at` | TIMESTAMPTZ | Server default now() |

**Indexes:**
- `(tenant_id, created_at DESC)` — for listing audit history
- `(entity_type, entity_id)` — for entity-specific history

### Modified Tables

#### `users`

| Change | Details |
|---|---|
| **Drop** `role` column | Remove `UserRole` enum column |
| **Add** `role_id` | UUID FK → `roles.id`. NOT NULL. |

The `UserRole` enum (`owner`, `admin`, `member`) is deleted entirely.

#### `invite_links`

| Change | Details |
|---|---|
| **Drop** `default_role` column | Remove enum column |
| **Add** `role_id` | UUID FK → `roles.id`. NOT NULL. Role assigned to users who sign up via this link. |

---

## 3. Seeding

On startup (idempotent), `seed_defaults.py` ensures:

1. **Apps table** — seed 3 rows:
   - `voice-rx` / "Voice Rx" / "Audio file evaluation tool"
   - `kaira-bot` / "Kaira Bot" / "Health chat bot assistant"
   - `inside-sales` / "Inside Sales" / "Inside sales call quality evaluation"

2. **Owner role** — for each tenant, ensure one `roles` row exists with `name="Owner"`, `is_system=True`. No `role_app_access` or `role_permissions` rows needed (Owner has implicit `*`).

3. **First user** — the tenant's first user gets `role_id` pointing to the Owner role.

---

## 4. Permission Rule IDs

### App Access Rules

These live in `role_app_access` (FK to apps table), not as permission strings.

| App slug | Display Name |
|---|---|
| `voice-rx` | Voice Rx |
| `kaira-bot` | Kaira Bot |
| `inside-sales` | Inside Sales |

### Action Permission Rules

These live in `role_permissions.permission` as `resource:action` strings.

| Permission | Description | Button / Route |
|---|---|---|
| **Listings** | | |
| `listing:create` | Create / upload / fetch listings | Fetch from API, Upload, Add Transcript |
| `listing:delete` | Delete listings | Delete button on listing row |
| **Evaluations** | | |
| `eval:run` | Run evaluations, submit jobs | Run Evaluation, Run All, Submit Job |
| `eval:delete` | Delete eval runs, cancel jobs | Delete Run, Cancel Job |
| `eval:export` | Export results (CSV, PDF) | Export buttons |
| **Resources (Prompts, Schemas, Evaluators)** | | |
| `resource:create` | Create prompts, schemas, evaluators, tags | Create/Fork buttons |
| `resource:edit` | Edit prompts, schemas, evaluators, tags | Edit buttons, Set Default |
| `resource:delete` | Delete prompts, schemas, evaluators, tags | Delete buttons |
| **Reports & Analytics** | | |
| `report:generate` | Generate reports, AI summaries | Generate Report button |
| `analytics:view` | View analytics, stats, trends, logs | Analytics tabs, dashboard stats |
| **Settings** | | |
| `settings:edit` | Edit LLM settings, app settings, adversarial config | Settings save buttons |
| **User Management** | | |
| `user:create` | Create users directly | Add User button |
| `user:invite` | Create and revoke invite links | Generate Link, Revoke |
| `user:edit` | Edit user name, role assignment | Edit User dialog, role dropdown |
| `user:deactivate` | Deactivate users | Deactivate button |
| `user:reset_password` | Reset other users' passwords | Reset Password button |
| `role:assign` | Assign roles to users | Role dropdown in user edit |
| **Tenant** | | |
| `tenant:settings` | Edit tenant name, config, branding, domains | Tenant settings panel |

**Owner-only (never grantable, never shown in role editor):**

| Permission | Description |
|---|---|
| `role:create` | Create custom roles |
| `role:edit` | Edit role name, permissions, app access |
| `role:delete` | Delete custom roles |

These three are **not stored** in `role_permissions`. They are enforced by checking `role.is_system AND role.name == 'Owner'` (i.e., `is_owner` check). The role editor UI never shows these as checkboxes.

---

## 5. Backend Changes

### 5.1 AuthContext

```python
@dataclass(frozen=True)
class AuthContext:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    role_id: uuid.UUID
    is_owner: bool              # True if role.is_system and role.name == "Owner"
    permissions: frozenset[str] # e.g., {"eval:run", "listing:delete", ...}
    app_access: frozenset[str]  # App slugs: {"voice-rx", "kaira-bot"}
```

### 5.2 Auth Dependencies

Replace `require_admin` / `require_owner` with:

```python
async def get_auth_context(credentials, db) -> AuthContext:
    """Decode JWT, load role + permissions from DB, build AuthContext."""
    payload = decode_access_token(credentials.credentials)
    user_id = uuid.UUID(payload["sub"])
    tenant_id = uuid.UUID(payload["tid"])
    role_id = uuid.UUID(payload["rid"])

    # Load role + permissions + app access in one query
    role, permissions, app_access = await load_role_permissions(db, role_id)

    return AuthContext(
        user_id=user_id,
        tenant_id=tenant_id,
        email=payload["email"],
        role_id=role_id,
        is_owner=role.is_system,  # Only system role is Owner
        permissions=frozenset(permissions),
        app_access=frozenset(app_access),
    )


def require_permission(*perms: str):
    """Dependency: require one or more permissions."""
    async def checker(auth: AuthContext = Depends(get_auth_context)):
        if auth.is_owner:
            return auth  # Owner bypasses all checks
        missing = set(perms) - auth.permissions
        if missing:
            raise HTTPException(403, f"Missing permissions: {', '.join(missing)}")
        return auth
    return Depends(checker)


def require_app_access(app_id_param: str = "app_id"):
    """Dependency: require access to the app specified in query/path."""
    async def checker(request: Request, auth: AuthContext = Depends(get_auth_context)):
        if auth.is_owner:
            return auth
        app_id = request.query_params.get(app_id_param) or request.path_params.get(app_id_param)
        if app_id and app_id not in auth.app_access:
            raise HTTPException(403, f"No access to app: {app_id}")
        return auth
    return Depends(checker)


def require_owner(auth: AuthContext = Depends(get_auth_context)):
    """Require Owner role (for role management)."""
    if not auth.is_owner:
        raise HTTPException(403, "Owner access required")
    return auth
```

### 5.3 JWT Changes

Add `rid` (role_id) to JWT payload. Remove `role` string.

```python
def create_access_token(user_id, tenant_id, email, role_id):
    payload = {
        "sub": str(user_id),
        "tid": str(tenant_id),
        "email": email,
        "rid": str(role_id),   # NEW: role UUID instead of role string
        "iat": ...,
        "exp": ...,
        "type": "access",
    }
```

### 5.4 Route-Level Permission Mapping

Every mutating route gets a `require_permission()` dependency. Read-only routes stay as `get_auth_context` but gain `require_app_access()` for app-scoped data.

| Route Pattern | Current Auth | New Auth |
|---|---|---|
| `POST /api/listings` | `get_auth_context` | `require_permission('listing:create')` + `require_app_access()` |
| `DELETE /api/listings/{id}` | `get_auth_context` | `require_permission('listing:delete')` + `require_app_access()` |
| `POST /api/jobs` | `get_auth_context` | `require_permission('eval:run')` + `require_app_access()` |
| `DELETE /api/eval-runs/{id}` | `get_auth_context` | `require_permission('eval:delete')` + `require_app_access()` |
| `POST /api/prompts` | `get_auth_context` | `require_permission('resource:create')` + `require_app_access()` |
| `PUT /api/prompts/{id}` | `get_auth_context` | `require_permission('resource:edit')` + `require_app_access()` |
| `DELETE /api/prompts/{id}` | `get_auth_context` | `require_permission('resource:delete')` + `require_app_access()` |
| `PUT /api/settings` | `get_auth_context` | `require_permission('settings:edit')` |
| `POST /api/admin/users` | `require_admin` | `require_permission('user:create')` |
| `PATCH /api/admin/users/{id}` | `require_admin` | `require_permission('user:edit')` |
| `DELETE /api/admin/users/{id}` | `require_owner` | `require_permission('user:deactivate')` |
| `POST /api/admin/invite-links` | `require_admin` | `require_permission('user:invite')` |
| `PATCH /api/admin/tenant` | `require_owner` | `require_owner` (unchanged — Owner-only) |
| `PATCH /api/admin/tenant-config` | `require_owner` | `require_owner` (unchanged — Owner-only) |
| `POST /api/reports/{id}/...` | `get_auth_context` | `require_permission('report:generate')` + `require_app_access()` |
| `GET /api/eval-runs/stats/*` | `get_auth_context` | `require_permission('analytics:view')` + `require_app_access()` |
| All read-only GET routes | `get_auth_context` | `get_auth_context` + `require_app_access()` |

### 5.5 New Admin Routes for RBAC

```
# Role management (Owner only)
GET    /api/admin/roles                    → list roles for tenant
POST   /api/admin/roles                    → create custom role
GET    /api/admin/roles/{role_id}          → get role with permissions + app access
PUT    /api/admin/roles/{role_id}          → update role (name, description, permissions, app access)
DELETE /api/admin/roles/{role_id}          → delete custom role (fail if users assigned)

# Apps (read-only, any authenticated user)
GET    /api/apps                           → list registered apps

# Audit log (Owner only)
GET    /api/admin/audit-log                → paginated audit log for tenant

# Me endpoint update
GET    /api/auth/me                        → now returns permissions[] and appAccess[]
```

### 5.6 `/api/auth/me` Response Change

```json
{
  "id": "uuid",
  "email": "user@example.com",
  "displayName": "Jane Doe",
  "tenantId": "uuid",
  "tenantName": "TatvaCare",
  "roleId": "uuid",
  "roleName": "Super Admin",
  "isOwner": false,
  "permissions": ["eval:run", "eval:delete", "listing:create", "..."],
  "appAccess": ["voice-rx", "kaira-bot", "inside-sales"]
}
```

---

## 6. Frontend Changes

### 6.1 Auth Types

```typescript
// src/types/auth.types.ts
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
  appAccess: string[];           // App slugs the user can access
}
```

### 6.2 Permission Utilities

```typescript
// src/utils/permissions.ts
import { useAuthStore } from '@/stores/authStore';

/** Check if current user has a specific permission */
export function hasPermission(permission: string): boolean {
  const user = useAuthStore.getState().user;
  if (!user) return false;
  if (user.isOwner) return true;
  return user.permissions.includes(permission);
}

/** Check if current user has access to an app */
export function hasAppAccess(appSlug: string): boolean {
  const user = useAuthStore.getState().user;
  if (!user) return false;
  if (user.isOwner) return true;
  return user.appAccess.includes(appSlug);
}
```

### 6.3 PermissionGate Component

```tsx
// src/components/auth/PermissionGate.tsx
interface PermissionGateProps {
  action: string;                  // e.g., "eval:run"
  app?: string;                    // optional app slug for app-level check
  fallback?: React.ReactNode;      // optional: show something else when denied
  children: React.ReactNode;
}

export function PermissionGate({ action, app, fallback = null, children }: PermissionGateProps) {
  const user = useAuthStore((s) => s.user);
  if (!user) return null;
  if (user.isOwner) return <>{children}</>;

  if (app && !user.appAccess.includes(app)) return <>{fallback}</>;
  if (!user.permissions.includes(action)) return <>{fallback}</>;

  return <>{children}</>;
}
```

### 6.4 Usage in Components

Before (current):
```tsx
{isOwner && !isSelf && user.role !== 'owner' && user.isActive && (
  <Button icon={UserX} onClick={() => setDeactivatingUser(user)} />
)}
```

After:
```tsx
<PermissionGate action="user:deactivate">
  {!isSelf && user.isActive && (
    <Button icon={UserX} onClick={() => setDeactivatingUser(user)} />
  )}
</PermissionGate>
```

### 6.5 AppSwitcher Change

```tsx
// Filter apps by user's appAccess
const accessibleApps = apps.filter(
  (app) => user.isOwner || user.appAccess.includes(app.id)
);
```

If only 1 app is accessible, show it as static (no dropdown).

### 6.6 Route-Level Guards

```tsx
// In router config, wrap app routes with access check
<Route path="/inside-sales/*" element={
  <AppAccessGuard app="inside-sales">
    <InsideSalesRoutes />
  </AppAccessGuard>
} />
```

`AppAccessGuard` redirects to first accessible app if the user navigates to an app they can't access.

### 6.7 Admin Roles Tab (new)

Replace the "Coming soon" placeholder in `AdminUsersPage.tsx` with a functional Roles management UI:

- **Roles list** — table of all custom roles + Owner (read-only row)
- **Create Role** button (Owner only)
- **Role editor** — two sections:
  1. **App Access** — toggle switches per app (from `/api/apps`)
  2. **Actions** — grouped checkboxes for each permission ID. Groups only visible/enabled for apps that are toggled ON. If an app is toggled OFF, its related action checkboxes are greyed out and unchecked.
- **Delete Role** — blocked if any users are assigned to it

### 6.8 Admin Security Tab (new)

Replace the "Coming soon" placeholder with:

- **Audit Log viewer** — paginated table from `/api/admin/audit-log`
- Columns: timestamp, actor (user name), action, entity type, entity details
- Filter by action type, date range

---

## 7. Action-to-Button Tag Inventory

Every action button in the frontend gets wrapped with `<PermissionGate action="...">`. Full inventory:

### Admin Features
| Component | Button / Action | Permission |
|---|---|---|
| `AdminUsersPage.tsx` | Add User | `user:create` |
| `AdminUsersPage.tsx` | Edit user (pencil) | `user:edit` |
| `AdminUsersPage.tsx` | Reset password (key) | `user:reset_password` |
| `AdminUsersPage.tsx` | Deactivate user (X) | `user:deactivate` |
| `InviteLinksSection.tsx` | Generate Link | `user:invite` |
| `InviteLinksSection.tsx` | Revoke Link (trash) | `user:invite` |

### Listing Actions
| Component | Button / Action | Permission |
|---|---|---|
| `ListingActionMenu.tsx` | Fetch from API | `listing:create` |
| `ListingActionMenu.tsx` | Refetch from API | `listing:create` |
| `ListingActionMenu.tsx` | Update Transcript | `listing:create` |
| `ListingActionMenu.tsx` | Run Evaluation | `eval:run` |
| `ListingActionMenu.tsx` | Rerun Evaluation | `eval:run` |
| `ListingActionMenu.tsx` | Export (CSV, PDF) | `eval:export` |

### Eval Run Actions
| Component | Button / Action | Permission |
|---|---|---|
| `RunList.tsx` | Delete run | `eval:delete` |
| `RunDetail.tsx` | Delete run | `eval:delete` |
| `RunDetail.tsx` | Cancel job | `eval:delete` |
| `VoiceRxRunDetail.tsx` | Delete run | `eval:delete` |
| `VoiceRxRunDetail.tsx` | Cancel job | `eval:delete` |
| `InsideSalesRunList.tsx` | Delete run | `eval:delete` |
| `InsideSalesRunDetail.tsx` | Delete run | `eval:delete` |
| `InsideSalesRunDetail.tsx` | Cancel job | `eval:delete` |
| `ReportTab.tsx` | Generate Report | `report:generate` |
| `ReportTab.tsx` | Refresh Report | `report:generate` |

### Resource Management (Prompts, Schemas, Evaluators)
| Component | Button / Action | Permission |
|---|---|---|
| `PromptsTab.tsx` | Create prompt | `resource:create` |
| `PromptsTab.tsx` | Edit prompt (pencil) | `resource:edit` |
| `PromptsTab.tsx` | Set default | `resource:edit` |
| `PromptsTab.tsx` | Delete prompt (trash) | `resource:delete` |
| `SchemasTab.tsx` | Create schema | `resource:create` |
| `SchemasTab.tsx` | Edit schema (pencil) | `resource:edit` |
| `SchemasTab.tsx` | Set default | `resource:edit` |
| `SchemasTab.tsx` | Delete schema (trash) | `resource:delete` |
| `EvaluatorsView.tsx` | Create evaluator | `resource:create` |
| `EvaluatorsView.tsx` | Edit evaluator | `resource:edit` |
| `EvaluatorsView.tsx` | Delete evaluator | `resource:delete` |
| `EvaluatorsView.tsx` | Run evaluator | `eval:run` |
| `EvaluatorsView.tsx` | Run All evaluators | `eval:run` |
| `EvaluatorRegistryPicker.tsx` | Fork evaluator | `resource:create` |
| `KairaBotEvaluatorsView.tsx` | Create/Edit/Delete | `resource:create/edit/delete` |

### Inside Sales Specific
| Component | Button / Action | Permission |
|---|---|---|
| `InsideSalesListing.tsx` | Evaluate Call | `eval:run` |

### Settings
| Component | Button / Action | Permission |
|---|---|---|
| LLM Settings (save) | Save settings | `settings:edit` |
| Adversarial Config (save) | Save config | `settings:edit` |
| Adversarial Config (reset) | Reset config | `settings:edit` |
| Adversarial Config (import) | Import config | `settings:edit` |

### Analytics / Reports
| Component | Button / Action | Permission |
|---|---|---|
| Analytics dashboards | View access | `analytics:view` |
| Cross-run analytics (refresh) | Compute analytics | `report:generate` |
| Report export (PDF) | Export PDF | `eval:export` |

---

## 8. Example: Owner Creates "Super Admin" Role

The Owner role matrix vs a custom "Super Admin":

| Rule | Owner | Super Admin |
|---|:---:|:---:|
| **App Access** | | |
| voice-rx | ✅ (implicit) | ✅ |
| kaira-bot | ✅ (implicit) | ✅ |
| inside-sales | ✅ (implicit) | ✅ |
| **Actions** | | |
| listing:create | ✅ (implicit) | ✅ |
| listing:delete | ✅ (implicit) | ✅ |
| eval:run | ✅ (implicit) | ✅ |
| eval:delete | ✅ (implicit) | ✅ |
| eval:export | ✅ (implicit) | ✅ |
| resource:create | ✅ (implicit) | ✅ |
| resource:edit | ✅ (implicit) | ✅ |
| resource:delete | ✅ (implicit) | ✅ |
| report:generate | ✅ (implicit) | ✅ |
| analytics:view | ✅ (implicit) | ✅ |
| settings:edit | ✅ (implicit) | ✅ |
| user:create | ✅ (implicit) | ✅ |
| user:invite | ✅ (implicit) | ✅ |
| user:edit | ✅ (implicit) | ✅ |
| user:deactivate | ✅ (implicit) | ✅ |
| user:reset_password | ✅ (implicit) | ✅ |
| role:assign | ✅ (implicit) | ✅ |
| tenant:settings | ✅ (implicit) | ❌ |
| role:create | ✅ (implicit) | 🔒 not grantable |
| role:edit | ✅ (implicit) | 🔒 not grantable |
| role:delete | ✅ (implicit) | 🔒 not grantable |

The difference: Super Admin can't touch tenant config or manage roles. Everything else is identical. The platform has zero special logic for this — it's just what the checkboxes look like.

---

## 9. Data Cleanup (Clean Slate)

Since there are no production users:

1. **Drop** `UserRole` enum type from PostgreSQL
2. **Drop** `users.role` column
3. **Drop** `invite_links.default_role` column
4. **Add** `users.role_id` FK → `roles.id`
5. **Add** `invite_links.role_id` FK → `roles.id`
6. **Create** new tables: `apps`, `roles`, `role_app_access`, `role_permissions`, `audit_log`
7. **Delete** all references to `UserRole` enum in Python code
8. **Delete** `require_admin` dependency (replaced by `require_permission`)
9. **Update** `require_owner` to check `auth.is_owner` instead of `auth.role == UserRole.OWNER`

---

## 10. Implementation Phases (High Level)

**Phase 1: Backend Schema + Auth Core**
- New models: `App`, `Role`, `RoleAppAccess`, `RolePermission`, `AuditLog`
- Modify `User` and `InviteLink` models
- Update `AuthContext`, JWT utils, auth dependencies
- Seed apps + Owner role
- New RBAC admin routes

**Phase 2: Backend Route Migration**
- Replace all `require_admin`/`require_owner` with `require_permission()`
- Add `require_app_access()` to app-scoped routes
- Update `/api/auth/me` response
- Audit log writes on all RBAC mutations

**Phase 3: Frontend Auth + Permission System**
- Update `User` type, auth store, auth API
- Create `PermissionGate` component and `hasPermission` / `hasAppAccess` utils
- `AppSwitcher` filtered by app access
- Route-level `AppAccessGuard`

**Phase 4: Frontend Button Tagging**
- Wrap every action button with `<PermissionGate>`
- Full inventory from Section 7

**Phase 5: Admin Roles + Security UI**
- Roles tab: list, create, edit, delete custom roles
- Role editor: app access toggles + permission checkbox grid
- Security tab: audit log viewer
- Update invite link form: role dropdown from roles API

---

## 11. Open Considerations

1. **Permission caching**: DB lookup per request (Option 9A). If performance becomes an issue later, add in-memory TTL cache keyed by `role_id` (not `user_id`) — since many users share a role, this is more cache-efficient.

2. **Role deletion safety**: Cannot delete a role while users are assigned to it. Owner must reassign users first.

3. **Owner transfer**: Not in scope. If needed later, it's a single DB update + audit log entry.

4. **Frontend app metadata**: Currently hardcoded in `src/types/app.types.ts` (`APPS` constant). After the `apps` table exists, the frontend should fetch app metadata from `/api/apps` instead. The `APPS` constant becomes a fallback/type definition only.

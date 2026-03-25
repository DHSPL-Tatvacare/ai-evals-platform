# Phase 7 — Admin UI

## 7.1 Admin API Module (`src/services/api/adminApi.ts`) — NEW FILE

```typescript
import { apiRequest } from './client';

export interface AdminUser {
  id: string;
  email: string;
  displayName: string;
  role: 'owner' | 'admin' | 'member';
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface CreateUserRequest {
  email: string;
  displayName: string;
  password: string;
  role: 'admin' | 'member';
}

export interface UpdateUserRequest {
  displayName?: string;
  role?: 'admin' | 'member';
  isActive?: boolean;
}

export interface TenantInfo {
  id: string;
  name: string;
  slug: string;
  isActive: boolean;
  createdAt: string;
}

export const adminApi = {
  // Users
  listUsers: (): Promise<AdminUser[]> =>
    apiRequest('/api/admin/users'),

  createUser: (data: CreateUserRequest): Promise<AdminUser> =>
    apiRequest('/api/admin/users', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateUser: (userId: string, data: UpdateUserRequest): Promise<AdminUser> =>
    apiRequest(`/api/admin/users/${userId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  deleteUser: (userId: string): Promise<void> =>
    apiRequest(`/api/admin/users/${userId}`, {
      method: 'DELETE',
    }),

  // Tenant
  getTenant: (): Promise<TenantInfo> =>
    apiRequest('/api/admin/tenant'),

  updateTenant: (data: { name: string }): Promise<TenantInfo> =>
    apiRequest('/api/admin/tenant', {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
};
```

---

## 7.2 Admin Users Page (`src/features/admin/AdminUsersPage.tsx`) — NEW FILE

### Layout

```
┌──────────────────────────────────────────────────┐
│  User Management                    [+ Add User] │
├──────────────────────────────────────────────────┤
│  Name          Email           Role    Status  ⋮ │
│  ──────────    ─────────────   ────    ──────  ─ │
│  Admin User    admin@co.com    owner   Active   │
│  Alice Dev     alice@co.com    admin   Active  ⋮ │
│  Bob Test      bob@co.com      member  Active  ⋮ │
│  Carol Old     carol@co.com    member  Disabled ⋮│
└──────────────────────────────────────────────────┘
```

### Features

1. **User table** — sortable by name, email, role, status
2. **Add User dialog** — email, display name, temporary password, role selector
3. **Edit User** — inline or dialog: change display name, role, active status
4. **Deactivate User** — soft-disable via `isActive: false` (owner-only action)
5. **Role constraints:**
   - Cannot change own role
   - Cannot deactivate self
   - Cannot promote to owner (only one owner per tenant)
   - Admins can manage members; owners can manage everyone

### Component Structure

```
AdminUsersPage
├── UsersTable (data table with actions)
├── CreateUserDialog (modal form)
└── EditUserDialog (modal form)
```

### State Management

Use local React state (not Zustand) — admin page is self-contained:

```typescript
const [users, setUsers] = useState<AdminUser[]>([]);
const [isCreateOpen, setIsCreateOpen] = useState(false);

useEffect(() => {
  adminApi.listUsers().then(setUsers);
}, []);
```

---

## 7.3 Backend Admin Routes (`backend/app/routes/admin.py`) — MODIFY

### New Endpoints

```python
# List users in tenant
@router.get("/users", response_model=list[UserResponse])
async def list_users(
    auth: AuthContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User)
        .where(User.tenant_id == auth.tenant_id)
        .order_by(User.created_at)
    )
    return result.scalars().all()


# Create user in tenant
@router.post("/users", response_model=UserResponse, status_code=201)
async def create_user(
    body: CreateUserRequest,
    auth: AuthContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    # Check email uniqueness within tenant
    existing = await db.scalar(
        select(User).where(
            User.tenant_id == auth.tenant_id,
            func.lower(User.email) == func.lower(body.email),
        )
    )
    if existing:
        raise HTTPException(409, detail="Email already registered in this tenant")

    user = User(
        tenant_id=auth.tenant_id,
        email=body.email,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        role=UserRole(body.role),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


# Update user
@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    body: UpdateUserRequest,
    auth: AuthContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await db.scalar(
        select(User).where(
            User.id == user_id,
            User.tenant_id == auth.tenant_id,
        )
    )
    if not user:
        raise HTTPException(404, detail="User not found")

    # Cannot modify owner unless you are owner
    if user.role == UserRole.OWNER and auth.role != UserRole.OWNER:
        raise HTTPException(403, detail="Cannot modify owner")

    # Cannot promote to owner
    if body.role == "owner":
        raise HTTPException(400, detail="Cannot set role to owner")

    if body.display_name is not None:
        user.display_name = body.display_name
    if body.role is not None:
        user.role = UserRole(body.role)
    if body.is_active is not None:
        user.is_active = body.is_active

    await db.commit()
    await db.refresh(user)
    return user


# Deactivate user (owner only)
@router.delete("/users/{user_id}")
async def deactivate_user(
    user_id: str,
    auth: AuthContext = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    user = await db.scalar(
        select(User).where(
            User.id == user_id,
            User.tenant_id == auth.tenant_id,
        )
    )
    if not user:
        raise HTTPException(404, detail="User not found")
    if str(user.id) == str(auth.user_id):
        raise HTTPException(400, detail="Cannot deactivate yourself")

    user.is_active = False
    await db.commit()
    return {"status": "ok"}


# Get tenant info
@router.get("/tenant", response_model=TenantResponse)
async def get_tenant(
    auth: AuthContext = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    tenant = await db.get(Tenant, auth.tenant_id)
    return tenant


# Update tenant
@router.patch("/tenant", response_model=TenantResponse)
async def update_tenant(
    body: UpdateTenantRequest,
    auth: AuthContext = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    tenant = await db.get(Tenant, auth.tenant_id)
    if body.name:
        tenant.name = body.name
    await db.commit()
    await db.refresh(tenant)
    return tenant
```

### Pydantic Schemas (`backend/app/schemas/admin.py`) — NEW

```python
class CreateUserRequest(CamelModel):
    email: str
    display_name: str
    password: str
    role: str  # "admin" or "member"

class UpdateUserRequest(CamelModel):
    display_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None

class UserResponse(CamelORMModel):
    id: str
    email: str
    display_name: str
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

class TenantResponse(CamelORMModel):
    id: str
    name: str
    slug: str
    is_active: bool
    created_at: datetime

class UpdateTenantRequest(CamelModel):
    name: Optional[str] = None
```

---

## 7.4 Admin Link in Sidebar

Show admin navigation only for admin/owner:

```typescript
// In Sidebar.tsx
const user = useAuthStore((s) => s.user);
const isAdmin = user?.role === 'admin' || user?.role === 'owner';

{isAdmin && (
  <NavLink to={ROUTES.ADMIN_USERS}>User Management</NavLink>
)}
```

---

## 7.5 User Onboarding Flow

### Step-by-step for Admin

1. Admin logs in → sees admin link in sidebar
2. Clicks "User Management" → navigates to `/admin/users`
3. Clicks "Add User" → fills form:
   - Email address
   - Display name
   - Temporary password
   - Role (admin or member)
4. Clicks "Create" → user created
5. Admin shares credentials with team member (email, Slack, etc.)
6. Team member logs in at `/login` with temporary password
7. Team member optionally changes password via profile

### Future Enhancement (Not in This Plan)

- Email invitation with magic link
- SSO / OAuth integration
- Self-service password reset

---

## 7.6 Files Summary

| File | Action | Purpose |
|------|--------|---------|
| `src/services/api/adminApi.ts` | CREATE | Admin API calls |
| `src/features/admin/AdminUsersPage.tsx` | CREATE | User management page |
| `src/features/admin/CreateUserDialog.tsx` | CREATE | Create user modal |
| `src/features/admin/EditUserDialog.tsx` | CREATE | Edit user modal |
| `backend/app/routes/admin.py` | MODIFY | Add user/tenant management endpoints |
| `backend/app/schemas/admin.py` | CREATE | Admin request/response schemas |
| `src/components/layout/Sidebar.tsx` | MODIFY | Add admin nav link |
| `src/app/Router.tsx` | MODIFY | Add admin routes |
| `src/config/routes.ts` | MODIFY | Add ADMIN_USERS constant |

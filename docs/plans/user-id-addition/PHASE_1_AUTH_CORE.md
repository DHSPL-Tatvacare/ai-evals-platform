# Phase 1: Backend Auth Core

## Goal

Stand up user registration, login, logout, and a reusable `get_current_user` FastAPI dependency — all JWT-based with httpOnly cookies. No route scoping yet (that's Phase 2). After this phase, auth endpoints work and the dependency is available but not injected into existing routes.

---

## 1.1 — User Model

**File:** `backend/app/models/user.py` (new)

```python
class User(Base, TimestampMixin):
    __tablename__ = "users"

    id:            Mapped[uuid.UUID]  = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email:         Mapped[str]        = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str]        = mapped_column(String(255), nullable=False)
    name:          Mapped[str]        = mapped_column(String(255), nullable=False)
    role:          Mapped[str]        = mapped_column(String(50), default="user")  # "admin" | "user"
    is_active:     Mapped[bool]       = mapped_column(Boolean, default=True)
```

**Register in `backend/app/models/__init__.py`:** Add `User` to the `__all__` / imports so `Base.metadata.create_all()` picks it up.

---

## 1.2 — Auth Schemas

**File:** `backend/app/schemas/auth.py` (new)

```
RegisterRequest(CamelModel):
    email: str          (EmailStr validator)
    password: str       (min_length=8)
    name: str

LoginRequest(CamelModel):
    email: str
    password: str

UserResponse(CamelORMModel):
    id: uuid.UUID
    email: str
    name: str
    role: str
    is_active: bool
    created_at: datetime

TokenPayload:
    sub: str            (user ID as string)
    role: str
    exp: datetime
    type: str           ("access" | "refresh")
```

---

## 1.3 — JWT & Cookie Utilities

**File:** `backend/app/auth.py` (new)

### Functions

| Function | Responsibility |
|----------|---------------|
| `hash_password(plain: str) -> str` | `passlib.hash.bcrypt.hash(plain)` |
| `verify_password(plain: str, hashed: str) -> bool` | `passlib.hash.bcrypt.verify(plain, hashed)` |
| `create_access_token(user_id: str, role: str) -> str` | JWT with `exp = now + ACCESS_TOKEN_EXPIRE_MINUTES` (default 15 min) |
| `create_refresh_token(user_id: str, role: str) -> str` | JWT with `exp = now + REFRESH_TOKEN_EXPIRE_DAYS` (default 7 days) |
| `decode_token(token: str) -> TokenPayload` | Decode + validate; raise on expired/invalid |
| `set_auth_cookies(response: Response, access: str, refresh: str)` | Set both as httpOnly, Secure, SameSite=Lax, Path=/ |
| `clear_auth_cookies(response: Response)` | Delete both cookies |
| `get_current_user(request: Request, db: AsyncSession) -> User` | Extract access token from cookie → decode → fetch User from DB → return. Raise 401 on failure. |
| `get_current_user_optional(request: Request, db: AsyncSession) -> User \| None` | Same but returns None instead of raising (for mixed endpoints). |
| `require_admin(current_user: User) -> User` | Raise 403 if `current_user.role != "admin"`. |

### Cookie Configuration

```
Cookie name (access):  "access_token"
Cookie name (refresh): "refresh_token"
httpOnly:              True
Secure:                True (False in dev via config flag)
SameSite:              "Lax"
Path:                  "/"
Domain:                not set (defaults to current host)
```

### Config Additions (`backend/app/config.py`)

```python
JWT_SECRET_KEY: str = ""            # MUST be set in .env.backend
JWT_ALGORITHM: str = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
REFRESH_TOKEN_EXPIRE_DAYS: int = 7
SECURE_COOKIES: bool = True         # Set False for local dev (no HTTPS)
```

---

## 1.4 — Auth Router

**File:** `backend/app/routes/auth.py` (new)
**Prefix:** `/api/auth`

### Endpoints

#### `POST /api/auth/register`
- **Input:** `RegisterRequest`
- **Logic:**
  1. Check email uniqueness → 409 if exists.
  2. Hash password.
  3. Create `User` row.
  4. Generate access + refresh tokens.
  5. Set cookies on response.
  6. Return `UserResponse`.
- **First-user rule:** If zero users exist in DB, auto-assign `role="admin"`. Otherwise `role="user"`.

#### `POST /api/auth/login`
- **Input:** `LoginRequest`
- **Logic:**
  1. Find user by email → 401 if not found.
  2. Verify password → 401 if wrong.
  3. Check `is_active` → 403 if deactivated.
  4. Generate access + refresh tokens.
  5. Set cookies on response.
  6. Return `UserResponse`.

#### `POST /api/auth/logout`
- **Logic:** Clear auth cookies. Return `{ "ok": true }`.
- **No dependency on `get_current_user`** — always succeeds (idempotent).

#### `POST /api/auth/refresh`
- **Logic:**
  1. Read refresh token from cookie.
  2. Decode → validate type == "refresh" and not expired.
  3. Fetch user from DB → verify still active.
  4. Issue new access token (NOT new refresh token — refresh token stays until expiry).
  5. Set access cookie.
  6. Return `UserResponse`.

#### `GET /api/auth/me`
- **Dependency:** `get_current_user`
- **Logic:** Return `UserResponse` for current user.
- **Purpose:** Frontend calls this on app load to check if session is valid.

#### `PUT /api/auth/me` (profile update)
- **Dependency:** `get_current_user`
- **Input:** `{ name?: str, currentPassword?: str, newPassword?: str }`
- **Logic:** Update name and/or password (with current password verification for password change).

---

## 1.5 — Register Router in `main.py`

- Import and include `auth_router` with prefix `/api/auth`.
- Ensure `User` table is created in the lifespan `create_all()`.
- **Do NOT add auth middleware to existing routes yet** — that's Phase 2.

---

## 1.6 — Health Check Exemption

`GET /api/health` must remain unauthenticated. Since we're not adding global middleware in this phase (auth is opt-in via `Depends(get_current_user)`), this is automatically handled.

---

## 1.7 — CORS Update

Update `CORS_ORIGINS` handling in `main.py`:
- Ensure `allow_credentials=True` is set (already is).
- This is required for browsers to send cookies cross-origin.
- Verify `allow_origins` is explicit (not `["*"]`) — wildcard + credentials is rejected by browsers.

---

## Verification Checklist

- [ ] `POST /api/auth/register` creates user, sets cookies, returns user JSON.
- [ ] `POST /api/auth/login` authenticates, sets cookies.
- [ ] `GET /api/auth/me` returns user when cookies present, 401 otherwise.
- [ ] `POST /api/auth/refresh` issues new access token from refresh cookie.
- [ ] `POST /api/auth/logout` clears cookies.
- [ ] First registered user gets `role=admin`.
- [ ] Duplicate email returns 409.
- [ ] Wrong password returns 401.
- [ ] Inactive user returns 403.
- [ ] All existing routes still work without auth (no breaking change yet).

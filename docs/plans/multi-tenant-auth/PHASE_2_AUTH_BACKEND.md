# Phase 2 — Authentication Backend

## 2.1 Dependencies

Add to `requirements.txt` / `pyproject.toml`:

```
PyJWT>=2.8.0        # JWT encode/decode
bcrypt>=4.1.0       # Password hashing
```

No OAuth2 libraries needed — we implement a focused JWT flow directly.

---

## 2.2 Configuration (`backend/app/config.py`)

Add to `Settings` class:

```python
# Auth
JWT_SECRET: str               # Required — no default. Fail loud if missing.
JWT_ALGORITHM: str = "HS256"
JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

# Bootstrap admin (used only when no users exist in DB)
ADMIN_EMAIL: str = ""
ADMIN_PASSWORD: str = ""
ADMIN_TENANT_NAME: str = ""
```

### Validation

On startup, if `JWT_SECRET` is not set, raise immediately. Do not default to an insecure value.

---

## 2.3 Auth Utilities (`backend/app/auth/utils.py`) — NEW FILE

```python
# backend/app/auth/utils.py

import uuid
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
import bcrypt

from app.config import settings


def hash_password(plain: str) -> str:
    """Hash password using bcrypt."""
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a password against its bcrypt hash."""
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    email: str,
    role: str,
) -> str:
    """Create a short-lived JWT access token."""
    payload = {
        "sub": str(user_id),
        "tid": str(tenant_id),
        "email": email,
        "role": role,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
        "type": "access",
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token() -> tuple[str, str]:
    """Create a refresh token. Returns (raw_token, token_hash)."""
    raw = uuid.uuid4().hex + uuid.uuid4().hex  # 64 hex chars
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    return raw, hashed


def decode_access_token(token: str) -> dict:
    """Decode and validate an access token. Raises jwt.exceptions on failure."""
    payload = jwt.decode(
        token,
        settings.JWT_SECRET,
        algorithms=[settings.JWT_ALGORITHM],
    )
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Not an access token")
    return payload


def hash_refresh_token(raw: str) -> str:
    """Hash a raw refresh token for DB storage."""
    return hashlib.sha256(raw.encode()).hexdigest()
```

---

## 2.4 Auth Context (`backend/app/auth/context.py`) — NEW FILE

This is the single dependency that every route uses.

```python
# backend/app/auth/context.py

import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import jwt

from app.auth.utils import decode_access_token
from app.database import get_db
from app.models.user import User, UserRole


bearer_scheme = HTTPBearer()


@dataclass(frozen=True)
class AuthContext:
    """Injected into every authenticated route."""
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    role: UserRole


async def get_auth_context(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> AuthContext:
    """Extract and validate auth context from Bearer token."""
    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    return AuthContext(
        user_id=uuid.UUID(payload["sub"]),
        tenant_id=uuid.UUID(payload["tid"]),
        email=payload["email"],
        role=UserRole(payload["role"]),
    )


async def require_admin(
    auth: AuthContext = Depends(get_auth_context),
) -> AuthContext:
    """Require admin or owner role."""
    if auth.role not in (UserRole.ADMIN, UserRole.OWNER):
        raise HTTPException(status_code=403, detail="Admin access required")
    return auth


async def require_owner(
    auth: AuthContext = Depends(get_auth_context),
) -> AuthContext:
    """Require owner role."""
    if auth.role != UserRole.OWNER:
        raise HTTPException(status_code=403, detail="Owner access required")
    return auth
```

### Usage in Routes

```python
# Every route — standard user access:
@router.get("")
async def list_listings(
    app_id: str = Query(...),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Listing)
        .where(Listing.tenant_id == auth.tenant_id, Listing.user_id == auth.user_id)
        .where(Listing.app_id == app_id)
    )
    return result.scalars().all()

# Admin-only route:
@router.get("/admin/users")
async def list_users(
    auth: AuthContext = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    ...
```

---

## 2.5 Auth Routes (`backend/app/routes/auth.py`) — NEW FILE

```
POST /api/auth/login          → Authenticate, return access token + set refresh cookie
POST /api/auth/refresh        → Use refresh cookie to get new access token
POST /api/auth/logout         → Clear refresh cookie, revoke token
GET  /api/auth/me             → Return current user profile
PUT  /api/auth/me/password    → Change own password
```

### Login Flow

```python
@router.post("/login")
async def login(body: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    # 1. Find user by email (case-insensitive)
    user = await db.scalar(
        select(User).where(func.lower(User.email) == func.lower(body.email))
    )
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(403, detail="Account disabled")

    # 2. Check tenant is active
    tenant = await db.get(Tenant, user.tenant_id)
    if not tenant or not tenant.is_active:
        raise HTTPException(403, detail="Tenant disabled")

    # 3. Create access token
    access_token = create_access_token(user.id, user.tenant_id, user.email, user.role.value)

    # 4. Create refresh token, store hash in DB
    raw_refresh, refresh_hash = create_refresh_token()
    db.add(RefreshToken(
        user_id=user.id,
        token_hash=refresh_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
    ))
    await db.commit()

    # 5. Set refresh token as httpOnly cookie
    response.set_cookie(
        key="refresh_token",
        value=raw_refresh,
        httponly=True,
        secure=True,          # HTTPS only
        samesite="lax",
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/api/auth/refresh",  # Only sent to refresh endpoint
    )

    # 6. Return access token + user profile
    return {
        "accessToken": access_token,
        "user": {
            "id": str(user.id),
            "email": user.email,
            "displayName": user.display_name,
            "role": user.role.value,
            "tenantId": str(user.tenant_id),
            "tenantName": tenant.name,
        },
    }
```

### Refresh Flow

```python
@router.post("/refresh")
async def refresh(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    raw_token = request.cookies.get("refresh_token")
    if not raw_token:
        raise HTTPException(401, detail="No refresh token")

    token_hash = hash_refresh_token(raw_token)

    # Find and validate stored token
    stored = await db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    if not stored or stored.expires_at < datetime.now(timezone.utc):
        raise HTTPException(401, detail="Invalid or expired refresh token")

    # Load user
    user = await db.get(User, stored.user_id)
    if not user or not user.is_active:
        raise HTTPException(403, detail="Account disabled")

    tenant = await db.get(Tenant, user.tenant_id)
    if not tenant or not tenant.is_active:
        raise HTTPException(403, detail="Tenant disabled")

    # Token rotation: delete old, create new
    await db.delete(stored)
    raw_refresh, refresh_hash = create_refresh_token()
    db.add(RefreshToken(
        user_id=user.id,
        token_hash=refresh_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
    ))
    await db.commit()

    # New access token
    access_token = create_access_token(user.id, user.tenant_id, user.email, user.role.value)

    # Set new refresh cookie
    response.set_cookie(
        key="refresh_token",
        value=raw_refresh,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/api/auth/refresh",
    )

    return {"accessToken": access_token}
```

### Logout Flow

```python
@router.post("/logout")
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    raw_token = request.cookies.get("refresh_token")
    if raw_token:
        token_hash = hash_refresh_token(raw_token)
        stored = await db.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        if stored:
            await db.delete(stored)
            await db.commit()

    response.delete_cookie("refresh_token", path="/api/auth/refresh")
    return {"status": "ok"}
```

### Me Endpoint

```python
@router.get("/me")
async def get_me(
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, auth.user_id)
    tenant = await db.get(Tenant, auth.tenant_id)
    return {
        "id": str(user.id),
        "email": user.email,
        "displayName": user.display_name,
        "role": user.role.value,
        "tenantId": str(user.tenant_id),
        "tenantName": tenant.name,
    }
```

### Password Change

```python
@router.put("/me/password")
async def change_password(
    body: ChangePasswordRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, auth.user_id)
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, detail="Current password incorrect")

    user.password_hash = hash_password(body.new_password)

    # Revoke all refresh tokens (force re-login on other devices)
    await db.execute(
        delete(RefreshToken).where(RefreshToken.user_id == user.id)
    )
    await db.commit()
    return {"status": "ok"}
```

---

## 2.6 Pydantic Schemas (`backend/app/schemas/auth.py`) — NEW FILE

```python
from app.models.base import CamelModel

class LoginRequest(CamelModel):
    email: str
    password: str

class ChangePasswordRequest(CamelModel):
    current_password: str
    new_password: str

class UserResponse(CamelModel):
    id: str
    email: str
    display_name: str
    role: str
    tenant_id: str
    tenant_name: str

class TokenResponse(CamelModel):
    access_token: str
    user: UserResponse
```

---

## 2.7 Register Auth Router (`backend/app/main.py`)

```python
from app.routes.auth import router as auth_router

app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
```

The auth router is **not protected** — `/api/auth/login` and `/api/auth/refresh` must be accessible without a token.

---

## 2.8 Bootstrap Admin Seed (`backend/app/services/seed_defaults.py`)

Add to startup sequence (runs after table creation, before other seeds):

```python
async def seed_bootstrap_admin():
    """Create the first tenant + admin user if no users exist. Uses env vars."""
    async with async_session() as db:
        user_count = await db.scalar(select(func.count(User.id)))
        if user_count > 0:
            return  # Already bootstrapped

        email = settings.ADMIN_EMAIL
        password = settings.ADMIN_PASSWORD
        tenant_name = settings.ADMIN_TENANT_NAME

        if not all([email, password, tenant_name]):
            logger.warning("No ADMIN_EMAIL/ADMIN_PASSWORD/ADMIN_TENANT_NAME set. Skipping bootstrap.")
            return

        # Create system tenant (for seed data)
        db.add(Tenant(id=SYSTEM_TENANT_ID, name="System", slug="system"))
        db.add(User(
            id=SYSTEM_USER_ID,
            tenant_id=SYSTEM_TENANT_ID,
            email="system@internal",
            password_hash=hash_password(uuid.uuid4().hex),  # Random, unguessable
            display_name="System",
            role=UserRole.OWNER,
        ))

        # Create admin tenant
        tenant = Tenant(name=tenant_name, slug=slugify(tenant_name))
        db.add(tenant)
        await db.flush()  # Get tenant.id

        # Create admin user
        db.add(User(
            tenant_id=tenant.id,
            email=email,
            password_hash=hash_password(password),
            display_name="Admin",
            role=UserRole.OWNER,
        ))

        await db.commit()
        logger.info(f"Bootstrapped tenant '{tenant_name}' with admin user '{email}'")
```

---

## 2.9 CORS Update (`backend/app/main.py`)

Ensure credentials are allowed for cookie-based refresh:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,  # Already set — required for cookies
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 2.10 Refresh Token Cleanup

Add periodic cleanup to the worker loop or as a separate task:

```python
async def cleanup_expired_refresh_tokens():
    """Delete expired refresh tokens. Run periodically."""
    async with async_session() as db:
        await db.execute(
            delete(RefreshToken).where(RefreshToken.expires_at < datetime.now(timezone.utc))
        )
        await db.commit()
```

Call from the existing recovery loop in `main.py` lifespan.

---

## 2.11 Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `backend/app/auth/__init__.py` | CREATE | Package init |
| `backend/app/auth/utils.py` | CREATE | Password hashing, JWT encode/decode |
| `backend/app/auth/context.py` | CREATE | AuthContext dataclass, FastAPI dependencies |
| `backend/app/routes/auth.py` | CREATE | Login, refresh, logout, me, password change |
| `backend/app/schemas/auth.py` | CREATE | Request/response schemas |
| `backend/app/config.py` | MODIFY | Add JWT_SECRET, token expiry, admin bootstrap vars |
| `backend/app/main.py` | MODIFY | Register auth router, CORS |
| `backend/app/services/seed_defaults.py` | MODIFY | Add bootstrap admin seed |
| `.env.backend` | MODIFY | Add JWT_SECRET, ADMIN_EMAIL, ADMIN_PASSWORD, ADMIN_TENANT_NAME |
| `.env.backend.example` | MODIFY | Document new env vars |

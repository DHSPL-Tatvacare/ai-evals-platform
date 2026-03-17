"""Auth routes — login, refresh, logout, me, password change."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import AuthContext, get_auth_context
from app.auth.utils import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.config import settings
from app.database import get_db
from app.models.tenant import Tenant
from app.models.user import RefreshToken, User
from app.schemas.auth import ChangePasswordRequest, LoginRequest

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_response(user: User, tenant: Tenant) -> dict:
    """Build a camelCase user profile dict."""
    return {
        "id": str(user.id),
        "email": user.email,
        "displayName": user.display_name,
        "role": user.role.value,
        "tenantId": str(user.tenant_id),
        "tenantName": tenant.name,
    }


def _set_refresh_cookie(response: Response, raw_token: str) -> None:
    """Set the httpOnly refresh-token cookie."""
    response.set_cookie(
        key="refresh_token",
        value=raw_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/api/auth/refresh",
    )


@router.post("/login")
async def login(
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
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
    _set_refresh_cookie(response, raw_refresh)

    # 6. Return access token + user profile
    return {
        "accessToken": access_token,
        "user": _user_response(user, tenant),
    }


@router.post("/refresh")
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
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
    _set_refresh_cookie(response, raw_refresh)

    return {"accessToken": access_token}


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
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


@router.get("/me")
async def get_me(
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, auth.user_id)
    if not user:
        raise HTTPException(404, detail="User not found")
    tenant = await db.get(Tenant, auth.tenant_id)
    if not tenant:
        raise HTTPException(404, detail="Tenant not found")
    return _user_response(user, tenant)


@router.put("/me/password")
async def change_password(
    body: ChangePasswordRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, auth.user_id)
    if not user:
        raise HTTPException(404, detail="User not found")
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, detail="Current password incorrect")

    user.password_hash = hash_password(body.new_password)

    # Revoke all refresh tokens (force re-login on other devices)
    await db.execute(
        delete(RefreshToken).where(RefreshToken.user_id == user.id)
    )
    await db.commit()
    return {"status": "ok"}

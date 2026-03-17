"""Password hashing and JWT token utilities."""
import uuid
import hashlib
from datetime import datetime, timedelta, timezone

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

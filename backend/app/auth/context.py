"""AuthContext dataclass and FastAPI dependencies for route-level auth."""
import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

import jwt

from app.auth.utils import decode_access_token
from app.models.user import UserRole


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

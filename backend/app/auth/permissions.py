"""Permission validation and RBAC dependency functions."""
import uuid

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.app_scope import require_registered_app_access
from app.auth.permission_catalog import VALID_PERMISSIONS
from app.database import get_db
from app.models.role import Role, RoleAppAccess, RolePermission


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
    """FastAPI dependency: require registry-backed access to the app in query/path params."""
    return require_registered_app_access(app_id_param)

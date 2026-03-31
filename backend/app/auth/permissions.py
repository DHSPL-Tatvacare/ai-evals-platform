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
    EVALUATOR_PROMOTE = "evaluator:promote"
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

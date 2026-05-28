"""The single scope boundary for orchestration analytics reads."""

from __future__ import annotations

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import AuthContext
from app.models.application import Application
from app.models.orchestration import Workflow
from app.schemas.app_config import AppConfig
from app.services.access_control import readable_scope_clause

ADMIN_AREA_PERMISSIONS = ("user:manage", "cost:view", "schedule:manage")


class ScopeForbidden(Exception):
    """Raised when a caller requests tenant-wide scope without authorization."""


def _is_admin_area(auth: AuthContext) -> bool:
    if getattr(auth, "is_owner", False):
        return True
    return any(p in auth.permissions for p in ADMIN_AREA_PERMISSIONS)


def resolve_analytics_scope(auth: AuthContext, requested_scope: str):
    """WHERE clause over Workflow for the caller's scope.

    tenant-wide iff admin-area authorized AND scope=='tenant'; else owned+shared.
    Unauthorized tenant request -> ScopeForbidden (handler maps to 403).
    """
    if requested_scope == "tenant":
        if not _is_admin_area(auth):
            raise ScopeForbidden("tenant-wide analytics requires admin access")
        return Workflow.tenant_id == auth.tenant_id
    return readable_scope_clause(Workflow, auth)


async def ensure_orchestration_enabled(db: AsyncSession, app_id: str) -> None:
    """403 unless the app exists and declares orchestration in its config."""
    app = await db.scalar(select(Application).where(Application.slug == app_id))
    if app is not None:
        try:
            enabled = AppConfig.model_validate(app.config or {}).features.has_orchestration
        except ValidationError:
            enabled = False
        if enabled:
            return
    raise HTTPException(status_code=403, detail="Orchestration not enabled for this app")

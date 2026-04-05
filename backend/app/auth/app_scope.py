"""Helpers for app-registry validation and app-access enforcement."""

from typing import TYPE_CHECKING

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.app import App

if TYPE_CHECKING:
    from app.auth.context import AuthContext


def normalize_app_slug(app_slug: str | None) -> str | None:
    normalized = (app_slug or '').strip()
    return normalized or None


async def load_active_app_map(db: AsyncSession) -> dict[str, App]:
    result = await db.execute(
        select(App).where(App.is_active == True).order_by(App.slug)
    )
    return {app.slug: app for app in result.scalars().all()}


async def validate_registered_app_slug(
    db: AsyncSession,
    app_slug: str | None,
    *,
    required: bool = True,
    param_name: str = 'app_id',
) -> str | None:
    normalized = normalize_app_slug(app_slug)
    if normalized is None:
        if required:
            raise HTTPException(400, f'Missing required parameter: {param_name}')
        return None

    app_map = await load_active_app_map(db)
    if normalized not in app_map:
        raise HTTPException(404, 'App not found')
    return normalized


async def ensure_registered_app_access(
    db: AsyncSession,
    auth: 'AuthContext',
    app_slug: str | None,
    *,
    required: bool = True,
    param_name: str = 'app_id',
) -> str | None:
    normalized = await validate_registered_app_slug(
        db,
        app_slug,
        required=required,
        param_name=param_name,
    )
    if normalized is None or auth.is_owner:
        return normalized
    if normalized not in auth.app_access:
        raise HTTPException(403, f'No access to app: {normalized}')
    return normalized


def require_registered_app_access(app_id_param: str = 'app_id'):
    from app.auth.context import AuthContext, get_auth_context

    async def _checker(
        request: Request,
        auth: AuthContext = Depends(get_auth_context),
        db: AsyncSession = Depends(get_db),
    ) -> AuthContext:
        app_slug = (
            request.query_params.get(app_id_param)
            or request.path_params.get(app_id_param)
        )
        await ensure_registered_app_access(
            db,
            auth,
            app_slug,
            required=True,
            param_name=app_id_param,
        )
        return auth

    return Depends(_checker)


def require_fixed_app_access(app_slug: str):
    from app.auth.context import AuthContext, get_auth_context

    async def _checker(
        auth: AuthContext = Depends(get_auth_context),
        db: AsyncSession = Depends(get_db),
    ) -> AuthContext:
        await ensure_registered_app_access(
            db,
            auth,
            app_slug,
            required=True,
            param_name='app_id',
        )
        return auth

    return Depends(_checker)

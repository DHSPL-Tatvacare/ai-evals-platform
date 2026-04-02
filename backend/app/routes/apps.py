"""Apps route — list registered applications."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import get_auth_context, AuthContext
from app.database import get_db
from app.models.app import App

router = APIRouter(prefix="/api/apps", tags=["apps"])


@router.get("")
async def list_apps(
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """List all registered apps."""
    result = await db.execute(select(App).where(App.is_active == True).order_by(App.slug))
    apps = result.scalars().all()
    return [
        {
            "id": str(a.id),
            "slug": a.slug,
            "displayName": a.display_name,
            "description": a.description,
            "iconUrl": a.icon_url,
            "isActive": a.is_active,
        }
        for a in apps
    ]


@router.get("/{slug}/config")
async def get_app_config(
    slug: str,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """Return the config payload for one app by slug."""
    result = await db.execute(
        select(App).where(App.slug == slug, App.is_active == True)
    )
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    return app.config or {}

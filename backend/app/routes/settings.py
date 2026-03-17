"""Settings API routes."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import AuthContext, get_auth_context
from app.database import get_db
from app.models.setting import Setting
from app.schemas.setting import SettingCreate, SettingResponse

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=list[SettingResponse])
async def list_settings(
    app_id: str = Query(None),
    key: str = Query(None),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """List settings for the current user, optionally filtered by app_id and/or key."""
    # Always filter by app_id — coerce None to empty string (global)
    resolved_app_id = app_id if app_id is not None else ""
    query = select(Setting).where(
        Setting.tenant_id == auth.tenant_id,
        Setting.user_id == auth.user_id,
        Setting.app_id == resolved_app_id,
    )
    if key:
        query = query.where(Setting.key == key)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{setting_id}", response_model=SettingResponse)
async def get_setting(
    setting_id: int,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """Get a single setting by ID."""
    result = await db.execute(
        select(Setting).where(
            Setting.id == setting_id,
            Setting.tenant_id == auth.tenant_id,
            Setting.user_id == auth.user_id,
        )
    )
    setting = result.scalar_one_or_none()
    if not setting:
        raise HTTPException(status_code=404, detail="Setting not found")
    return setting


@router.put("", response_model=SettingResponse)
async def upsert_setting(
    body: SettingCreate,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """Upsert a setting (insert or update if exists). Per-user scoped."""
    # Coerce None to empty string — NULL breaks the unique constraint
    app_id = body.app_id or ""

    stmt = pg_insert(Setting).values(
        app_id=app_id,
        key=body.key,
        value=body.value,
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
    ).on_conflict_do_update(
        constraint="uq_setting",
        set_={"value": body.value, "updated_at": func.now()}
    ).returning(Setting)

    result = await db.execute(stmt)
    await db.commit()
    setting = result.scalar_one()
    return setting


@router.delete("")
async def delete_setting_by_key(
    key: str = Query(...),
    app_id: str = Query(None),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """Delete a setting by key + app_id for the current user."""
    resolved_app_id = app_id if app_id is not None else ""
    result = await db.execute(
        select(Setting)
        .where(
            Setting.key == key,
            Setting.app_id == resolved_app_id,
            Setting.tenant_id == auth.tenant_id,
            Setting.user_id == auth.user_id,
        )
    )
    setting = result.scalar_one_or_none()
    if not setting:
        raise HTTPException(status_code=404, detail="Setting not found")

    await db.delete(setting)
    await db.commit()
    return {"deleted": True, "key": key, "appId": resolved_app_id}


@router.delete("/{setting_id}")
async def delete_setting(
    setting_id: int,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """Delete a setting by ID."""
    result = await db.execute(
        select(Setting).where(
            Setting.id == setting_id,
            Setting.tenant_id == auth.tenant_id,
            Setting.user_id == auth.user_id,
        )
    )
    setting = result.scalar_one_or_none()
    if not setting:
        raise HTTPException(status_code=404, detail="Setting not found")

    await db.delete(setting)
    await db.commit()
    return {"deleted": True, "id": setting_id}

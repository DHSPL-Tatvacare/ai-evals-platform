"""Adversarial config API routes.

Typed endpoints for managing adversarial evaluation config, with validation.
Preferred over raw settings writes so the FE gets validation errors early.
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from app.auth.context import AuthContext, get_auth_context
from app.auth.permissions import require_permission
from app.services.evaluators.adversarial_config import (
    AdversarialConfig, get_default_config,
    load_config_from_db, save_config_to_db,
)

router = APIRouter(prefix="/api/adversarial-config", tags=["adversarial-config"])


@router.get("")
async def get_config(
    auth: AuthContext = Depends(get_auth_context),
):
    """Return current adversarial config (resolved: app shared -> system default)."""
    config = await load_config_from_db(tenant_id=auth.tenant_id, user_id=auth.user_id)
    return config.model_dump()


@router.put("")
async def update_config(
    body: dict,
    auth: AuthContext = require_permission('settings:edit'),
):
    """Validate and save adversarial config as the app-shared contract."""
    try:
        config = AdversarialConfig.model_validate(body)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    await save_config_to_db(config, tenant_id=auth.tenant_id, user_id=auth.user_id)
    return config.model_dump()


@router.post("/reset")
async def reset_config(
    auth: AuthContext = require_permission('settings:edit'),
):
    """Restore built-in default config for the tenant-shared contract."""
    config = get_default_config()
    await save_config_to_db(config, tenant_id=auth.tenant_id, user_id=auth.user_id)
    return config.model_dump()


@router.get("/export")
async def export_config(
    auth: AuthContext = Depends(get_auth_context),
):
    """Export current config as downloadable JSON."""
    config = await load_config_from_db(tenant_id=auth.tenant_id, user_id=auth.user_id)
    return JSONResponse(
        content=config.model_dump(),
        headers={"Content-Disposition": "attachment; filename=adversarial-config.json"},
    )


@router.post("/import")
async def import_config(
    body: dict,
    auth: AuthContext = require_permission('settings:edit'),
):
    """Validate and replace config from imported JSON."""
    try:
        config = AdversarialConfig.model_validate(body)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    await save_config_to_db(config, tenant_id=auth.tenant_id, user_id=auth.user_id)
    return config.model_dump()

"""Prompts API routes."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, desc, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import AuthContext, get_auth_context
from app.constants import SYSTEM_TENANT_ID
from app.database import get_db
from app.models.prompt import Prompt
from app.schemas.prompt import PromptCreate, PromptUpdate, PromptResponse

router = APIRouter(prefix="/api/prompts", tags=["prompts"])


@router.get("", response_model=list[PromptResponse])
async def list_prompts(
    app_id: str = Query(...),
    prompt_type: Optional[str] = Query(None),
    source_type: Optional[str] = Query(None),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """List user's prompts + system defaults for an app."""
    query = select(Prompt).where(
        or_(
            and_(Prompt.tenant_id == auth.tenant_id, Prompt.user_id == auth.user_id),
            Prompt.tenant_id == SYSTEM_TENANT_ID,
        ),
        Prompt.app_id == app_id,
    )
    if prompt_type:
        query = query.where(Prompt.prompt_type == prompt_type)
    if source_type:
        query = query.where(
            or_(Prompt.source_type == source_type, Prompt.source_type.is_(None))
        )
    query = query.order_by(desc(Prompt.created_at))

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{prompt_id}", response_model=PromptResponse)
async def get_prompt(
    prompt_id: int,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """Get a single prompt by ID (own or system)."""
    result = await db.execute(
        select(Prompt).where(
            Prompt.id == prompt_id,
            or_(
                and_(Prompt.tenant_id == auth.tenant_id, Prompt.user_id == auth.user_id),
                Prompt.tenant_id == SYSTEM_TENANT_ID,
            ),
        )
    )
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return prompt


@router.post("", response_model=PromptResponse, status_code=201)
async def create_prompt(
    body: PromptCreate,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """Create a new prompt with auto-incremented version."""
    result = await db.execute(
        select(func.max(Prompt.version))
        .where(
            Prompt.tenant_id == auth.tenant_id,
            Prompt.user_id == auth.user_id,
            Prompt.app_id == body.app_id,
            Prompt.prompt_type == body.prompt_type,
        )
    )
    max_version = result.scalar() or 0

    prompt = Prompt(
        **body.model_dump(),
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        version=max_version + 1,
    )
    db.add(prompt)
    await db.commit()
    await db.refresh(prompt)
    return prompt


@router.put("/{prompt_id}", response_model=PromptResponse)
async def update_prompt(
    prompt_id: int,
    body: PromptUpdate,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """Update a prompt. Cannot edit system prompts."""
    result = await db.execute(
        select(Prompt).where(
            Prompt.id == prompt_id,
            Prompt.tenant_id == auth.tenant_id,
            Prompt.user_id == auth.user_id,
        )
    )
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(prompt, key, value)

    await db.commit()
    await db.refresh(prompt)
    return prompt


@router.delete("/{prompt_id}")
async def delete_prompt(
    prompt_id: int,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """Delete a prompt. Cannot delete system prompts."""
    result = await db.execute(
        select(Prompt).where(
            Prompt.id == prompt_id,
            Prompt.tenant_id == auth.tenant_id,
            Prompt.user_id == auth.user_id,
        )
    )
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    if prompt.is_default:
        raise HTTPException(status_code=400, detail="Cannot delete default prompt")

    await db.delete(prompt)
    await db.commit()
    return {"deleted": True, "id": prompt_id}



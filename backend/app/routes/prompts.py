"""Prompts API routes."""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, desc, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import AuthContext, get_auth_context
from app.auth.permissions import require_permission, require_app_access
from app.database import get_db
from app.models.prompt import Prompt
from app.models.mixins.shareable import Visibility
from app.schemas.prompt import PromptCreate, PromptUpdate, PromptResponse
from app.services.access_control import readable_scope_clause

router = APIRouter(prefix="/api/prompts", tags=["prompts"])


@router.get("", response_model=list[PromptResponse])
async def list_prompts(
    app_id: str = Query(...),
    prompt_type: Optional[str] = Query(None),
    source_type: Optional[str] = Query(None),
    branch_key: Optional[str] = Query(None),
    latest_only: bool = Query(True),
    auth: AuthContext = require_app_access(),
    db: AsyncSession = Depends(get_db),
):
    """List prompts visible to the current user for an app.

    By default returns only the latest version per branch. Pass latest_only=false
    with branch_key to get full version history for one branch.
    """
    # Visibility-aware: own rows + shared in tenant + system defaults
    query = select(Prompt).where(readable_scope_clause(Prompt, auth), Prompt.app_id == app_id)
    if prompt_type:
        query = query.where(Prompt.prompt_type == prompt_type)
    if source_type:
        query = query.where(
            or_(Prompt.source_type == source_type, Prompt.source_type.is_(None))
        )
    if branch_key:
        query = query.where(Prompt.branch_key == branch_key)

    if latest_only and not branch_key:
        # Subquery: max version per branch_key within the visible set
        # Use a window function approach: order by version desc, pick first per branch
        query = query.order_by(Prompt.branch_key, desc(Prompt.version))
        result = await db.execute(query)
        all_rows = result.scalars().all()
        # Deduplicate: keep first (latest version) per branch_key
        seen_branches: set[tuple[str, str, str | None]] = set()
        latest: list[Prompt] = []
        for row in all_rows:
            branch_identity = (row.branch_key, row.prompt_type, row.source_type)
            if branch_identity not in seen_branches:
                seen_branches.add(branch_identity)
                latest.append(row)
        return latest

    query = query.order_by(desc(Prompt.version))
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{prompt_id}", response_model=PromptResponse)
async def get_prompt(
    prompt_id: int,
    auth: AuthContext = require_app_access(),
    db: AsyncSession = Depends(get_db),
):
    """Get a single prompt by ID if visible in the current library scope."""
    result = await db.execute(
        select(Prompt).where(
            Prompt.id == prompt_id,
            readable_scope_clause(Prompt, auth),
        )
    )
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return prompt


@router.post("", response_model=PromptResponse, status_code=201)
async def create_prompt(
    body: PromptCreate,
    auth: AuthContext = require_permission('asset:create'),
    _app_check: AuthContext = require_app_access(),
    db: AsyncSession = Depends(get_db),
):
    """Create a new prompt with auto-incremented version within its branch."""
    data = body.model_dump(exclude_none=True)
    branch_key = data.get("branch_key") or str(uuid.uuid4())
    data["branch_key"] = branch_key

    # Version increment scoped by the branch identity
    result = await db.execute(
        select(func.max(Prompt.version))
        .where(
            Prompt.tenant_id == auth.tenant_id,
            Prompt.user_id == auth.user_id,
            Prompt.app_id == body.app_id,
            Prompt.prompt_type == body.prompt_type,
            Prompt.source_type == body.source_type,
            Prompt.branch_key == branch_key,
        )
    )
    max_version = result.scalar() or 0

    prompt = Prompt(
        **data,
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        version=max_version + 1,
    )
    db.add(prompt)
    await db.commit()
    await db.refresh(prompt)
    return prompt


@router.post("/{prompt_id}/fork", response_model=PromptResponse, status_code=201)
async def fork_prompt(
    prompt_id: int,
    auth: AuthContext = require_permission('asset:create'),
    _app_check: AuthContext = require_app_access(),
    db: AsyncSession = Depends(get_db),
):
    """Fork a visible prompt into a new private branch with version=1."""
    # Can fork any visible prompt (own, shared, system)
    result = await db.execute(
        select(Prompt).where(
            Prompt.id == prompt_id,
            readable_scope_clause(Prompt, auth),
        )
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Prompt not found")

    forked = Prompt(
        app_id=source.app_id,
        prompt_type=source.prompt_type,
        branch_key=str(uuid.uuid4()),  # New branch
        version=1,
        name=source.name,
        prompt=source.prompt,
        description=source.description,
        is_default=False,
        source_type=source.source_type,
        visibility=Visibility.PRIVATE,
        forked_from=source.id,
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
    )
    db.add(forked)
    await db.commit()
    await db.refresh(forked)
    return forked


@router.patch("/{prompt_id}/visibility", response_model=PromptResponse)
async def patch_prompt_visibility(
    prompt_id: int,
    body: dict,
    auth: AuthContext = require_permission('asset:share'),
    _app_check: AuthContext = require_app_access(),
    db: AsyncSession = Depends(get_db),
):
    """Change visibility on a prompt. Only the owner can change visibility."""
    result = await db.execute(
        select(Prompt).where(
            Prompt.id == prompt_id,
            Prompt.tenant_id == auth.tenant_id,
            Prompt.user_id == auth.user_id,
        )
    )
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found or not owned by you")

    if prompt.is_default:
        raise HTTPException(status_code=400, detail="Cannot change visibility of system defaults")

    latest_version = await db.scalar(
        select(func.max(Prompt.version)).where(
            Prompt.tenant_id == prompt.tenant_id,
            Prompt.user_id == prompt.user_id,
            Prompt.app_id == prompt.app_id,
            Prompt.prompt_type == prompt.prompt_type,
            Prompt.source_type == prompt.source_type,
            Prompt.branch_key == prompt.branch_key,
        )
    )
    if latest_version != prompt.version:
        raise HTTPException(status_code=409, detail="Visibility can only be changed on the latest prompt version")

    try:
        new_visibility = Visibility.normalize(body.get("visibility"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="visibility must be 'private' or 'shared'") from exc
    if new_visibility is None:
        raise HTTPException(status_code=422, detail="visibility must be 'private' or 'shared'")

    prompt.visibility = new_visibility
    if new_visibility == Visibility.SHARED:
        prompt.shared_by = auth.user_id
        from sqlalchemy import func as sqlfunc
        prompt.shared_at = sqlfunc.now()

    await db.commit()
    await db.refresh(prompt)
    return prompt


@router.put("/{prompt_id}", response_model=PromptResponse)
async def update_prompt(
    prompt_id: int,
    body: PromptUpdate,
    auth: AuthContext = require_permission('asset:edit'),
    _app_check: AuthContext = require_app_access(),
    db: AsyncSession = Depends(get_db),
):
    """Metadata-only prompt update. Content edits must create a new version."""
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
    if body.requires_new_version():
        raise HTTPException(status_code=400, detail="Content edits must create a new prompt version")
    for key, value in update_data.items():
        setattr(prompt, key, value)

    await db.commit()
    await db.refresh(prompt)
    return prompt


@router.delete("/{prompt_id}")
async def delete_prompt(
    prompt_id: int,
    auth: AuthContext = require_permission('asset:delete'),
    _app_check: AuthContext = require_app_access(),
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

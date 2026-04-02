"""Schemas API routes."""
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, desc, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import AuthContext, get_auth_context
from app.auth.permissions import require_permission, require_app_access
from app.constants import SYSTEM_TENANT_ID
from app.database import get_db
from app.models.listing import Listing
from app.models.schema import Schema
from app.models.mixins.shareable import Visibility
from app.schemas.schema import SchemaCreate, SchemaUpdate, SchemaResponse
from app.services.access_control import readable_scope_clause

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/schemas", tags=["schemas"])


@router.get("", response_model=list[SchemaResponse])
async def list_schemas(
    app_id: str = Query(...),
    prompt_type: Optional[str] = Query(None),
    source_type: Optional[str] = Query(None),
    branch_key: Optional[str] = Query(None),
    latest_only: bool = Query(True),
    auth: AuthContext = require_app_access(),
    db: AsyncSession = Depends(get_db),
):
    """List schemas visible to the current user for an app.

    By default returns only the latest version per branch. Pass latest_only=false
    with branch_key to get full version history for one branch.
    """
    # Visibility-aware: own rows + app-shared in tenant + system defaults
    query = select(Schema).where(readable_scope_clause(Schema, auth), Schema.app_id == app_id)
    if prompt_type:
        query = query.where(Schema.prompt_type == prompt_type)
    if source_type:
        query = query.where(
            or_(Schema.source_type == source_type, Schema.source_type.is_(None))
        )
    if branch_key:
        query = query.where(Schema.branch_key == branch_key)

    if latest_only and not branch_key:
        # Subquery: max version per branch_key within the visible set
        # Use a window function approach: order by version desc, pick first per branch
        query = query.order_by(Schema.branch_key, desc(Schema.version))
        result = await db.execute(query)
        all_rows = result.scalars().all()
        # Deduplicate: keep first (latest version) per branch_key
        seen_branches: set[tuple[str, str, str | None]] = set()
        latest: list[Schema] = []
        for row in all_rows:
            branch_identity = (row.branch_key, row.prompt_type, row.source_type)
            if branch_identity not in seen_branches:
                seen_branches.add(branch_identity)
                latest.append(row)
        return latest

    query = query.order_by(desc(Schema.version))
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{schema_id}", response_model=SchemaResponse)
async def get_schema(
    schema_id: int,
    auth: AuthContext = require_app_access(),
    db: AsyncSession = Depends(get_db),
):
    """Get a single schema by ID if visible in the current library scope."""
    result = await db.execute(
        select(Schema).where(
            Schema.id == schema_id,
            readable_scope_clause(Schema, auth),
        )
    )
    schema = result.scalar_one_or_none()
    if not schema:
        raise HTTPException(status_code=404, detail="Schema not found")
    return schema


@router.post("", response_model=SchemaResponse, status_code=201)
async def create_schema(
    body: SchemaCreate,
    auth: AuthContext = require_permission('resource:create'),
    _app_check: AuthContext = require_app_access(),
    db: AsyncSession = Depends(get_db),
):
    """Create a new schema with auto-incremented version within its branch."""
    data = body.model_dump(exclude_none=True)
    branch_key = data.get("branch_key") or str(uuid.uuid4())
    data["branch_key"] = branch_key

    # Version increment scoped by the branch identity
    result = await db.execute(
        select(func.max(Schema.version))
        .where(
            Schema.tenant_id == auth.tenant_id,
            Schema.user_id == auth.user_id,
            Schema.app_id == body.app_id,
            Schema.prompt_type == body.prompt_type,
            Schema.source_type == body.source_type,
            Schema.branch_key == branch_key,
        )
    )
    max_version = result.scalar() or 0

    schema = Schema(
        **data,
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        version=max_version + 1,
    )
    db.add(schema)
    await db.commit()
    await db.refresh(schema)
    return schema


@router.post("/{schema_id}/fork", response_model=SchemaResponse, status_code=201)
async def fork_schema(
    schema_id: int,
    auth: AuthContext = require_permission('resource:create'),
    _app_check: AuthContext = require_app_access(),
    db: AsyncSession = Depends(get_db),
):
    """Fork a visible schema into a new private branch with version=1."""
    # Can fork any visible schema (own, app-shared, system)
    result = await db.execute(
        select(Schema).where(
            Schema.id == schema_id,
            or_(
                and_(Schema.tenant_id == auth.tenant_id, Schema.user_id == auth.user_id),
                and_(Schema.tenant_id == auth.tenant_id, Schema.visibility == Visibility.APP),
                Schema.tenant_id == SYSTEM_TENANT_ID,
            ),
        )
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Schema not found")

    forked = Schema(
        app_id=source.app_id,
        prompt_type=source.prompt_type,
        branch_key=str(uuid.uuid4()),  # New branch
        version=1,
        name=source.name,
        schema_data=source.schema_data,
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


@router.patch("/{schema_id}/visibility", response_model=SchemaResponse)
async def patch_schema_visibility(
    schema_id: int,
    body: dict,
    auth: AuthContext = require_permission('resource:edit'),
    _app_check: AuthContext = require_app_access(),
    db: AsyncSession = Depends(get_db),
):
    """Change visibility on a schema. Only the owner can change visibility."""
    result = await db.execute(
        select(Schema).where(
            Schema.id == schema_id,
            Schema.tenant_id == auth.tenant_id,
            Schema.user_id == auth.user_id,
        )
    )
    schema = result.scalar_one_or_none()
    if not schema:
        raise HTTPException(status_code=404, detail="Schema not found or not owned by you")

    if schema.is_default:
        raise HTTPException(status_code=400, detail="Cannot change visibility of system defaults")

    latest_version = await db.scalar(
        select(func.max(Schema.version)).where(
            Schema.tenant_id == schema.tenant_id,
            Schema.user_id == schema.user_id,
            Schema.app_id == schema.app_id,
            Schema.prompt_type == schema.prompt_type,
            Schema.source_type == schema.source_type,
            Schema.branch_key == schema.branch_key,
        )
    )
    if latest_version != schema.version:
        raise HTTPException(status_code=409, detail="Visibility can only be changed on the latest schema version")

    new_visibility = body.get("visibility")
    if new_visibility not in ("private", "app"):
        raise HTTPException(status_code=422, detail="visibility must be 'private' or 'app'")

    schema.visibility = Visibility(new_visibility)
    if new_visibility == "app":
        schema.shared_by = auth.user_id
        from sqlalchemy import func as sqlfunc
        schema.shared_at = sqlfunc.now()

    await db.commit()
    await db.refresh(schema)
    return schema


@router.put("/{schema_id}", response_model=SchemaResponse)
async def update_schema(
    schema_id: int,
    body: SchemaUpdate,
    auth: AuthContext = require_permission('resource:edit'),
    _app_check: AuthContext = require_app_access(),
    db: AsyncSession = Depends(get_db),
):
    """Metadata-only schema update. Content edits must create a new version."""
    result = await db.execute(
        select(Schema).where(
            Schema.id == schema_id,
            Schema.tenant_id == auth.tenant_id,
            Schema.user_id == auth.user_id,
        )
    )
    schema = result.scalar_one_or_none()
    if not schema:
        raise HTTPException(status_code=404, detail="Schema not found")

    update_data = body.model_dump(exclude_unset=True)
    if body.requires_new_version():
        raise HTTPException(status_code=400, detail="Content edits must create a new schema version")
    for key, value in update_data.items():
        setattr(schema, key, value)

    await db.commit()
    await db.refresh(schema)
    return schema


@router.delete("/{schema_id}")
async def delete_schema(
    schema_id: int,
    auth: AuthContext = require_permission('resource:delete'),
    _app_check: AuthContext = require_app_access(),
    db: AsyncSession = Depends(get_db),
):
    """Delete a schema. Cannot delete system schemas."""
    result = await db.execute(
        select(Schema).where(
            Schema.id == schema_id,
            Schema.tenant_id == auth.tenant_id,
            Schema.user_id == auth.user_id,
        )
    )
    schema = result.scalar_one_or_none()
    if not schema:
        raise HTTPException(status_code=404, detail="Schema not found")

    if schema.is_default:
        raise HTTPException(status_code=400, detail="Cannot delete default schema")

    await db.delete(schema)
    await db.commit()
    return {"deleted": True, "id": schema_id}




# ── Schema sync from listing ────────────────────────────────────


def _infer_json_schema(value: object) -> dict:
    """Generate a JSON Schema from a sample Python value by walking its structure."""
    if value is None:
        return {"type": "string"}
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, int):
        return {"type": "number"}
    if isinstance(value, float):
        return {"type": "number"}
    if isinstance(value, str):
        return {"type": "string"}
    if isinstance(value, list):
        if len(value) == 0:
            return {"type": "array", "items": {"type": "object"}}
        # Infer item schema from first element
        first = value[0]
        if isinstance(first, str):
            return {"type": "array", "items": {"type": "string"}}
        if isinstance(first, dict):
            item_schema = _infer_json_schema(first)
            # Only require keys that have non-empty values in the sample
            required = [k for k, v in first.items() if v not in (None, "", 0, [], {})]
            if required:
                item_schema["required"] = required[:3]  # Keep required list small
            return {"type": "array", "items": item_schema}
        return {"type": "array", "items": _infer_json_schema(first)}
    if isinstance(value, dict):
        properties = {}
        for k, v in value.items():
            properties[k] = _infer_json_schema(v)
        schema: dict = {"type": "object", "properties": properties}
        return schema
    return {"type": "string"}


class SyncSchemaRequest(BaseModel):
    listing_id: str


@router.post("/sync-from-listing")
async def sync_schema_from_listing(
    body: SyncSchemaRequest,
    auth: AuthContext = require_permission('resource:edit'),
    _app_check: AuthContext = require_app_access(),
    db: AsyncSession = Depends(get_db),
):
    """Generate JSON Schema from a listing's api_response and update the default API transcription schema."""
    # Verify listing ownership
    listing = await db.scalar(
        select(Listing).where(
            Listing.id == body.listing_id,
            Listing.tenant_id == auth.tenant_id,
            Listing.user_id == auth.user_id,
        )
    )
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")

    api_response = listing.api_response
    if not api_response or not isinstance(api_response, dict):
        raise HTTPException(status_code=400, detail="Listing has no API response")

    if "rx" not in api_response:
        raise HTTPException(status_code=400, detail="API response has no 'rx' field")

    # Build schema from {input, rx} shape
    generated_schema: dict = {
        "type": "object",
        "properties": {
            "input": {
                "type": "string",
                "description": "Full transcribed text of the audio conversation",
            },
            "rx": _infer_json_schema(api_response["rx"]),
        },
        "required": ["input", "rx"],
    }
    generated_schema["properties"]["rx"]["description"] = (
        "Structured prescription and clinical data extracted from the conversation"
    )

    # Find and update the default API transcription schema
    result = await db.execute(
        select(Schema).where(
            Schema.app_id == "voice-rx",
            Schema.prompt_type == "transcription",
            Schema.source_type == "api",
            Schema.is_default == True,
        )
    )
    schema_row = result.scalar_one_or_none()

    if not schema_row:
        raise HTTPException(
            status_code=404,
            detail="No default API transcription schema found — run seed defaults first",
        )

    schema_row.schema_data = generated_schema
    await db.commit()
    await db.refresh(schema_row)

    field_count = len(generated_schema["properties"].get("rx", {}).get("properties", {}))
    logger.info("Synced API transcription schema from listing %s (%d rx fields)", body.listing_id, field_count)

    return {
        "synced": True,
        "schema_id": schema_row.id,
        "field_count": field_count,
        "schema_data": generated_schema,
    }

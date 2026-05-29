"""Listings API routes."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import AuthContext, get_auth_context
from app.auth.permissions import require_permission, require_app_access
from app.database import get_db
from app.models.evaluation_dataset import EvaluationDataset
from app.models.application_uploaded_file import ApplicationUploadedFile
from app.openapi_examples import err, ok
from app.schemas.listing import ListingCreate, ListingUpdate, ListingResponse

router = APIRouter(prefix="/api/listings", tags=["listings"])

_LISTING_EXAMPLE = {
    "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
    "appId": "support-assistant",
    "title": "Call with Jane Cooper — 2026-05-20",
    "status": "ready",
    "sourceType": "upload",
    "audioFile": {"id": "1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d", "originalName": "call-0420.mp3"},
    "transcriptFile": None,
    "structuredJsonFile": None,
    "transcript": None,
    "apiResponse": None,
    "structuredOutputReferences": [],
    "structuredOutputs": [],
    "createdAt": "2026-05-20T09:15:00Z",
    "updatedAt": "2026-05-20T09:15:00Z",
    "tenantId": "3a2e1b0c-9d8e-7f6a-5b4c-3d2e1f0a9b8c",
    "userId": "9b1f2c3d-4e5a-6b7c-8d9e-0f1a2b3c4d5e",
}


@router.get(
    "",
    response_model=list[ListingResponse],
    summary="List listings",
    description=(
        "Return every listing for an app, most recently updated first. Use it to populate "
        "a picker or dashboard of the conversations and records available to evaluate. "
        "Results are always scoped to your tenant, app, and user.\n\n"
        "**Authentication:** Bearer token with access to the requested app."
    ),
    responses={200: ok("Listings for the app, newest first.", [_LISTING_EXAMPLE])},
)
async def list_listings(
    app_id: str = Query(..., description="The app whose listings to return."),
    auth: AuthContext = require_app_access(),
    db: AsyncSession = Depends(get_db),
):
    """List all listings for an app, sorted by updated_at DESC."""
    result = await db.execute(
        select(EvaluationDataset)
        .where(
            EvaluationDataset.tenant_id == auth.tenant_id,
            EvaluationDataset.user_id == auth.user_id,
            EvaluationDataset.app_id == app_id,
        )
        .order_by(desc(EvaluationDataset.updated_at))
    )
    return result.scalars().all()


@router.get(
    "/search",
    response_model=list[ListingResponse],
    summary="Search listings by title",
    description=(
        "Filter an app's listings by a case-insensitive substring match on the title. "
        "An empty query returns everything (same as listing). Useful for type-ahead and "
        "search boxes.\n\n"
        "**Authentication:** Bearer token with access to the requested app."
    ),
    responses={200: ok("Matching listings, newest first.", [_LISTING_EXAMPLE])},
)
async def search_listings(
    app_id: str = Query(..., description="The app to search within."),
    q: str = Query("", description="Case-insensitive substring matched against the listing title."),
    auth: AuthContext = require_app_access(),
    db: AsyncSession = Depends(get_db),
):
    """Search listings by title."""
    result = await db.execute(
        select(EvaluationDataset)
        .where(
            EvaluationDataset.tenant_id == auth.tenant_id,
            EvaluationDataset.user_id == auth.user_id,
            EvaluationDataset.app_id == app_id,
        )
        .where(EvaluationDataset.title.ilike(f"%{q}%"))
        .order_by(desc(EvaluationDataset.updated_at))
    )
    return result.scalars().all()


@router.get(
    "/{listing_id}",
    response_model=ListingResponse,
    summary="Get a listing",
    description=(
        "Fetch a single listing by id, including its source data references (audio, "
        "transcript, structured output).\n\n"
        "**Authentication:** Bearer token with access to the requested app."
    ),
    responses={
        200: ok("The listing.", _LISTING_EXAMPLE),
        404: err("No listing with that id exists for your tenant, app, and user.", "Listing not found"),
    },
)
async def get_listing(
    listing_id: UUID,
    app_id: str = Query(..., description="The app the listing belongs to."),
    auth: AuthContext = require_app_access(),
    db: AsyncSession = Depends(get_db),
):
    """Get a single listing by ID."""
    result = await db.execute(
        select(EvaluationDataset).where(
            EvaluationDataset.id == listing_id,
            EvaluationDataset.tenant_id == auth.tenant_id,
            EvaluationDataset.user_id == auth.user_id,
            EvaluationDataset.app_id == app_id,
        )
    )
    listing = result.scalar_one_or_none()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    return listing


@router.post(
    "",
    response_model=ListingResponse,
    status_code=201,
    summary="Create a listing",
    description=(
        "Register a new listing — the input record an evaluation runs against. Set "
        "`sourceType` to declare where its data comes from: `upload` (you attach uploaded "
        "audio/transcript files) or `api` (you supply a captured API response). The type is "
        "fixed once chosen, so pick the flow up front.\n\n"
        "**Authentication:** Bearer token with `listing:manage` and access to the app."
    ),
    responses={
        201: ok("The created listing.", _LISTING_EXAMPLE),
        403: err("You lack `listing:manage` or access to this app.", "Forbidden"),
    },
)
async def create_listing(
    body: ListingCreate,
    auth: AuthContext = require_permission('listing:manage'),
    _app_check: AuthContext = require_app_access(),
    db: AsyncSession = Depends(get_db),
):
    """Create a new listing."""
    listing = EvaluationDataset(
        **body.model_dump(),
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
    )
    db.add(listing)
    await db.commit()
    await db.refresh(listing)
    return listing


@router.put(
    "/{listing_id}",
    response_model=ListingResponse,
    summary="Update a listing",
    description=(
        "Partially update a listing — only the fields you send are changed. Note two "
        "guards: `sourceType` cannot change once it is set (create a new listing for a "
        "different flow), and you cannot attach an API response to an upload-flow listing.\n\n"
        "**Authentication:** Bearer token with `listing:manage` and access to the app."
    ),
    responses={
        200: ok("The updated listing.", _LISTING_EXAMPLE),
        400: err("Attempted to change a fixed `sourceType`, or mix incompatible source data.", "Cannot change sourceType"),
        404: err("No such listing for your tenant and user.", "Listing not found"),
    },
)
async def update_listing(
    listing_id: UUID,
    body: ListingUpdate,
    auth: AuthContext = require_permission('listing:manage'),
    _app_check: AuthContext = require_app_access(),
    db: AsyncSession = Depends(get_db),
):
    """Update a listing. Only provided fields are updated."""
    result = await db.execute(
        select(EvaluationDataset).where(
            EvaluationDataset.id == listing_id,
            EvaluationDataset.tenant_id == auth.tenant_id,
            EvaluationDataset.user_id == auth.user_id,
        )
    )
    listing = result.scalar_one_or_none()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")

    # ── sourceType immutability ──
    if body.source_type is not None and listing.source_type != "pending":
        if body.source_type != listing.source_type:
            raise HTTPException(
                400,
                f"Cannot change sourceType from '{listing.source_type}' to '{body.source_type}'. "
                f"Create a new listing for a different flow."
            )

    # ── Prevent cross-flow data mixing ──
    if listing.source_type == "upload" and body.api_response is not None:
        raise HTTPException(400, "Cannot add API response to an upload-flow listing.")

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(listing, key, value)

    await db.commit()
    await db.refresh(listing)
    return listing


@router.delete(
    "/{listing_id}",
    summary="Delete a listing",
    description=(
        "Permanently delete a listing. This **cascades**: every evaluation run derived "
        "from it (and their detail rows) is removed, and any uploaded audio file it owns "
        "is deleted from storage. Not reversible.\n\n"
        "**Authentication:** Bearer token with `listing:manage` and access to the app."
    ),
    responses={
        200: ok("The listing and its dependent rows were deleted.", {"deleted": True, "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7"}),
        404: err("No such listing for your tenant and user.", "Listing not found"),
    },
)
async def delete_listing(
    listing_id: UUID,
    app_id: str = Query(..., description="The app the listing belongs to."),
    auth: AuthContext = require_permission('listing:manage'),
    _app_check: AuthContext = require_app_access(),
    db: AsyncSession = Depends(get_db),
):
    """Delete a listing. ORM cascade deletes evaluation_runs → evaluation_run_api_call_logs/threads/adversarial.
    Manual cleanup for file storage only.
    """
    result = await db.execute(
        select(EvaluationDataset).where(
            EvaluationDataset.id == listing_id,
            EvaluationDataset.tenant_id == auth.tenant_id,
            EvaluationDataset.user_id == auth.user_id,
            EvaluationDataset.app_id == app_id,
        )
    )
    listing = result.scalar_one_or_none()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")

    # Manual: delete associated file from storage
    if listing.audio_file and listing.audio_file.get("id"):
        file_result = await db.execute(
            select(ApplicationUploadedFile).where(ApplicationUploadedFile.id == UUID(listing.audio_file["id"]))
        )
        file_rec = file_result.scalar_one_or_none()
        if file_rec:
            from app.services.file_storage import file_storage
            await file_storage.delete(file_rec.storage_path)
            await db.delete(file_rec)

    # ORM cascade handles: evaluation_runs → evaluation_run_thread_results, evaluation_run_adversarial_results, evaluation_run_api_call_logs
    await db.delete(listing)
    await db.commit()
    return {"deleted": True, "id": str(listing_id)}

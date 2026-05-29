"""Cohort dataset routes (auth-required).

Phase 12 — REST surface for the Phase-12 cohort dataset CRUD + import service.
All routes are tenant-scoped via ``Depends(get_auth_context)`` and (where the
app_id is known) app-gated via ``ensure_registered_app_access``.

Service-layer exceptions from ``services.orchestration.api.datasets`` are
mapped here to stable client-facing HTTP errors:

- ``DatasetNotFound``  -> 404 ("dataset not found" / "dataset version not found")
- ``DatasetConflict``  -> 409 (str(exc))
- ``DatasetInUse``     -> 409 (workflow names listed in detail)
- ``DatasetImportError`` / ``FormatNotSupportedError`` -> 400 (str(exc))

Tenant-mismatch returns 404, never 403, to avoid leaking row existence across
tenants.
"""
from __future__ import annotations

import uuid
from typing import Literal, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthContext, get_auth_context
from app.auth.app_scope import ensure_registered_app_access
from app.auth.permissions import require_permission
from app.database import get_db
from app.models.orchestration import CohortDataset
from app.openapi_examples import err
from app.services.access_control import can_access
from app.schemas.orchestration_dataset import (
    DatasetCreate,
    DatasetDetailResponse,
    DatasetFormatResponse,
    DatasetResponse,
    DatasetUpdate,
    DatasetVersionResponse,
)
from app.services.orchestration.api import datasets as dataset_service
from app.services.orchestration.datasets.dataset_validator import DatasetImportError
from app.services.orchestration.datasets import format_registry
from app.services.orchestration.datasets.format_registry import (
    FormatNotSupportedError,
)


router = APIRouter(prefix="/api/orchestration/datasets", tags=["orchestration"])


# ─── helpers ────────────────────────────────────────────────────────────────


async def _load_and_gate_dataset(
    db: AsyncSession,
    auth: AuthContext,
    dataset_id: uuid.UUID,
    *,
    action: Literal["read", "edit"] = "read",
) -> CohortDataset:
    row = await db.scalar(
        select(CohortDataset).where(
            CohortDataset.id == dataset_id,
            CohortDataset.tenant_id == auth.tenant_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    await ensure_registered_app_access(db, auth, row.app_id)
    if not can_access(auth, row, action):
        if action == "read":
            raise HTTPException(status_code=404, detail="dataset not found")
        raise HTTPException(status_code=403, detail="dataset is read-only")
    return row


def _format_in_use_detail(exc: dataset_service.DatasetInUse) -> str:
    names = sorted(exc.workflow_names)
    return f"dataset version is in use by workflow(s): {', '.join(names)}"


# ─── dataset routes ─────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=DatasetResponse,
    status_code=201,
    summary="Create a dataset",
    description=(
        "Create an empty dataset — a named container that a workflow source can draw "
        "contacts from. After creating it, import one or more **versions** (uploaded "
        "files) and publish the version you want workflows to use.\n\n"
        "**Authentication:** Bearer token with `orchestration:manage` and access to the app."
    ),
    responses={409: err("A dataset with this name already exists for the app.", "Dataset name already in use")},
)
async def create_dataset_route(
    body: DatasetCreate,
    auth: AuthContext = require_permission('orchestration:manage'),
    db: AsyncSession = Depends(get_db),
):
    await ensure_registered_app_access(db, auth, body.app_id)
    try:
        return await dataset_service.create_dataset(
            db,
            tenant_id=auth.tenant_id,
            app_id=body.app_id,
            name=body.name,
            description=body.description,
            created_by=auth.user_id,
            visibility=body.visibility,
        )
    except dataset_service.DatasetConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get(
    "",
    response_model=list[DatasetResponse],
    summary="List datasets",
    description=(
        "List the datasets for an app that you can see, optionally filtered by sharing "
        "state.\n\n"
        "**Authentication:** Bearer token with access to the app."
    ),
)
async def list_datasets_route(
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
    app_id: str = Query(..., alias="appId", description="The app whose datasets to list."),
    visibility: Literal["all", "private", "shared"] = Query("all", description="Filter by sharing state."),
):
    await ensure_registered_app_access(db, auth, app_id)
    return await dataset_service.list_datasets(
        db,
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        app_id=app_id,
        visibility=visibility,
    )


@router.get(
    "/formats",
    response_model=list[DatasetFormatResponse],
    summary="List supported import formats",
    description=(
        "List the file formats accepted when importing a dataset version — extensions, "
        "MIME types, upload size limit, and whether client-side preview is supported. Use "
        "it to drive the upload UI's file picker and validation.\n\n"
        "**Authentication:** Bearer token."
    ),
)
async def list_formats_route(
    auth: AuthContext = Depends(get_auth_context),
):
    _ = auth
    return [
        DatasetFormatResponse(
            source_type=h.source_type,
            extensions=list(h.extensions),
            mime_types=list(h.mime_types),
            label=h.label,
            max_upload_bytes=h.max_upload_bytes,
            supports_client_preview=h.supports_client_preview,
        )
        for h in format_registry.all_handlers()
    ]


@router.get(
    "/{dataset_id}",
    response_model=DatasetDetailResponse,
    summary="Get a dataset",
    description=(
        "Fetch a dataset with its version list and which version is published. Returns 404 "
        "for a dataset you can't read.\n\n"
        "**Authentication:** Bearer token."
    ),
    responses={404: err("No such dataset readable by you.", "dataset not found")},
)
async def get_dataset_route(
    dataset_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    await _load_and_gate_dataset(db, auth, dataset_id)
    return await dataset_service.get_dataset(
        db, tenant_id=auth.tenant_id, dataset_id=dataset_id,
    )


@router.patch(
    "/{dataset_id}",
    response_model=DatasetDetailResponse,
    summary="Update a dataset",
    description=(
        "Rename a dataset or change its description/visibility. Does not touch its "
        "versions or imported rows. Shared datasets you don't own are read-only (403).\n\n"
        "**Authentication:** Bearer token with `orchestration:manage`."
    ),
    responses={
        403: err("The dataset is shared and read-only for you.", "dataset is read-only"),
        404: err("No such dataset.", "dataset not found"),
        409: err("Name conflicts with another dataset.", "Dataset name already in use"),
    },
)
async def update_dataset_route(
    dataset_id: uuid.UUID,
    body: DatasetUpdate,
    auth: AuthContext = require_permission('orchestration:manage'),
    db: AsyncSession = Depends(get_db),
):
    await _load_and_gate_dataset(db, auth, dataset_id, action="edit")
    try:
        return await dataset_service.update_dataset(
            db,
            tenant_id=auth.tenant_id,
            dataset_id=dataset_id,
            name=body.name,
            description=body.description,
            visibility=body.visibility,
        )
    except dataset_service.DatasetConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.delete(
    "/{dataset_id}",
    status_code=204,
    summary="Delete a dataset",
    description=(
        "Delete a dataset and all its versions. Blocked with 409 if any version is still "
        "referenced by a workflow (the response lists which). Returns 204 on success.\n\n"
        "**Authentication:** Bearer token with `orchestration:manage`."
    ),
    responses={
        204: {"description": "Deleted; no content."},
        404: err("No such dataset.", "dataset not found"),
        409: err("A version is still used by one or more workflows.", "dataset version is in use by workflow(s): Welcome flow"),
    },
)
async def delete_dataset_route(
    dataset_id: uuid.UUID,
    auth: AuthContext = require_permission('orchestration:manage'),
    db: AsyncSession = Depends(get_db),
):
    await _load_and_gate_dataset(db, auth, dataset_id, action="edit")
    try:
        await dataset_service.delete_dataset(
            db, tenant_id=auth.tenant_id, dataset_id=dataset_id,
        )
    except dataset_service.DatasetNotFound:
        raise HTTPException(status_code=404, detail="dataset not found")
    except dataset_service.DatasetInUse as exc:
        raise HTTPException(status_code=409, detail=_format_in_use_detail(exc))
    return Response(status_code=204)


# ─── version routes ─────────────────────────────────────────────────────────


@router.post(
    "/{dataset_id}/versions",
    response_model=DatasetVersionResponse,
    status_code=201,
    summary="Import a dataset version",
    description=(
        "Upload a file (`multipart/form-data`) to create a new, unpublished version of the "
        "dataset. You declare how each row's identity is derived (`idStrategy` + optional "
        "`idColumn`) and which column carries the contact's communication key (phone/email "
        "via `communicationColumn`). The format is detected from the file; rows are parsed "
        "and validated before the version is stored. Publish it separately to make it "
        "usable by workflows.\n\n"
        "**Authentication:** Bearer token with `orchestration:manage`."
    ),
    responses={
        400: err("Unsupported format or the file failed validation.", "Unsupported file format"),
        413: err("The upload exceeds the size limit.", "upload exceeds 50MB limit"),
        404: err("No such dataset.", "dataset not found"),
    },
)
async def import_version_route(
    dataset_id: uuid.UUID,
    file: UploadFile = File(..., description="The data file to import (CSV or other supported format)."),
    id_strategy: str = Form(..., description="How each row's stable id is derived (e.g. from a column or generated)."),
    id_column: Optional[str] = Form(None, description="Column to use as the id when `idStrategy` requires one."),
    communication_column: str = Form(..., description="Column holding the contact's phone/email (the communication key)."),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = require_permission('orchestration:manage'),
):
    await _load_and_gate_dataset(db, auth, dataset_id, action="edit")

    try:
        handler = format_registry.resolve(
            filename=file.filename, content_type=file.content_type,
        )
    except FormatNotSupportedError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    declared_size = getattr(file, "size", None)
    if isinstance(declared_size, int) and declared_size > handler.max_upload_bytes:
        raise HTTPException(
            status_code=413, detail="upload exceeds 50MB limit",
        )
    raw = await file.read()
    if len(raw) > handler.max_upload_bytes:
        raise HTTPException(
            status_code=413, detail="upload exceeds 50MB limit",
        )

    try:
        imported = handler.parser(
            raw, id_strategy=id_strategy, id_column=id_column,
        )
    except DatasetImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        return await dataset_service.import_version(
            db,
            tenant_id=auth.tenant_id,
            dataset_id=dataset_id,
            imported=imported,
            source_type=handler.source_type,
            source_filename=file.filename,
            source_byte_size=len(raw),
            id_strategy=id_strategy,
            id_column=id_column,
            communication_key=communication_column,
            imported_by=auth.user_id,
        )
    except DatasetImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except dataset_service.DatasetNotFound:
        raise HTTPException(status_code=404, detail="dataset not found")


@router.get(
    "/{dataset_id}/versions/{version_id}",
    response_model=DatasetVersionResponse,
    summary="Get a dataset version",
    description=(
        "Fetch a version's metadata and, optionally, a sample of its rows for preview. "
        "`sampleRows` is clamped to a server ceiling rather than rejected when too high.\n\n"
        "**Authentication:** Bearer token."
    ),
    responses={
        400: err("`sampleRows` is negative.", "sampleRows must not be negative"),
        404: err("No such dataset version.", "dataset version not found"),
    },
)
async def get_version_route(
    dataset_id: uuid.UUID,
    version_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
    sample_rows: int = Query(0, alias="sampleRows", description="How many sample rows to include for preview (clamped to a server max)."),
):
    if sample_rows < 0:
        raise HTTPException(
            status_code=400, detail="sampleRows must not be negative",
        )
    # Over-large requests are clamped to the configured ceiling in get_version,
    # not rejected — a read-only preview count should never 400 for asking high.
    await _load_and_gate_dataset(db, auth, dataset_id)
    try:
        return await dataset_service.get_version(
            db,
            tenant_id=auth.tenant_id,
            dataset_id=dataset_id,
            version_id=version_id,
            sample_rows=sample_rows,
        )
    except dataset_service.DatasetNotFound:
        raise HTTPException(status_code=404, detail="dataset version not found")


@router.delete(
    "/{dataset_id}/versions/{version_id}",
    status_code=204,
    summary="Delete a dataset version",
    description=(
        "Delete a single version of a dataset. Blocked with 409 if the version is "
        "referenced by a workflow (the response lists which). Returns 204 on success.\n\n"
        "**Authentication:** Bearer token with `orchestration:manage`."
    ),
    responses={
        204: {"description": "Deleted; no content."},
        404: err("No such dataset version.", "dataset version not found"),
        409: err("The version is still used by one or more workflows.", "dataset version is in use by workflow(s): Welcome flow"),
    },
)
async def delete_version_route(
    dataset_id: uuid.UUID,
    version_id: uuid.UUID,
    auth: AuthContext = require_permission('orchestration:manage'),
    db: AsyncSession = Depends(get_db),
):
    await _load_and_gate_dataset(db, auth, dataset_id, action="edit")
    try:
        await dataset_service.delete_version(
            db,
            tenant_id=auth.tenant_id,
            dataset_id=dataset_id,
            version_id=version_id,
        )
    except dataset_service.DatasetNotFound:
        raise HTTPException(status_code=404, detail="dataset version not found")
    except dataset_service.DatasetInUse as exc:
        raise HTTPException(status_code=409, detail=_format_in_use_detail(exc))
    return Response(status_code=204)


@router.post(
    "/{dataset_id}/versions/{version_id}/publish",
    response_model=DatasetVersionResponse,
    summary="Publish a dataset version",
    description=(
        "Mark a version as published so workflows can bind to it. A dataset has at most "
        "one published version at a time; publishing is idempotent and re-publishing an "
        "already-published version returns 409.\n\n"
        "**Authentication:** Bearer token with `orchestration:manage`."
    ),
    responses={
        404: err("No such dataset version.", "dataset version not found"),
        409: err("The version is already published.", "version is already published"),
    },
)
async def publish_version_route(
    dataset_id: uuid.UUID,
    version_id: uuid.UUID,
    auth: AuthContext = require_permission('orchestration:manage'),
    db: AsyncSession = Depends(get_db),
):
    await _load_and_gate_dataset(db, auth, dataset_id, action="edit")
    try:
        return await dataset_service.publish_version(
            db,
            tenant_id=auth.tenant_id,
            dataset_id=dataset_id,
            version_id=version_id,
            published_by=auth.user_id,
        )
    except dataset_service.DatasetNotFound:
        raise HTTPException(status_code=404, detail="dataset version not found")
    except dataset_service.DatasetVersionAlreadyPublished as exc:
        raise HTTPException(status_code=409, detail=str(exc))

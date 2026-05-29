"""Saved cohort routes (auth-required).

REST surface for ``orchestration.cohort_definitions`` and
``cohort_definition_versions``. Sister to ``orchestration_datasets``: tenant
scoping via ``Depends(get_auth_context)``, app-gating via
``ensure_registered_app_access``, structured 409 on delete-in-use.
"""
from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthContext, get_auth_context
from app.auth.app_scope import ensure_registered_app_access
from app.auth.permissions import require_permission
from app.database import get_db
from app.models.orchestration import CohortDefinition
from app.openapi_examples import err
from app.services.access_control import can_access
from app.schemas.orchestration_cohort import (
    CohortCreate,
    CohortDetailResponse,
    CohortResponse,
    CohortUpdate,
    CohortVersionEditPayload,
    CohortVersionResponse,
    WorkflowBindingResponse,
)
from app.services.orchestration.api import cohorts as cohort_service


router = APIRouter(prefix="/api/orchestration/cohorts", tags=["orchestration"])


async def _load_and_gate_cohort(
    db: AsyncSession,
    auth: AuthContext,
    cohort_id: uuid.UUID,
    *,
    action: Literal["read", "edit"] = "read",
) -> CohortDefinition:
    row = await db.scalar(
        select(CohortDefinition).where(
            CohortDefinition.id == cohort_id,
            CohortDefinition.tenant_id == auth.tenant_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="cohort not found")
    await ensure_registered_app_access(db, auth, row.app_id)
    if not can_access(auth, row, action):
        if action == "read":
            raise HTTPException(status_code=404, detail="cohort not found")
        raise HTTPException(status_code=403, detail="cohort is read-only")
    return row


def _format_in_use_detail(exc: cohort_service.CohortInUse) -> list[dict[str, str]]:
    # Returned as a list of FieldErrorItem-shaped rows so
    # ``decodeApiErrorBody`` on the FE resolves to ``kind: 'fieldErrors'``
    # and the cohort detail panel can render one row per blocking workflow
    # with the workflow id available for a deep-link.
    pairs = list(zip(exc.workflow_ids, exc.workflow_names))
    return [
        {
            "node_id": str(wid),
            "field": "workflow",
            "message": f"Used by workflow “{name}”",
        }
        for wid, name in pairs
    ] or [{"message": str(exc), "field": "cohort"}]


# ─── cohort routes ──────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=CohortDetailResponse,
    status_code=201,
    summary="Create a cohort",
    description=(
        "Create a saved cohort — a reusable, versioned audience definition a workflow "
        "source can draw from. You supply a slug, name, and an initial version (the "
        "audience rules); the cohort is created with that version as a draft.\n\n"
        "**Authentication:** Bearer token with `orchestration:manage` and access to the app."
    ),
    responses={409: err("A cohort with this slug already exists for the app.", "Cohort slug already in use")},
)
async def create_cohort_route(
    body: CohortCreate,
    auth: AuthContext = require_permission("orchestration:manage"),
    db: AsyncSession = Depends(get_db),
):
    await ensure_registered_app_access(db, auth, body.app_id)
    try:
        return await cohort_service.create_cohort(
            db,
            tenant_id=auth.tenant_id,
            app_id=body.app_id,
            slug=body.slug,
            name=body.name,
            description=body.description,
            created_by=auth.user_id,
            visibility=body.visibility,
            initial_version=body.initial_version.model_dump(),
        )
    except cohort_service.CohortConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get(
    "",
    response_model=list[CohortResponse],
    summary="List cohorts",
    description=(
        "List the saved cohorts for an app that you can see.\n\n"
        "**Authentication:** Bearer token with access to the app."
    ),
)
async def list_cohorts_route(
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
    app_id: str = Query(..., alias="appId", description="The app whose cohorts to list."),
):
    await ensure_registered_app_access(db, auth, app_id)
    return await cohort_service.list_cohorts(
        db,
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        app_id=app_id,
    )


@router.get(
    "/{cohort_id}",
    response_model=CohortDetailResponse,
    summary="Get a cohort",
    description=(
        "Fetch a cohort with its versions and which one is published. Returns 404 for a "
        "cohort you can't read.\n\n"
        "**Authentication:** Bearer token."
    ),
    responses={404: err("No such cohort readable by you.", "cohort not found")},
)
async def get_cohort_route(
    cohort_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    await _load_and_gate_cohort(db, auth, cohort_id)
    return await cohort_service.get_cohort(
        db, tenant_id=auth.tenant_id, cohort_id=cohort_id,
    )


@router.patch(
    "/{cohort_id}",
    response_model=CohortDetailResponse,
    summary="Update a cohort",
    description=(
        "Update a cohort's name, description, visibility, or active flag. Audience rules "
        "live on versions, not here. Shared cohorts you don't own are read-only (403).\n\n"
        "**Authentication:** Bearer token with `orchestration:manage`."
    ),
    responses={
        403: err("The cohort is shared and read-only for you.", "cohort is read-only"),
        404: err("No such cohort.", "cohort not found"),
    },
)
async def update_cohort_route(
    cohort_id: uuid.UUID,
    body: CohortUpdate,
    auth: AuthContext = require_permission("orchestration:manage"),
    db: AsyncSession = Depends(get_db),
):
    await _load_and_gate_cohort(db, auth, cohort_id, action="edit")
    return await cohort_service.update_cohort(
        db,
        tenant_id=auth.tenant_id,
        cohort_id=cohort_id,
        name=body.name,
        description=body.description,
        visibility=body.visibility,
        active=body.active,
    )


@router.delete(
    "/{cohort_id}",
    status_code=204,
    summary="Delete a cohort",
    description=(
        "Delete a cohort and its versions. Blocked with 409 if any workflow still binds to "
        "it; the error body lists the blocking workflows (with ids) for deep-linking. "
        "Returns 204 on success.\n\n"
        "**Authentication:** Bearer token with `orchestration:manage`."
    ),
    responses={
        204: {"description": "Deleted; no content."},
        404: err("No such cohort.", "cohort not found"),
        409: err("The cohort is still bound by one or more workflows.", "Used by workflow “Welcome flow”"),
    },
)
async def delete_cohort_route(
    cohort_id: uuid.UUID,
    auth: AuthContext = require_permission("orchestration:manage"),
    db: AsyncSession = Depends(get_db),
):
    await _load_and_gate_cohort(db, auth, cohort_id, action="edit")
    try:
        await cohort_service.delete_cohort(
            db, tenant_id=auth.tenant_id, cohort_id=cohort_id,
        )
    except cohort_service.CohortNotFound:
        raise HTTPException(status_code=404, detail="cohort not found")
    except cohort_service.CohortInUse as exc:
        raise HTTPException(status_code=409, detail=_format_in_use_detail(exc))
    return Response(status_code=204)


# ─── version routes ─────────────────────────────────────────────────────────


@router.post(
    "/{cohort_id}/versions",
    response_model=CohortVersionResponse,
    status_code=201,
    summary="Create a draft cohort version",
    description=(
        "Add a new **draft** version to a cohort, carrying the audience rules. Drafts are "
        "editable; publish one to make it the active definition workflows use.\n\n"
        "**Authentication:** Bearer token with `orchestration:manage`."
    ),
    responses={404: err("No such cohort.", "cohort not found")},
)
async def create_draft_version_route(
    cohort_id: uuid.UUID,
    body: CohortVersionEditPayload,
    auth: AuthContext = require_permission("orchestration:manage"),
    db: AsyncSession = Depends(get_db),
):
    await _load_and_gate_cohort(db, auth, cohort_id, action="edit")
    return await cohort_service.create_draft_version(
        db,
        tenant_id=auth.tenant_id,
        cohort_id=cohort_id,
        payload=body.model_dump(),
    )


@router.patch(
    "/{cohort_id}/versions/{version_id}",
    response_model=CohortVersionResponse,
    summary="Edit a draft cohort version",
    description=(
        "Update the audience rules of a **draft** version. Published versions are "
        "immutable — editing one returns 409; create a new draft instead.\n\n"
        "**Authentication:** Bearer token with `orchestration:manage`."
    ),
    responses={
        404: err("No such cohort version.", "cohort version not found"),
        409: err("The version is published and can no longer be edited.", "version is not editable"),
    },
)
async def edit_draft_version_route(
    cohort_id: uuid.UUID,
    version_id: uuid.UUID,
    body: CohortVersionEditPayload,
    auth: AuthContext = require_permission("orchestration:manage"),
    db: AsyncSession = Depends(get_db),
):
    await _load_and_gate_cohort(db, auth, cohort_id, action="edit")
    try:
        return await cohort_service.edit_draft_version(
            db,
            tenant_id=auth.tenant_id,
            cohort_id=cohort_id,
            version_id=version_id,
            payload=body.model_dump(),
        )
    except cohort_service.CohortNotFound:
        raise HTTPException(status_code=404, detail="cohort version not found")
    except cohort_service.CohortVersionNotEditable as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post(
    "/{cohort_id}/versions/{version_id}/publish",
    response_model=CohortVersionResponse,
    summary="Publish a cohort version",
    description=(
        "Publish a draft version so workflows bind to it as the cohort's active "
        "definition. Re-publishing an already-published version returns 409.\n\n"
        "**Authentication:** Bearer token with `orchestration:manage`."
    ),
    responses={
        404: err("No such cohort version.", "cohort version not found"),
        409: err("The version is already published.", "version is already published"),
    },
)
async def publish_version_route(
    cohort_id: uuid.UUID,
    version_id: uuid.UUID,
    auth: AuthContext = require_permission("orchestration:manage"),
    db: AsyncSession = Depends(get_db),
):
    await _load_and_gate_cohort(db, auth, cohort_id, action="edit")
    try:
        return await cohort_service.publish_version(
            db,
            tenant_id=auth.tenant_id,
            cohort_id=cohort_id,
            version_id=version_id,
            published_by=auth.user_id,
        )
    except cohort_service.CohortNotFound:
        raise HTTPException(status_code=404, detail="cohort version not found")
    except cohort_service.CohortVersionAlreadyPublished as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get(
    "/{cohort_id}/used-by",
    response_model=list[WorkflowBindingResponse],
    summary="List workflows using a cohort",
    description=(
        "List the workflows currently bound to this cohort. Use it to see the impact "
        "before editing or deleting the cohort.\n\n"
        "**Authentication:** Bearer token."
    ),
    responses={404: err("No such cohort.", "cohort not found")},
)
async def list_used_by_route(
    cohort_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    await _load_and_gate_cohort(db, auth, cohort_id)
    return await cohort_service.list_used_by(
        db, tenant_id=auth.tenant_id, cohort_id=cohort_id,
    )

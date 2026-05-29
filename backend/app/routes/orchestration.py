"""Orchestration API routes (auth-required).

All routes require a Bearer token via ``Depends(get_auth_context)``. Public
webhooks live in ``orchestration_webhooks.py`` (Phase 4).

Routes that accept ``app_id`` also enforce registered-app access via
``ensure_registered_app_access``. Run-scoped routes load the run first and
then app-gate using ``run.app_id``.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthContext, get_auth_context
from app.auth.app_scope import ensure_registered_app_access
from app.auth.permissions import require_permission
from app.database import get_db
from app.models.orchestration import Workflow, WorkflowRun
from app.models.user import User
from app.openapi_examples import err
from app.services.access_control import can_access
from app.schemas.orchestration import (
    ActionResponse,
    ActionTemplateResponse,
    ActionTemplateUpsertRequest,
    CancelAuditRead,
    CancelRunRequest,
    CloneSystemWorkflowRequest,
    CohortSourceResponse,
    ColumnValuesResponse,
    ConsentResponse,
    ConsentSetRequest,
    EventCatalogResponse,
    LlmExtractDryRunRequest,
    LlmExtractDryRunResponse,
    NodeTypeDescriptor,
    OverrideRequest,
    OverrideResponse,
    RecipientStateResponse,
    ResolveUpstreamVariablesRequest,
    ResolveUpstreamVariablesResponse,
    RunCreateRequest,
    RunListResponse,
    RunNodeStepResponse,
    RunOverlaySnapshotResponse,
    RunResponse,
    TerminationReceipt,
    TriggerCreateRequest,
    TriggerUpdateRequest,
    TriggerResponse,
    TriggerRotateTokenResponse,
    WorkflowActionGlobalRow,
    WorkflowActionListResponse,
    WorkflowCreateRequest,
    WorkflowDefinitionEdge,
    WorkflowDefinitionNode,
    WorkflowDraftSaveRequest,
    WorkflowResponse,
    WorkflowUpdateRequest,
    WorkflowValidateRequest,
    WorkflowValidateResponse,
    WorkflowVersionResponse,
)
from app.services.orchestration.api import (
    clone as clone_service,
    consent as consent_service,
    runs as run_service,
    templates as tmpl_service,
    triggers as trig_service,
    versions as ver_service,
    workflows as wf_service,
)
from app.services.orchestration.api.node_types import list_node_types
from app.services.orchestration.api.source_catalog import fetch_column_values, list_cohort_sources
from app.services.orchestration.cancel.run_terminator import terminate_run
from app.services.orchestration.llm_extract_dry_run import run_llm_extract_dry_run
from app.services.orchestration.nodes.llm_extract import _Config as LlmExtractConfig
from app.services.orchestration.upstream_variables import (
    UpstreamSourceNotFound,
    resolve_upstream_variables,
)
from app.services.orchestration.definition_validator import (
    DispatchRequiredFieldsError,
)


router = APIRouter(prefix="/api/orchestration", tags=["orchestration"])


# ─── Workflows ───────────────────────────────────────────────────────────────


@router.post(
    "/workflows/validate",
    response_model=WorkflowValidateResponse,
    summary="Validate a workflow definition",
    description=(
        "Validate a workflow graph without saving anything — checks node types, edges, "
        "predicates, and config shapes. Powers JSON-import preview and authored-payload "
        "checks. Unknown `connection_id` references come back as **warnings**, not errors, "
        "so a cross-tenant import can land as a draft you rebind in the builder.\n\n"
        "**Authentication:** Bearer token with `orchestration:manage`."
    ),
)
async def validate_workflow_payload(
    body: WorkflowValidateRequest,
    auth: AuthContext = require_permission('orchestration:manage'),
    db: AsyncSession = Depends(get_db),
):
    """Pure validate — no DB writes. Powers JSON import preview and Claude-
    authored payload checks. Unknown ``connection_id`` refs return as
    warnings (not errors) so a cross-tenant import lands as a draft the
    user rebinds in the builder; runtime contract still enforces the
    binding at publish."""
    await ensure_registered_app_access(db, auth, body.app_id)
    result = await ver_service.validate_workflow_payload(
        db,
        tenant_id=auth.tenant_id,
        app_id=body.app_id,
        workflow_type=body.workflow_type,
        definition=body.definition.model_dump(),
    )
    return WorkflowValidateResponse.model_validate(result)


@router.post(
    "/workflows",
    response_model=WorkflowResponse,
    status_code=201,
    summary="Create a workflow",
    description=(
        "Create an empty workflow shell (name, slug, type). The graph itself is added "
        "afterward by saving a draft, then published to become runnable.\n\n"
        "**Authentication:** Bearer token with `orchestration:manage` and access to the app."
    ),
    responses={409: err("A workflow with this slug already exists for the app.", "Workflow slug already in use")},
)
async def create_workflow(
    body: WorkflowCreateRequest,
    auth: AuthContext = require_permission('orchestration:manage'),
    db: AsyncSession = Depends(get_db),
):
    await ensure_registered_app_access(db, auth, body.app_id)
    try:
        wf = await wf_service.create_workflow(
            db, tenant_id=auth.tenant_id, app_id=body.app_id,
            workflow_type=body.workflow_type, slug=body.slug,
            name=body.name, description=body.description,
            created_by=auth.user_id, visibility=body.visibility,
        )
    except wf_service.WorkflowConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return wf


async def _load_and_gate_workflow(
    db: AsyncSession,
    auth: AuthContext,
    workflow_id: uuid.UUID,
    *,
    require_active: bool = True,
    action: Literal["read", "edit"] = "read",
):
    """Load a workflow visible to the caller and apply row-level gating."""
    stmt = select(Workflow).where(Workflow.id == workflow_id)
    if require_active:
        stmt = stmt.where(Workflow.active.is_(True))
    wf = (await db.execute(stmt)).scalar_one_or_none()
    if wf is None:
        raise HTTPException(status_code=404, detail="workflow not found")
    if wf.tenant_id not in {auth.tenant_id}:
        from app.constants import SYSTEM_TENANT_ID

        if wf.tenant_id != SYSTEM_TENANT_ID:
            raise HTTPException(status_code=404, detail="workflow not found")
    await ensure_registered_app_access(db, auth, wf.app_id)
    if not can_access(auth, wf, action):
        if action == "read":
            raise HTTPException(status_code=404, detail="workflow not found")
        raise HTTPException(status_code=403, detail="workflow is read-only")
    return wf


_NO_RUN: tuple[Optional[uuid.UUID], Optional[datetime], Optional[str]] = (
    None, None, None,
)


_NO_CREATOR: tuple[Optional[str], Optional[str]] = (None, None)


def _to_workflow_response(
    wf: Workflow,
    last_run: tuple[Optional[uuid.UUID], Optional[datetime], Optional[str]] = _NO_RUN,
    creator: tuple[Optional[str], Optional[str]] = _NO_CREATOR,
) -> WorkflowResponse:
    """Project a Workflow ORM row + its latest run summary + creator
    profile into the API response. Centralised so list and single-get
    share the identical field-population path — keeps ``last_run_*`` /
    ``created_by_name`` / ``created_by_email`` consistent."""
    resp = WorkflowResponse.model_validate(wf)
    resp.last_run_id = last_run[0]
    resp.last_run_at = last_run[1]
    resp.last_run_status = last_run[2]
    resp.created_by_name = creator[0]
    resp.created_by_email = creator[1]
    return resp


async def _resolve_creators(
    db: AsyncSession,
    *,
    workflows: list[Workflow],
) -> dict[uuid.UUID, tuple[Optional[str], Optional[str]]]:
    """Bulk-resolve `(created_by) -> (display_name, email)` so the listing
    avoids N+1 lookups. Tenant-agnostic on purpose: a workflow's creator
    might be the system user (cross-tenant), so we look up by id alone.
    Missing rows fall through to (None, None)."""
    ids = list({w.created_by for w in workflows if w.created_by})
    if not ids:
        return {}
    rows = (
        await db.execute(
            select(User.id, User.display_name, User.email).where(User.id.in_(ids))
        )
    ).all()
    return {r.id: (r.display_name, r.email) for r in rows}


async def _attach_last_runs(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    workflows: list[Workflow],
) -> list[WorkflowResponse]:
    last_runs = await run_service.latest_runs_by_workflow_ids(
        db, tenant_id=tenant_id, workflow_ids=[w.id for w in workflows],
    )
    creators = await _resolve_creators(db, workflows=workflows)
    return [
        _to_workflow_response(
            w,
            last_runs.get(w.id, _NO_RUN),
            creators.get(w.created_by, _NO_CREATOR),
        )
        for w in workflows
    ]


@router.get(
    "/workflows",
    response_model=list[WorkflowResponse],
    summary="List workflows",
    description=(
        "List the workflows you can see, each annotated with its latest run summary and "
        "creator. Filter by app, type, and sharing state. With no `appId`, results are "
        "limited to the apps you can access.\n\n"
        "**Authentication:** Bearer token."
    ),
)
async def list_workflows(
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
    app_id: Optional[str] = Query(None, alias="appId", description="Restrict to one app."),
    workflow_type: Optional[str] = Query(None, alias="workflowType", description="Filter by workflow type."),
    visibility: Literal["all", "private", "shared"] = Query("all", description="Filter by sharing state."),
):
    if app_id is not None:
        await ensure_registered_app_access(db, auth, app_id)
        wfs = await wf_service.list_workflows(
            db,
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            app_id=app_id,
            workflow_type=workflow_type,
            visibility=visibility,
        )
    else:
        # No explicit app filter — restrict to apps the caller can reach.
        wfs = await wf_service.list_workflows(
            db,
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            workflow_type=workflow_type,
            app_ids=frozenset(auth.app_access),
            visibility=visibility,
        )
    return await _attach_last_runs(db, tenant_id=auth.tenant_id, workflows=wfs)


@router.get(
    "/system-workflows",
    response_model=list[WorkflowResponse],
    summary="List system workflow templates",
    description=(
        "List the platform-seeded workflow templates you can clone (e.g. a default "
        "concierge or adherence flow). Templates are never run directly, so their "
        "`lastRun` fields are null; clone one into your tenant to run and edit it.\n\n"
        "**Authentication:** Bearer token."
    ),
)
async def list_system_workflows(
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
    app_id: Optional[str] = Query(None, alias="appId"),
    workflow_type: Optional[str] = Query(None, alias="workflowType"),
):
    """List cloneable system-seeded workflows visible to the caller's app scope.

    System workflows are templates — never directly run — so ``last_run_*``
    is left as ``None``. Tenant clones expose their own run history.
    """
    if app_id is not None:
        await ensure_registered_app_access(db, auth, app_id)
        wfs = await wf_service.list_system_workflows(
            db, app_id=app_id, workflow_type=workflow_type,
        )
    else:
        wfs = await wf_service.list_system_workflows(
            db, workflow_type=workflow_type, app_ids=frozenset(auth.app_access),
        )
    return [_to_workflow_response(w) for w in wfs]


@router.get(
    "/workflows/{workflow_id}",
    response_model=WorkflowResponse,
    summary="Get a workflow",
    description=(
        "Fetch one workflow (active or archived) with its latest run summary and creator. "
        "Returns 404 for a workflow you can't read.\n\n"
        "**Authentication:** Bearer token."
    ),
    responses={404: err("No such workflow readable by you.", "workflow not found")},
)
async def get_workflow(
    workflow_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    wf = await _load_and_gate_workflow(db, auth, workflow_id, require_active=False)
    last_runs = await run_service.latest_runs_by_workflow_ids(
        db, tenant_id=auth.tenant_id, workflow_ids=[wf.id],
    )
    creators = await _resolve_creators(db, workflows=[wf])
    return _to_workflow_response(
        wf,
        last_runs.get(wf.id, _NO_RUN),
        creators.get(wf.created_by, _NO_CREATOR),
    )


@router.patch(
    "/workflows/{workflow_id}",
    response_model=WorkflowResponse,
    summary="Update workflow metadata",
    description=(
        "Update a workflow's name, description, or visibility. The graph is edited via the "
        "draft endpoint, not here. Shared workflows you don't own are read-only (403).\n\n"
        "**Authentication:** Bearer token with `orchestration:manage`."
    ),
    responses={
        403: err("The workflow is shared and read-only for you.", "workflow is read-only"),
        404: err("No such workflow.", "workflow not found"),
    },
)
async def update_workflow(
    workflow_id: uuid.UUID,
    body: WorkflowUpdateRequest,
    auth: AuthContext = require_permission('orchestration:manage'),
    db: AsyncSession = Depends(get_db),
):
    await _load_and_gate_workflow(db, auth, workflow_id, action="edit")
    wf = await wf_service.update_workflow(
        db, tenant_id=auth.tenant_id, workflow_id=workflow_id,
        name=body.name, description=body.description,
        visibility=body.visibility,
    )
    if wf is None:
        raise HTTPException(status_code=404, detail="workflow not found")
    return wf


@router.delete(
    "/workflows/{workflow_id}",
    status_code=204,
    summary="Archive a workflow",
    description=(
        "Archive (soft-delete) a workflow so it no longer appears in active listings or "
        "runs. Existing run history is preserved. Returns 204.\n\n"
        "**Authentication:** Bearer token with `orchestration:manage`."
    ),
    responses={
        204: {"description": "Archived; no content."},
        404: err("No such workflow.", "workflow not found"),
    },
)
async def archive_workflow(
    workflow_id: uuid.UUID,
    auth: AuthContext = require_permission('orchestration:manage'),
    db: AsyncSession = Depends(get_db),
):
    await _load_and_gate_workflow(db, auth, workflow_id, action="edit")
    if not await wf_service.archive_workflow(db, tenant_id=auth.tenant_id, workflow_id=workflow_id):
        raise HTTPException(status_code=404, detail="workflow not found")
    return Response(status_code=204)


@router.post(
    "/workflows/clone",
    response_model=WorkflowResponse,
    status_code=201,
    summary="Clone a system workflow",
    description=(
        "Copy a platform-seeded system workflow into your tenant under a new slug and "
        "name, so you can edit and run it without affecting the shared template. This is "
        "how seeded flows are rolled out per tenant.\n\n"
        "**Authentication:** Bearer token with `orchestration:manage` and access to the target app."
    ),
    responses={
        400: err("The clone request is invalid (e.g. slug taken, bad target).", "slug already in use"),
        404: err("The source system workflow does not exist.", "source system workflow not found"),
    },
)
async def clone_system_workflow(
    body: CloneSystemWorkflowRequest,
    auth: AuthContext = require_permission('orchestration:manage'),
    db: AsyncSession = Depends(get_db),
):
    """Clone a system-owned workflow into the caller's tenant.

    Used for tenant rollout of seeded workflows ("Default MQL Concierge",
    "DM2 Adherence Watch"). Tenants edit the cloned workflow visually
    without affecting the system seed.
    """
    await ensure_registered_app_access(db, auth, body.target_app_id)
    try:
        wf = await clone_service.clone_system_workflow(
            db,
            tenant_id=auth.tenant_id,
            source_workflow_id=body.source_workflow_id,
            new_slug=body.new_slug,
            new_name=body.new_name,
            target_app_id=body.target_app_id,
            created_by=auth.user_id,
        )
    except clone_service.CloneError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if wf is None:
        raise HTTPException(
            status_code=404, detail="source system workflow not found",
        )
    return wf


# ─── Workflow versions ──────────────────────────────────────────────────────


@router.put(
    "/workflows/{workflow_id}/draft",
    response_model=WorkflowResponse,
    summary="Save the workflow draft",
    description=(
        "Save the working graph as the workflow's draft. Drafts may omit runtime-required "
        "fields, but fabricated keys, wrong types, bad edges, malformed predicates, and "
        "unknown node types are rejected with a structured error list (same shape as "
        "publish). Publish the draft separately to make it runnable.\n\n"
        "**Authentication:** Bearer token with `orchestration:manage`."
    ),
    responses={
        400: err("The draft graph is structurally invalid (see the errors array).", "Unknown node type"),
        404: err("No such workflow.", "workflow not found"),
    },
)
async def save_draft(
    workflow_id: uuid.UUID,
    body: WorkflowDraftSaveRequest,
    auth: AuthContext = require_permission('orchestration:manage'),
    db: AsyncSession = Depends(get_db),
):
    await _load_and_gate_workflow(db, auth, workflow_id, action="edit")
    try:
        wf = await ver_service.save_draft(
            db, tenant_id=auth.tenant_id, workflow_id=workflow_id,
            definition=body.definition.model_dump(),
        )
    except ver_service.DraftValidationError as exc:
        # Mirrors the publish path: structured ``errors`` go as the detail
        # array so the FE renders draft and publish failures through the
        # same ``PublishErrorPanel``. Drafts may have missing required
        # runtime fields; what's rejected here is fabricated keys, wrong
        # types, bad edges, malformed predicates, and unknown node types.
        if exc.errors:
            raise HTTPException(status_code=400, detail=exc.errors)
        raise HTTPException(status_code=400, detail=str(exc))
    if wf is None:
        raise HTTPException(status_code=404, detail="workflow not found")
    return _to_workflow_response(wf)


@router.get(
    "/workflows/{workflow_id}/versions",
    response_model=list[WorkflowVersionResponse],
    summary="List workflow versions",
    description=(
        "List a workflow's version history — the draft plus every published version, newest "
        "first.\n\n"
        "**Authentication:** Bearer token."
    ),
    responses={404: err("No such workflow.", "workflow not found")},
)
async def list_versions(
    workflow_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    await _load_and_gate_workflow(db, auth, workflow_id, require_active=False)
    return await ver_service.list_versions(
        db, tenant_id=auth.tenant_id, workflow_id=workflow_id,
    )


@router.get(
    "/workflows/{workflow_id}/versions/{version_id}",
    response_model=WorkflowVersionResponse,
    summary="Get a workflow version",
    description=(
        "Fetch one specific version of a workflow, including its full graph definition.\n\n"
        "**Authentication:** Bearer token."
    ),
    responses={404: err("No such version for this workflow.", "version not found")},
)
async def get_version(
    workflow_id: uuid.UUID,
    version_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    await _load_and_gate_workflow(db, auth, workflow_id, require_active=False)
    v = await ver_service.get_version(db, tenant_id=auth.tenant_id, version_id=version_id)
    if v is None or v.workflow_id != workflow_id:
        raise HTTPException(status_code=404, detail="version not found")
    return v


@router.post(
    "/workflows/{workflow_id}/publish",
    response_model=WorkflowVersionResponse,
    summary="Publish the workflow draft",
    description=(
        "Promote the current draft to a new published version, making the workflow "
        "runnable. Full validation runs here: missing runtime-required fields (e.g. an "
        "unbound dispatch field) return **422** with a structured error list; structural "
        "problems return **400**.\n\n"
        "**Authentication:** Bearer token with `orchestration:manage`."
    ),
    responses={
        400: err("The draft graph is structurally invalid (see the errors array).", "Invalid workflow definition"),
        422: err("Runtime-required fields are missing for one or more dispatch nodes.", "Missing required field: template"),
        404: err("No such workflow.", "workflow not found"),
    },
)
async def publish_draft(
    workflow_id: uuid.UUID,
    auth: AuthContext = require_permission('orchestration:manage'),
    db: AsyncSession = Depends(get_db),
):
    await _load_and_gate_workflow(db, auth, workflow_id, action="edit")
    try:
        v = await ver_service.publish_draft(
            db, tenant_id=auth.tenant_id, workflow_id=workflow_id,
            published_by=auth.user_id,
        )
    except DispatchRequiredFieldsError as exc:
        raise HTTPException(status_code=422, detail=exc.errors)
    except ver_service.VersionPublishError as exc:
        # Phase 14 / Phase E — when the publish failure carries a
        # structured ``errors`` list (the normal validator path), surface
        # it as the ``detail`` array so the FE renders 400 and 422 the
        # same way. Bare freeform-message failures still 400 with the
        # legacy string body.
        if exc.errors:
            raise HTTPException(status_code=400, detail=exc.errors)
        raise HTTPException(status_code=400, detail=str(exc))
    if v is None:
        raise HTTPException(status_code=404, detail="workflow not found")
    return v


# ─── Event catalog ────────────────────────────────────────────────────────────


@router.get(
    "/event-catalog",
    response_model=EventCatalogResponse,
    summary="List canonical event names",
    description=(
        "Return the canonical event names available for an event trigger, scoped to a "
        "workflow type (`crm` or `clinical`). Powers the event-trigger picker; any other "
        "type returns an empty list.\n\n"
        "**Authentication:** Bearer token."
    ),
)
async def get_event_catalog(
    workflow_type: str = Query(..., alias="workflowType"),
    auth: AuthContext = Depends(get_auth_context),
):
    """Canonical event names for the event-trigger combobox, gated by workflow_type.

    Keys are lowercase ``crm`` / ``clinical``; any other value (including
    uppercase) returns an empty list."""
    from app.services.orchestration.event_catalog import catalog_for_workflow_type

    return EventCatalogResponse(
        workflow_type=workflow_type,
        events=catalog_for_workflow_type(workflow_type),
    )


# ─── Triggers ───────────────────────────────────────────────────────────────


def _trigger_view(trig, request: Request) -> TriggerResponse:
    from app.services.orchestration.api.connections import resolve_base_url

    base_url = resolve_base_url(request.headers.get("origin"))
    return TriggerResponse(**trig_service.serialize_trigger(trig, base_url=base_url))


@router.post(
    "/workflows/{workflow_id}/triggers",
    response_model=TriggerResponse,
    status_code=201,
    summary="Create a trigger",
    description=(
        "Attach a trigger to a workflow so it fires automatically — a `schedule` trigger "
        "(cron) or an `event` trigger (inbound CRM/clinical event). Event triggers come "
        "back with a unique inbound webhook URL the external system posts to.\n\n"
        "**Authentication:** Bearer token with `orchestration:manage`."
    ),
    responses={
        400: err("Invalid trigger config (e.g. bad cron, unknown event).", "invalid cron expression"),
        404: err("No such workflow.", "workflow not found"),
    },
)
async def create_trigger(
    workflow_id: uuid.UUID,
    body: TriggerCreateRequest,
    request: Request,
    auth: AuthContext = require_permission('orchestration:manage'),
    db: AsyncSession = Depends(get_db),
):
    await _load_and_gate_workflow(db, auth, workflow_id, action="edit")
    try:
        trig = await trig_service.create_trigger(
            db, tenant_id=auth.tenant_id, workflow_id=workflow_id,
            kind=body.kind, cron_expression=body.cron_expression,
            event_name=body.event_name, vendor=body.vendor,
            params=body.params, active=body.active,
            created_by=auth.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if trig is None:
        raise HTTPException(status_code=404, detail="workflow not found")
    return _trigger_view(trig, request)


@router.get(
    "/workflows/{workflow_id}/triggers",
    response_model=list[TriggerResponse],
    summary="List a workflow's triggers",
    description=(
        "List the schedule and event triggers attached to a workflow, including each event "
        "trigger's inbound webhook URL.\n\n"
        "**Authentication:** Bearer token."
    ),
    responses={404: err("No such workflow.", "workflow not found")},
)
async def list_triggers(
    workflow_id: uuid.UUID,
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    await _load_and_gate_workflow(db, auth, workflow_id)
    rows = await trig_service.list_triggers(
        db, tenant_id=auth.tenant_id, workflow_id=workflow_id,
    )
    return [_trigger_view(t, request) for t in rows]


@router.patch(
    "/triggers/{trigger_id}",
    response_model=TriggerResponse,
    summary="Update a trigger",
    description=(
        "Update a trigger — toggle it active/inactive, change a schedule's cron, or adjust "
        "its params. Event-name and vendor are fixed at creation.\n\n"
        "**Authentication:** Bearer token with `orchestration:manage`."
    ),
    responses={
        400: err("Invalid update (e.g. bad cron).", "invalid cron expression"),
        404: err("No such trigger.", "trigger not found"),
    },
)
async def update_trigger(
    trigger_id: uuid.UUID,
    body: TriggerUpdateRequest,
    request: Request,
    auth: AuthContext = require_permission('orchestration:manage'),
    db: AsyncSession = Depends(get_db),
):
    trig = await trig_service.get_trigger(db, tenant_id=auth.tenant_id, trigger_id=trigger_id)
    if trig is None:
        raise HTTPException(status_code=404, detail="trigger not found")
    await ensure_registered_app_access(db, auth, trig.app_id)
    await _load_and_gate_workflow(db, auth, trig.workflow_id, action="edit")
    try:
        updated = await trig_service.update_trigger(
            db,
            tenant_id=auth.tenant_id,
            trigger_id=trigger_id,
            active=body.active,
            cron_expression=body.cron_expression,
            params=body.params,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if updated is None:
        raise HTTPException(status_code=404, detail="trigger not found")
    return _trigger_view(updated, request)


@router.post(
    "/triggers/{trigger_id}/rotate-token",
    response_model=TriggerRotateTokenResponse,
    summary="Rotate an event trigger's webhook token",
    description=(
        "Issue a fresh inbound-webhook token for an event trigger and return the new URL. "
        "The previous URL stops working immediately — update the external system after "
        "rotating.\n\n"
        "**Authentication:** Bearer token with `orchestration:manage`."
    ),
    responses={
        400: err("This trigger is not an event trigger (nothing to rotate).", "trigger has no webhook token"),
        404: err("No such trigger.", "trigger not found"),
    },
)
async def rotate_trigger_token(
    trigger_id: uuid.UUID,
    request: Request,
    auth: AuthContext = require_permission('orchestration:manage'),
    db: AsyncSession = Depends(get_db),
):
    trig = await trig_service.get_trigger(db, tenant_id=auth.tenant_id, trigger_id=trigger_id)
    if trig is None:
        raise HTTPException(status_code=404, detail="trigger not found")
    await ensure_registered_app_access(db, auth, trig.app_id)
    await _load_and_gate_workflow(db, auth, trig.workflow_id, action="edit")
    from app.services.orchestration.api.connections import resolve_base_url

    base_url = resolve_base_url(request.headers.get("origin"))
    try:
        result = await trig_service.rotate_trigger_token(
            db, tenant_id=auth.tenant_id, trigger_id=trigger_id,
            actor_id=auth.user_id, base_url=base_url,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return TriggerRotateTokenResponse(**result)


@router.delete(
    "/triggers/{trigger_id}",
    status_code=204,
    summary="Delete a trigger",
    description=(
        "Remove a trigger from its workflow. For an event trigger this also invalidates its "
        "inbound webhook URL. Returns 204.\n\n"
        "**Authentication:** Bearer token with `orchestration:manage`."
    ),
    responses={
        204: {"description": "Deleted; no content."},
        404: err("No such trigger.", "trigger not found"),
    },
)
async def delete_trigger(
    trigger_id: uuid.UUID,
    auth: AuthContext = require_permission('orchestration:manage'),
    db: AsyncSession = Depends(get_db),
):
    # Load trigger first to learn its app_id; bare delete-by-id can't gate.
    trig = await trig_service.get_trigger(db, tenant_id=auth.tenant_id, trigger_id=trigger_id)
    if trig is None:
        raise HTTPException(status_code=404, detail="trigger not found")
    await ensure_registered_app_access(db, auth, trig.app_id)
    await _load_and_gate_workflow(db, auth, trig.workflow_id, action="edit")
    if not await trig_service.delete_trigger(
        db, tenant_id=auth.tenant_id, trigger_id=trigger_id, actor_id=auth.user_id,
    ):
        raise HTTPException(status_code=404, detail="trigger not found")
    return Response(status_code=204)


# ─── Runs ───────────────────────────────────────────────────────────────────


@router.post(
    "/runs",
    response_model=RunResponse,
    status_code=201,
    summary="Run a workflow now",
    description=(
        "Manually fire a published workflow (\"Run now\"), creating a run over the resolved "
        "recipient set. Poll the returned run for live progress, recipient state, and "
        "actions. The workflow must be published and runnable.\n\n"
        "**Authentication:** Bearer token with `orchestration:manage`."
    ),
    responses={
        400: err("The workflow can't be fired (e.g. no published version or empty audience).", "workflow has no published version"),
        404: err("No such workflow.", "workflow not found"),
    },
)
async def fire_manual(
    body: RunCreateRequest,
    auth: AuthContext = require_permission('orchestration:manage'),
    db: AsyncSession = Depends(get_db),
):
    await _load_and_gate_workflow(db, auth, body.workflow_id, action="edit")
    try:
        run = await run_service.fire_manual_run(
            db, tenant_id=auth.tenant_id, workflow_id=body.workflow_id,
            user_id=auth.user_id, params=body.params,
        )
    except run_service.RunFireError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if run is None:
        raise HTTPException(status_code=404, detail="workflow not found")
    return run


async def _load_and_gate_run(db: AsyncSession, auth: AuthContext, run_id: uuid.UUID):
    """Load a run scoped to ``auth.tenant_id`` and verify the caller has access
    to the run's ``app_id``. Returns the run or raises HTTPException(404)."""
    run = await run_service.get_run(db, tenant_id=auth.tenant_id, run_id=run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    workflow = (await db.execute(select(Workflow).where(Workflow.id == run.workflow_id))).scalar_one_or_none()
    if workflow is None or not can_access(auth, workflow, "read"):
        raise HTTPException(status_code=404, detail="run not found")
    await ensure_registered_app_access(db, auth, run.app_id)
    return run


@router.get(
    "/runs",
    response_model=RunListResponse,
    summary="List workflow runs",
    description=(
        "List workflow runs you can read, filtered by workflow, app, and status, with a "
        "total count for pagination. With no `appId`, results are limited to the apps you "
        "can access.\n\n"
        "**Authentication:** Bearer token."
    ),
)
async def list_runs(
    workflow_id: Optional[uuid.UUID] = Query(None, alias="workflowId", description="Restrict to one workflow."),
    app_id: Optional[str] = Query(None, alias="appId", description="Restrict to one app."),
    status: Optional[str] = Query(None, description="Filter by run status."),
    limit: int = Query(50, ge=1, le=200, description="Page size (1–200)."),
    offset: int = Query(0, ge=0, description="Rows to skip."),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    # App-scoped logs routes pass `appId` explicitly so `/voice-rx/logs` only
    # sees Voice Rx rows even when the caller can access multiple apps.
    scoped_app_ids: frozenset[str] | None = frozenset(auth.app_access)
    if app_id is not None:
        await ensure_registered_app_access(db, auth, app_id)
        scoped_app_ids = None

    # When the caller filters by workflow, app-gate via that workflow and reject
    # mismatched explicit `appId` so cross-app bookmarks 404 cleanly.
    if workflow_id is not None:
        wf = await _load_and_gate_workflow(
            db, auth, workflow_id, require_active=False, action="read",
        )
        if app_id is not None and wf.app_id != app_id:
            raise HTTPException(status_code=404, detail="workflow not found")
    items, total = await run_service.list_runs(
        db,
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        workflow_id=workflow_id,
        app_id=app_id,
        status=status,
        limit=limit,
        offset=offset,
        app_ids=None if workflow_id is not None else scoped_app_ids,
    )
    return RunListResponse(
        runs=[RunResponse.model_validate(r) for r in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/actions",
    response_model=WorkflowActionListResponse,
    summary="List outbound actions (tenant-wide)",
    description=(
        "The tenant-wide outbound action log — every message/call a workflow dispatched, "
        "across runs. Rich filters (workflow, app, channel, action type, status, recipient, "
        "provider correlation id, time window) feed the platform Logs page. App-gated to "
        "the apps you can access.\n\n"
        "**Authentication:** Bearer token."
    ),
)
async def list_workflow_actions_global(
    workflow_id: Optional[uuid.UUID] = Query(None, alias="workflowId", description="Restrict to one workflow."),
    app_id: Optional[str] = Query(None, alias="appId", description="Restrict to one app."),
    channel: Optional[str] = Query(None, description="Filter by channel, e.g. `whatsapp`, `voice`."),
    action_type: Optional[str] = Query(None, alias="actionType", description="Filter by action type."),
    status: Optional[str] = Query(None, description="Filter by action status."),
    recipient_id: Optional[str] = Query(None, alias="recipientId", description="Filter to one recipient."),
    provider_correlation_id: Optional[str] = Query(None, alias="providerCorrelationId", description="Filter by the provider's correlation id."),
    since: Optional[datetime] = Query(None, description="Only actions at or after this timestamp."),
    until: Optional[datetime] = Query(None, description="Only actions before this timestamp."),
    limit: int = Query(100, ge=1, le=200, description="Page size (1–200)."),
    offset: int = Query(0, ge=0, description="Rows to skip."),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """Tenant-wide outbound action log — feeds the platform Logs page's
    "Workflow actions" tab. App-gated via the caller's ``app_access`` set so a
    tenant admin without app A's grant can't see app A's actions; when
    ``workflow_id`` is supplied, gate via that workflow's app instead (mirrors
    the ``/runs`` listing pattern)."""
    scoped_app_ids: frozenset[str] | None = frozenset(auth.app_access)
    if app_id is not None:
        await ensure_registered_app_access(db, auth, app_id)
        scoped_app_ids = None
    if workflow_id is not None:
        wf = await _load_and_gate_workflow(
            db, auth, workflow_id, require_active=False, action="read",
        )
        if app_id is not None and wf.app_id != app_id:
            raise HTTPException(status_code=404, detail="workflow not found")
    items, total = await run_service.list_actions_global(
        db,
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        app_ids=None if workflow_id is not None else scoped_app_ids,
        app_id=app_id,
        workflow_id=workflow_id,
        channel=channel,
        action_type=action_type,
        status=status,
        recipient_id=recipient_id,
        provider_correlation_id=provider_correlation_id,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
    )
    return WorkflowActionListResponse(
        items=[WorkflowActionGlobalRow.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/runs/{run_id}",
    response_model=RunResponse,
    summary="Get a run",
    description=(
        "Fetch a single workflow run by id — status, counts, and timing. Poll it to track "
        "progress after firing.\n\n"
        "**Authentication:** Bearer token; the run must be readable by you."
    ),
    responses={404: err("No such run readable by you.", "run not found")},
)
async def get_run(
    run_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    return await _load_and_gate_run(db, auth, run_id)


@router.get(
    "/runs/{run_id}/overlay",
    response_model=RunOverlaySnapshotResponse,
    summary="Get a run's canvas overlay",
    description=(
        "Return the run plus the latest per-node step states, so the builder canvas can "
        "overlay live progress on the workflow graph (which nodes are done, active, or "
        "errored).\n\n"
        "**Authentication:** Bearer token; the run must be readable by you."
    ),
    responses={404: err("No such run.", "run not found")},
)
async def get_run_overlay(
    run_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    run = await _load_and_gate_run(db, auth, run_id)
    node_steps = await run_service.list_latest_node_steps(
        db, tenant_id=auth.tenant_id, run_id=run_id,
    )
    return RunOverlaySnapshotResponse(
        run=RunResponse.model_validate(run),
        node_steps=[RunNodeStepResponse.model_validate(step) for step in node_steps],
    )


@router.get(
    "/runs/{run_id}/recipients",
    response_model=list[RecipientStateResponse],
    summary="List a run's recipients",
    description=(
        "List the recipients in a run and each one's current state — which node they're at, "
        "whether they're waiting, done, or errored. Paginated.\n\n"
        "**Authentication:** Bearer token; the run must be readable by you."
    ),
    responses={404: err("No such run.", "run not found")},
)
async def list_run_recipients(
    run_id: uuid.UUID,
    limit: int = Query(100, ge=1, le=500, description="Page size (1–500)."),
    offset: int = Query(0, ge=0, description="Rows to skip."),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    await _load_and_gate_run(db, auth, run_id)
    return await run_service.list_recipients(
        db, tenant_id=auth.tenant_id, run_id=run_id, limit=limit, offset=offset,
    )


@router.get(
    "/runs/{run_id}/actions",
    response_model=list[ActionResponse],
    summary="List a run's actions",
    description=(
        "List the outbound actions (messages, calls) dispatched within a single run, "
        "filterable by channel and action type.\n\n"
        "**Authentication:** Bearer token; the run must be readable by you."
    ),
    responses={404: err("No such run.", "run not found")},
)
async def list_run_actions(
    run_id: uuid.UUID,
    channel: Optional[str] = Query(None, description="Filter by channel."),
    action_type: Optional[str] = Query(None, alias="actionType", description="Filter by action type."),
    limit: int = Query(200, ge=1, le=1000, description="Page size (1–1000)."),
    offset: int = Query(0, ge=0, description="Rows to skip."),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    await _load_and_gate_run(db, auth, run_id)
    return await run_service.list_actions(
        db, tenant_id=auth.tenant_id, run_id=run_id,
        channel=channel, action_type=action_type, limit=limit, offset=offset,
    )


@router.get(
    "/runs/{run_id}/actions/{action_id}",
    response_model=ActionResponse,
    summary="Get a run action",
    description=(
        "Fetch a single dispatched action within a run — its payload, provider correlation "
        "id, status, and outcome.\n\n"
        "**Authentication:** Bearer token; the run must be readable by you."
    ),
    responses={404: err("No such run or action.", "action not found")},
)
async def get_run_action(
    run_id: uuid.UUID,
    action_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    await _load_and_gate_run(db, auth, run_id)
    action = await run_service.get_action(
        db,
        tenant_id=auth.tenant_id,
        run_id=run_id,
        action_id=action_id,
    )
    if action is None:
        raise HTTPException(status_code=404, detail="action not found")
    return action


@router.post(
    "/runs/{run_id}/cancel",
    response_model=TerminationReceipt,
    summary="Cancel a run",
    description=(
        "Request cancellation of an in-progress run. Returns a termination receipt; "
        "provider-side cancellation of already-dispatched actions finalizes asynchronously "
        "(poll `cancel-audits` for those outcomes).\n\n"
        "**Authentication:** Bearer token with `orchestration:manage`."
    ),
    responses={404: err("No such run.", "run not found")},
)
async def cancel_run(
    run_id: uuid.UUID,
    body: CancelRunRequest = CancelRunRequest(),
    auth: AuthContext = require_permission('orchestration:manage'),
    db: AsyncSession = Depends(get_db),
) -> TerminationReceipt:
    run = await _load_and_gate_run(db, auth, run_id)
    await _load_and_gate_workflow(db, auth, run.workflow_id, action="edit")
    receipt = await terminate_run(
        db, run_id=run_id, tenant_id=auth.tenant_id,
        user_id=auth.user_id, reason=body.reason,
    )
    if receipt is None:
        raise HTTPException(status_code=404, detail="run not found")
    await db.commit()
    return receipt


@router.get(
    "/runs/{run_id}/cancel-audits",
    response_model=list[CancelAuditRead],
    summary="List a run's cancellation audits",
    description=(
        "List the provider-side cancellation outcomes recorded after a run was cancelled. "
        "The Stop receipt panel polls this; rows appearing mean the async finalize ran.\n\n"
        "**Authentication:** Bearer token; the run must be readable by you."
    ),
    responses={404: err("No such run.", "run not found")},
)
async def list_run_cancel_audits(
    run_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """Provider-cancel outcomes written by finalize-run-cancel. The Stop receipt
    panel polls this; rows appearing means the async finalize ran."""
    await _load_and_gate_run(db, auth, run_id)
    return await run_service.list_cancel_audits(
        db, tenant_id=auth.tenant_id, run_id=run_id,
    )


@router.post(
    "/runs/{run_id}/recipients/{recipient_id}/override",
    response_model=OverrideResponse,
    status_code=201,
    summary="Override a recipient's path",
    description=(
        "Manually intervene on one recipient in a run — e.g. skip them, or jump them to a "
        "specific node — with a reason recorded for audit. Used by operators to unstick or "
        "redirect individual recipients.\n\n"
        "**Authentication:** Bearer token with `orchestration:manage`."
    ),
    responses={404: err("No such run or recipient.", "run not found")},
)
async def override_recipient(
    run_id: uuid.UUID,
    recipient_id: str,
    body: OverrideRequest,
    auth: AuthContext = require_permission('orchestration:manage'),
    db: AsyncSession = Depends(get_db),
):
    run = await _load_and_gate_run(db, auth, run_id)
    await _load_and_gate_workflow(db, auth, run.workflow_id, action="edit")
    ov = await run_service.apply_override(
        db, tenant_id=auth.tenant_id, run_id=run_id, recipient_id=recipient_id,
        action=body.action, target_node_id=body.target_node_id,
        reason=body.reason, applied_by=auth.user_id,
    )
    if ov is None:
        raise HTTPException(status_code=404, detail="run not found")
    return ov


# ─── Action templates ───────────────────────────────────────────────────────


@router.get(
    "/action_templates",
    response_model=list[ActionTemplateResponse],
    summary="List action templates",
    description=(
        "List reusable action templates (per channel) that workflow dispatch nodes can "
        "bind to, optionally scoped to one app and channel.\n\n"
        "**Authentication:** Bearer token."
    ),
)
async def list_action_templates(
    app_id: Optional[str] = Query(None, alias="appId", description="Restrict to one app."),
    channel: Optional[str] = Query(None, description="Filter by channel, e.g. `whatsapp`, `voice`."),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    if app_id is not None:
        await ensure_registered_app_access(db, auth, app_id)
    return await tmpl_service.list_templates(
        db, tenant_id=auth.tenant_id, app_id=app_id, channel=channel,
    )


@router.post(
    "/action_templates",
    response_model=ActionTemplateResponse,
    summary="Create or update an action template",
    description=(
        "Upsert a tenant-owned action template by slug for an app and channel — its name, "
        "payload schema, and active flag. Re-posting the same slug updates it in place.\n\n"
        "**Authentication:** Bearer token with `orchestration:manage`."
    ),
)
async def upsert_action_template(
    body: ActionTemplateUpsertRequest,
    app_id: str = Query(..., alias="appId"),
    auth: AuthContext = require_permission('orchestration:manage'),
    db: AsyncSession = Depends(get_db),
):
    await ensure_registered_app_access(db, auth, app_id)
    return await tmpl_service.upsert_tenant_template(
        db, tenant_id=auth.tenant_id, app_id=app_id,
        channel=body.channel, slug=body.slug, name=body.name,
        payload_schema=body.payload_schema, active=body.active,
    )


# ─── Consent ────────────────────────────────────────────────────────────────


@router.get(
    "/consent/{recipient_id}",
    response_model=list[ConsentResponse],
    summary="Get a recipient's consent",
    description=(
        "Return the consent records for a recipient in an app — per channel, the current "
        "opt-in/opt-out status and its source. Workflows honor these before dispatching.\n\n"
        "**Authentication:** Bearer token with access to the app."
    ),
)
async def get_consent(
    recipient_id: str,
    app_id: str = Query(..., alias="appId"),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    await ensure_registered_app_access(db, auth, app_id)
    return await consent_service.get_recipient_consent(
        db, tenant_id=auth.tenant_id, app_id=app_id, recipient_id=recipient_id,
    )


@router.post(
    "/consent",
    response_model=ConsentResponse,
    status_code=201,
    summary="Set a recipient's consent",
    description=(
        "Record a consent decision for a recipient on a channel — opt-in or opt-out, with "
        "its source and supporting evidence. This is the gate workflows check before "
        "contacting someone.\n\n"
        "**Authentication:** Bearer token with `orchestration:manage` and access to the app."
    ),
)
async def set_consent(
    body: ConsentSetRequest,
    app_id: str = Query(..., alias="appId"),
    auth: AuthContext = require_permission('orchestration:manage'),
    db: AsyncSession = Depends(get_db),
):
    await ensure_registered_app_access(db, auth, app_id)
    return await consent_service.set_consent(
        db, tenant_id=auth.tenant_id, app_id=app_id,
        recipient_id=body.recipient_id, channel=body.channel,
        status=body.status, source=body.source, evidence=body.evidence,
    )


# ─── Node-type catalog (palette) ───────────────────────────────────────────


@router.get(
    "/node_types",
    response_model=list[NodeTypeDescriptor],
    summary="List node types (palette)",
    description=(
        "Return the catalog of node types available to the builder palette — sources, "
        "filters, logic, messaging, voice, and sinks — with their display metadata and "
        "config schemas. Optionally scoped to a workflow type.\n\n"
        "**Authentication:** Bearer token."
    ),
)
async def get_node_types(
    workflow_type: Optional[str] = Query(None, alias="workflowType", description="Restrict to node types valid for this workflow type."),
    auth: AuthContext = Depends(get_auth_context),
):
    return list_node_types(workflow_type=workflow_type)


@router.get(
    "/source_catalog",
    response_model=list[CohortSourceResponse],
    summary="List cohort sources",
    description=(
        "List the sources a workflow's source node can draw from — platform static sources "
        "plus your tenant's published dataset versions. Each entry carries a `kind` "
        "(`static` vs `dataset`); the underlying table is never exposed.\n\n"
        "**Authentication:** Bearer token."
    ),
)
async def get_source_catalog(
    workflow_type: Optional[str] = Query(None, alias="workflowType", description="Restrict to sources valid for this workflow type."),
    app_id: Optional[str] = Query(None, alias="appId", description="Restrict to one app."),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """Phase 11 (Commit 2) — registered cohort sources for the SourceSelector editor.

    Engineering-owned static catalog plus tenant-owned dataset versions
    (Phase 12). Each entry carries a ``kind`` discriminator (``"static"``
    vs ``"dataset"``); the underlying schema-qualified table is never
    surfaced. Dataset entries are tenant-scoped via ``auth.tenant_id``.
    """
    scoped_app_ids: list[str] | None = None
    if app_id is not None:
        await ensure_registered_app_access(db, auth, app_id)
    else:
        scoped_app_ids = sorted(auth.app_access)
    return await list_cohort_sources(
        db,
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        workflow_type=workflow_type,
        app_id=app_id,
        app_ids=scoped_app_ids,
    )


@router.get(
    "/source_catalog/{source_ref:path}/columns/{column}/values",
    response_model=ColumnValuesResponse,
    summary="List distinct values for a source column",
    description=(
        "Return distinct values for a filterable column on a cohort source, to populate "
        "filter dropdowns in the builder. Only columns the source whitelists are "
        "accessible; supports optional substring search and is capped at 50 results "
        "(`hasMore` signals more exist).\n\n"
        "**Authentication:** Bearer token with access to the app."
    ),
)
async def get_source_column_values(
    source_ref: str,
    column: str,
    app_id: str = Query(..., alias="appId"),
    q: Optional[str] = Query(None),
    limit: int = Query(default=50, le=50, ge=1),
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """Distinct values for a filter column on a cohort source.

    Only columns in allowed_filter_columns are accessible. Supports optional
    substring search (q) and a hard limit cap of 50. hasMore=true signals the
    caller that there are further results beyond the returned slice.
    """
    await ensure_registered_app_access(db, auth, app_id)
    result = await fetch_column_values(
        db,
        source_ref=source_ref,
        column=column,
        tenant_id=auth.tenant_id,
        app_id=app_id,
        q=q,
        limit=limit,
    )
    return ColumnValuesResponse(values=result["values"], has_more=result["has_more"])


@router.post(
    "/nodes/upstream-variables",
    response_model=ResolveUpstreamVariablesResponse,
    summary="Resolve a node's upstream variables",
    description=(
        "Given a workflow graph and a target node, return the payload variables available "
        "upstream of it — powering the builder's input pane and prompt picker. Read-only. A "
        "cohort/dataset owned by another tenant resolves to 404, never leaking data.\n\n"
        "**Authentication:** Bearer token with access to the app."
    ),
    responses={404: err("An upstream source reference could not be resolved.", "upstream source not found")},
)
async def resolve_node_upstream_variables(
    body: ResolveUpstreamVariablesRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """Read-only: payload variables available upstream of ``targetNodeId``.

    Powers the AI agent Input pane + prompt picker. A cohort/dataset UUID owned
    by another tenant resolves to 404 (never 403, never data)."""
    await ensure_registered_app_access(db, auth, body.app_id)
    nodes = [WorkflowDefinitionNode.model_validate(n) for n in body.nodes]
    edges = [WorkflowDefinitionEdge.model_validate(e) for e in body.edges]
    try:
        return await resolve_upstream_variables(
            db,
            tenant_id=auth.tenant_id,
            app_id=body.app_id,
            workflow_type=body.workflow_type,
            nodes=nodes,
            edges=edges,
            target_node_id=body.target_node_id,
        )
    except UpstreamSourceNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/nodes/llm-extract/test",
    response_model=LlmExtractDryRunResponse,
    summary="Dry-run an llm.extract node",
    description=(
        "Run a single-sample dry run of an `llm.extract` node from the builder's Test pane — "
        "returns the resolved prompt and the model's structured result, without saving a "
        "run. Cost is tracked under a `builder_test` purpose so test spend rolls up "
        "separately from production.\n\n"
        "**Authentication:** Bearer token with access to the app."
    ),
    responses={400: err("The node config is invalid.", "invalid llm.extract config")},
)
async def run_llm_extract_test(
    body: LlmExtractDryRunRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """One-sample dry-run of an llm.extract node (AI agent Test pane).

    Runs the node's own runtime over the supplied sample, resolving the
    ``workflow_llm_extract`` call site; cost rows carry the
    ``workflow_llm_extract:builder_test`` purpose so builder tests roll up
    separately."""
    await ensure_registered_app_access(db, auth, body.app_id)
    # ``nodeType`` is the FE discriminator, not a node-runtime config field.
    raw_config = {k: v for k, v in body.config.items() if k != "nodeType"}
    try:
        config = LlmExtractConfig.model_validate(raw_config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    out = await run_llm_extract_dry_run(
        db=db,
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        app_id=body.app_id,
        config=config,
        sample=body.sample,
    )
    return LlmExtractDryRunResponse(prompt=out["prompt"], result=out["result"])

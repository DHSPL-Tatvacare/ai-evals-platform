"""Provider connection routes (auth-required).

CRUD + test + rotate-token + schema + agent-variables.
All routes are gated on ``require_permission('orchestration:manage')``,
tenant-scoped via the resulting ``AuthContext``, and app-gated via
``ensure_registered_app_access`` against the connection's ``app_id``.

Public webhook routes (matched by per-connection ``webhook_token``) move in
commit 2 — see ``orchestration_webhooks.py``.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthContext
from app.auth.app_scope import ensure_registered_app_access
from app.auth.permissions import require_permission
from app.database import get_db
from app.models.provider_connection import ProviderConnection
from app.openapi_examples import err
from app.schemas.orchestration_connection import (
    AgentVariablesResponse,
    ConnectionCreateRequest,
    ConnectionResponse,
    ConnectionRotateTokenResponse,
    ConnectionTestResponse,
    ConnectionUpdateRequest,
    ProviderAgentsListResponse,
    ProviderPhoneNumbersListResponse,
    ProviderTemplatesListResponse,
    ProviderSpecResponse,
)
from app.services.orchestration.api import connections as conn_service
from app.services.orchestration.api import provider_listings as listings_service


router = APIRouter(prefix="/api/orchestration/connections", tags=["orchestration"])


# Routes whose paths could collide with the {connection_id} pattern must be
# declared before the generic ones (FastAPI matches in declaration order).


@router.get(
    "/schema",
    response_model=ProviderSpecResponse,
    summary="Get a provider's connection schema",
    description=(
        "Return the field shape for a provider so a UI can render the right connection "
        "form — which fields exist, which are secret, and their types. Call this before "
        "creating or editing a connection for that provider.\n\n"
        "**Authentication:** Bearer token with `orchestration:manage`."
    ),
    responses={400: err("Unknown provider key.", "Unknown provider: 'foo'")},
)
async def get_provider_schema(
    provider: str = Query(..., description="Provider key, e.g. `wati`, `bolna`, `webhook`."),
    auth: AuthContext = require_permission('orchestration:manage'),
):
    """Gated on ``orchestration:manage``; the dependency enforces the permission."""
    _ = auth
    try:
        return conn_service.get_provider_schema(provider)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post(
    "",
    response_model=ConnectionResponse,
    status_code=201,
    summary="Create a provider connection",
    description=(
        "Create a tenant- and app-owned connection to a provider (WhatsApp, voice, SMS, "
        "CRM). Secrets in `config` are encrypted at rest and never returned. Workflows "
        "later reference this connection by its id rather than embedding credentials.\n\n"
        "**Authentication:** Bearer token with `orchestration:manage` and access to the app."
    ),
    responses={
        400: err("Invalid config for the provider, or unknown provider.", "Missing required field: apiKey"),
        409: err("A connection with this name already exists for the app.", "Connection name already in use"),
    },
)
async def create_connection(
    body: ConnectionCreateRequest,
    request: Request,
    auth: AuthContext = require_permission('orchestration:manage'),
    db: AsyncSession = Depends(get_db),
):
    await ensure_registered_app_access(db, auth, body.app_id)
    for scope_app in body.app_scopes:
        await ensure_registered_app_access(db, auth, scope_app)
    base_url = conn_service.resolve_base_url(request.headers.get("origin"))
    try:
        return await conn_service.create_connection(
            db,
            tenant_id=auth.tenant_id,
            app_id=body.app_id,
            provider=body.provider,
            name=body.name,
            config=body.config,
            active=body.active,
            created_by=auth.user_id,
            tenant_wide=body.tenant_wide,
            app_scopes=body.app_scopes,
            is_default=body.is_default,
            base_url=base_url,
        )
    except conn_service.ConnectionInvalid as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except conn_service.ConnectionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        # provider_specs.get_spec(unknown) lands here.
        raise HTTPException(status_code=400, detail=str(exc))


@router.get(
    "",
    response_model=list[ConnectionResponse],
    summary="List provider connections",
    description=(
        "List the connections you can see, filtered by app, provider, and whether to "
        "include inactive ones. Secrets are never included.\n\n"
        "**Authentication:** Bearer token with `orchestration:manage`."
    ),
)
async def list_connections(
    request: Request,
    auth: AuthContext = require_permission('orchestration:manage'),
    db: AsyncSession = Depends(get_db),
    app_id: Optional[str] = Query(None, alias="appId", description="Restrict to one app."),
    provider: Optional[list[str]] = Query(None, description="Filter to one or more provider keys."),
    include_inactive: bool = Query(False, alias="includeInactive", description="Include inactive connections."),
):
    if app_id is not None:
        await ensure_registered_app_access(db, auth, app_id)
    base_url = conn_service.resolve_base_url(request.headers.get("origin"))
    return await conn_service.list_connections(
        db,
        tenant_id=auth.tenant_id,
        app_id=app_id,
        providers=provider or None,
        include_inactive=include_inactive,
        base_url=base_url,
    )


async def _load_and_gate_connection(
    db: AsyncSession,
    auth: AuthContext,
    connection_id: uuid.UUID,
):
    row = await db.scalar(
        select(ProviderConnection).where(
            ProviderConnection.id == connection_id,
            ProviderConnection.tenant_id == auth.tenant_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="connection not found")
    # Site 5 access rule: a tenant-wide connection is reachable by any
    # orchestration:manage admin; otherwise the caller must have app access
    # to the home app_id or to any app in app_scopes.
    reachable_apps = {row.app_id, *(row.app_scopes or [])}
    if not row.tenant_wide and not (reachable_apps & auth.app_access):
        raise HTTPException(status_code=404, detail="connection not found")
    return row


@router.get(
    "/{connection_id}",
    response_model=ConnectionResponse,
    summary="Get a connection",
    description=(
        "Fetch one connection by id, with secrets redacted. Returns 404 for a connection "
        "you can't read (existence is not revealed).\n\n"
        "**Authentication:** Bearer token with `orchestration:manage`."
    ),
    responses={404: err("No such connection readable by you.", "connection not found")},
)
async def get_connection(
    connection_id: uuid.UUID,
    request: Request,
    auth: AuthContext = require_permission('orchestration:manage'),
    db: AsyncSession = Depends(get_db),
):
    row = await _load_and_gate_connection(db, auth, connection_id)
    base_url = conn_service.resolve_base_url(request.headers.get("origin"))
    default_ids = await conn_service.default_connection_ids(db, auth.tenant_id)
    return conn_service.serialize_connection(
        row, base_url, is_default=row.id in default_ids,
    )


@router.patch(
    "/{connection_id}",
    response_model=ConnectionResponse,
    summary="Update a connection",
    description=(
        "Partially update a connection's name, active flag, scope, or config. Toggle the "
        "`active` flag to enable or disable a connection — an inactive connection stops "
        "resolving for live dispatch and webhooks but is never deleted. **Secret-preserving:** "
        "any secret field you omit (or send blank) keeps its stored value — only fields you "
        "explicitly set are changed.\n\n"
        "**Authentication:** Bearer token with `orchestration:manage`."
    ),
    responses={
        400: err("Invalid config for the provider.", "Invalid config"),
        404: err("No such connection.", "connection not found"),
        409: err("Name conflicts with another connection.", "Connection name already in use"),
    },
)
async def update_connection(
    connection_id: uuid.UUID,
    body: ConnectionUpdateRequest,
    request: Request,
    auth: AuthContext = require_permission('orchestration:manage'),
    db: AsyncSession = Depends(get_db),
):
    await _load_and_gate_connection(db, auth, connection_id)
    if body.app_scopes is not None:
        for scope_app in body.app_scopes:
            await ensure_registered_app_access(db, auth, scope_app)
    base_url = conn_service.resolve_base_url(request.headers.get("origin"))
    try:
        return await conn_service.update_connection(
            db,
            tenant_id=auth.tenant_id,
            connection_id=connection_id,
            name=body.name,
            active=body.active,
            config=body.config,
            tenant_wide=body.tenant_wide,
            app_scopes=body.app_scopes,
            is_default=body.is_default,
            base_url=base_url,
        )
    except conn_service.ConnectionInvalid as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except conn_service.ConnectionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except conn_service.ConnectionNotFound:
        raise HTTPException(status_code=404, detail="connection not found")


@router.post(
    "/{connection_id}/test",
    response_model=ConnectionTestResponse,
    summary="Test a connection",
    description=(
        "Verify a connection's stored credentials by making a lightweight live call to the "
        "provider. Returns whether the connection is healthy and a short diagnostic "
        "message; it does not raise on provider failure.\n\n"
        "**Authentication:** Bearer token with `orchestration:manage`."
    ),
    responses={404: err("No such connection.", "connection not found")},
)
async def test_connection(
    connection_id: uuid.UUID,
    auth: AuthContext = require_permission('orchestration:manage'),
    db: AsyncSession = Depends(get_db),
):
    await _load_and_gate_connection(db, auth, connection_id)
    return await conn_service.test_connection(
        db, tenant_id=auth.tenant_id, connection_id=connection_id,
    )


@router.post(
    "/{connection_id}/rotate-token",
    response_model=ConnectionRotateTokenResponse,
    summary="Rotate the webhook token",
    description=(
        "Issue a fresh inbound-webhook token for this connection and return the new "
        "callback URL. The previous token stops working immediately, so update the "
        "provider's webhook configuration after rotating.\n\n"
        "**Authentication:** Bearer token with `orchestration:manage`."
    ),
    responses={
        400: err("This connection's provider does not use inbound webhooks.", "Provider does not support webhooks"),
        404: err("No such connection.", "connection not found"),
    },
)
async def rotate_webhook_token(
    connection_id: uuid.UUID,
    request: Request,
    auth: AuthContext = require_permission('orchestration:manage'),
    db: AsyncSession = Depends(get_db),
):
    await _load_and_gate_connection(db, auth, connection_id)
    base_url = conn_service.resolve_base_url(request.headers.get("origin"))
    try:
        return await conn_service.rotate_webhook_token(
            db,
            tenant_id=auth.tenant_id,
            connection_id=connection_id,
            base_url=base_url,
        )
    except conn_service.ConnectionInvalid as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get(
    "/{connection_id}/agent-variables",
    response_model=AgentVariablesResponse,
    summary="Get a provider's template/agent variables",
    description=(
        "Return the variables a provider expects so a workflow can map values into them — "
        "WATI template `customParams` or Bolna prompt placeholders. Variables are "
        "provider-truth, surfaced through one uniform shape regardless of provider. Uses a "
        "soft-error envelope (HTTP 200 with an error field) when the provider call fails.\n\n"
        "**Authentication:** Bearer token with `orchestration:manage`."
    ),
    responses={404: err("No such connection.", "connection not found")},
)
async def get_agent_variables(
    connection_id: uuid.UUID,
    auth: AuthContext = require_permission('orchestration:manage'),
    db: AsyncSession = Depends(get_db),
    agent_id: Optional[str] = Query(None, alias="agentId", description="Bolna agent id (voice connections)."),
    template_name: Optional[str] = Query(None, alias="templateName", description="WATI template name (messaging connections)."),
):
    """Return variable list for a Bolna agent or WATI template. Soft-error envelope."""
    await _load_and_gate_connection(db, auth, connection_id)
    return await listings_service.get_agent_variables(
        db,
        tenant_id=auth.tenant_id,
        connection_id=connection_id,
        agent_id=agent_id,
        template_name=template_name,
    )


@router.get(
    "/{connection_id}/agents",
    response_model=ProviderAgentsListResponse,
    summary="List a voice connection's agents",
    description=(
        "List the voice agents available on a Bolna connection, for the agent picker. "
        "Cached for 7 days; pass `refresh=true` to re-fetch live. Soft-error envelope "
        "(HTTP 200 with an error field) on upstream failure.\n\n"
        "**Authentication:** Bearer token with `orchestration:manage`."
    ),
    responses={
        400: err("The connection is not a Bolna (voice) connection.", "connection is provider='wati', expected bolna"),
        404: err("No such connection.", "connection not found"),
    },
)
async def list_connection_agents(
    connection_id: uuid.UUID,
    auth: AuthContext = require_permission('orchestration:manage'),
    db: AsyncSession = Depends(get_db),
    refresh: bool = Query(False, description="Bypass the 7-day cache and re-fetch from the provider."),
):
    """Live agent listing for the Bolna picker. Soft-error contract: HTTP 200 on upstream failure."""
    row = await _load_and_gate_connection(db, auth, connection_id)
    if row.provider != "bolna":
        raise HTTPException(
            status_code=400,
            detail=f"connection {connection_id} is provider={row.provider!r}, expected bolna",
        )
    return await listings_service.list_connection_bolna_agents(
        db,
        tenant_id=auth.tenant_id,
        app_id=row.app_id,
        connection_id=connection_id,
        refresh=refresh,
    )


@router.get(
    "/{connection_id}/templates",
    response_model=ProviderTemplatesListResponse,
    summary="List a messaging connection's templates",
    description=(
        "List the approved WhatsApp templates available on a WATI connection, for the "
        "template picker. Cached for 7 days; pass `refresh=true` to re-fetch live. "
        "Soft-error envelope on upstream failure.\n\n"
        "**Authentication:** Bearer token with `orchestration:manage`."
    ),
    responses={
        400: err("The connection is not a WATI (messaging) connection.", "connection is provider='bolna', expected wati"),
        404: err("No such connection.", "connection not found"),
    },
)
async def list_connection_templates(
    connection_id: uuid.UUID,
    auth: AuthContext = require_permission('orchestration:manage'),
    db: AsyncSession = Depends(get_db),
    refresh: bool = Query(False, description="Bypass the 7-day cache and re-fetch from the provider."),
):
    """Live template listing for the WATI picker. Same soft-error envelope as the agents endpoint."""
    row = await _load_and_gate_connection(db, auth, connection_id)
    if row.provider != "wati":
        raise HTTPException(
            status_code=400,
            detail=f"connection {connection_id} is provider={row.provider!r}, expected wati",
        )
    return await listings_service.list_connection_wati_templates(
        db,
        tenant_id=auth.tenant_id,
        app_id=row.app_id,
        connection_id=connection_id,
        refresh=refresh,
    )


@router.get(
    "/{connection_id}/phone-numbers",
    response_model=ProviderPhoneNumbersListResponse,
    summary="List a connection's phone numbers",
    description=(
        "List the phone numbers available on a connection — Bolna voice from-numbers or "
        "WATI channel numbers — for the from-number picker. Supports Bolna and WATI only; "
        "other providers return 400. Soft-error envelope on upstream failure.\n\n"
        "**Authentication:** Bearer token with `orchestration:manage`."
    ),
    responses={
        400: err("Provider does not support phone-number listing.", "phone-number listing supports bolna and wati only"),
        404: err("No such connection.", "connection not found"),
    },
)
async def list_connection_phone_numbers(
    connection_id: uuid.UUID,
    auth: AuthContext = require_permission('orchestration:manage'),
    db: AsyncSession = Depends(get_db),
    refresh: bool = Query(False, description="Bypass the cache and re-fetch from the provider."),
):
    """Live phone-number listing for bolna/wati pickers; soft-error envelope on provider failure."""
    row = await _load_and_gate_connection(db, auth, connection_id)
    if row.provider not in ("bolna", "wati"):
        raise HTTPException(
            status_code=400,
            detail=f"connection {connection_id} is provider={row.provider!r}; phone-number listing supports bolna and wati only",
        )
    return await listings_service.list_connection_phone_numbers(
        db,
        tenant_id=auth.tenant_id,
        app_id=row.app_id,
        connection_id=connection_id,
        provider=row.provider,
        refresh=refresh,
    )



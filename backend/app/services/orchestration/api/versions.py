"""Workflow draft save / publish / version listing.

Save overwrites the workflow's single mutable draft in place. Publish mints
one immutable ``workflow_versions`` row from that draft and repoints the live
pointer. Publish runs the Phase 11 contract pipeline:

  1. ``definition_normalizer.normalize_definition`` — rewrites pre-Phase-11
     edge labels, source ``next_node_id`` pointers, split branch labels,
     wait config, merge config, and consent_gate config into the canonical
     shape.
  2. ``definition_validator.validate_definition`` — enforces graph rules,
     per-node-config validity, source / sink / split / wait routing
     constraints. Aggregates errors and raises ``VersionPublishError`` with
     a human-readable list.

Successful validation persists the canonical (post-normalization)
definition and flips the version to 'published'. Pointing the workflow at
the version is the same row update.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orchestration import Workflow, WorkflowVersion
from app.models.provider_connection import ProviderConnection
from app.services.orchestration.definition_normalizer import normalize_definition
from app.services.orchestration.definition_validator import (
    DefinitionValidationError,
    DispatchRequiredFieldsError,
    validate_definition,
    validate_dispatch_required_fields,
)


class VersionPublishError(ValueError):
    """Phase 14 / Phase E — carries a structured ``errors: list[dict]`` so
    the route layer can return HTTP 400 with the same
    ``{node_id, field, message}`` shape that 422 dispatch errors already
    use. ``str(exc)`` keeps the legacy bullet-list format for logs and
    backward-compatible callers. ``errors`` is empty when the failure is
    a freeform message (e.g. legacy ``raise VersionPublishError("...")``)."""

    def __init__(
        self,
        message: str,
        *,
        errors: "Optional[list[dict[str, str | None]]]" = None,
    ) -> None:
        self.errors = list(errors or [])
        super().__init__(message)


class DraftValidationError(ValueError):
    """Raised when a draft save fails ``validate_definition(mode='draft')``.

    Mirrors :class:`VersionPublishError` so the route layer renders both
    publish and draft failures through the same ``PublishErrorPanel``
    contract. The save is rejected before the row hits the database — a
    half-broken draft cannot poison subsequent publish attempts.
    """

    def __init__(
        self,
        message: str,
        *,
        errors: "Optional[list[dict[str, str | None]]]" = None,
    ) -> None:
        self.errors = list(errors or [])
        super().__init__(message)


async def save_draft(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    workflow_id: uuid.UUID,
    definition: dict[str, Any],
) -> Optional[Workflow]:
    """Overwrite the workflow's single mutable draft in place. No version row.

    Normalizes first so the stored draft carries the canonical shape; then
    validates in draft mode. Draft tolerates missing required runtime fields
    but blocks fabricated keys, wrong types, malformed predicates, bad edges,
    and unknown node types. Returns the updated ``Workflow`` (``None`` if missing).
    """
    wf = (await db.execute(
        select(Workflow).where(Workflow.id == workflow_id, Workflow.tenant_id == tenant_id)
    )).scalar_one_or_none()
    if wf is None:
        return None

    canonical = normalize_definition(definition)
    try:
        validate_definition(
            canonical, workflow_type=wf.workflow_type, mode="draft",
        )
    except DefinitionValidationError as exc:
        raise DraftValidationError(str(exc), errors=exc.errors) from exc

    wf.draft_definition = canonical
    wf.draft_updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(wf)
    return wf


async def list_versions(
    db: AsyncSession, *, tenant_id: uuid.UUID, workflow_id: uuid.UUID,
) -> list[WorkflowVersion]:
    """Published release history, newest first. Drafts live on the workflow
    row now; archived rows are dead history — neither is returned here."""
    return list((await db.execute(
        select(WorkflowVersion).where(
            WorkflowVersion.workflow_id == workflow_id,
            WorkflowVersion.tenant_id == tenant_id,
            WorkflowVersion.status == "published",
        ).order_by(WorkflowVersion.version.desc())
    )).scalars().all())


async def get_version(
    db: AsyncSession, *, tenant_id: uuid.UUID, version_id: uuid.UUID,
) -> Optional[WorkflowVersion]:
    return (await db.execute(
        select(WorkflowVersion).where(
            WorkflowVersion.id == version_id,
            WorkflowVersion.tenant_id == tenant_id,
            WorkflowVersion.status == "published",
        )
    )).scalar_one_or_none()


async def publish_draft(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    workflow_id: uuid.UUID,
    published_by: uuid.UUID,
) -> Optional[WorkflowVersion]:
    """Mint one immutable published version from the workflow's current draft.

    Reads ``workflows.draft_definition``, normalizes, runs the dispatch-field
    gate then the structural validator (publish mode), inserts a new
    ``WorkflowVersion`` (``version=max+1``, ``status='published'``), repoints
    ``current_published_version_id``, and resets the draft to the just-published
    canonical definition (clean state). Returns ``None`` if the workflow is missing.
    """
    wf = (await db.execute(
        select(Workflow).where(Workflow.id == workflow_id, Workflow.tenant_id == tenant_id)
    )).scalar_one_or_none()
    if wf is None:
        return None
    if wf.draft_definition is None:
        raise VersionPublishError("workflow has no draft to publish")

    canonical = normalize_definition(wf.draft_definition)
    # Phase 13 publish-gate: dispatch nodes must carry UI-supplied
    # provider identifiers before the workflow can publish. Runs before
    # the structural validator so authors get a clean per-field message
    # instead of a Pydantic stack from the config-schema rule.
    dispatch_errors = validate_dispatch_required_fields(canonical)
    if dispatch_errors:
        raise DispatchRequiredFieldsError(dispatch_errors)
    try:
        validate_definition(canonical, workflow_type=wf.workflow_type)
    except DefinitionValidationError as exc:
        # Surface the structured error list under the same VersionPublishError
        # type the route handler already maps to a 400. Phase E: also carry
        # the per-node/field list so the FE renders both 400 and 422 through
        # the shared ``PublishErrorPanel``.
        raise VersionPublishError(str(exc), errors=exc.errors) from exc

    next_version = (await db.execute(
        select(func.coalesce(func.max(WorkflowVersion.version), 0))
        .where(WorkflowVersion.workflow_id == workflow_id)
    )).scalar_one() + 1
    v = WorkflowVersion(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        app_id=wf.app_id,
        workflow_id=workflow_id,
        version=next_version,
        definition=canonical,
        status="published",
        published_by=published_by,
        published_at=datetime.now(timezone.utc),
    )
    db.add(v)
    await db.flush()
    wf.current_published_version_id = v.id
    wf.draft_definition = canonical
    wf.draft_updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(v)
    return v


# ─── Pure validate (no DB writes) ────────────────────────────────────────────


async def validate_workflow_payload(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    app_id: str,
    workflow_type: str,
    definition: dict[str, Any],
) -> dict[str, Any]:
    """Run normalize + publish-mode validate + dispatch-field gate without writing.

    Used by ``POST /api/orchestration/workflows/validate`` and the JSON
    import preview. Mirrors :func:`publish_draft`'s pipeline so a payload
    that validates here is guaranteed to publish (modulo unknown
    ``connection_id`` references, which are softened to warnings — the
    caller may still need to rebind credentials post-import).

    Returns ``{ok, errors, warnings, normalized_definition}``.
    """
    errors: list[dict[str, str | None]] = []
    warnings: list[dict[str, str | None]] = []

    canonical = normalize_definition(definition)

    for d in validate_dispatch_required_fields(canonical):
        errors.append({"node_id": d.get("node_id"), "field": d.get("field"), "message": d.get("message")})

    try:
        validate_definition(canonical, workflow_type=workflow_type)
    except DefinitionValidationError as exc:
        errors.extend(exc.errors)

    # Soften unknown connection_ids to warnings so imports across tenants
    # can land as drafts the user rebinds in the builder. Matches the
    # clone_system_workflow behavior at the runtime contract level.
    referenced = _collect_connection_ids(canonical)
    if referenced:
        known = await _resolve_known_connection_ids(
            db, tenant_id=tenant_id, app_id=app_id, ids=referenced.keys(),
        )
        for conn_id, locations in referenced.items():
            if conn_id in known:
                continue
            for node_id in locations:
                warnings.append({
                    "node_id": node_id,
                    "field": "config.connection_id",
                    "message": (
                        f"connection_id {conn_id} is not bound to a "
                        f"connection in this tenant/app; rebind in the builder "
                        f"before publishing."
                    ),
                })

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "normalized_definition": canonical,
    }


def _collect_connection_ids(definition: dict[str, Any]) -> dict[str, list[str]]:
    """Return ``{connection_id: [node_id, ...]}`` for every node config that
    carries a ``connection_id`` string. Returns ``{}`` when none are present."""
    out: dict[str, list[str]] = {}
    for node in definition.get("nodes") or []:
        cfg = node.get("config") or {}
        conn_id = cfg.get("connection_id")
        if not isinstance(conn_id, str) or not conn_id.strip():
            continue
        out.setdefault(conn_id, []).append(str(node.get("id") or "<unknown>"))
    return out


async def _resolve_known_connection_ids(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    app_id: str,
    ids,
) -> set[str]:
    """Return the subset of referenced connection ids that exist for this
    tenant/app and are still active. Stringified for symmetric comparison
    with the JSON-side ``connection_id`` strings."""
    try:
        ids_as_uuid = [uuid.UUID(i) for i in ids]
    except (TypeError, ValueError):
        # Any malformed id falls through as "unknown" → warning.
        ids_as_uuid = []
        for i in ids:
            try:
                ids_as_uuid.append(uuid.UUID(i))
            except (TypeError, ValueError):
                continue
    if not ids_as_uuid:
        return set()
    rows = (await db.execute(
        select(ProviderConnection.id).where(
            ProviderConnection.id.in_(ids_as_uuid),
            ProviderConnection.tenant_id == tenant_id,
            ProviderConnection.app_id == app_id,
            ProviderConnection.active.is_(True),
        )
    )).scalars().all()
    return {str(r) for r in rows}

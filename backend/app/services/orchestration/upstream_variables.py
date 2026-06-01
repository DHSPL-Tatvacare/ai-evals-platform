"""Resolve the payload variables available upstream of a target node.

Walks a posted (unsaved) graph backward from ``target_node_id`` and, per
ancestor source/producer node, reports the fields it contributes. Field
discovery reuses the live source catalog
(``introspect_static_schema_descriptor`` / ``resolve_source``), a saved
cohort's ``payload_fields`` and a node's ``output_schema`` — no real recipient
row is fetched. Cohort/static fields are typed blanks; only dataset columns
carry an example value. Event sources cannot be enumerated yet and are reported
as ``unresolved``.
"""
from __future__ import annotations

import enum
import uuid
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orchestration import CohortDefinitionVersion
from app.models.provider_connection import ProviderConnection
from app.schemas.orchestration import (
    ResolveUpstreamVariablesResponse,
    UpstreamEvent,
    UpstreamField,
    UpstreamOutcomeEnum,
    UpstreamUnresolved,
    WorkflowDefinitionEdge,
    WorkflowDefinitionNode,
)
from app.services.orchestration.node_descriptors import (
    producer_capability,
    producer_vocabulary,
)
from app.services.orchestration.source_catalog import (
    DatasetSource,
    SourceCatalogError,
    _DATASET_PREFIX,
    introspect_static_schema_descriptor,
    lookup_source,
    resolve_source,
)

# Non-outcome step keys an action node injects for later steps. The canonical
# OUTCOME field is NOT listed here — it is declared by the capability adapter
# (ProducerVocabulary.outcome_field) and emitted via the producer path so the
# field and its pickable enums always travel together.
_DISPATCH_EMITS: dict[str, list[str]] = {
    "messaging.send_whatsapp_template": ["wa_button_id", "wa_reply_text"],
}


class UpstreamSourceNotFound(Exception):
    """An upstream cohort/dataset reference is missing or not owned by the tenant."""


class _ConnectionMissing(enum.Enum):
    """Sentinel: a same-tenant connection_id that resolves to no row (deleted/missing).
    Degrades to an unresolved entry rather than 404-ing the whole picker."""

    TOKEN = enum.auto()


_CONNECTION_MISSING = _ConnectionMissing.TOKEN


def collect_ancestors(
    target_node_id: str, edge_pairs: list[tuple[str, str]],
) -> list[str]:
    """Node ids reachable upstream of ``target_node_id`` via incoming edges.

    ``edge_pairs`` are ``(source, target)`` tuples so callers holding either
    typed edges or raw dict edges share one ancestor walk."""
    incoming: dict[str, list[str]] = {}
    for source, target in edge_pairs:
        incoming.setdefault(target, []).append(source)

    ordered: list[str] = []
    seen: set[str] = set()
    stack = list(incoming.get(target_node_id, []))
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        ordered.append(current)
        for parent in incoming.get(current, []):
            if parent not in seen:
                stack.append(parent)
    return ordered


async def _resolve_cohort(
    db: AsyncSession,
    node: WorkflowDefinitionNode,
    *,
    tenant_id: uuid.UUID,
    app_id: str,
    add: Callable[[UpstreamField, Any], None],
) -> None:
    config = node.config
    mode = config.get("mode")
    if mode == "saved":
        raw_version_id = config.get("cohort_definition_version_id")
        try:
            version_id = uuid.UUID(str(raw_version_id))
        except (ValueError, TypeError) as exc:
            raise UpstreamSourceNotFound(
                f"invalid cohort_definition_version_id: {raw_version_id!r}"
            ) from exc
        version = (
            await db.execute(
                select(CohortDefinitionVersion).where(
                    CohortDefinitionVersion.id == version_id,
                    CohortDefinitionVersion.tenant_id == tenant_id,
                )
            )
        ).scalar_one_or_none()
        if version is None:
            raise UpstreamSourceNotFound(
                f"cohort version not found or not owned by tenant: {version_id}"
            )
        source_ref = version.source_ref
        payload_fields = list(version.payload_fields or [])
    else:
        source_ref = config.get("source_ref")
        payload_fields = [f for f in config.get("payload_fields", []) if isinstance(f, str)]

    if not source_ref or not payload_fields:
        return
    source = lookup_source(source_ref)
    if source is None:
        return

    descriptor = await introspect_static_schema_descriptor(
        db,
        schema_qualified_table=source.schema_qualified_table,
        tenant_id=tenant_id,
        app_id=app_id,
    )
    col_by_name = {c["name"]: c for c in descriptor.get("columns", [])}
    for field_name in payload_fields:
        col = col_by_name.get(field_name)
        is_jsonb = bool(col["isJsonb"]) if col else False
        field_type = col["type"] if col else "text"
        add(
            UpstreamField(
                path=field_name,
                type=field_type,
                source="static" if is_jsonb else "cohort",
                source_node_id=node.id,
                is_jsonb=is_jsonb,
            ),
            None,
        )


async def _resolve_dataset(
    db: AsyncSession,
    node: WorkflowDefinitionNode,
    *,
    tenant_id: uuid.UUID,
    add: Callable[[UpstreamField, Any], None],
) -> None:
    raw_version_id = node.config.get("dataset_version_id")
    source_ref = f"{_DATASET_PREFIX}{raw_version_id}"
    try:
        resolved = await resolve_source(source_ref, db=db, tenant_id=tenant_id)
    except SourceCatalogError as exc:
        raise UpstreamSourceNotFound(str(exc)) from exc
    if not isinstance(resolved, DatasetSource):
        raise UpstreamSourceNotFound(
            f"dataset_version_id did not resolve to a dataset: {raw_version_id!r}"
        )
    for col in resolved.schema_descriptor.get("columns", []):
        samples = col.get("sample_values") or []
        sample_value = samples[0] if samples else None
        add(
            UpstreamField(
                path=col["name"],
                type=col.get("type", "text"),
                source="dataset",
                source_node_id=node.id,
                sample_value=sample_value,
            ),
            sample_value,
        )


def _sample_for_field(field_type: str, enum_values: list[Any]) -> Any:
    """Representative preview value derived from the field's declared type — never an LLM call."""
    if field_type == "enum":
        return str(enum_values[0]) if enum_values else "value"
    if field_type == "number":
        return 42
    if field_type == "boolean":
        return True
    if field_type == "array":
        return ["value"]
    return "text"


def _resolve_llm_extract(
    node: WorkflowDefinitionNode,
    *,
    add: Callable[[UpstreamField, Any], None],
) -> None:
    namespace = node.config.get("output_namespace") or node.id
    for field in node.config.get("output_schema", []):
        if not isinstance(field, dict):
            continue
        key = field.get("key")
        if not key:
            continue
        field_type = field.get("type") or "text"
        raw_enum = field.get("enumValues")
        enum_values = raw_enum if isinstance(raw_enum, list) else []
        sample = _sample_for_field(field_type, enum_values)
        add(
            UpstreamField(
                path=f"{namespace}.{key}",
                type=field_type,
                source="step",
                source_node_id=node.id,
                sample_value=sample,
            ),
            sample,
        )


async def _lookup_connection_provider(
    db: AsyncSession,
    *,
    connection_id_raw: Any,
    tenant_id: uuid.UUID,
    app_id: str,
) -> tuple[str, bool] | None | _ConnectionMissing:
    """Read-only, tenant+app-scoped vendor lookup for a producer's connection_id.

    A missing/blank id yields ``None`` (the node is unconfigured — surface
    nothing rather than guess a provider). Returns ``(provider, active)`` for an
    existing row so a deactivated connection is reported, not silently skipped.

    When the scoped row is absent we disambiguate two cases that must NOT be
    conflated: a row that exists under a *different* tenant raises
    ``UpstreamSourceNotFound`` (cross-tenant 404, no existence oracle); a row
    that exists nowhere — same-tenant deleted/missing — returns the
    ``_CONNECTION_MISSING`` sentinel so the caller degrades it to an unresolved
    entry instead of 404-ing the whole picker for unrelated downstream nodes."""
    if connection_id_raw in (None, ""):
        return None
    try:
        connection_id = uuid.UUID(str(connection_id_raw))
    except (ValueError, TypeError):
        return None
    row = (
        await db.execute(
            select(ProviderConnection.provider, ProviderConnection.active).where(
                ProviderConnection.id == connection_id,
                ProviderConnection.tenant_id == tenant_id,
                ProviderConnection.app_id == app_id,
            )
        )
    ).first()
    if row is not None:
        return row[0], bool(row[1])
    exists_anywhere = (
        await db.execute(
            select(ProviderConnection.id).where(ProviderConnection.id == connection_id)
        )
    ).first() is not None
    if exists_anywhere:
        raise UpstreamSourceNotFound(
            f"connection not found or not owned by tenant: {connection_id}"
        )
    return _CONNECTION_MISSING


async def _resolve_producer(
    db: AsyncSession,
    node: WorkflowDefinitionNode,
    *,
    tenant_id: uuid.UUID,
    app_id: str,
    add_field: Callable[[UpstreamField, Any], None],
    add_event: Callable[[UpstreamEvent], None],
    add_outcome: Callable[[UpstreamOutcomeEnum], None],
    add_unresolved: Callable[[UpstreamUnresolved], None],
) -> None:
    resolved = await _lookup_connection_provider(
        db,
        connection_id_raw=node.config.get("connection_id"),
        tenant_id=tenant_id,
        app_id=app_id,
    )
    if resolved is None:
        return
    if resolved is _CONNECTION_MISSING:
        add_unresolved(UpstreamUnresolved(
            node_id=node.id,
            label=node.data.get("label") or node.type,
            reason="The connected provider could not be found — it may have been deleted. Reconnect a provider to surface its outcomes and events.",
        ))
        return
    provider, active = resolved
    if not active:
        add_unresolved(UpstreamUnresolved(
            node_id=node.id,
            label=node.data.get("label") or node.type,
            reason="The connected provider is deactivated — its outcomes and events are unavailable until it is re-enabled.",
        ))
        return
    vocab = producer_vocabulary(node_type=node.type, vendor=provider)
    if vocab is None:
        return
    for event_name in vocab.event_names:
        add_event(UpstreamEvent(
            event_name=event_name, source_node_id=node.id, provider=provider,
        ))
    # The outcome bag path the adapter declares — offered as a pickable field AND
    # stamped on every outcome so the downstream picker binds by contract.
    outcome_path = (
        f"steps.{node.id}.{vocab.outcome_field}"
        if vocab.outcomes and vocab.outcome_field
        else ""
    )
    if outcome_path:
        add_field(
            UpstreamField(
                path=outcome_path, type="enum", source="step", source_node_id=node.id,
            ),
            None,
        )
    for outcome in vocab.outcomes:
        add_outcome(UpstreamOutcomeEnum(
            canonical=outcome.canonical,
            provider_label=outcome.provider_label,
            source_node_id=node.id,
            provider=provider,
            field=outcome_path,
        ))


async def resolve_upstream_variables(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    app_id: str,
    workflow_type: str,
    nodes: list[WorkflowDefinitionNode],
    edges: list[WorkflowDefinitionEdge],
    target_node_id: str,
) -> ResolveUpstreamVariablesResponse:
    # workflow_type is a stable request-contract field; resume events are
    # capability-truth (not workflow_type-scoped), so resolution does not branch on it.
    _ = workflow_type
    node_by_id = {n.id: n for n in nodes}
    fields: list[UpstreamField] = []
    sample: dict[str, Any] = {}
    unresolved: list[UpstreamUnresolved] = []
    events: list[UpstreamEvent] = []
    outcome_enums: list[UpstreamOutcomeEnum] = []
    seen_paths: set[str] = set()

    def _add(field: UpstreamField, value: Any) -> None:
        if field.path in seen_paths:
            return
        seen_paths.add(field.path)
        fields.append(field)
        sample[field.path] = value

    for node_id in collect_ancestors(target_node_id, [(e.source, e.target) for e in edges]):
        node = node_by_id.get(node_id)
        if node is None:
            continue
        if node.type == "source.cohort":
            await _resolve_cohort(db, node, tenant_id=tenant_id, app_id=app_id, add=_add)
        elif node.type == "source.dataset":
            await _resolve_dataset(db, node, tenant_id=tenant_id, add=_add)
        elif node.type == "source.event_trigger":
            unresolved.append(UpstreamUnresolved(
                node_id=node.id,
                label=node.data.get("label") or "Event trigger",
                reason="Event payload fields are not known until the workflow runs.",
            ))
        elif node.type == "llm.extract":
            _resolve_llm_extract(node, add=_add)
        elif node.type in _DISPATCH_EMITS:
            for key in _DISPATCH_EMITS[node.type]:
                _add(
                    UpstreamField(
                        path=f"steps.{node.id}.{key}",
                        type="text",
                        source="step",
                        source_node_id=node.id,
                    ),
                    None,
                )
        if producer_capability(node.type) is not None:
            await _resolve_producer(
                db, node, tenant_id=tenant_id, app_id=app_id,
                add_field=_add,
                add_event=events.append, add_outcome=outcome_enums.append,
                add_unresolved=unresolved.append,
            )

    return ResolveUpstreamVariablesResponse(
        fields=fields, sample=sample, unresolved=unresolved,
        events=events, outcome_enums=outcome_enums,
    )

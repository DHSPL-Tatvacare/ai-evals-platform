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

import uuid
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orchestration import CohortDefinitionVersion
from app.schemas.orchestration import (
    ResolveUpstreamVariablesResponse,
    UpstreamField,
    UpstreamUnresolved,
    WorkflowDefinitionEdge,
    WorkflowDefinitionNode,
)
from app.services.orchestration.source_catalog import (
    DatasetSource,
    SourceCatalogError,
    _DATASET_PREFIX,
    introspect_static_schema_descriptor,
    lookup_source,
    resolve_source,
)

# Server-side dispatch-emit map: keys an action node injects for later steps.
_DISPATCH_EMITS: dict[str, list[str]] = {
    "messaging.send_whatsapp_template": ["wa_button_id", "wa_reply_text"],
    "voice.place_call": ["voice_outcome"],
}


class UpstreamSourceNotFound(Exception):
    """An upstream cohort/dataset reference is missing or not owned by the tenant."""


def _collect_ancestors(
    target_node_id: str, edges: list[WorkflowDefinitionEdge],
) -> list[str]:
    """Node ids reachable upstream of ``target_node_id`` via incoming edges."""
    incoming: dict[str, list[str]] = {}
    for edge in edges:
        incoming.setdefault(edge.target, []).append(edge.source)

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
    node_by_id = {n.id: n for n in nodes}
    fields: list[UpstreamField] = []
    sample: dict[str, Any] = {}
    unresolved: list[UpstreamUnresolved] = []
    seen_paths: set[str] = set()

    def _add(field: UpstreamField, value: Any) -> None:
        if field.path in seen_paths:
            return
        seen_paths.add(field.path)
        fields.append(field)
        sample[field.path] = value

    for node_id in _collect_ancestors(target_node_id, edges):
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

    return ResolveUpstreamVariablesResponse(
        fields=fields, sample=sample, unresolved=unresolved,
    )

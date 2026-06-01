"""Cat-B field discovery for a cohort source.

Surfaces a cohort source's columns + types + allowed-values + PII flag so
the authoring agent (and any builder picker) can wire predicates and
payload fields against the real field set instead of guessing.

Reuses, never reinvents:
  - source_catalog.lookup_source resolves the source_ref.
  - source_catalog.introspect_static_schema_descriptor is the SAME live
    introspection the cohort-query compiler uses, so the discovered field
    set can never drift from what the run path accepts.
  - crm_workspace_pii._manifest_pii_fields reads the manifest's pii tag —
    the manifest is the single source of truth for what is PII. The
    manifest catalog table is keyed by the source's bare table name; a
    source whose physical table is not a manifest catalog table (hidden
    mirrors, clinical roster) resolves to no manifest entry, so every
    field comes back pii=False.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.services.chat_engine.manifest import get_manifest
from app.services.crm_workspace_pii import _manifest_pii_fields
from app.services.orchestration.source_catalog import (
    SourceCatalogError,
    introspect_static_schema_descriptor,
    lookup_source,
)


class CohortFieldRef(BaseModel):
    """One discoverable field on a cohort source."""

    model_config = ConfigDict(extra="forbid")

    name: str
    type: str
    allowed_values: list[str | int | float | bool] | None = None
    pii: bool = False
    filterable: bool = False


def _manifest_table_key(schema_qualified_table: str) -> str:
    """Bare table name from ``schema.table`` — the manifest catalog key."""
    return schema_qualified_table.rsplit(".", 1)[-1]


def _manifest_allowed_values(app_id: str, table_key: str) -> dict[str, list]:
    """``{column: allowed_values}`` for manifest columns that declare them."""
    try:
        manifest = get_manifest(app_id)
    except KeyError:
        return {}
    table = manifest.catalog_tables.get(table_key)
    if table is None:
        return {}
    return {
        name: list(col.allowed_values)
        for name, col in table.columns.items()
        if col.allowed_values
    }


async def list_cohort_fields(
    *,
    db,
    app_id: str,
    source_ref: str,
    tenant_id=None,
) -> list[CohortFieldRef]:
    """Discover the columns, types, allowed-values, and PII flag of a source.

    Explicit-curation sources (clinical.dim_patient) constrain the column
    set to ``allowed_payload_columns``; empty-static sources (crm.lead_record)
    take the full live column set. Types always come from the shared
    introspection. ``filterable`` reflects ``allowed_filter_columns`` when the
    source curates them, else every introspected column is filterable.

    ``tenant_id`` scopes only the shared introspection's raw_payload
    JSONB-key probe (so a source's JSONB keys surface for the right tenant);
    the structural column set is tenant-invariant. Defaults to the nil UUID
    for schema-only reads.
    """
    source = lookup_source(source_ref)
    if source is None:
        raise SourceCatalogError(f"unknown source_ref: {source_ref!r}")

    payload_cols = set(source.allowed_payload_columns)
    descriptor = await introspect_static_schema_descriptor(
        db,
        schema_qualified_table=source.schema_qualified_table,
        tenant_id=tenant_id if tenant_id is not None else _nil_tenant(),
        app_id=app_id,
        allowed_columns=payload_cols or None,
    )

    filter_cols = set(source.allowed_filter_columns)
    table_key = _manifest_table_key(source.schema_qualified_table)
    column_pii, _attribute_pii = _manifest_pii_fields(app_id, table_key)
    allowed_values = _manifest_allowed_values(app_id, table_key)

    fields: list[CohortFieldRef] = []
    for col in descriptor.get("columns", []):
        name = col["name"]
        fields.append(
            CohortFieldRef(
                name=name,
                type=col["type"],
                allowed_values=allowed_values.get(name),
                pii=name in column_pii,
                # Empty filter curation => the whole live set is filterable.
                filterable=(name in filter_cols) if filter_cols else True,
            )
        )
    return fields


def _nil_tenant():
    import uuid

    return uuid.UUID(int=0)


__all__ = ["CohortFieldRef", "list_cohort_fields"]

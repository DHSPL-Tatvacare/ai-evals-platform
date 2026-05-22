"""Phase 11 — registered cohort sources.

A ``source.cohort`` node selects a cohort source by a stable
``source_ref`` key (e.g. ``crm.lead_record``) — set inline on the node or
stored on its pinned ``cohort_definition_versions`` row. The catalog says which
underlying ``schema.table`` and id column back that ref, plus the columns
authors are allowed to project into payload, filter on, or use as a lookback
column. Authors never name raw tables or column lists themselves — that
keeps "what fields exist on a recipient" a tenant-stable contract instead
of a per-workflow free-form string.

Design intent:

  - The catalog is **engineering-owned**, not user-editable. Adding a source
    is a code change reviewed alongside any new fact / dimension table.
  - The catalog drives both **runtime SQL compilation** (cohort query) and
    **builder authoring affordances** (which fields show up in the
    payload-field picker, which columns are filter-able).
  - Per-app sources scope authoring: a workflow under ``app_id='inside-sales'``
    sees CRM sources; a workflow under a clinical app sees clinical sources.
    A single source may be shared across apps when its row-level security
    naturally filters by ``app_id`` (the cohort compiler always adds the
    tenant + app filter, regardless of catalog config).
  - The legacy ``source_table`` / ``id_column`` config remains supported via
    the normalization layer so old saved definitions and seed JSON load
    without churn — but new authoring should produce ``source_ref``.

This is the Commit 1 catalog scaffolding. A later commit will surface it
through an API route for builder dropdowns; this commit only wires the
in-process registry needed by the contract.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional, Union

from pydantic import BaseModel, Field
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mixins.shareable import Visibility
from app.models.orchestration import CohortDataset, CohortDatasetVersion


class CohortSource(BaseModel):
    """One registered cohort source.

    ``schema_qualified_table`` is always written ``schema.table`` (never
    bare) so cohort-query SQL is schema-qualified per the project invariant.
    ``allowed_payload_columns`` and ``allowed_filter_columns`` may overlap.
    ``allowed_lookback_columns`` lists timestamp columns valid for the
    ``lookback_hours`` mechanic; if empty, lookback is not supported on
    this source.
    ``jsonb_keys`` is populated at resolution time by ``resolve_source`` after
    live introspection; the compiler uses it to route column references to
    ``src.raw_payload->>'key'`` instead of bare ``src.key``.
    """
    source_ref: str
    display_label: str
    description: str
    workflow_types: list[str]  # ["crm"], ["clinical"], or both
    app_ids: list[str]
    schema_qualified_table: str
    id_column: str
    allowed_payload_columns: list[str] = Field(default_factory=list)
    allowed_filter_columns: list[str] = Field(default_factory=list)
    allowed_lookback_columns: list[str] = Field(default_factory=list)
    # Live-derived JSONB key set — populated by resolve_source, not the static catalog.
    jsonb_keys: list[str] = Field(default_factory=list)


_CATALOG: dict[str, CohortSource] = {
    "crm.lead_record": CohortSource(
        source_ref="crm.lead_record",
        display_label="CRM Leads",
        description="Lead records ingested from LeadSquared (analytics.crm_lead_record).",
        workflow_types=["crm"],
        app_ids=["inside-sales"],
        schema_qualified_table="analytics.crm_lead_record",
        # Real id column post-Alembic-0043; prospect_id moved to raw_payload.
        id_column="lead_id",
        # Curation hints are intentionally empty — the live field set (real
        # columns + raw_payload JSONB keys) is derived at request time by
        # _introspect_static_schema_descriptor so it can never drift.
        allowed_payload_columns=[],
        allowed_filter_columns=[],
        allowed_lookback_columns=["created_on"],
    ),
    "clinical.dim_patient": CohortSource(
        source_ref="clinical.dim_patient",
        display_label="Clinical Patients",
        description="Active patient roster (clinical.dim_patient). Outbox-backed in v1.",
        workflow_types=["clinical"],
        app_ids=["inside-sales"],  # mounted under inside-sales until a dedicated care-pathways app pack ships
        schema_qualified_table="clinical.dim_patient",
        id_column="patient_id",
        allowed_payload_columns=[
            "first_name", "last_name", "preferred_language",
            "primary_condition", "active",
            "hba1c_latest", "hba1c_prior", "ldl_latest",
            "weight_kg", "bmi", "sbp_latest", "dbp_latest",
            "last_visit_at",
        ],
        allowed_filter_columns=[
            "primary_condition", "active", "hba1c_latest",
            "ldl_latest", "preferred_language",
        ],
        allowed_lookback_columns=["last_visit_at"],
    ),
}


class SourceCatalogError(KeyError):
    pass


def get_source(source_ref: str) -> CohortSource:
    if source_ref not in _CATALOG:
        raise SourceCatalogError(f"unknown source_ref: {source_ref!r}")
    return _CATALOG[source_ref]


def lookup_source(source_ref: str) -> Optional[CohortSource]:
    return _CATALOG.get(source_ref)


def list_sources(
    *,
    workflow_type: Optional[str] = None,
    app_id: Optional[str] = None,
) -> list[CohortSource]:
    """Filter sources by workflow type and / or app id."""
    out: list[CohortSource] = []
    for s in _CATALOG.values():
        if workflow_type and workflow_type not in s.workflow_types:
            continue
        if app_id and app_id not in s.app_ids:
            continue
        out.append(s)
    return sorted(out, key=lambda s: s.source_ref)


def all_source_refs() -> list[str]:
    return sorted(_CATALOG.keys())


# ─── Phase 12 — DB-backed dataset sources ─────────────────────────────────
#
# Datasets are tenant-owned, user-uploaded cohort sources persisted in
# ``orchestration.cohort_dataset_versions``. They sit alongside the static
# engineering-owned catalog above: the ``resolve_source`` async helper
# returns a discriminated union covering both kinds so the cohort-query
# compiler can branch on the value type without re-doing the lookup.
#
# Static entries are returned as ``CohortSource`` (pydantic) by both the
# sync ``lookup_source`` helper and the async ``resolve_source``. Dataset
# entries are returned as ``DatasetSource`` (frozen dataclass) — this
# mirrors ``ImportedDataset`` in ``datasets/csv_importer.py`` and signals
# "value object resolved from a single DB row" rather than a
# pydantic-validated request/response model.

_DATASET_PREFIX = "dataset."


@dataclass(frozen=True)
class DatasetSource:
    """One DB-backed dataset version exposed as a cohort source.

    ``schema_descriptor`` is the JSONB blob persisted on
    ``cohort_dataset_versions.schema_descriptor`` (shape:
    ``{"columns": [{name, type, sample_values, distinct_count}], "row_count": int}``).
    The Phase 12 / Task 6 compiler branch reads it for type-aware predicate
    emission against ``orchestration.cohort_dataset_rows.payload``.
    """
    source_ref: str
    dataset_id: uuid.UUID
    dataset_version_id: uuid.UUID
    display_label: str
    workflow_types: list[str]
    app_id: str
    id_strategy: str  # 'column' or 'uuid'
    id_column: Optional[str]
    schema_descriptor: dict
    version_number: int = 0
    row_count: int = 0
    imported_at: Optional[datetime] = None


ResolvedSource = Union[CohortSource, DatasetSource]


def _row_to_dataset_source(
    version: CohortDatasetVersion,
    dataset: CohortDataset,
) -> DatasetSource:
    return DatasetSource(
        source_ref=f"{_DATASET_PREFIX}{version.id}",
        dataset_id=dataset.id,
        dataset_version_id=version.id,
        display_label=f"{dataset.name} (v{version.version_number})",
        workflow_types=["*"],
        app_id=dataset.app_id,
        version_number=version.version_number,
        row_count=version.row_count,
        imported_at=version.imported_at,
        id_strategy=version.id_strategy,
        id_column=version.id_column,
        schema_descriptor=dict(version.schema_descriptor or {}),
    )


async def _load_dataset_source(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    source_ref: str,
) -> DatasetSource:
    suffix = source_ref[len(_DATASET_PREFIX):]
    try:
        version_id = uuid.UUID(suffix)
    except ValueError as exc:
        raise SourceCatalogError(
            f"malformed dataset source_ref: {source_ref!r}"
        ) from exc

    stmt = (
        select(CohortDatasetVersion, CohortDataset)
        .join(CohortDataset, CohortDatasetVersion.dataset_id == CohortDataset.id)
        .where(
            CohortDatasetVersion.id == version_id,
            CohortDatasetVersion.tenant_id == tenant_id,
        )
    )
    result = await db.execute(stmt)
    row = result.first()
    if row is None:
        raise SourceCatalogError(
            f"dataset version not found or not owned by tenant: {source_ref}"
        )
    version, dataset = row
    return _row_to_dataset_source(version, dataset)


# ─── Live schema introspection (shared by API layer + run path) ───────────
#
# ONE introspection. The builder column picker (API layer) and the cohort
# run path (resolve_source) both read the live field set from this function
# so they can never drift — a JSONB key the FE offers is the same key the
# compiler routes through ``raw_payload->>'key'``.

_PLAIN_IDENT_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
_SCHEMA_TABLE_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*$")

# Infra/mixin columns that are never authoring-visible payload or filter fields.
_INFRA_COLUMNS: frozenset[str] = frozenset({
    "id", "tenant_id", "app_id", "created_at", "updated_at",
    "source_system", "source_record_hash",
    "first_synced_at", "last_synced_at", "last_seen_in_source_at",
    "last_synced_by_user_id",
    "raw_payload",  # the JSONB container itself is never a filter field
})

# Map information_schema data_type strings → frontend CohortColumnType literals.
_PG_TYPE_MAP: dict[str, str] = {
    "character varying": "string",
    "text": "string",
    "uuid": "string",
    "character": "string",
    "smallint": "integer",
    "integer": "integer",
    "bigint": "integer",
    "numeric": "number",
    "decimal": "number",
    "real": "number",
    "double precision": "number",
    "boolean": "boolean",
}


def _pg_type_to_cohort_type(pg_type: str) -> str:
    if pg_type in _PG_TYPE_MAP:
        return _PG_TYPE_MAP[pg_type]
    if pg_type.startswith("timestamp") or pg_type == "date":
        return "datetime"
    return "string"


async def introspect_static_schema_descriptor(
    db: AsyncSession,
    *,
    schema_qualified_table: str,
    tenant_id: uuid.UUID,
    app_id: str,
    allowed_columns: Optional[set[str]] = None,
) -> dict[str, Any]:
    """Query information_schema + raw_payload JSONB keys for the given table.

    Returns a schema_descriptor with all authoring-visible columns:
      - Real columns (non-infra, non-raw_payload) from information_schema
      - Distinct JSONB keys from raw_payload for this tenant+app

    Each column entry carries: {name, type, isJsonb}.
    ``allowed_columns`` is an optional curation filter; when None (or empty)
    all non-infra columns are included so the live set can never drift.
    """
    # Guard the table identifier before any interpolation — catalog config only.
    if not _SCHEMA_TABLE_RE.match(schema_qualified_table):
        raise SourceCatalogError(f"invalid schema-qualified table: {schema_qualified_table!r}")
    dot_pos = schema_qualified_table.index(".")
    tbl_schema = schema_qualified_table[:dot_pos]
    tbl_name = schema_qualified_table[dot_pos + 1:]

    real_stmt = text(
        "SELECT column_name, data_type"
        " FROM information_schema.columns"
        " WHERE table_schema = :tbl_schema AND table_name = :tbl_name"
        " ORDER BY ordinal_position"
    )
    result = await db.execute(real_stmt, {"tbl_schema": tbl_schema, "tbl_name": tbl_name})
    all_rows = result.all()

    columns: list[dict] = []
    has_raw_payload = False

    for col_name, data_type in all_rows:
        if col_name == "raw_payload":
            has_raw_payload = True
            continue
        if col_name in _INFRA_COLUMNS:
            continue
        if allowed_columns and col_name not in allowed_columns:
            continue
        columns.append({"name": col_name, "type": _pg_type_to_cohort_type(data_type), "isJsonb": False})

    jsonb_keys: list[str] = []
    if has_raw_payload:
        # schema_qualified_table is regex-validated above (``schema.table``,
        # catalog config never user input) — safe to interpolate.
        jsonb_stmt = text(
            f"SELECT DISTINCT jsonb_object_keys(raw_payload)"  # noqa: S608
            f" FROM {schema_qualified_table}"
            " WHERE tenant_id = :tenant_id AND app_id = :app_id"
            " LIMIT 200"
        )
        jresult = await db.execute(
            jsonb_stmt, {"tenant_id": str(tenant_id), "app_id": app_id}
        )
        for (key,) in jresult.all():
            if _PLAIN_IDENT_RE.match(key):
                jsonb_keys.append(key)
        jsonb_keys.sort()
        for key in jsonb_keys:
            columns.append({"name": key, "type": "string", "isJsonb": True})

    return {"columns": columns, "jsonb_keys": jsonb_keys}


async def _enrich_static_jsonb_keys(
    db: AsyncSession,
    source: CohortSource,
    *,
    tenant_id: uuid.UUID,
    app_id: Optional[str],
) -> CohortSource:
    """Populate ``jsonb_keys`` on a static source via one live introspection.

    Falls back to the source's first declared app_id when the caller has no
    app context (e.g. the dataset-only resolver path). Returns the source
    unchanged when no app can be resolved — the compiler then emits bare
    columns, matching pre-enrichment behaviour for real-column-only configs.
    """
    eff_app_id = app_id or (source.app_ids[0] if source.app_ids else None)
    if eff_app_id is None:
        return source
    descriptor = await introspect_static_schema_descriptor(
        db,
        schema_qualified_table=source.schema_qualified_table,
        tenant_id=tenant_id,
        app_id=eff_app_id,
    )
    return source.model_copy(update={"jsonb_keys": list(descriptor.get("jsonb_keys", []))})


async def resolve_source(
    source_ref: str,
    *,
    db: AsyncSession,
    tenant_id: uuid.UUID,
    app_id: Optional[str] = None,
) -> ResolvedSource:
    """Resolve a source_ref against the static catalog or DB-backed datasets.

    Static entries hit the in-process ``_CATALOG`` and are enriched with their
    live ``jsonb_keys`` via one introspection (so the run path routes JSONB
    keys through ``raw_payload->>'key'`` exactly as the builder column picker
    does). ``dataset.<uuid>`` entries are looked up against
    ``orchestration.cohort_dataset_versions`` filtered by ``tenant_id``.
    Cross-tenant access raises ``SourceCatalogError`` (the route layer maps
    it to 404 — never leak existence).
    """
    if source_ref in _CATALOG:
        return await _enrich_static_jsonb_keys(
            db, _CATALOG[source_ref], tenant_id=tenant_id, app_id=app_id,
        )
    if source_ref.startswith(_DATASET_PREFIX):
        return await _load_dataset_source(db, tenant_id=tenant_id, source_ref=source_ref)
    raise SourceCatalogError(f"unknown source_ref: {source_ref!r}")


async def list_dataset_sources(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: Optional[uuid.UUID] = None,
    app_id: Optional[str] = None,
    app_ids: Optional[list[str]] = None,
) -> list[DatasetSource]:
    """Return all dataset versions for the given tenant and app scope.

    Version pinning is the Phase 12 contract: re-uploading creates v2, but
    workflows pinned to v1 must still be authorable/viewable. The source
    catalog therefore exposes every version, not just the latest.
    """
    stmt = (
        select(CohortDatasetVersion, CohortDataset)
        .join(CohortDataset, CohortDatasetVersion.dataset_id == CohortDataset.id)
        .where(CohortDataset.tenant_id == tenant_id)
        .order_by(
            CohortDataset.name.asc(),
            CohortDatasetVersion.version_number.desc(),
        )
    )
    if app_id is not None:
        stmt = stmt.where(CohortDataset.app_id == app_id)
    elif app_ids is not None:
        if not app_ids:
            return []
        stmt = stmt.where(CohortDataset.app_id.in_(app_ids))
    if user_id is not None:
        stmt = stmt.where(
            or_(
                CohortDataset.created_by == user_id,
                CohortDataset.visibility == Visibility.SHARED,
            )
        )

    result = await db.execute(stmt)
    sources = [_row_to_dataset_source(version, dataset) for version, dataset in result.all()]
    return sources


__all__ = [
    "CohortSource",
    "DatasetSource",
    "ResolvedSource",
    "SourceCatalogError",
    "get_source",
    "lookup_source",
    "list_sources",
    "list_dataset_sources",
    "resolve_source",
    "all_source_refs",
    "introspect_static_schema_descriptor",
]

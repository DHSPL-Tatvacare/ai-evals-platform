"""Phase 11 (Commit 2) — source catalog API surface.

Surfaces ``backend/app/services/orchestration/source_catalog.py`` to the
frontend so the SourceSelector editor can populate the source dropdown,
the payload-field picker, and the filter-column picker without the
builder having to know table names.

Phase 12: extended to merge tenant-owned dataset versions alongside the
engineering-owned static catalog. The response carries a ``kind``
discriminator so the frontend picker can group the two visually. Dataset
entries derive their allowed-column lists from the persisted
``schema_descriptor`` (lookback columns = datetime-typed columns).

Phase 13 (JSONB unpack): static sources with a ``raw_payload`` JSONB column
surface their distinct JSONB keys alongside real columns so the column
picker never drifts from the actual DB schema.
"""
from __future__ import annotations

import re
import uuid
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.orchestration import CohortSourceResponse
from app.services.orchestration.source_catalog import (
    CohortSource,
    DatasetSource,
    list_dataset_sources,
    list_sources,
    lookup_source,
)


# Where dataset rows physically live — surfaced for callers that may want
# to display it. The compiler's JSONB branch (Phase 12 / Task 6) is the
# only consumer that actually executes against this table.
_DATASET_ROWS_TABLE = "orchestration.cohort_dataset_rows"

# Reuse the same identifier safety regex as the cohort query compiler.
_PLAIN_IDENT_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

_MAX_VALUES_LIMIT = 50

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


async def _introspect_static_schema_descriptor(
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
        # Apply optional curation allowlist (only when non-empty)
        if allowed_columns and col_name not in allowed_columns:
            continue
        columns.append({"name": col_name, "type": _pg_type_to_cohort_type(data_type), "isJsonb": False})

    # Fetch distinct JSONB keys from raw_payload for this tenant+app
    jsonb_keys: list[str] = []
    if has_raw_payload:
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


async def fetch_column_values(
    db: AsyncSession,
    *,
    source_ref: str,
    column: str,
    tenant_id: uuid.UUID,
    app_id: str,
    q: Optional[str],
    limit: int,
) -> dict[str, Any]:
    """Return distinct values for a filter column on a static or dataset source.

    Enforces:
    - column identifier regex (no injection)
    - column must be in the live field set (real columns + JSONB keys); the
      static catalog's allowed_filter_columns lists are curation hints only
    - tenant_id + app_id predicates always present
    - limit capped at _MAX_VALUES_LIMIT
    """
    limit = min(limit, _MAX_VALUES_LIMIT)

    if not _PLAIN_IDENT_RE.match(column):
        raise HTTPException(status_code=400, detail=f"invalid column identifier: {column!r}")

    static_source = lookup_source(source_ref)
    if static_source is not None:
        # Derive live field set and validate against it (prevents drift from hardcoded list)
        descriptor = await _introspect_static_schema_descriptor(
            db,
            schema_qualified_table=static_source.schema_qualified_table,
            tenant_id=tenant_id,
            app_id=app_id,
        )
        col_entry = next(
            (c for c in descriptor["columns"] if c["name"] == column), None
        )
        if col_entry is None:
            raise HTTPException(
                status_code=400,
                detail=f"column {column!r} is not in allowed_filter_columns for {source_ref!r}",
            )
        if col_entry.get("isJsonb"):
            return await _fetch_static_jsonb_column_values(
                db,
                table=static_source.schema_qualified_table,
                column=column,
                tenant_id=tenant_id,
                app_id=app_id,
                q=q,
                limit=limit,
            )
        return await _fetch_static_column_values(
            db,
            table=static_source.schema_qualified_table,
            column=column,
            tenant_id=tenant_id,
            app_id=app_id,
            q=q,
            limit=limit,
        )

    # Dataset source: source_ref = "dataset.<uuid>"
    from app.services.orchestration.source_catalog import resolve_source, DatasetSource, SourceCatalogError
    try:
        resolved = await resolve_source(source_ref, db=db, tenant_id=tenant_id)
    except SourceCatalogError:
        raise HTTPException(status_code=404, detail=f"source not found: {source_ref!r}")

    if not isinstance(resolved, DatasetSource):
        raise HTTPException(status_code=404, detail=f"source not found: {source_ref!r}")

    cols_from_schema = {
        c["name"]
        for c in (resolved.schema_descriptor.get("columns") or [])
        if isinstance(c, dict) and c.get("name")
    }
    if column not in cols_from_schema:
        raise HTTPException(
            status_code=400,
            detail=f"column {column!r} is not in allowed_filter_columns for {source_ref!r}",
        )
    return await _fetch_dataset_column_values(
        db,
        dataset_version_id=resolved.dataset_version_id,
        column=column,
        q=q,
        limit=limit,
    )


async def _fetch_static_column_values(
    db: AsyncSession,
    *,
    table: str,
    column: str,
    tenant_id: uuid.UUID,
    app_id: str,
    q: Optional[str],
    limit: int,
) -> dict[str, Any]:
    # column is regex-validated at call site — safe to interpolate.
    base_sql = (
        f"SELECT DISTINCT {column}::text"
        f" FROM {table}"
        f" WHERE tenant_id = (:tenant_id)::uuid AND app_id = (:app_id)::text"
    )
    params: dict[str, Any] = {
        "tenant_id": tenant_id,
        "app_id": app_id,
        "limit": limit,
    }
    if q:
        base_sql += f" AND {column}::text ILIKE (:q)::text"
        params["q"] = f"%{q}%"
    base_sql += f" ORDER BY 1 LIMIT (:limit)::int"

    result = await db.execute(text(base_sql), params)
    rows = result.all()
    values = [r[0] for r in rows if r[0] is not None]
    return {"values": values, "has_more": len(rows) == limit}


async def _fetch_static_jsonb_column_values(
    db: AsyncSession,
    *,
    table: str,
    column: str,
    tenant_id: uuid.UUID,
    app_id: str,
    q: Optional[str],
    limit: int,
) -> dict[str, Any]:
    # column is regex-validated at call site — safe to use as JSONB key.
    base_sql = (
        f"SELECT DISTINCT raw_payload->>:column_key"
        f" FROM {table}"
        f" WHERE tenant_id = (:tenant_id)::uuid AND app_id = (:app_id)::text"
        f"   AND raw_payload->>:column_key IS NOT NULL"
    )
    params: dict[str, Any] = {
        "column_key": column,
        "tenant_id": tenant_id,
        "app_id": app_id,
        "limit": limit,
    }
    if q:
        base_sql += f" AND (raw_payload->>:column_key) ILIKE (:q)::text"
        params["q"] = f"%{q}%"
    base_sql += f" ORDER BY 1 LIMIT (:limit)::int"

    result = await db.execute(text(base_sql), params)
    rows = result.all()
    values = [r[0] for r in rows if r[0] is not None]
    return {"values": values, "has_more": len(rows) == limit}


async def _fetch_dataset_column_values(
    db: AsyncSession,
    *,
    dataset_version_id: uuid.UUID,
    column: str,
    q: Optional[str],
    limit: int,
) -> dict[str, Any]:
    # column is regex-validated at call site — safe to interpolate in the JSONB path.
    base_sql = (
        f"SELECT DISTINCT (payload->>'{column}')"
        " FROM orchestration.cohort_dataset_rows"
        " WHERE dataset_version_id = (:version_id)::uuid"
        f"  AND payload->>'{column}' IS NOT NULL"
    )
    params: dict[str, Any] = {"version_id": dataset_version_id, "limit": limit}
    if q:
        base_sql += f"  AND (payload->>'{column}') ILIKE (:q)::text"
        params["q"] = f"%{q}%"
    base_sql += " ORDER BY 1 LIMIT (:limit)::int"

    result = await db.execute(text(base_sql), params)
    rows = result.all()
    values = [r[0] for r in rows]
    return {"values": values, "has_more": len(rows) == limit}


def _dataset_to_response(ds: DatasetSource) -> CohortSourceResponse:
    columns = ds.schema_descriptor.get("columns") or []
    column_names = [c["name"] for c in columns if isinstance(c, dict) and c.get("name")]
    lookback_names = [
        c["name"]
        for c in columns
        if isinstance(c, dict) and c.get("type") == "datetime" and c.get("name")
    ]
    # ``recipient_id`` is the column the runtime materialises the
    # auto-generated UUID into when ``id_strategy == 'uuid'``; for column
    # strategy we surface the user's chosen id_column.
    id_column = ds.id_column if ds.id_strategy == "column" and ds.id_column else "recipient_id"
    return CohortSourceResponse(
        source_ref=ds.source_ref,
        display_label=ds.display_label,
        description=f"Uploaded dataset version ({len(column_names)} columns).",
        kind="dataset",
        workflow_types=list(ds.workflow_types),
        app_ids=[ds.app_id],
        id_column=id_column,
        allowed_payload_columns=list(column_names),
        allowed_filter_columns=list(column_names),
        allowed_lookback_columns=list(lookback_names),
        schema_descriptor=ds.schema_descriptor,
        row_count=ds.row_count,
        imported_at=ds.imported_at,
    )


async def list_cohort_sources(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: Optional[uuid.UUID] = None,
    workflow_type: Optional[str] = None,
    app_id: Optional[str] = None,
    app_ids: Optional[list[str]] = None,
) -> list[CohortSourceResponse]:
    """Return registered cohort sources, filtered by workflow type / app id.

    Static engineering-owned entries always carry ``kind='static'``; dataset
    entries scoped to ``tenant_id`` carry ``kind='dataset'``. Datasets are
    workflow-type-agnostic — they're returned regardless of the
    ``workflow_type`` filter, since an uploaded list of recipients can drive
    either CRM or clinical pathways.

    The schema-qualified table name is intentionally **not** surfaced —
    authors select sources by ``source_ref``; the underlying table is an
    engineering concern and not authoring config.
    """
    static_app_ids = [app_id] if app_id is not None else (app_ids or None)
    filtered_static = [
        s for s in list_sources(workflow_type=workflow_type, app_id=app_id)
        if static_app_ids is None or any(a in static_app_ids for a in s.app_ids)
    ]

    static_entries: list[CohortSourceResponse] = []
    for s in filtered_static:
        try:
            eff_app_id = app_id or (s.app_ids[0] if s.app_ids else "")
            # Pass allowed_columns=None so all non-infra columns are included
            # (no drift from stale curation hints). Lookback is filtered separately.
            descriptor = await _introspect_static_schema_descriptor(
                db,
                schema_qualified_table=s.schema_qualified_table,
                tenant_id=tenant_id,
                app_id=eff_app_id,
                allowed_columns=None,
            )
        except Exception:
            # Never crash the catalog listing on introspection failure
            descriptor = {"columns": [], "jsonb_keys": []}

        all_col_names = [c["name"] for c in descriptor["columns"]]
        jsonb_keys = descriptor.get("jsonb_keys", [])
        lookback_names = [
            c["name"] for c in descriptor["columns"]
            if not c.get("isJsonb") and c.get("type") == "datetime"
        ]
        # Intersect with catalog curation hint for lookback if provided
        if s.allowed_lookback_columns:
            lookback_names = [n for n in lookback_names if n in set(s.allowed_lookback_columns)]

        static_entries.append(CohortSourceResponse(
            source_ref=s.source_ref,
            display_label=s.display_label,
            description=s.description,
            kind="static",
            workflow_types=list(s.workflow_types),
            app_ids=list(s.app_ids),
            id_column=s.id_column,
            allowed_payload_columns=list(all_col_names),
            allowed_filter_columns=list(all_col_names),
            allowed_lookback_columns=list(lookback_names),
            jsonb_keys=list(jsonb_keys),
            schema_descriptor=descriptor,
        ))
    dataset_entries = [
        _dataset_to_response(ds)
        for ds in await list_dataset_sources(
            db, tenant_id=tenant_id, user_id=user_id, app_id=app_id, app_ids=app_ids,
        )
    ]
    return static_entries + dataset_entries


__all__ = ["list_cohort_sources", "fetch_column_values"]

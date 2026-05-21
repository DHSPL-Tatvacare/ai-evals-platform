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

# Map Postgres data_type strings → frontend CohortColumnType literals.
_PG_TYPE_MAP: dict[str, str] = {
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
    """Map a Postgres data_type value to a frontend CohortColumnType literal."""
    if pg_type in _PG_TYPE_MAP:
        return _PG_TYPE_MAP[pg_type]
    if pg_type.startswith("timestamp") or pg_type == "date":
        return "datetime"
    return "string"


async def _introspect_static_schema_descriptor(
    db: AsyncSession,
    *,
    schema_qualified_table: str,
    allowed_columns: set[str],
) -> dict[str, Any]:
    """Query information_schema.columns for the given table and return schema_descriptor.

    Only columns present in ``allowed_columns`` are included; missing ones are
    silently omitted (the table may not exist yet or the column list may be aspirational).
    Params are bound — never interpolated — so the schema/table pair is safe.
    """
    dot_pos = schema_qualified_table.index(".")
    tbl_schema = schema_qualified_table[:dot_pos]
    tbl_name = schema_qualified_table[dot_pos + 1:]

    stmt = text(
        "SELECT column_name, data_type"
        " FROM information_schema.columns"
        " WHERE table_schema = :tbl_schema AND table_name = :tbl_name"
        " ORDER BY ordinal_position"
    )
    result = await db.execute(stmt, {"tbl_schema": tbl_schema, "tbl_name": tbl_name})
    columns = [
        {"name": row[0], "type": _pg_type_to_cohort_type(row[1])}
        for row in result.all()
        if row[0] in allowed_columns
    ]
    return {"columns": columns}


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
    - column must be in the source's allowed_filter_columns
    - tenant_id + app_id predicates always present
    - limit capped at _MAX_VALUES_LIMIT
    """
    limit = min(limit, _MAX_VALUES_LIMIT)

    if not _PLAIN_IDENT_RE.match(column):
        raise HTTPException(status_code=400, detail=f"invalid column identifier: {column!r}")

    static_source = lookup_source(source_ref)
    if static_source is not None:
        if column not in static_source.allowed_filter_columns:
            raise HTTPException(
                status_code=400,
                detail=f"column {column!r} is not in allowed_filter_columns for {source_ref!r}",
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
        allowed = (
            set(s.allowed_filter_columns)
            | set(s.allowed_payload_columns)
            | set(s.allowed_lookback_columns)
        )
        schema_desc = await _introspect_static_schema_descriptor(
            db,
            schema_qualified_table=s.schema_qualified_table,
            allowed_columns=allowed,
        )
        static_entries.append(CohortSourceResponse(
            source_ref=s.source_ref,
            display_label=s.display_label,
            description=s.description,
            kind="static",
            workflow_types=list(s.workflow_types),
            app_ids=list(s.app_ids),
            id_column=s.id_column,
            allowed_payload_columns=list(s.allowed_payload_columns),
            allowed_filter_columns=list(s.allowed_filter_columns),
            allowed_lookback_columns=list(s.allowed_lookback_columns),
            schema_descriptor=schema_desc,
        ))
    dataset_entries = [
        _dataset_to_response(ds)
        for ds in await list_dataset_sources(
            db, tenant_id=tenant_id, user_id=user_id, app_id=app_id, app_ids=app_ids,
        )
    ]
    return static_entries + dataset_entries


__all__ = ["list_cohort_sources", "fetch_column_values"]

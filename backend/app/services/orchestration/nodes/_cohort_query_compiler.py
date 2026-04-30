"""Compile source.cohort_query config → INSERT-from-SELECT SQL + bind params.

Materializes the entry cohort directly into workflow_run_recipient_states in
one round-trip. Set algebra at the boundary; per-recipient walking downstream.

Config shape:
  source_table:        FROM target ('analytics.crm_lead_record', 'clinical.dim_patient', ...)
  id_column:           recipient_id source ('lead_id', 'patient_id')
  filters:             list of {column, op, value} — column names regex-validated
  payload_columns:     list of column names to carry into payload JSONB
  lookback_hours:      optional N — adds 'lookback_column >= now() - N hours'
  lookback_column:     required when lookback_hours set
  consent_gate_channel: optional channel — adds NOT EXISTS subquery on workflow_consent_records

SAFETY:
  - All column names and source_table validated against ^[a-zA-Z_][a-zA-Z0-9_.]*$
  - All filter values bound as named params (never interpolated)
  - tenant_id always added to WHERE clause
"""
from __future__ import annotations

import re
import uuid
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class CohortQueryCompileError(ValueError):
    pass


# Plain column identifiers may NOT contain dots. Dots are only legal for
# ``source_table`` (schema-qualified). Reusing one regex for both let bad
# config like ``payload_columns=['some.col']`` survive validation and emit
# ``src.some.col`` SQL — a dotted column reference confuses the planner and
# fails downstream with an opaque "column does not exist" error.
_PLAIN_IDENT_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
_QUALIFIED_IDENT_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)?$")
_SUPPORTED_OPS = {"eq", "neq", "gte", "gt", "lte", "lt", "in", "not_in", "contains"}


class CohortQueryFilter(BaseModel):
    column: str
    op: str
    value: Any

    @field_validator("column")
    @classmethod
    def _validate_column(cls, v: str) -> str:
        if not _PLAIN_IDENT_RE.match(v):
            raise CohortQueryCompileError(f"unsafe column name: {v!r}")
        return v

    @field_validator("op")
    @classmethod
    def _validate_op(cls, v: str) -> str:
        if v not in _SUPPORTED_OPS:
            raise CohortQueryCompileError(f"unsupported filter op: {v!r}")
        return v


class CohortQueryConfig(BaseModel):
    source_table: str
    id_column: str
    filters: list[CohortQueryFilter] = Field(default_factory=list)
    payload_columns: list[str] = Field(default_factory=list)
    lookback_hours: Optional[int] = None
    lookback_column: Optional[str] = None
    consent_gate_channel: Optional[str] = None

    @field_validator("source_table")
    @classmethod
    def _validate_source(cls, v: str) -> str:
        # Schema-qualified names like ``analytics.crm_lead_record`` are valid here.
        if not _QUALIFIED_IDENT_RE.match(v):
            raise CohortQueryCompileError(f"unsafe source_table: {v!r}")
        return v

    @field_validator("id_column", "lookback_column")
    @classmethod
    def _validate_optional_column(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not _PLAIN_IDENT_RE.match(v):
            raise CohortQueryCompileError(f"unsafe column: {v!r}")
        return v

    @field_validator("payload_columns")
    @classmethod
    def _validate_payload(cls, cols: list[str]) -> list[str]:
        for c in cols:
            if not _PLAIN_IDENT_RE.match(c):
                raise CohortQueryCompileError(f"unsafe payload column: {c!r}")
        return cols


def compile_cohort_query(
    cfg: CohortQueryConfig,
    *,
    run_id: uuid.UUID,
    workflow_id: uuid.UUID,
    workflow_version_id: uuid.UUID,
    tenant_id: uuid.UUID,
    app_id: str,
    next_node_id: str,
) -> tuple[str, dict[str, Any]]:
    """Return (sql_string, bind_params)."""

    # Casts disambiguate asyncpg parameter type inference — same param used in
    # both INSERT VALUES (varchar column) and WHERE (varchar column) confuses
    # the driver into raising AmbiguousParameterError. Explicit ::text on string
    # params and ::uuid on tenant_id resolves it.
    where_parts: list[str] = ["src.tenant_id = (:tenant_id)::uuid", "src.app_id = (:app_id)::text"]
    params: dict[str, Any] = {
        "run_id": run_id,
        "workflow_id": workflow_id,
        "workflow_version_id": workflow_version_id,
        "tenant_id": tenant_id,
        "app_id": app_id,
        "next_node_id": next_node_id,
    }

    for i, f in enumerate(cfg.filters):
        bind_name = f"filter_{i}"
        if f.op == "eq":
            where_parts.append(f"src.{f.column} = :{bind_name}")
        elif f.op == "neq":
            where_parts.append(f"src.{f.column} <> :{bind_name}")
        elif f.op == "gte":
            where_parts.append(f"src.{f.column} >= :{bind_name}")
        elif f.op == "gt":
            where_parts.append(f"src.{f.column} > :{bind_name}")
        elif f.op == "lte":
            where_parts.append(f"src.{f.column} <= :{bind_name}")
        elif f.op == "lt":
            where_parts.append(f"src.{f.column} < :{bind_name}")
        elif f.op == "in":
            where_parts.append(f"src.{f.column} = ANY(:{bind_name})")
        elif f.op == "not_in":
            where_parts.append(f"src.{f.column} <> ALL(:{bind_name})")
        elif f.op == "contains":
            where_parts.append(f"src.{f.column} ILIKE :{bind_name}")
            params[bind_name] = f"%{f.value}%"
            continue
        params[bind_name] = f.value

    if cfg.lookback_hours is not None:
        if not cfg.lookback_column:
            raise CohortQueryCompileError("lookback_column required when lookback_hours is set")
        # lookback_hours is an int (Pydantic-validated), so embedding it directly is safe.
        where_parts.append(
            f"src.{cfg.lookback_column} >= now() - INTERVAL '{int(cfg.lookback_hours)} hours'"
        )

    if cfg.consent_gate_channel:
        where_parts.append(
            "NOT EXISTS ("
            "  SELECT 1 FROM orchestration.workflow_consent_records c"
            "  WHERE c.tenant_id = (:tenant_id)::uuid AND c.app_id = (:app_id)::text"
            f"    AND c.recipient_id = (src.{cfg.id_column})::text"
            "    AND c.channel = (:consent_channel)::text"
            "    AND c.status = 'opted_out'"
            ")"
        )
        params["consent_channel"] = cfg.consent_gate_channel

    where_clause = " AND ".join(where_parts)

    if cfg.payload_columns:
        payload_args = ", ".join(f"'{c}', src.{c}" for c in cfg.payload_columns)
        payload_expr = f"jsonb_build_object({payload_args})"
    else:
        payload_expr = "'{}'::jsonb"

    # Casts on every parameter — asyncpg deduces types from first use across
    # SELECT-list and WHERE; mixed varchar/text/uuid contexts trigger
    # AmbiguousParameterError. Explicit casts give the driver one answer.
    sql = f"""
        INSERT INTO orchestration.workflow_run_recipient_states
            (id, tenant_id, app_id, workflow_id, workflow_version_id,
             run_id, recipient_id, current_node_id, status, payload, enrolled_at)
        SELECT
            gen_random_uuid(),
            (:tenant_id)::uuid,
            (:app_id)::text,
            (:workflow_id)::uuid,
            (:workflow_version_id)::uuid,
            (:run_id)::uuid,
            src.{cfg.id_column}::text,
            (:next_node_id)::text,
            'ready',
            {payload_expr},
            now()
        FROM {cfg.source_table} src
        WHERE {where_clause}
        ON CONFLICT (run_id, recipient_id) DO NOTHING
        RETURNING recipient_id
    """.strip()

    return sql, params

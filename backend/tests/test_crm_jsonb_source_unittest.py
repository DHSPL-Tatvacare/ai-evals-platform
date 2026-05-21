"""Tests for CRM lead_record JSONB-aware cohort source — real + JSONB column unification.

Covers:
  - id_column = 'lead_id' (not 'prospect_id')
  - CohortSource.jsonb_keys field exists
  - Compiler emits raw_payload->> for JSONB keys and src.col for real columns
  - fetch_column_values validates against live field set and resolves JSONB keys
  - useCohortColumnValues sends appId (FE behaviour verified via TypeScript compile)
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from app.services.orchestration.nodes._cohort_query_compiler import (
    CohortQueryConfig,
    CohortQueryCompileError,
    compile_cohort_query,
)
from app.services.orchestration.source_catalog import (
    CohortSource,
    get_source,
    lookup_source,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


def _static_crm_source_with_jsonb(jsonb_keys: list[str]) -> CohortSource:
    """CRM source with live-derived jsonb_keys (as populated by the API layer)."""
    s = get_source("crm.lead_record")
    # Return a copy with the jsonb_keys populated (simulating API layer introspection)
    return s.model_copy(update={"jsonb_keys": jsonb_keys})


def _compile(cfg: CohortQueryConfig, source: CohortSource):
    return compile_cohort_query(
        cfg,
        run_id=uuid.uuid4(),
        workflow_id=uuid.uuid4(),
        workflow_version_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        app_id="inside-sales",
        next_node_id="n1",
        resolved_source=source,
    )


# ─── 1. Catalog correctness ───────────────────────────────────────────────────


def test_crm_source_id_column_is_lead_id():
    """After Alembic 0043 the real id column is lead_id, not prospect_id."""
    s = get_source("crm.lead_record")
    assert s.id_column == "lead_id", (
        f"id_column must be 'lead_id', got {s.id_column!r}. "
        "prospect_id lives in raw_payload, not as a real column."
    )


def test_crm_source_has_jsonb_keys_field():
    """CohortSource must have a jsonb_keys field (default empty list)."""
    s = lookup_source("crm.lead_record")
    assert s is not None
    assert hasattr(s, "jsonb_keys"), "CohortSource must have a jsonb_keys attribute"
    assert isinstance(s.jsonb_keys, list)


def test_crm_source_schema_qualified_table():
    s = get_source("crm.lead_record")
    assert s.schema_qualified_table == "analytics.crm_lead_record"


# ─── 2. Compiler: real column → src.col ───────────────────────────────────────


def test_compiler_real_column_emits_bare_src_col():
    """A column NOT in jsonb_keys resolves to src.<col> (not raw_payload)."""
    source = _static_crm_source_with_jsonb(jsonb_keys=["prospect_stage", "plan_name"])
    cfg = CohortQueryConfig(
        source_ref="crm.lead_record",
        filters=[{"column": "city", "op": "eq", "value": "Mumbai"}],
    )
    sql, params = _compile(cfg, source)
    # city is a real column (not in jsonb_keys) → bare src.city
    assert "src.city = :filter_0" in sql
    assert "raw_payload" not in sql
    assert params["filter_0"] == "Mumbai"


def test_compiler_emits_lead_id_not_prospect_id_in_recipient():
    """INSERT SELECT uses src.lead_id::text for the recipient_id column."""
    source = _static_crm_source_with_jsonb(jsonb_keys=[])
    cfg = CohortQueryConfig(source_ref="crm.lead_record")
    sql, _params = _compile(cfg, source)
    assert "src.lead_id::text" in sql
    assert "src.prospect_id" not in sql


# ─── 3. Compiler: JSONB key → src.raw_payload->> ─────────────────────────────


def test_compiler_jsonb_key_emits_raw_payload_extraction():
    """A column in jsonb_keys emits src.raw_payload->>'<key>' (not src.<key>)."""
    source = _static_crm_source_with_jsonb(jsonb_keys=["prospect_stage", "plan_name"])
    cfg = CohortQueryConfig(
        source_ref="crm.lead_record",
        filters=[{"column": "prospect_stage", "op": "eq", "value": "Interested"}],
    )
    sql, params = _compile(cfg, source)
    assert "src.raw_payload->>'prospect_stage' = :filter_0" in sql
    assert "src.prospect_stage" not in sql
    assert params["filter_0"] == "Interested"


def test_compiler_mixed_real_and_jsonb_filters():
    """Filters can mix real columns and JSONB keys in the same query."""
    source = _static_crm_source_with_jsonb(jsonb_keys=["prospect_stage"])
    cfg = CohortQueryConfig(
        source_ref="crm.lead_record",
        filters=[
            {"column": "city", "op": "eq", "value": "Delhi"},       # real column
            {"column": "prospect_stage", "op": "eq", "value": "MQL"},  # JSONB key
        ],
    )
    sql, params = _compile(cfg, source)
    assert "src.city = :filter_0" in sql
    assert "src.raw_payload->>'prospect_stage' = :filter_1" in sql
    assert params["filter_0"] == "Delhi"
    assert params["filter_1"] == "MQL"


def test_compiler_payload_projection_jsonb_key_uses_raw_payload():
    """Payload projection for a JSONB key uses raw_payload->>'key', not src.key."""
    source = _static_crm_source_with_jsonb(jsonb_keys=["prospect_stage"])
    cfg = CohortQueryConfig(
        source_ref="crm.lead_record",
        payload_fields=["city", "prospect_stage"],  # city=real, prospect_stage=JSONB
    )
    sql, _params = _compile(cfg, source)
    # city → src.city; prospect_stage → src.raw_payload->>'prospect_stage'
    assert "'city', src.city" in sql
    assert "'prospect_stage', src.raw_payload->>'prospect_stage'" in sql


def test_compiler_static_legacy_path_unaffected():
    """_compile_static_legacy (no resolved_source) still emits bare src.col for all cols."""
    cfg = CohortQueryConfig(
        source_ref="crm.lead_record",
        filters=[{"column": "city", "op": "eq", "value": "Chennai"}],
    )
    # Call without resolved_source → legacy path
    sql, params = compile_cohort_query(
        cfg,
        run_id=uuid.uuid4(),
        workflow_id=uuid.uuid4(),
        workflow_version_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        app_id="inside-sales",
        next_node_id="n1",
        resolved_source=None,
    )
    assert "src.city = :filter_0" in sql
    # Lead_id comes from catalog now
    assert "src.lead_id::text" in sql


# ─── 4. fetch_column_values: live validation + JSONB resolution ───────────────


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


def _make_introspect_side_effect(
    real_cols: list[tuple[str, str]],
    jsonb_keys: list[str],
):
    """Return an async side_effect list for db.execute covering introspection + values query.

    The first call = information_schema real columns.
    The second call = jsonb_object_keys (if table has raw_payload col).
    Subsequent calls return an empty FakeResult (values query handled by caller).
    """
    infra_call = _FakeResult(real_cols)
    jsonb_call = _FakeResult([(k,) for k in jsonb_keys])

    async def _side_effect(*args, **kwargs):
        return _side_effect._results.pop(0)
    _side_effect._results = [infra_call, jsonb_call]
    return _side_effect


@pytest.mark.asyncio
async def test_fetch_column_values_real_column_emits_select_distinct():
    """Real column (in information_schema) resolves to SELECT DISTINCT col."""
    from app.services.orchestration.api.source_catalog import fetch_column_values

    tenant_id = uuid.uuid4()
    db = AsyncMock()
    # Call 1: information_schema returns city as text
    # Call 2: jsonb_object_keys returns prospect_stage
    # Call 3: the values query
    db.execute.side_effect = [
        _FakeResult([("id", "uuid"), ("tenant_id", "uuid"), ("app_id", "text"),
                     ("lead_id", "character varying"), ("first_name", "character varying"),
                     ("city", "text"), ("created_on", "timestamp with time zone"),
                     ("raw_payload", "jsonb")]),
        _FakeResult([("prospect_stage",), ("plan_name",)]),
        _FakeResult([("Mumbai",), ("Delhi",)]),
    ]

    result = await fetch_column_values(
        db,
        source_ref="crm.lead_record",
        column="city",
        tenant_id=tenant_id,
        app_id="inside-sales",
        q=None,
        limit=10,
    )

    assert result["values"] == ["Mumbai", "Delhi"]
    assert result["has_more"] is False
    # Three calls total: info_schema, jsonb_keys, values
    assert db.execute.call_count == 3


@pytest.mark.asyncio
async def test_fetch_column_values_jsonb_key_emits_raw_payload_query():
    """JSONB key resolves to SELECT DISTINCT raw_payload->>'key'."""
    from app.services.orchestration.api.source_catalog import fetch_column_values

    tenant_id = uuid.uuid4()
    db = AsyncMock()
    db.execute.side_effect = [
        _FakeResult([("id", "uuid"), ("tenant_id", "uuid"), ("app_id", "text"),
                     ("lead_id", "character varying"), ("city", "text"),
                     ("created_on", "timestamp with time zone"),
                     ("raw_payload", "jsonb")]),
        _FakeResult([("prospect_stage",), ("plan_name",)]),
        _FakeResult([("Interested",), ("Hot",)]),
    ]

    result = await fetch_column_values(
        db,
        source_ref="crm.lead_record",
        column="prospect_stage",  # lives in raw_payload
        tenant_id=tenant_id,
        app_id="inside-sales",
        q=None,
        limit=10,
    )

    assert result["values"] == ["Interested", "Hot"]
    # Third call must be the raw_payload->>:column_key query (JSONB branch)
    third_call = db.execute.call_args_list[2]
    sql_text = str(third_call[0][0]).lower()
    assert "raw_payload" in sql_text
    # Column key is bound as a parameter, not interpolated
    params = third_call[0][1] if len(third_call[0]) > 1 else {}
    assert params.get("column_key") == "prospect_stage"


@pytest.mark.asyncio
async def test_fetch_column_values_unknown_column_raises_400():
    """Column not in live field set (real or JSONB) raises HTTPException 400."""
    from fastapi import HTTPException
    from app.services.orchestration.api.source_catalog import fetch_column_values

    tenant_id = uuid.uuid4()
    db = AsyncMock()
    db.execute.side_effect = [
        _FakeResult([("id", "uuid"), ("tenant_id", "uuid"), ("app_id", "text"),
                     ("lead_id", "character varying"), ("city", "text"),
                     ("raw_payload", "jsonb")]),
        _FakeResult([("prospect_stage",)]),
    ]

    with pytest.raises(HTTPException) as exc_info:
        await fetch_column_values(
            db,
            source_ref="crm.lead_record",
            column="completely_unknown_col",
            tenant_id=tenant_id,
            app_id="inside-sales",
            q=None,
            limit=10,
        )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_fetch_column_values_raw_payload_col_itself_rejected():
    """'raw_payload' is an infra column — must not be fetchable as a value column."""
    from fastapi import HTTPException
    from app.services.orchestration.api.source_catalog import fetch_column_values

    tenant_id = uuid.uuid4()
    db = AsyncMock()
    db.execute.side_effect = [
        _FakeResult([("id", "uuid"), ("tenant_id", "uuid"), ("app_id", "text"),
                     ("lead_id", "character varying"), ("city", "text"),
                     ("raw_payload", "jsonb")]),
        _FakeResult([("prospect_stage",)]),
    ]

    with pytest.raises(HTTPException) as exc_info:
        await fetch_column_values(
            db,
            source_ref="crm.lead_record",
            column="raw_payload",
            tenant_id=tenant_id,
            app_id="inside-sales",
            q=None,
            limit=10,
        )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_fetch_column_values_binds_tenant_and_app():
    """Values query always binds tenant_id and app_id."""
    from app.services.orchestration.api.source_catalog import fetch_column_values

    tenant_id = uuid.uuid4()
    db = AsyncMock()
    db.execute.side_effect = [
        _FakeResult([("id", "uuid"), ("tenant_id", "uuid"), ("app_id", "text"),
                     ("lead_id", "character varying"), ("city", "text"),
                     ("raw_payload", "jsonb")]),
        _FakeResult([("prospect_stage",)]),
        _FakeResult([("Mumbai",)]),
    ]

    await fetch_column_values(
        db,
        source_ref="crm.lead_record",
        column="city",
        tenant_id=tenant_id,
        app_id="inside-sales",
        q=None,
        limit=10,
    )

    # Check the values-query call (3rd call) binds tenant_id and app_id
    third_call = db.execute.call_args_list[2]
    params = third_call[0][1] if len(third_call[0]) > 1 else third_call.kwargs.get("parameters", {})
    assert "tenant_id" in params
    assert "app_id" in params
    assert params["tenant_id"] == tenant_id
    assert params["app_id"] == "inside-sales"


@pytest.mark.asyncio
async def test_fetch_column_values_limit_capped():
    """limit > 50 is silently capped to 50."""
    from app.services.orchestration.api.source_catalog import fetch_column_values

    db = AsyncMock()
    db.execute.side_effect = [
        _FakeResult([("city", "text"), ("raw_payload", "jsonb")]),
        _FakeResult([]),
        _FakeResult([]),
    ]

    await fetch_column_values(
        db,
        source_ref="crm.lead_record",
        column="city",
        tenant_id=uuid.uuid4(),
        app_id="inside-sales",
        q=None,
        limit=9999,
    )

    third_call = db.execute.call_args_list[2]
    params = third_call[0][1] if len(third_call[0]) > 1 else third_call.kwargs.get("parameters", {})
    assert params.get("limit") == 50


# ─── 5. CohortSourceResponse.jsonbKeys field ─────────────────────────────────


def test_cohort_source_response_has_jsonb_keys_field():
    """CohortSourceResponse schema must carry jsonbKeys (camelCase) for the FE."""
    from app.schemas.orchestration import CohortSourceResponse

    resp = CohortSourceResponse(
        source_ref="crm.lead_record",
        display_label="CRM Leads",
        description="test",
        kind="static",
        workflow_types=["crm"],
        app_ids=["inside-sales"],
        id_column="lead_id",
        jsonb_keys=["prospect_stage", "plan_name"],
    )
    assert resp.jsonb_keys == ["prospect_stage", "plan_name"]
    # Verify camelCase serialization
    d = resp.model_dump(by_alias=True)
    assert "jsonbKeys" in d
    assert d["jsonbKeys"] == ["prospect_stage", "plan_name"]

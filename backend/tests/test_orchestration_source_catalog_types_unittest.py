"""Tests for datatype-driven cohort filter values — Task 1 + Task 2.

Task 1: static sources carry schema_descriptor.columns with PG-introspected types.
Task 2: distinct-values endpoint security, SQL shape, ILIKE, limit cap, hasMore.

Live-DB tests (marked asyncio + use db_session) hit the local docker postgres.
Pure-logic tests (no db_session) run against fakes.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from app.auth import AuthContext, get_auth_context
from app.constants import SYSTEM_USER_ID
from app.database import get_db
from app.main import app as fastapi_app
from app.models.tenant import Tenant


# ─── helpers ─────────────────────────────────────────────────────────────────


def _make_auth(tenant_id: uuid.UUID) -> AuthContext:
    return AuthContext(
        user_id=SYSTEM_USER_ID,
        tenant_id=tenant_id,
        email="catalog-types@orchestration.local",
        role_id=uuid.uuid4(),
        is_owner=True,
        permissions=frozenset(),
        app_access=frozenset({"inside-sales", "voice-rx", "kaira-bot"}),
    )


def _override_db(db_session):
    async def _g():
        yield db_session
    fastapi_app.dependency_overrides[get_db] = _g
    db_session.commit = db_session.flush  # type: ignore[assignment]


def _override_auth(auth: AuthContext):
    fastapi_app.dependency_overrides[get_auth_context] = lambda: auth


# ─── Task 1: schema_descriptor on static sources (live DB) ───────────────────


@pytest.mark.asyncio
async def test_crm_static_source_has_schema_descriptor_columns(db_session):
    """list_cohort_sources returns schema_descriptor.columns for the CRM static source."""
    import uuid as _uuid
    from app.services.orchestration.api.source_catalog import list_cohort_sources

    tenant_id = _uuid.uuid4()
    db_session.add(Tenant(
        id=tenant_id,
        name=f"catalog-types-{tenant_id.hex[:8]}",
        slug=f"catalog-types-{tenant_id.hex[:8]}",
        is_active=True,
    ))
    await db_session.flush()

    sources = await list_cohort_sources(
        db_session,
        tenant_id=tenant_id,
        app_id="inside-sales",
    )

    crm = next((s for s in sources if s.source_ref == "crm.lead_record"), None)
    assert crm is not None, "crm.lead_record must be in catalog"
    assert crm.schema_descriptor is not None, "static source must carry schema_descriptor"
    cols = crm.schema_descriptor.get("columns", [])
    assert len(cols) > 0, "schema_descriptor.columns must not be empty"

    col_map = {c["name"]: c["type"] for c in cols}

    # created_on is timestamptz → datetime
    assert "created_on" in col_map, "created_on must be in allowed filter columns"
    assert col_map["created_on"] == "datetime", (
        f"expected datetime for created_on, got {col_map['created_on']!r}"
    )

    # city is text → string
    assert "city" in col_map, "city must appear (it is in allowed_payload_columns)"
    assert col_map["city"] == "string", (
        f"expected string for city, got {col_map['city']!r}"
    )


@pytest.mark.asyncio
async def test_static_source_schema_descriptor_omits_non_allowlisted_columns(db_session):
    """Columns not in allowed_filter | allowed_payload | allowed_lookback are absent."""
    import uuid as _uuid
    from app.services.orchestration.api.source_catalog import list_cohort_sources

    tenant_id = _uuid.uuid4()
    db_session.add(Tenant(
        id=tenant_id,
        name=f"catalog-omit-{tenant_id.hex[:8]}",
        slug=f"catalog-omit-{tenant_id.hex[:8]}",
        is_active=True,
    ))
    await db_session.flush()

    sources = await list_cohort_sources(db_session, tenant_id=tenant_id, app_id="inside-sales")
    crm = next((s for s in sources if s.source_ref == "crm.lead_record"), None)
    assert crm is not None
    assert crm.schema_descriptor is not None

    cols = crm.schema_descriptor.get("columns", [])
    col_names = {c["name"] for c in cols}

    # raw_payload, source_record_hash, etc. are not in any allowlist — must be absent
    assert "raw_payload" not in col_names
    assert "source_record_hash" not in col_names
    assert "last_synced_by_user_id" not in col_names


# ─── Task 2: fetch_column_values service logic (fake DB) ─────────────────────


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


@pytest.mark.asyncio
async def test_column_not_in_allowlist_raises_400():
    """Column absent from allowed_filter_columns must raise HTTPException 400."""
    from fastapi import HTTPException
    from app.services.orchestration.api.source_catalog import fetch_column_values

    db = AsyncMock()
    db.execute.return_value = _FakeResult([])

    with pytest.raises(HTTPException) as exc_info:
        await fetch_column_values(
            db,
            source_ref="crm.lead_record",
            column="raw_payload",  # not in allowed_filter_columns
            tenant_id=uuid.uuid4(),
            app_id="inside-sales",
            q=None,
            limit=10,
        )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_invalid_column_identifier_raises_400():
    """Column with an invalid identifier (e.g. SQL-injection attempt) raises 400."""
    from fastapi import HTTPException
    from app.services.orchestration.api.source_catalog import fetch_column_values

    db = AsyncMock()
    db.execute.return_value = _FakeResult([])

    with pytest.raises(HTTPException) as exc_info:
        await fetch_column_values(
            db,
            source_ref="crm.lead_record",
            column="city; DROP TABLE tenants--",
            tenant_id=uuid.uuid4(),
            app_id="inside-sales",
            q=None,
            limit=10,
        )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_fetch_column_values_tenant_predicate_present():
    """The emitted SQL must bind tenant_id and app_id."""
    from app.services.orchestration.api.source_catalog import fetch_column_values

    tenant_id = uuid.uuid4()
    db = AsyncMock()
    db.execute.return_value = _FakeResult([("active",), ("pending",)])

    await fetch_column_values(
        db,
        source_ref="crm.lead_record",
        column="prospect_stage",
        tenant_id=tenant_id,
        app_id="inside-sales",
        q=None,
        limit=50,
    )

    assert db.execute.called
    call_args = db.execute.call_args
    params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]

    # tenant_id and app_id must appear as bind parameters
    assert "tenant_id" in params, "tenant_id must be bound"
    assert "app_id" in params, "app_id must be bound"
    assert params["tenant_id"] == tenant_id
    assert params["app_id"] == "inside-sales"


@pytest.mark.asyncio
async def test_fetch_column_values_ilike_applied_when_q_given():
    """When q is provided, a ILIKE '%q%' predicate must be emitted."""
    from app.services.orchestration.api.source_catalog import fetch_column_values

    db = AsyncMock()
    db.execute.return_value = _FakeResult([("Active",)])

    await fetch_column_values(
        db,
        source_ref="crm.lead_record",
        column="prospect_stage",
        tenant_id=uuid.uuid4(),
        app_id="inside-sales",
        q="act",
        limit=10,
    )

    call_args = db.execute.call_args
    params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
    assert "q" in params, "q must be bound when q arg is non-empty"
    assert params["q"] == "%act%"

    stmt_text = str(call_args[0][0]).upper()
    assert "ILIKE" in stmt_text, "SQL must contain ILIKE when q is given"


@pytest.mark.asyncio
async def test_fetch_column_values_no_ilike_when_q_empty():
    """When q is empty/None, no ILIKE predicate must be emitted."""
    from app.services.orchestration.api.source_catalog import fetch_column_values

    db = AsyncMock()
    db.execute.return_value = _FakeResult([("Active",)])

    await fetch_column_values(
        db,
        source_ref="crm.lead_record",
        column="prospect_stage",
        tenant_id=uuid.uuid4(),
        app_id="inside-sales",
        q=None,
        limit=10,
    )

    call_args = db.execute.call_args
    params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
    assert "q" not in params


@pytest.mark.asyncio
async def test_fetch_column_values_limit_capped_at_50():
    """Caller-supplied limit > 50 must be silently clamped to 50."""
    from app.services.orchestration.api.source_catalog import fetch_column_values

    db = AsyncMock()
    db.execute.return_value = _FakeResult([])

    await fetch_column_values(
        db,
        source_ref="crm.lead_record",
        column="prospect_stage",
        tenant_id=uuid.uuid4(),
        app_id="inside-sales",
        q=None,
        limit=9999,
    )

    call_args = db.execute.call_args
    params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
    assert params.get("limit") == 50, "limit must be capped at 50"


@pytest.mark.asyncio
async def test_fetch_column_values_has_more_true_when_results_equal_limit():
    """has_more=True when result count == limit (there may be more rows)."""
    from app.services.orchestration.api.source_catalog import fetch_column_values

    rows = [(f"val{i}",) for i in range(5)]
    db = AsyncMock()
    db.execute.return_value = _FakeResult(rows)

    result = await fetch_column_values(
        db,
        source_ref="crm.lead_record",
        column="prospect_stage",
        tenant_id=uuid.uuid4(),
        app_id="inside-sales",
        q=None,
        limit=5,
    )

    assert result["has_more"] is True
    assert len(result["values"]) == 5


@pytest.mark.asyncio
async def test_fetch_column_values_has_more_false_when_results_under_limit():
    """has_more=False when result count < limit."""
    from app.services.orchestration.api.source_catalog import fetch_column_values

    rows = [("active",), ("pending",)]
    db = AsyncMock()
    db.execute.return_value = _FakeResult(rows)

    result = await fetch_column_values(
        db,
        source_ref="crm.lead_record",
        column="prospect_stage",
        tenant_id=uuid.uuid4(),
        app_id="inside-sales",
        q=None,
        limit=5,
    )

    assert result["has_more"] is False
    assert result["values"] == ["active", "pending"]


# ─── Task 2: route endpoint (live DB via FastAPI test client) ─────────────────


@pytest_asyncio.fixture
async def route_tenant_id(db_session) -> uuid.UUID:
    tenant_id = uuid.uuid4()
    db_session.add(Tenant(
        id=tenant_id,
        name=f"col-vals-{tenant_id.hex[:8]}",
        slug=f"col-vals-{tenant_id.hex[:8]}",
        is_active=True,
    ))
    await db_session.flush()
    return tenant_id


@pytest_asyncio.fixture
async def client(db_session, route_tenant_id):
    import httpx
    _override_db(db_session)
    _override_auth(_make_auth(route_tenant_id))
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=fastapi_app),
            base_url="http://test",
        ) as c:
            yield c
    finally:
        fastapi_app.dependency_overrides.pop(get_db, None)
        fastapi_app.dependency_overrides.pop(get_auth_context, None)


@pytest.mark.asyncio
async def test_column_values_route_rejects_non_allowlisted_column(client):
    """Route returns 400 for a column not in allowed_filter_columns."""
    r = await client.get(
        "/api/orchestration/source_catalog/crm.lead_record/columns/raw_payload/values"
        "?appId=inside-sales"
    )
    assert r.status_code == 400, r.text


@pytest.mark.asyncio
async def test_column_values_route_returns_200_for_valid_column(client):
    """Route returns 200 for a column that is in allowed_filter_columns."""
    r = await client.get(
        "/api/orchestration/source_catalog/crm.lead_record/columns/city/values"
        "?appId=inside-sales"
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "values" in body
    assert "hasMore" in body
    assert isinstance(body["values"], list)
    assert isinstance(body["hasMore"], bool)

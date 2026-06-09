"""sync-crm-source is the first source-bound workload: list endpoint + launch resolver."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi import HTTPException

from app.auth import AuthContext
from app.constants import SYSTEM_USER_ID
from app.models.provider_connection import ProviderConnection
from app.models.tenant import Tenant
from app.routes import crm as crm_routes
from app.schemas.scheduled_job import ScheduleSourcesResponse
from app.services.crm import scheduling as crm_scheduling
from app.services.scheduler import launch_sources
from app.services.scheduler.workloads import (
    ensure_handler_workloads_registered,
    get_workload,
)


def _auth(tenant_id: uuid.UUID | None = None) -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant_id or uuid.uuid4(),
        email="test@example.com",
        role_id=uuid.uuid4(),
        is_owner=True,
        permissions=frozenset({"orchestration:manage"}),
        app_access=frozenset({"inside-sales"}),
    )


def _connection(tenant_id: uuid.UUID, *, provider: str = "lsq", app_id: str = "inside-sales",
                name: str = "LSQ Prod", created_by: uuid.UUID | None = None) -> ProviderConnection:
    return ProviderConnection(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        app_id=app_id,
        provider=provider,
        name=name,
        config_encrypted=b"x",
        active=True,
        created_by=created_by or uuid.uuid4(),
    )


async def _seed_tenant(db, tenant_id: uuid.UUID) -> None:
    db.add(Tenant(id=tenant_id, name=f"t-{tenant_id.hex[:8]}", slug=f"t-{tenant_id.hex[:8]}", is_active=True))
    await db.flush()


class _FakeScalarResult:
    def __init__(self, items):
        self._items = list(items)

    def all(self):
        return list(self._items)


class _FakeResult:
    def __init__(self, items):
        self._items = list(items)

    def scalars(self):
        return _FakeScalarResult(self._items)


class _FakeSession:
    def __init__(self, *, connections=(), scalar_value=None):
        self._connections = list(connections)
        self._scalar = scalar_value
        self.scalar_calls = 0

    async def execute(self, _stmt):
        return _FakeResult(self._connections)

    async def scalar(self, _stmt):
        self.scalar_calls += 1
        return self._scalar


# ---- the handler is now source-bound -------------------------------------------------


def test_sync_crm_source_is_source_bound_workload():
    ensure_handler_workloads_registered()
    wl = get_workload("", "sync-crm-source")
    assert wl is not None
    assert wl.launch_source == "canonical_config"
    assert wl.source_list_endpoint == "/api/crm/schedule-sources"


# ---- the source-list endpoint ---------------------------------------------------------


@pytest.mark.asyncio
async def test_schedule_sources_lists_one_item_per_dataset(db_session):
    # Live DB so the route's tenant_id WHERE clause is actually exercised: a foreign tenant's
    # connection must NOT surface for the caller (a mock that ignores the predicate can't prove this).
    tenant, foreign = uuid.uuid4(), uuid.uuid4()
    await _seed_tenant(db_session, tenant)
    await _seed_tenant(db_session, foreign)
    conn = _connection(tenant, name="LSQ Prod", created_by=SYSTEM_USER_ID)
    foreign_conn = _connection(foreign, name="Foreign LSQ", created_by=SYSTEM_USER_ID)
    db_session.add_all([conn, foreign_conn])
    await db_session.flush()

    resp = await crm_routes.list_schedule_sources(app_id=None, auth=_auth(tenant), db=db_session)
    assert isinstance(resp, ScheduleSourcesResponse)
    ids = {i.id for i in resp.items}
    assert ids == {f"{conn.id}:lead", f"{conn.id}:activity"}  # only the caller tenant's dataset
    assert all(i.params["connection_id"] == str(conn.id) for i in resp.items)
    lead = next(i for i in resp.items if i.id == f"{conn.id}:lead")
    assert lead.label == "LSQ Prod · Lead"
    assert lead.sublabel == "LSQ Prod"
    assert lead.schedule_key == f"{conn.id}:lead"
    assert lead.params["source_objects"] == ["Lead"]


@pytest.mark.asyncio
async def test_schedule_sources_only_lists_crm_source_connections():
    tenant = uuid.uuid4()
    crm = _connection(tenant, provider="lsq", name="LSQ")
    voice = _connection(tenant, provider="bolna", name="Bolna")
    db = _FakeSession(connections=[crm, voice])
    resp = await crm_routes.list_schedule_sources(app_id=None, auth=_auth(tenant), db=db)
    conn_ids = {i.params["connection_id"] for i in resp.items}
    assert conn_ids == {str(crm.id)}


@pytest.mark.asyncio
async def test_schedule_sources_filters_by_app_id(db_session):
    # Live DB so the optional app_id WHERE clause is actually exercised: a connection in another
    # app must be excluded when app_id is supplied.
    tenant = uuid.uuid4()
    await _seed_tenant(db_session, tenant)
    inside = _connection(tenant, app_id="inside-sales", name="Inside", created_by=SYSTEM_USER_ID)
    voice = _connection(tenant, app_id="voice-rx", name="Voice", created_by=SYSTEM_USER_ID)
    db_session.add_all([inside, voice])
    await db_session.flush()

    resp = await crm_routes.list_schedule_sources(app_id="inside-sales", auth=_auth(tenant), db=db_session)
    assert {i.params["connection_id"] for i in resp.items} == {str(inside.id)}  # voice-rx filtered out
    assert len(resp.items) == 2


def test_schedule_sources_route_gated_orchestration_manage():
    route = next(
        r for r in crm_routes.router.routes
        if getattr(r, "path", None) == "/api/crm/schedule-sources"
    )
    # require_permission injects a _checker closure that closes over the perm ids.
    found = set()
    for dep in route.dependant.dependencies:
        closure = getattr(dep.call, "__closure__", None) or ()
        for cell in closure:
            value = cell.cell_contents
            if isinstance(value, tuple):
                found.update(value)
    assert "orchestration:manage" in found


# ---- the resolver --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolver_builds_canonical_params_from_source_id():
    crm_scheduling.register()
    tenant = uuid.uuid4()
    conn = _connection(tenant, name="LSQ Prod")
    db = _FakeSession(scalar_value=conn)
    spec = await launch_sources.resolve_launch_source(
        db,
        job_type="sync-crm-source",
        tenant_id=tenant,
        app_id="inside-sales",
        source_id=f"{conn.id}:lead",
    )
    assert spec.params == {"connection_id": str(conn.id), "source_objects": ["Lead"]}
    assert spec.schedule_key == f"{conn.id}:lead"
    assert spec.name == "LSQ Prod · Lead sync"


@pytest.mark.asyncio
async def test_resolver_rejects_foreign_connection():
    crm_scheduling.register()
    tenant = uuid.uuid4()
    conn_id = uuid.uuid4()
    db = _FakeSession(scalar_value=None)  # tenant-scoped query returns nothing
    with pytest.raises(ValueError):
        await launch_sources.resolve_launch_source(
            db,
            job_type="sync-crm-source",
            tenant_id=tenant,
            app_id="inside-sales",
            source_id=f"{conn_id}:lead",
        )


@pytest.mark.asyncio
async def test_resolver_rejects_bad_record_type():
    crm_scheduling.register()
    tenant = uuid.uuid4()
    conn = _connection(tenant)
    db = _FakeSession(scalar_value=conn)
    with pytest.raises(ValueError):
        await launch_sources.resolve_launch_source(
            db,
            job_type="sync-crm-source",
            tenant_id=tenant,
            app_id="inside-sales",
            source_id=f"{conn.id}:bogus",
        )

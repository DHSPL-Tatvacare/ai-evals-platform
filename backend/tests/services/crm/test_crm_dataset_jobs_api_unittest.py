"""GET /api/crm/connections/{id}/datasets/{recordType}/jobs — the chain job list + active schedule.

Live-DB route test (real Postgres), fake adapter, tenant-scoped. Seeds chain BackgroundJob rows and an
active ScheduledJobDefinition for the dataset, then asserts the endpoint returns the chain jobs (newest
first) with status/timestamps and the active schedule. A non-owner without ``orchestration:manage`` gets 403.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import httpx
import pytest
import pytest_asyncio

from app.auth import AuthContext, get_auth_context
from app.constants import SYSTEM_USER_ID
from app.database import get_db
from app.main import app as fastapi_app
from app.models.job import BackgroundJob
from app.models.provider_connection import ProviderConnection
from app.models.scheduled_job import ScheduledJobDefinition
from app.models.tenant import Tenant

_APP = "inside-sales"
_VENDOR = "fake-crm"

pytestmark = pytest.mark.asyncio


def _override_db(db_session):
    async def _g():
        yield db_session
    fastapi_app.dependency_overrides[get_db] = _g
    db_session.commit = db_session.flush  # type: ignore[assignment]


def _override_auth(tenant_id: uuid.UUID, *, is_owner: bool, permissions: frozenset[str]):
    auth = AuthContext(
        user_id=SYSTEM_USER_ID, tenant_id=tenant_id, email="t@crm.local",
        role_id=uuid.uuid4(), is_owner=is_owner, permissions=permissions,
        app_access=frozenset({_APP}),
    )
    fastapi_app.dependency_overrides[get_auth_context] = lambda: auth
    return auth


@pytest_asyncio.fixture
async def tenant_id(db_session) -> uuid.UUID:
    tid = uuid.uuid4()
    db_session.add(Tenant(id=tid, name=f"crm-j-{tid.hex[:8]}", slug=f"crm-j-{tid.hex[:8]}", is_active=True))
    await db_session.flush()
    return tid


@pytest_asyncio.fixture
async def connection(db_session, tenant_id) -> ProviderConnection:
    conn = ProviderConnection(
        id=uuid.uuid4(), tenant_id=tenant_id, app_id=_APP, provider=_VENDOR,
        name=f"fake-{uuid.uuid4().hex[:8]}", config_encrypted=b"x", active=True,
        created_by=SYSTEM_USER_ID,
    )
    db_session.add(conn)
    await db_session.flush()
    return conn


@pytest_asyncio.fixture
async def client(db_session, connection, tenant_id):
    _override_db(db_session)
    _override_auth(tenant_id, is_owner=True, permissions=frozenset())
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=fastapi_app), base_url="http://test",
        ) as c:
            yield c
    finally:
        fastapi_app.dependency_overrides.pop(get_db, None)
        fastapi_app.dependency_overrides.pop(get_auth_context, None)


async def _seed_chain_jobs(db_session, tenant_id, connection):
    now = datetime.now(timezone.utc)
    base = {"tenant_id": tenant_id, "user_id": SYSTEM_USER_ID, "app_id": _APP}
    params = {"connection_id": str(connection.id), "app_id": _APP}
    db_session.add(BackgroundJob(
        id=uuid.uuid4(), job_type="sync-crm-source", status="completed",
        params=params, created_at=now, completed_at=now, **base,
    ))
    db_session.add(BackgroundJob(
        id=uuid.uuid4(), job_type="unpack-crm-source", status="running",
        params=params, created_at=now, **base,
    ))
    db_session.add(BackgroundJob(
        id=uuid.uuid4(), job_type="backfill-stage-transitions", status="queued",
        params={"app_id": _APP}, created_at=now, **base,
    ))
    # An unrelated job for the same tenant must NOT appear (not a chain type).
    db_session.add(BackgroundJob(
        id=uuid.uuid4(), job_type="generate-report", status="completed",
        params={"run_id": "x"}, created_at=now, **base,
    ))
    await db_session.flush()


async def test_jobs_returns_chain_and_schedule(client, connection, db_session, tenant_id):
    await _seed_chain_jobs(db_session, tenant_id, connection)
    sched = ScheduledJobDefinition(
        id=uuid.uuid4(), tenant_id=tenant_id, app_id=_APP, job_type="sync-crm-source",
        schedule_key=f"{connection.id}:lead", name="LSQ – CRM · Lead sync", cron="0 */6 * * *",
        params={"connection_id": str(connection.id), "source_objects": ["Lead"]}, enabled=True,
    )
    db_session.add(sched)
    await db_session.flush()

    r = await client.get(f"/api/crm/connections/{connection.id}/datasets/lead/jobs")
    assert r.status_code == 200, r.text
    body = r.json()
    job_types = [j["jobType"] for j in body["jobs"]]
    assert "sync-crm-source" in job_types
    assert "unpack-crm-source" in job_types
    assert "backfill-stage-transitions" in job_types
    assert "generate-report" not in job_types
    by_type = {j["jobType"]: j for j in body["jobs"]}
    assert by_type["unpack-crm-source"]["status"] == "running"
    assert by_type["sync-crm-source"]["completedAt"] is not None
    assert body["schedule"] is not None
    assert body["schedule"]["cron"] == "0 */6 * * *"
    assert body["schedule"]["enabled"] is True


async def test_jobs_no_schedule_returns_null(client, connection, db_session, tenant_id):
    await _seed_chain_jobs(db_session, tenant_id, connection)
    r = await client.get(f"/api/crm/connections/{connection.id}/datasets/lead/jobs")
    assert r.status_code == 200, r.text
    assert r.json()["schedule"] is None


async def test_jobs_tenant_scoped_other_connection_404(client):
    r = await client.get(f"/api/crm/connections/{uuid.uuid4()}/datasets/lead/jobs")
    assert r.status_code == 404


async def test_jobs_requires_orchestration_manage(client, connection, tenant_id):
    _override_auth(tenant_id, is_owner=False, permissions=frozenset())
    r = await client.get(f"/api/crm/connections/{connection.id}/datasets/lead/jobs")
    assert r.status_code == 403, r.text


async def test_jobs_rejects_bad_record_type(client, connection):
    r = await client.get(f"/api/crm/connections/{connection.id}/datasets/nonsense/jobs")
    assert r.status_code == 400, r.text

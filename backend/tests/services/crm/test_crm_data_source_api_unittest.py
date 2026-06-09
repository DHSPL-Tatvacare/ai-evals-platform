"""Phase 3 — data-source API surface on /api/crm/connections/{id}/datasets/* (live DB, fake adapter).

End-to-end route tests against the real local Postgres (the draft→activate cycle rebuilds the
resolved matview, so a mock session can't catch the bug class). The provider is faked: the adapter
is registered into the registry under a test vendor and ConnectionResolver.get_config is patched, so
no LSQ/OpenAI call ever leaves the process. Assertions are against verbatim fixtures.
"""
from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest
import pytest_asyncio

from app.auth import AuthContext, get_auth_context
from app.constants import SYSTEM_USER_ID
from app.database import get_db
from app.main import app as fastapi_app
from app.models.provider_connection import ProviderConnection
from app.models.tenant import Tenant
from app.services.crm.adapters.protocol import (
    DiscoveredObject,
    FetchPage,
    FilterableField,
    FilterCapability,
    SourceRecordDraft,
)
from app.services.orchestration.adapters import register_adapter

_APP = "inside-sales"
_VENDOR = "fake-crm"

LEAD_A: dict[str, Any] = {"Id": "L1", "Stage": "Interested", "City": "Pune"}
LEAD_B: dict[str, Any] = {"Id": "L2", "Stage": "New", "City": "Mumbai"}


class _FakeAdapter:
    capability = "crm_source"
    vendor = _VENDOR

    async def discover_objects(self, *, creds, sample_size: int = 50):
        return [
            DiscoveredObject(source_object="Lead", record_type="lead", fields=["Id", "Stage", "City"]),
            DiscoveredObject(source_object="Activity", record_type="activity", fields=["AId", "Lead"]),
        ]

    def filter_capabilities(self, source_object: str) -> FilterCapability:
        if source_object == "Lead":
            return FilterCapability(source_object="Lead", fields=(
                FilterableField(field="Stage", operators=("eq", "in"), pushable=True),
                FilterableField(field="City", operators=("eq", "in"), pushable=False),
            ))
        return FilterCapability(source_object=source_object, fields=())

    async def field_values(self, *, creds, source_object: str, field: str, limit: int = 50):
        return sorted({str(LEAD_A.get(field)), str(LEAD_B.get(field))})[:limit]

    async def sample_records(self, *, creds, source_object: str, limit: int = 20):
        return [
            SourceRecordDraft(source_object="Lead", record_type="lead", source_record_id="L1", raw_payload=LEAD_A),
            SourceRecordDraft(source_object="Lead", record_type="lead", source_record_id="L2", raw_payload=LEAD_B),
        ][:limit]

    async def fetch_records(self, *, creds, source_object: str, watermark=None, page: int = 1,
                            page_size: int = 200, predicate: Any | None = None) -> FetchPage:
        return FetchPage(records=[], next_watermark=None, has_more=False)


register_adapter(capability="crm_source", vendor=_VENDOR, adapter=_FakeAdapter())


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
    # A fresh tenant → a unique resolved-view slug, so committed leftovers from prior runs
    # (DDL is not rolled back with the test transaction) cannot collide with this test.
    tid = uuid.uuid4()
    db_session.add(Tenant(
        id=tid, name=f"crm-ds-{tid.hex[:8]}", slug=f"crm-ds-{tid.hex[:8]}", is_active=True,
    ))
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


@pytest_asyncio.fixture(autouse=True)
def patch_creds(monkeypatch):
    async def _get_config(self, connection_id):  # noqa: ANN001
        return {"__provider__": _VENDOR, "access_key": "ak"}
    monkeypatch.setattr(
        "app.services.orchestration.connections.resolver.ConnectionResolver.get_config", _get_config,
    )


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


pytestmark = pytest.mark.asyncio


async def test_list_datasets_scoped(client, connection):
    r = await client.get(f"/api/crm/connections/{connection.id}/datasets")
    assert r.status_code == 200, r.text
    datasets = r.json()["datasets"]
    rts = {d["recordType"] for d in datasets}
    assert {"lead", "activity"} <= rts
    lead = next(d for d in datasets if d["recordType"] == "lead")
    assert lead["status"] == "draft"  # no definition yet → default draft
    assert lead["hasSchedule"] is False


async def test_list_datasets_non_owner_connection_404(client):
    # A connection that does not belong to the caller's tenant is not found.
    r = await client.get(f"/api/crm/connections/{uuid.uuid4()}/datasets")
    assert r.status_code == 404


async def test_raw_sample_returns_provider_shape(client, connection):
    r = await client.get(f"/api/crm/connections/{connection.id}/datasets/lead/raw-sample")
    assert r.status_code == 200, r.text
    records = r.json()["records"]
    assert [x["sourceRecordId"] for x in records] == ["L1", "L2"]
    assert records[0]["rawPayload"]["Stage"] == "Interested"


async def test_unpacked_sample_applies_draft_map_without_persisting(client, connection, db_session):
    from sqlalchemy import func, select
    from app.models.crm import CrmLead, CrmSourceRecord

    body = {"recordType": "lead", "bindings": [
        {"slot": "lead_id", "semanticKey": "lead_id", "sourceField": "Id", "dataType": "text"},
        {"slot": "lead_stage", "semanticKey": "lead_stage", "sourceField": "Stage", "dataType": "text"},
        {"slot": "txt_01", "semanticKey": "city", "sourceField": "City", "dataType": "text"},
    ]}
    r = await client.post(
        f"/api/crm/connections/{connection.id}/datasets/lead/unpacked-sample", json=body,
    )
    assert r.status_code == 200, r.text
    rows = r.json()["rows"]
    by_id = {row["lead_id"]: row for row in rows}
    assert by_id["L1"]["lead_stage"] == "Interested"
    assert by_id["L1"]["city"] == "Pune"
    # No persistence: the sampled ids never landed (raw tape) nor became serving rows.
    landed = await db_session.scalar(
        select(func.count()).select_from(CrmSourceRecord).where(CrmSourceRecord.connection_id == connection.id)
    )
    served = await db_session.scalar(
        select(func.count()).select_from(CrmLead).where(CrmLead.lead_id.in_(["L1", "L2"]))
    )
    assert landed == 0 and served == 0


async def test_filter_capabilities_passthrough(client, connection):
    r = await client.get(f"/api/crm/connections/{connection.id}/datasets/lead/filter-capabilities")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sourceObject"] == "Lead"
    by_field = {f["field"]: f for f in body["fields"]}
    assert by_field["Stage"]["pushable"] is True
    assert by_field["City"]["pushable"] is False
    assert set(by_field["Stage"]["operators"]) == {"eq", "in"}


async def test_field_values_passthrough_capped(client, connection):
    r = await client.get(
        f"/api/crm/connections/{connection.id}/datasets/lead/field-values?field=Stage"
    )
    assert r.status_code == 200, r.text
    assert r.json()["field"] == "Stage"
    assert r.json()["values"] == ["Interested", "New"]


async def test_draft_then_activate_cycle(client, connection, db_session, tenant_id):
    from sqlalchemy import select, text
    from app.models.crm import CrmLead, CrmLeadExt, SourceDatasetDefinition
    from app.services.crm.crm_resolved_populator import resolved_matview_name

    # Seed two leads — one matching the filter, one not — so the rebuilt matview can prove the cut.
    for lid, stage in (("won-1", "won"), ("new-1", "New")):
        lead = CrmLead(id=uuid.uuid4(), tenant_id=tenant_id, app_id=_APP, lead_id=lid, lead_stage=stage)
        db_session.add(lead)
        await db_session.flush()
        db_session.add(CrmLeadExt(id=uuid.uuid4(), crm_lead_id=lead.id, tenant_id=tenant_id, app_id=_APP, txt_01="x"))
    await db_session.flush()

    draft_body = {
        "recordType": "lead",
        "bindings": [
            {"slot": "lead_id", "semanticKey": "lead_id", "sourceField": "Id", "dataType": "text"},
            {"slot": "lead_stage", "semanticKey": "lead_stage", "sourceField": "Stage", "dataType": "text"},
        ],
        "filterPredicate": {"field": "lead_stage", "op": "in", "value": ["won"]},
    }
    d = await client.put(f"/api/crm/connections/{connection.id}/datasets/lead/draft", json=draft_body)
    assert d.status_code == 200, d.text
    assert d.json()["status"] == "draft"

    # Draft alone built no resolved matview keyed to this filter (status stays draft).
    defn = await db_session.scalar(select(SourceDatasetDefinition).where(
        SourceDatasetDefinition.tenant_id == tenant_id,
        SourceDatasetDefinition.connection_id == connection.id,
        SourceDatasetDefinition.record_type == "lead",
    ))
    assert defn.status == "draft" and defn.version == 0

    a = await client.post(f"/api/crm/connections/{connection.id}/datasets/lead/activate", json={"recordType": "lead"})
    assert a.status_code == 200, a.text
    assert a.json()["version"] == 1
    assert a.json()["status"] == "active"

    # Activate alone made the resolved view match the filter — no sync in between.
    mv = resolved_matview_name("lead", tenant_id, _APP)
    ids = {row[0] for row in (await db_session.execute(text(f"SELECT lead_id FROM analytics.{mv}"))).all()}
    assert "won-1" in ids and "new-1" not in ids

    p = await client.get(f"/api/crm/connections/{connection.id}/datasets/lead/preview")
    assert p.status_code == 200, p.text
    preview_ids = {row["lead_id"] for row in p.json()["rows"]}
    assert preview_ids == {"won-1"}


async def test_activate_rejects_invalid_predicate(client, connection, db_session):
    bad = {
        "recordType": "lead",
        "bindings": [{"slot": "lead_id", "semanticKey": "lead_id", "sourceField": "Id", "dataType": "text"}],
        "filterPredicate": {"field": "lead_stage", "op": "wat", "value": "x"},
    }
    r = await client.put(f"/api/crm/connections/{connection.id}/datasets/lead/draft", json=bad)
    assert r.status_code == 400, r.text
    assert "predicate" in r.json()["detail"].lower()


async def test_rejects_activity_missing_required_lead_link(client, connection):
    # Activity requires a lead-link binding; the publish-time invariant refuses an incomplete map
    # with a stable, client-facing detail (the same guard the activate path also enforces).
    body = {
        "recordType": "activity",
        "bindings": [{"slot": "source_activity_id", "semanticKey": "source_activity_id", "sourceField": "AId", "dataType": "text"}],
    }
    d = await client.put(f"/api/crm/connections/{connection.id}/datasets/activity/draft", json=body)
    assert d.status_code == 400, d.text
    assert "lead-link" in d.json()["detail"].lower()


async def test_activate_without_a_draft_map_is_rejected(client, connection):
    # Nothing published yet → activate refuses with a stable detail (never builds an empty surface).
    a = await client.post(
        f"/api/crm/connections/{connection.id}/datasets/lead/activate", json={"recordType": "lead"},
    )
    assert a.status_code == 400, a.text
    assert "no draft field map" in a.json()["detail"].lower()


@pytest.mark.parametrize("method,path,has_body", [
    ("get", "/datasets", False),
    ("get", "/datasets/lead/raw-sample", False),
    ("post", "/datasets/lead/unpacked-sample", True),
    ("get", "/datasets/lead/filter-capabilities", False),
    ("get", "/datasets/lead/field-values?field=Stage", False),
    ("put", "/datasets/lead/draft", True),
    ("post", "/datasets/lead/activate", True),
    ("get", "/datasets/lead/preview", False),
])
async def test_routes_require_orchestration_manage(client, connection, tenant_id, method, path, has_body):
    _override_auth(tenant_id, is_owner=False, permissions=frozenset())  # no orchestration:manage
    url = f"/api/crm/connections/{connection.id}{path}"
    kwargs = {"json": {"recordType": "lead", "bindings": []}} if has_body else {}
    r = await getattr(client, method)(url, **kwargs)
    assert r.status_code == 403, f"{method} {path} -> {r.status_code}: {r.text}"

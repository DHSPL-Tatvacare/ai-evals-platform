"""A CRM sync run enqueues the downstream chain (unpack → resolved → analytics) — no live provider.

The land path is the chain's head: after records land it enqueues an ``unpack-crm-source`` job, which
in turn enqueues the analytics populate. We assert the enqueued ``job_type`` set and that tenant + app +
connection params flow through, against a fake session that records ``db.add`` rows. No adapter call
leaves the process (the adapter + resolver are faked).
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

import pytest

import app.services.crm.crm_source_sync as sync_mod
import app.services.crm.crm_source_unpacker as unpack_mod
from app.models.job import BackgroundJob
from app.services.crm.adapters.protocol import DiscoveredObject, FetchPage, SourceRecordDraft

pytestmark = pytest.mark.asyncio

_TENANT = uuid.uuid4()
_USER = uuid.uuid4()
_CONN = uuid.uuid4()


class _FakeAdapter:
    async def discover_objects(self, *, creds, sample_size: int = 50):
        return [DiscoveredObject(source_object="Lead", record_type="lead", fields=["Id"])]

    async def fetch_records(self, *, creds, source_object, watermark=None, page=1,
                            page_size=200, predicate=None):
        # One record lands so the chain head fires; single page.
        return FetchPage(
            records=[SourceRecordDraft(
                source_object="Lead", record_type="lead", source_record_id="L1", raw_payload={"Id": "L1"},
            )],
            next_watermark="w1", has_more=False,
        )


class _FakeResolver:
    def __init__(self, *_a, **_k) -> None:
        pass

    async def get_config(self, _cid):
        return {"__provider__": "lsq", "region_host": "https://x", "access_key": "k", "secret_key": "s"}


class _RecordingSession:
    """Captures rows added so we can assert the enqueued chain jobs."""

    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, row) -> None:
        self.added.append(row)

    async def execute(self, *_a, **_k):
        class _R:
            def scalar_one_or_none(self_inner):
                return None
        return _R()

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        pass

    def enqueued_job_types(self) -> set[str]:
        return {r.job_type for r in self.added if isinstance(r, BackgroundJob)}

    def enqueued_jobs(self) -> list[BackgroundJob]:
        return [r for r in self.added if isinstance(r, BackgroundJob)]


@pytest.fixture
def _patched(monkeypatch):
    session = _RecordingSession()

    @asynccontextmanager
    async def _fake_async_session():
        yield session

    monkeypatch.setattr("app.database.async_session", _fake_async_session)
    monkeypatch.setattr(sync_mod, "ConnectionResolver", _FakeResolver)
    monkeypatch.setattr(sync_mod, "resolve_crm_adapter", lambda *, vendor: _FakeAdapter())

    async def _none(*_a, **_k):
        return None

    monkeypatch.setattr(sync_mod, "_latest_watermark", _none)
    monkeypatch.setattr(sync_mod, "_active_filter_predicate", _none)
    return session


async def test_sync_enqueues_unpack_chain_with_scope(_patched):
    session = _patched
    await sync_mod.run_crm_source_sync(
        uuid.uuid4(),
        {"app_id": "inside-sales", "connection_id": str(_CONN), "source_objects": ["Lead"]},
        tenant_id=_TENANT, user_id=_USER,
    )
    assert "unpack-crm-source" in session.enqueued_job_types()
    job = next(j for j in session.enqueued_jobs() if j.job_type == "unpack-crm-source")
    assert job.tenant_id == _TENANT
    assert job.user_id == _USER
    assert job.app_id == "inside-sales"
    assert job.params["connection_id"] == str(_CONN)
    assert job.params["tenant_id"] == str(_TENANT)
    assert job.params["user_id"] == str(_USER)


async def test_sync_does_not_chain_when_nothing_landed(monkeypatch, _patched):
    session = _patched

    class _EmptyAdapter(_FakeAdapter):
        async def fetch_records(self, *, creds, source_object, watermark=None, page=1,
                                page_size=200, predicate=None):
            return FetchPage(records=[], next_watermark=None, has_more=False)

    monkeypatch.setattr(sync_mod, "resolve_crm_adapter", lambda *, vendor: _EmptyAdapter())
    await sync_mod.run_crm_source_sync(
        uuid.uuid4(),
        {"app_id": "inside-sales", "connection_id": str(_CONN), "source_objects": ["Lead"]},
        tenant_id=_TENANT, user_id=_USER,
    )
    assert "unpack-crm-source" not in session.enqueued_job_types()


async def test_unpack_enqueues_analytics_populate_with_app(monkeypatch):
    """The unpack tail enqueues the CRM analytics populate (deterministic stage-transition fact)."""
    session = _RecordingSession()

    @asynccontextmanager
    async def _fake_async_session():
        yield session

    monkeypatch.setattr("app.database.async_session", _fake_async_session)

    class _Resolver:
        def __init__(self, *_a, **_k) -> None:
            pass

        async def get_config(self, _cid):
            return {"__provider__": "lsq"}

    monkeypatch.setattr(
        "app.services.orchestration.connections.resolver.ConnectionResolver", _Resolver,
    )

    async def _fake_unpack(db, **_k):
        return unpack_mod.UnpackResult(scanned=1, upserted=1)

    async def _fake_refresh(db, **_k):
        return ["lead"]

    monkeypatch.setattr(unpack_mod, "unpack", _fake_unpack)
    monkeypatch.setattr(
        "app.services.crm.crm_resolved_populator.refresh_resolved_matviews", _fake_refresh,
    )

    await unpack_mod.run_crm_source_unpack(
        uuid.uuid4(),
        {"app_id": "inside-sales", "connection_id": str(_CONN)},
        tenant_id=_TENANT, user_id=_USER,
    )
    jobs = session.enqueued_jobs()
    assert "backfill-stage-transitions" in {j.job_type for j in jobs}
    analytics = next(j for j in jobs if j.job_type == "backfill-stage-transitions")
    assert analytics.tenant_id == _TENANT
    assert analytics.app_id == "inside-sales"
    assert analytics.params["app_id"] == "inside-sales"

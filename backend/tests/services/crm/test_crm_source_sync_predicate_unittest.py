"""run_crm_source_sync pushes the active definition's filter into the adapter fetch (no live call).

The land path is read-only over the definition: it loads the active dataset definition's
filter_predicate per record_type and forwards the pushable part to fetch_records(predicate=...),
narrowing the pull. With no definition / no filter it forwards None.
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

import pytest

import app.services.crm.crm_source_sync as sync_mod
from app.services.crm.adapters.protocol import DiscoveredObject, FetchPage, SourceRecordDraft

pytestmark = pytest.mark.asyncio

_PRED = {"field": "ProspectStage", "op": "in", "value": ["won", "lost"]}


class _FakeAdapter:
    def __init__(self) -> None:
        self.fetch_predicates: list[object] = []

    async def discover_objects(self, *, creds, sample_size: int = 50):
        return [DiscoveredObject(source_object="Lead", record_type="lead", fields=["ProspectID"])]

    async def fetch_records(self, *, creds, source_object, watermark=None, page=1,
                            page_size=200, predicate=None):
        self.fetch_predicates.append(predicate)
        return FetchPage(records=[], next_watermark=None, has_more=False)


class _FakeResolver:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    async def get_config(self, _connection_id):
        return {"__provider__": "lsq", "region_host": "https://x", "access_key": "k", "secret_key": "s"}


class _FakeSession:
    async def commit(self) -> None:  # log row + nothing else committed in this test
        pass

    async def flush(self) -> None:
        pass

    def add(self, _row) -> None:
        pass


@asynccontextmanager
async def _fake_async_session():
    yield _FakeSession()


@pytest.fixture
def _patched(monkeypatch):
    adapter = _FakeAdapter()
    monkeypatch.setattr("app.database.async_session", _fake_async_session)
    monkeypatch.setattr(sync_mod, "ConnectionResolver", _FakeResolver)
    monkeypatch.setattr(sync_mod, "resolve_crm_adapter", lambda *, vendor: adapter)
    monkeypatch.setattr(sync_mod, "_latest_watermark", _async_none)
    return adapter


async def _async_none(*_a, **_k):
    return None


async def test_forwards_active_definition_predicate_to_fetch(monkeypatch, _patched):
    adapter = _patched

    async def _pred(_db, *, tenant_id, app_id, connection_id, record_type):
        return _PRED if record_type == "lead" else None

    monkeypatch.setattr(sync_mod, "_active_filter_predicate", _pred)

    await sync_mod.run_crm_source_sync(
        uuid.uuid4(),
        {"app_id": "inside-sales", "connection_id": str(uuid.uuid4()), "source_objects": ["Lead"]},
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
    )
    assert adapter.fetch_predicates == [_PRED]


async def test_forwards_none_when_no_definition(monkeypatch, _patched):
    adapter = _patched

    async def _no_pred(_db, **_k):
        return None

    monkeypatch.setattr(sync_mod, "_active_filter_predicate", _no_pred)

    await sync_mod.run_crm_source_sync(
        uuid.uuid4(),
        {"app_id": "inside-sales", "connection_id": str(uuid.uuid4()), "source_objects": ["Lead"]},
        tenant_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
    )
    assert adapter.fetch_predicates == [None]

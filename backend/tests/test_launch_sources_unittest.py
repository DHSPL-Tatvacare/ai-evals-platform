"""launch_sources resolver registry — register + resolve + error paths."""

from __future__ import annotations

import uuid

import pytest

from app.services.scheduler import launch_sources


@pytest.fixture(autouse=True)
def _isolate_registry():
    saved = dict(launch_sources._RESOLVERS)
    launch_sources._RESOLVERS.clear()
    try:
        yield
    finally:
        launch_sources._RESOLVERS.clear()
        launch_sources._RESOLVERS.update(saved)


@pytest.mark.asyncio
async def test_resolve_calls_registered_resolver():
    captured = {}

    async def _resolver(db, *, tenant_id, app_id, source_id):
        captured["args"] = (db, tenant_id, app_id, source_id)
        return launch_sources.LaunchSpec(
            params={"connection_id": source_id, "source_objects": ["Leads"]},
            schedule_key=f"sync:{source_id}",
            name="Lead sync",
        )

    launch_sources.register_launch_source_resolver("sync-x", _resolver)
    tenant = uuid.uuid4()
    spec = await launch_sources.resolve_launch_source(
        db="DB", job_type="sync-x", tenant_id=tenant, app_id="voice-rx", source_id="abc"
    )
    assert spec.params == {"connection_id": "abc", "source_objects": ["Leads"]}
    assert spec.schedule_key == "sync:abc"
    assert spec.name == "Lead sync"
    assert captured["args"] == ("DB", tenant, "voice-rx", "abc")


@pytest.mark.asyncio
async def test_resolve_raises_when_no_resolver_registered():
    with pytest.raises(ValueError):
        await launch_sources.resolve_launch_source(
            db="DB",
            job_type="no-resolver",
            tenant_id=uuid.uuid4(),
            app_id="voice-rx",
            source_id="abc",
        )


@pytest.mark.asyncio
async def test_resolver_value_error_propagates():
    async def _resolver(db, *, tenant_id, app_id, source_id):
        raise ValueError("Unknown source")

    launch_sources.register_launch_source_resolver("sync-x", _resolver)
    with pytest.raises(ValueError):
        await launch_sources.resolve_launch_source(
            db="DB",
            job_type="sync-x",
            tenant_id=uuid.uuid4(),
            app_id="voice-rx",
            source_id="bad",
        )

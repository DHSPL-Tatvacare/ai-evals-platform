"""Phase 2 — the CRM source sync is schedulable per dataset (no live provider)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.models.job import BackgroundJob
from app.models.scheduled_job import ScheduledJobDefinition
from app.services.scheduler import engine
from app.services.scheduler import predicates as predicate_registry
from app.services.scheduler.workloads import (
    ensure_handler_workloads_registered,
    get_workload,
)


def _crm_sync_workload():
    ensure_handler_workloads_registered()
    # App-agnostic: registered under the empty app key, not pinned to one app.
    return get_workload("", "sync-crm-source")


def test_sync_crm_source_is_schedulable_with_generic_label():
    workload = _crm_sync_workload()
    assert workload is not None, "sync-crm-source must register a schedulable workload"
    assert workload.job_type == "sync-crm-source"
    # App-agnostic: any app owning a CRM connection can schedule it.
    assert workload.app_id == ""
    # Generic, capability-named label/description — no vendor or app name.
    blob = f"{workload.label} {workload.description}".lower()
    for banned in ("lsq", "leadsquared", "inside sales", "inside-sales", "crm"):
        assert banned not in blob, f"schedule copy leaks {banned!r}: {blob!r}"
    assert workload.label.strip()
    assert workload.description.strip()
    # Default params reflect the connection + source_objects shape the handler reads.
    assert "connection_id" in workload.default_params
    assert "source_objects" in workload.default_params


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
    def __init__(self, due_schedules: list[ScheduledJobDefinition]):
        self._due = due_schedules
        self.added: list[Any] = []
        self.commits = 0
        self.flushes = 0

    async def execute(self, _stmt):
        return _FakeResult(self._due)

    def add(self, item):
        self.added.append(item)

    async def flush(self):
        self.flushes += 1

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_scheduled_sync_fires_definition_with_connection_params():
    connection_id = str(uuid.uuid4())
    schedule = ScheduledJobDefinition(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        app_id="voice-rx",
        job_type="sync-crm-source",
        schedule_key="voice-rx-leads-sync",
        name="Lead sync",
        description=None,
        cron="0 */6 * * *",
        params={"connection_id": connection_id, "source_objects": ["Leads"]},
        override={"skip_criteria": []},
        enabled=True,
        next_check_at=None,
        current_cycle_started_at=None,
        current_cycle_attempts=0,
        last_fire_at=None,
        last_fire_job_id=None,
        last_skip_reason=None,
        created_by=uuid.uuid4(),
    )
    session = _FakeSession([schedule])
    now = datetime(2026, 6, 9, 12, 0, tzinfo=timezone.utc)

    with patch.object(
        engine, "_resolve_platform_user_id", AsyncMock(return_value=uuid.uuid4())
    ):
        fired = await engine.tick_once(session, now=now)

    assert len(fired) == 1
    job = next(item for item in session.added if isinstance(item, BackgroundJob))
    assert job.job_type == "sync-crm-source"
    assert job.app_id == "voice-rx"
    assert job.params["app_id"] == "voice-rx"
    assert job.params["connection_id"] == connection_id
    assert job.params["source_objects"] == ["Leads"]
    assert job.params["is_scheduled_run"] is True

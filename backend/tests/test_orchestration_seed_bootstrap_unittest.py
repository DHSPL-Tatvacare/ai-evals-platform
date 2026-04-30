"""Phase 10 commit 1: env→connection bootstrap and seed-JSON injection.

Asserts:
- ``_bootstrap_default_connections_from_env`` inserts one row per provider
  whose env vars are present, idempotently.
- The MQL Concierge seed loads with ``connection_id`` and ``variable_mappings``
  populated on each crm.* node, drawn from the matching action template.
- When env vars are absent, no bootstrapped rows are inserted and the
  seeded workflow loads without ``connection_id`` (system seed still works).
"""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.constants import SYSTEM_TENANT_ID
from app.models.orchestration import Workflow, WorkflowVersion
from app.models.provider_connection import ProviderConnection


@pytest.fixture(autouse=True)
def fernet_key(monkeypatch):
    monkeypatch.setattr(
        "app.config.settings.ORCHESTRATION_CONNECTION_KEY",
        Fernet.generate_key().decode(),
    )


def _set_bolna_env(monkeypatch):
    # All three required per provider_specs.bolna; partial env → no row.
    monkeypatch.setattr("app.config.settings.BOLNA_API_KEY", "k")
    monkeypatch.setattr("app.config.settings.BOLNA_BASE_URL", "https://api.bolna.ai")
    monkeypatch.setattr("app.config.settings.BOLNA_FROM_PHONE", "+911234567890")


def _set_wati_env(monkeypatch):
    monkeypatch.setattr("app.config.settings.WATI_BASE_URL", "https://live-mt-server.wati.io")
    monkeypatch.setattr("app.config.settings.WATI_TENANT_ID", "12345")
    monkeypatch.setattr("app.config.settings.WATI_API_TOKEN", "tok")


def _clear_provider_env(monkeypatch):
    for var in (
        "BOLNA_API_KEY", "BOLNA_BASE_URL", "BOLNA_FROM_PHONE",
        "WATI_BASE_URL", "WATI_TENANT_ID", "WATI_API_TOKEN",
        "LSQ_BASE_URL", "LSQ_ACCESS_KEY", "LSQ_SECRET_KEY",
    ):
        monkeypatch.setattr(f"app.config.settings.{var}", "")


@pytest.mark.asyncio
async def test_bootstrap_inserts_when_env_set(db_session, monkeypatch):
    _set_bolna_env(monkeypatch)
    monkeypatch.setattr("app.config.settings.ORCHESTRATION_DEFAULT_APP_ID", "inside-sales")

    from app.services.orchestration_seed import _bootstrap_default_connections_from_env

    await _bootstrap_default_connections_from_env(db_session)

    row = await db_session.scalar(
        select(ProviderConnection).where(
            ProviderConnection.tenant_id == SYSTEM_TENANT_ID,
            ProviderConnection.provider == "bolna",
            ProviderConnection.app_id == "inside-sales",
        )
    )
    assert row is not None
    assert row.webhook_token is not None  # bolna supports webhooks


@pytest.mark.asyncio
async def test_bootstrap_is_idempotent(db_session, monkeypatch):
    _set_bolna_env(monkeypatch)
    monkeypatch.setattr("app.config.settings.ORCHESTRATION_DEFAULT_APP_ID", "inside-sales")

    from app.services.orchestration_seed import _bootstrap_default_connections_from_env

    await _bootstrap_default_connections_from_env(db_session)
    rows_before = (await db_session.execute(
        select(ProviderConnection).where(
            ProviderConnection.tenant_id == SYSTEM_TENANT_ID,
            ProviderConnection.provider == "bolna",
            ProviderConnection.app_id == "inside-sales",
        )
    )).scalars().all()

    await _bootstrap_default_connections_from_env(db_session)
    rows_after = (await db_session.execute(
        select(ProviderConnection).where(
            ProviderConnection.tenant_id == SYSTEM_TENANT_ID,
            ProviderConnection.provider == "bolna",
            ProviderConnection.app_id == "inside-sales",
        )
    )).scalars().all()
    assert len(rows_before) == len(rows_after) == 1


@pytest.mark.asyncio
async def test_bootstrap_skips_partial_bolna_env(db_session, monkeypatch):
    """All three bolna fields are required per provider_specs; partial env
    must not produce a half-configured row."""
    _clear_provider_env(monkeypatch)
    monkeypatch.setattr("app.config.settings.BOLNA_API_KEY", "k")
    monkeypatch.setattr("app.config.settings.BOLNA_BASE_URL", "https://api.bolna.ai")
    # BOLNA_FROM_PHONE intentionally left blank.
    monkeypatch.setattr("app.config.settings.ORCHESTRATION_DEFAULT_APP_ID", "inside-sales")

    from app.services.orchestration_seed import _bootstrap_default_connections_from_env

    await _bootstrap_default_connections_from_env(db_session)

    rows = (await db_session.execute(
        select(ProviderConnection).where(
            ProviderConnection.tenant_id == SYSTEM_TENANT_ID,
            ProviderConnection.provider == "bolna",
            ProviderConnection.app_id == "inside-sales",
        )
    )).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_bootstrap_skips_provider_without_env(db_session, monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setattr("app.config.settings.ORCHESTRATION_DEFAULT_APP_ID", "inside-sales")

    from app.services.orchestration_seed import _bootstrap_default_connections_from_env

    await _bootstrap_default_connections_from_env(db_session)
    rows = (await db_session.execute(
        select(ProviderConnection).where(
            ProviderConnection.tenant_id == SYSTEM_TENANT_ID,
            ProviderConnection.app_id == "inside-sales",
        )
    )).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_seed_workflow_injects_connection_ids_and_mappings(
    db_session, monkeypatch,
):
    """Full seed run with bolna+wati env set should produce an MQL Concierge
    seed where every crm.send_wati and crm.place_bolna_call node has
    ``connection_id`` and ``variable_mappings`` populated."""
    _set_bolna_env(monkeypatch)
    _set_wati_env(monkeypatch)
    monkeypatch.setattr("app.config.settings.ORCHESTRATION_DEFAULT_APP_ID", "inside-sales")

    from app.services.orchestration_seed import seed_orchestration_defaults

    await seed_orchestration_defaults(db_session)

    wf = await db_session.scalar(
        select(Workflow).where(
            Workflow.tenant_id == SYSTEM_TENANT_ID,
            Workflow.slug == "mql-concierge-default",
        )
    )
    assert wf is not None
    v = await db_session.scalar(
        select(WorkflowVersion).where(
            WorkflowVersion.id == wf.current_published_version_id
        )
    )
    assert v is not None

    wati_nodes = [n for n in v.definition["nodes"] if n["type"] == "crm.send_wati"]
    bolna_nodes = [n for n in v.definition["nodes"] if n["type"] == "crm.place_bolna_call"]
    assert wati_nodes and bolna_nodes
    for node in wati_nodes:
        assert "connection_id" in node["config"]
        # parameter_map → variable_mappings
        assert isinstance(node["config"].get("variable_mappings"), list)
        if node["config"]["variable_mappings"]:
            entry = node["config"]["variable_mappings"][0]
            assert "agent_variable" in entry
            assert entry["source_kind"] == "payload"
    for node in bolna_nodes:
        assert "connection_id" in node["config"]
        # user_data_map → variable_mappings
        assert isinstance(node["config"].get("variable_mappings"), list)


@pytest.mark.asyncio
async def test_seed_workflow_no_env_keeps_loading(db_session, monkeypatch):
    """Without env vars present, seed still succeeds — connection_id just
    isn't injected (commit-2 handlers fall back to env-backed services
    until bootstrapped)."""
    _clear_provider_env(monkeypatch)
    monkeypatch.setattr("app.config.settings.ORCHESTRATION_DEFAULT_APP_ID", "inside-sales")

    from app.services.orchestration_seed import seed_orchestration_defaults

    await seed_orchestration_defaults(db_session)

    wf = await db_session.scalar(
        select(Workflow).where(
            Workflow.tenant_id == SYSTEM_TENANT_ID,
            Workflow.slug == "mql-concierge-default",
        )
    )
    assert wf is not None
    v = await db_session.scalar(
        select(WorkflowVersion).where(
            WorkflowVersion.id == wf.current_published_version_id
        )
    )
    bolna_nodes = [n for n in v.definition["nodes"] if n["type"] == "crm.place_bolna_call"]
    for node in bolna_nodes:
        assert "connection_id" not in node["config"]

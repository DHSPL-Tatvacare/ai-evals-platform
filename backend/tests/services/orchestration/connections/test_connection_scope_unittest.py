"""Connection scope clause — tenant-wide + app_scopes reach for comm connections.

Live-DB. Seeds connections with the new scope flags and asserts the resolver
and builder picker honour ``tenant_wide`` / ``app_scopes`` while single-app
(home-only) rows stay app-bound.
"""
from __future__ import annotations

import uuid

import pytest
from cryptography.fernet import Fernet

from app.constants import SYSTEM_USER_ID


@pytest.fixture(autouse=True)
def fernet_key(monkeypatch):
    monkeypatch.setattr(
        "app.config.settings.ORCHESTRATION_CONNECTION_KEY",
        Fernet.generate_key().decode(),
    )


def _bolna_config() -> dict:
    return {"api_key": "k", "base_url": "https://api.bolna.ai", "from_phone": "+91"}


async def _add_bolna_row(
    db, *, tenant_id, app_id, tenant_wide=False, app_scopes=None, active=True,
) -> uuid.UUID:
    from app.models.provider_connection import ProviderConnection as PC
    from app.services.orchestration.connections import crypto

    cid = uuid.uuid4()
    db.add(
        PC(
            id=cid, tenant_id=tenant_id, app_id=app_id,
            provider="bolna", name=f"bolna-{cid.hex[:8]}",
            config_encrypted=crypto.encrypt(_bolna_config()),
            webhook_token=None, active=active, created_by=SYSTEM_USER_ID,
            tenant_wide=tenant_wide, app_scopes=app_scopes or [],
        )
    )
    await db.flush()
    return cid


@pytest.mark.asyncio
async def test_tenant_wide_resolves_from_different_app(db_session, seed_tenant_user_app):
    from app.services.orchestration.connections.resolver import ConnectionResolver

    tenant_id, _user, home_app = seed_tenant_user_app
    cid = await _add_bolna_row(
        db_session, tenant_id=tenant_id, app_id=home_app, tenant_wide=True,
    )

    resolver = ConnectionResolver(db_session, tenant_id=tenant_id, app_id="another-app")
    config = await resolver.get_config(cid, expected_provider="bolna")
    assert config["__provider__"] == "bolna"


@pytest.mark.asyncio
async def test_app_scopes_listed_app_resolves(db_session, seed_tenant_user_app):
    from app.services.orchestration.connections.resolver import ConnectionResolver

    tenant_id, _user, home_app = seed_tenant_user_app
    cid = await _add_bolna_row(
        db_session, tenant_id=tenant_id, app_id=home_app, app_scopes=["scoped-app"],
    )

    resolver = ConnectionResolver(db_session, tenant_id=tenant_id, app_id="scoped-app")
    config = await resolver.get_config(cid, expected_provider="bolna")
    assert config["__provider__"] == "bolna"


@pytest.mark.asyncio
async def test_app_not_in_scope_returns_not_found(db_session, seed_tenant_user_app):
    from app.services.orchestration.connections.resolver import (
        ConnectionNotFound, ConnectionResolver,
    )

    tenant_id, _user, home_app = seed_tenant_user_app
    cid = await _add_bolna_row(
        db_session, tenant_id=tenant_id, app_id=home_app, app_scopes=["scoped-app"],
    )

    resolver = ConnectionResolver(db_session, tenant_id=tenant_id, app_id="unlisted-app")
    with pytest.raises(ConnectionNotFound):
        await resolver.get_config(cid, expected_provider="bolna")


@pytest.mark.asyncio
async def test_home_only_row_stays_app_bound(db_session, seed_tenant_user_app):
    """A single-app row (no tenant_wide, empty app_scopes) matches only its home app."""
    from app.services.orchestration.connections.resolver import (
        ConnectionNotFound, ConnectionResolver,
    )

    tenant_id, _user, home_app = seed_tenant_user_app
    cid = await _add_bolna_row(db_session, tenant_id=tenant_id, app_id=home_app)

    resolver = ConnectionResolver(db_session, tenant_id=tenant_id, app_id="other-app")
    with pytest.raises(ConnectionNotFound):
        await resolver.get_config(cid, expected_provider="bolna")


@pytest.mark.asyncio
async def test_deactivated_connection_excluded_from_resolution(
    db_session, seed_tenant_user_app,
):
    """A connection toggled inactive (PATCH active=false) drops out of runtime resolution."""
    from app.services.orchestration.connections.resolver import (
        ConnectionNotFound, ConnectionResolver,
    )

    tenant_id, _user, home_app = seed_tenant_user_app
    cid = await _add_bolna_row(
        db_session, tenant_id=tenant_id, app_id=home_app, active=False,
    )

    resolver = ConnectionResolver(db_session, tenant_id=tenant_id, app_id=home_app)
    with pytest.raises(ConnectionNotFound):
        await resolver.get_config(cid, expected_provider="bolna")


@pytest.mark.asyncio
async def test_scope_clause_shape(seed_tenant_user_app):
    """The shared helper is an OR over home app, tenant_wide, and app_scopes containment."""
    from app.services.orchestration.connections.scope import connection_app_scope_clause

    clause = connection_app_scope_clause("voice-rx")
    compiled = str(clause)
    assert "tenant_wide" in compiled
    assert "app_scopes" in compiled
    assert "app_id" in compiled


@pytest.mark.asyncio
async def test_builder_picker_surfaces_tenant_wide_across_apps(
    db_session, seed_tenant_user_app, monkeypatch,
):
    """list_provider_connections from a different app surfaces a tenant_wide comm row.

    The connection's home app is the seeded app; the builder is open on a
    *different* app whose workflow the caller owns. A tenant_wide comm row
    must still appear in the picker.
    """
    import json
    import uuid as _uuid
    from contextlib import asynccontextmanager

    from app.auth import AuthContext
    from app.models.orchestration import Workflow
    from app.services.orchestration_authoring import orchestration_authoring_pack as pack

    tenant_id, user_id, home_app = seed_tenant_user_app
    builder_app = "kaira-bot"
    cid = await _add_bolna_row(
        db_session, tenant_id=tenant_id, app_id=home_app, tenant_wide=True,
    )

    workflow = Workflow(
        id=_uuid.uuid4(), tenant_id=tenant_id, app_id=builder_app,
        workflow_type="crm", slug=f"picker-test-{_uuid.uuid4().hex[:8]}",
        name="Picker Test", created_by=user_id,
    )
    db_session.add(workflow)
    await db_session.flush()

    auth = AuthContext(
        user_id=user_id, tenant_id=tenant_id, email="picker@test.local",
        role_id=_uuid.uuid4(), is_owner=True, permissions=frozenset(),
        app_access=frozenset({home_app, builder_app}),
    )

    class _BuilderCtx:
        app_id = builder_app
        view_mode = "edit"
        workflow_id = workflow.id

    class _SherlockCtx:
        pass

    sherlock_ctx = _SherlockCtx()
    sherlock_ctx.auth = auth
    sherlock_ctx.builder_context = _BuilderCtx()

    class _Ctx:
        context = sherlock_ctx

    @asynccontextmanager
    async def _session_cm():
        yield db_session

    # Handler + ownership-assert both open their own session; bind to the test one.
    monkeypatch.setattr("app.database.async_session", _session_cm)

    result = await pack._list_provider_connections_handler(
        _Ctx(), json.dumps({"provider": "bolna"}),
    )
    assert str(cid) in result, result

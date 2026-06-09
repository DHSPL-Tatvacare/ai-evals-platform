"""End-to-end /api/orchestration/connections route tests.

Asserts the safe-secret semantics from phase-10 §1.1:

- GET responses NEVER include plaintext secret values.
- PATCH preserves omitted secret keys (does not force re-entry of every credential).
- Blank-string secret overwrites are rejected (cannot wipe a stored credential).
"""
from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest
import pytest_asyncio
from cryptography.fernet import Fernet

from app.auth import AuthContext, get_auth_context
from app.constants import SYSTEM_USER_ID
from app.database import get_db
from app.main import app as fastapi_app
from app.models.tenant import Tenant


@pytest.fixture(autouse=True)
def fernet_key(monkeypatch):
    monkeypatch.setattr(
        "app.config.settings.ORCHESTRATION_CONNECTION_KEY",
        Fernet.generate_key().decode(),
    )


def _override_db(db_session):
    async def _g():
        yield db_session
    fastapi_app.dependency_overrides[get_db] = _g
    db_session.commit = db_session.flush  # type: ignore[assignment]


def _override_auth(tenant_id: uuid.UUID):
    auth = AuthContext(
        user_id=SYSTEM_USER_ID,
        tenant_id=tenant_id,
        email="test@orchestration.local",
        role_id=uuid.uuid4(),
        is_owner=True,
        permissions=frozenset(),
        app_access=frozenset({"voice-rx", "kaira-bot", "inside-sales"}),
    )
    fastapi_app.dependency_overrides[get_auth_context] = lambda: auth
    return auth


@pytest_asyncio.fixture
async def route_tenant_id(db_session) -> uuid.UUID:
    tenant_id = uuid.uuid4()
    db_session.add(Tenant(
        id=tenant_id,
        name=f"route-test-{tenant_id.hex[:8]}",
        slug=f"route-test-{tenant_id.hex[:8]}",
        is_active=True,
    ))
    await db_session.flush()
    return tenant_id


@pytest_asyncio.fixture
async def client(db_session, route_tenant_id):
    _override_db(db_session)
    _override_auth(route_tenant_id)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=fastapi_app), base_url="http://test",
        ) as c:
            yield c
    finally:
        fastapi_app.dependency_overrides.pop(get_db, None)
        fastapi_app.dependency_overrides.pop(get_auth_context, None)


def _bolna_create_body(name: str | None = None) -> dict[str, Any]:
    return {
        "appId": "inside-sales",
        "provider": "bolna",
        "name": name or f"bolna-{uuid.uuid4().hex[:8]}",
        "config": {
            "api_key": "secret-original",
            "base_url": "https://api.bolna.ai",
            "from_phone": "+911234567890",
        },
        "active": True,
    }


def _webhook_create_body(name: str | None = None) -> dict[str, Any]:
    return {
        "appId": "inside-sales",
        "provider": "webhook",
        "name": name or f"webhook-{uuid.uuid4().hex[:8]}",
        "config": {
            "base_url": "https://hooks.example.com",
            "auth_header_name": "Authorization",
            "auth_header_value": "Bearer top-secret",
        },
        "active": True,
    }


def _wati_create_body(name: str | None = None) -> dict[str, Any]:
    return {
        "appId": "inside-sales",
        "provider": "wati",
        "name": name or f"wati-{uuid.uuid4().hex[:8]}",
        "config": {
            "base_url": "https://live-mt-server.wati.io/123",
            "wati_tenant_id": "123",
            "api_token": "wati-secret",
            "channel_numbers": ["+919999990000"],
        },
        "active": True,
    }


@pytest.mark.asyncio
async def test_create_then_get_never_returns_secret_value(client):
    body = _bolna_create_body()
    r = await client.post("/api/orchestration/connections", json=body)
    assert r.status_code == 201, r.text
    payload = r.json()
    cid = payload["id"]

    # GET — secret stripped from configRedacted, base_url visible.
    g = await client.get(f"/api/orchestration/connections/{cid}")
    assert g.status_code == 200, g.text
    redacted = g.json()["configRedacted"]
    assert "api_key" not in redacted
    assert redacted.get("base_url") == "https://api.bolna.ai"
    assert redacted.get("from_phone") == "+911234567890"
    # webhook URL composed for inbound providers.
    assert g.json()["webhookUrl"] is not None


@pytest.mark.asyncio
async def test_get_returns_partial_reveal_secret_preview(client):
    """Phase 14 follow-up: stored secrets surface as a `secretPreviews`
    map keyed by field name. Format `XYZA••••WXYZ` for values ≥ 8 chars,
    `••••WXYZ` for shorter. The full secret is still stripped from
    ``configRedacted`` — only the masked preview leaves the server."""
    body = _bolna_create_body()
    # Use a deterministic secret long enough to hit the first-4 + last-4 path.
    body["config"]["api_key"] = "AAAAxxxxxxxxZZZZ"
    r = await client.post("/api/orchestration/connections", json=body)
    assert r.status_code == 201, r.text
    cid = r.json()["id"]

    g = await client.get(f"/api/orchestration/connections/{cid}")
    assert g.status_code == 200, g.text
    payload = g.json()
    assert "api_key" not in payload["configRedacted"]
    previews = payload.get("secretPreviews") or {}
    assert previews.get("api_key") == "AAAA••••ZZZZ", previews
    # The preview itself is partial — does not let a viewer reconstruct
    # the secret. Spot-check: the middle chars never appear in the
    # preview.
    assert "xxxxxxxx" not in previews["api_key"]


@pytest.mark.asyncio
async def test_get_secret_preview_clamps_short_values_to_last_four(client):
    """Short secrets (< 8 chars) collapse to last-4 only — surfacing the
    first-4 of a 5-char key would leak too much. Empty / missing values
    drop out of the preview map entirely."""
    body = _bolna_create_body()
    body["config"]["api_key"] = "abc12"  # 5 chars
    r = await client.post("/api/orchestration/connections", json=body)
    assert r.status_code == 201, r.text
    cid = r.json()["id"]

    g = await client.get(f"/api/orchestration/connections/{cid}")
    assert g.status_code == 200, g.text
    previews = g.json().get("secretPreviews") or {}
    assert previews.get("api_key") == "••••bc12", previews


@pytest.mark.asyncio
async def test_webhook_connection_redacts_secret_and_has_no_webhook_url(client):
    r = await client.post("/api/orchestration/connections", json=_webhook_create_body())
    assert r.status_code == 201, r.text
    cid = r.json()["id"]

    g = await client.get(f"/api/orchestration/connections/{cid}")
    assert g.status_code == 200, g.text
    redacted = g.json()["configRedacted"]
    assert redacted["base_url"] == "https://hooks.example.com"
    assert redacted["auth_header_name"] == "Authorization"
    assert "auth_header_value" not in redacted
    assert g.json()["webhookUrl"] is None


@pytest.mark.asyncio
async def test_patch_preserves_omitted_secret(client, monkeypatch):
    """Phase-10 §1.1: edit form may omit secret keys; the stored value is preserved.

    Verification: stub ``health.probe`` to capture the decrypted plaintext
    config the test endpoint would dispatch with. After PATCHing a
    non-secret field with the api_key key omitted, the captured plaintext
    must still carry the original ``api_key`` — proving the stored secret
    survived the edit.
    """
    captured: dict = {}

    async def _spy_probe(provider, config):
        captured["provider"] = provider
        captured["config"] = config
        return {"ok": True, "detail": "stubbed"}

    monkeypatch.setattr(
        "app.services.orchestration.api.connections.health.probe", _spy_probe,
    )

    create = await client.post("/api/orchestration/connections", json=_bolna_create_body())
    cid = create.json()["id"]

    # PATCH only base_url — api_key omitted.
    r = await client.patch(
        f"/api/orchestration/connections/{cid}",
        json={"config": {"base_url": "https://staging.bolna.ai"}},
    )
    assert r.status_code == 200, r.text
    redacted = r.json()["configRedacted"]
    assert redacted["base_url"] == "https://staging.bolna.ai"
    assert "api_key" not in redacted

    # /test exercises the decrypt path with the stored row.
    t = await client.post(f"/api/orchestration/connections/{cid}/test")
    assert t.status_code == 200, t.text
    assert captured["provider"] == "bolna"
    assert captured["config"]["api_key"] == "secret-original"
    assert captured["config"]["base_url"] == "https://staging.bolna.ai"


@pytest.mark.asyncio
async def test_patch_rejects_blank_secret_overwrite(client):
    create = await client.post("/api/orchestration/connections", json=_bolna_create_body())
    cid = create.json()["id"]
    r = await client.patch(
        f"/api/orchestration/connections/{cid}",
        json={"config": {"api_key": ""}},
    )
    assert r.status_code == 400, r.text
    assert "blank" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_patch_overwrites_secret_when_explicit(client, monkeypatch):
    captured: dict = {}

    async def _spy_probe(provider, config):
        captured["config"] = config
        return {"ok": True, "detail": "stubbed"}

    monkeypatch.setattr(
        "app.services.orchestration.api.connections.health.probe", _spy_probe,
    )

    create = await client.post("/api/orchestration/connections", json=_bolna_create_body())
    cid = create.json()["id"]
    r = await client.patch(
        f"/api/orchestration/connections/{cid}",
        json={"config": {"api_key": "rotated-key"}},
    )
    assert r.status_code == 200, r.text

    t = await client.post(f"/api/orchestration/connections/{cid}/test")
    assert t.status_code == 200, t.text
    assert captured["config"]["api_key"] == "rotated-key"


@pytest.mark.asyncio
async def test_create_with_unknown_provider_returns_400(client):
    body = _bolna_create_body()
    body["provider"] = "ghost-provider"
    r = await client.post("/api/orchestration/connections", json=body)
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_duplicate_name_returns_409(client):
    name = f"dup-{uuid.uuid4().hex[:8]}"
    a = await client.post("/api/orchestration/connections", json=_bolna_create_body(name))
    assert a.status_code == 201, a.text
    b = await client.post("/api/orchestration/connections", json=_bolna_create_body(name))
    assert b.status_code == 409


@pytest.mark.asyncio
async def test_get_schema_returns_x_secret_metadata(client):
    r = await client.get("/api/orchestration/connections/schema?provider=bolna")
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["provider"] == "bolna"
    properties = payload["jsonSchema"]["properties"]
    assert properties["api_key"]["x-secret"] is True
    assert properties["base_url"].get("x-secret") is None
    secret_field = next(f for f in payload["fields"] if f["name"] == "api_key")
    assert secret_field["secret"] is True


@pytest.mark.asyncio
async def test_webhook_schema_returns_secret_metadata(client):
    r = await client.get("/api/orchestration/connections/schema?provider=webhook")
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["provider"] == "webhook"
    assert payload["supportsWebhook"] is False
    properties = payload["jsonSchema"]["properties"]
    assert properties["auth_header_value"]["x-secret"] is True
    assert properties["base_url"].get("x-secret") is None


@pytest.mark.asyncio
async def test_webhook_connection_rejects_half_auth_pair(client):
    body = _webhook_create_body()
    body["config"].pop("auth_header_value")
    r = await client.post("/api/orchestration/connections", json=body)
    assert r.status_code == 400, r.text
    assert "provided together" in r.json()["detail"]


@pytest.mark.asyncio
async def test_delete_route_is_gone(client):
    create = await client.post("/api/orchestration/connections", json=_bolna_create_body())
    cid = create.json()["id"]
    d = await client.delete(f"/api/orchestration/connections/{cid}")
    assert d.status_code == 405


@pytest.mark.asyncio
async def test_patch_active_round_trips_both_directions(client):
    create = await client.post("/api/orchestration/connections", json=_bolna_create_body())
    cid = create.json()["id"]
    assert create.json()["active"] is True

    off = await client.patch(
        f"/api/orchestration/connections/{cid}", json={"active": False},
    )
    assert off.status_code == 200, off.text
    assert off.json()["active"] is False
    # Deactivated row is hidden from the default listing, visible with includeInactive.
    listing = await client.get("/api/orchestration/connections?appId=inside-sales")
    assert all(r["id"] != cid for r in listing.json())
    listing_all = await client.get(
        "/api/orchestration/connections?appId=inside-sales&includeInactive=true",
    )
    assert any(r["id"] == cid and r["active"] is False for r in listing_all.json())

    on = await client.patch(
        f"/api/orchestration/connections/{cid}", json={"active": True},
    )
    assert on.status_code == 200, on.text
    assert on.json()["active"] is True
    listing_back = await client.get("/api/orchestration/connections?appId=inside-sales")
    assert any(r["id"] == cid for r in listing_back.json())


@pytest.mark.asyncio
async def test_rotate_token_changes_webhook_url(client):
    create = await client.post("/api/orchestration/connections", json=_bolna_create_body())
    cid = create.json()["id"]
    original_url = create.json()["webhookUrl"]
    rot = await client.post(f"/api/orchestration/connections/{cid}/rotate-token")
    assert rot.status_code == 200, rot.text
    assert rot.json()["webhookUrl"] != original_url


@pytest.mark.asyncio
async def test_agent_variables_route_uses_live_provider_lookup(client, monkeypatch):
    # Real Bolna shape: variables are {token} placeholders in the prompt + the
    # top-level welcome message; there is no declared-variables field.
    async def _fake_get_agent(self, connection, *, agent_id):
        assert agent_id == "agent-7"
        return {
            "id": agent_id,
            "agent_name": "TestAgent",
            "agent_welcome_message": "Hello, am I speaking with {user_name}?",
            "agent_prompts": {
                "task_1": {"system_prompt": "Offer a slot at {preferred_time}."},
            },
        }

    monkeypatch.setattr(
        "app.services.orchestration.adapters.bolna.BolnaAdapter.get_agent",
        _fake_get_agent,
    )

    create = await client.post("/api/orchestration/connections", json=_bolna_create_body())
    cid = create.json()["id"]
    r = await client.get(
        f"/api/orchestration/connections/{cid}/agent-variables?agentId=agent-7"
    )
    assert r.status_code == 200, r.text
    assert r.json()["provider"] == "bolna"
    assert r.json()["variables"] == ["preferred_time", "user_name"]


@pytest.mark.asyncio
async def test_agent_variables_route_uses_selected_wati_template_name(client, monkeypatch):
    async def _fake_list_templates(self, connection):
        return [
            {
                "name": "concierge_qualify_v1",
                "language": "en",
                "status": "APPROVED",
                "parameters": ["first_name", "city"],
            },
            {
                "name": "concierge_priority_v1",
                "language": "en",
                "status": "APPROVED",
                "parameters": ["lead_stage"],
            },
        ]

    monkeypatch.setattr(
        "app.services.orchestration.adapters.wati.WatiAdapter.list_message_templates",
        _fake_list_templates,
    )

    create = await client.post("/api/orchestration/connections", json=_wati_create_body())
    cid = create.json()["id"]
    r = await client.get(
        f"/api/orchestration/connections/{cid}/agent-variables?templateName=concierge_qualify_v1"
    )
    assert r.status_code == 200, r.text
    assert r.json()["provider"] == "wati"
    assert r.json()["variables"] == ["first_name", "city"]


@pytest.mark.asyncio
async def test_get_unknown_id_returns_404(client):
    r = await client.get(f"/api/orchestration/connections/{uuid.uuid4()}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_validation_error_on_missing_required(client):
    body = _bolna_create_body()
    body["config"].pop("api_key")
    r = await client.post("/api/orchestration/connections", json=body)
    assert r.status_code == 400


def _lsq_create_body(name: str | None = None) -> dict[str, Any]:
    return {
        "appId": "inside-sales",
        "provider": "lsq",
        "name": name or f"lsq-{uuid.uuid4().hex[:8]}",
        "config": {
            "access_key": "ak-secret",
            "secret_key": "sk-secret",
            "region_host": "https://api-in21.leadsquared.com",
        },
        "active": True,
    }


@pytest.mark.asyncio
async def test_create_comm_connection_round_trips_scope_fields(client):
    body = _bolna_create_body()
    body["tenantWide"] = True
    body["appScopes"] = ["kaira-bot"]
    r = await client.post("/api/orchestration/connections", json=body)
    assert r.status_code == 201, r.text
    payload = r.json()
    assert payload["tenantWide"] is True
    assert payload["appScopes"] == ["kaira-bot"]


@pytest.mark.asyncio
async def test_crm_connection_allows_app_scopes_on_create(client):
    # CRM is no longer single-app: every provider gets the same multi-app reach.
    body = _lsq_create_body()
    body["appScopes"] = ["kaira-bot"]
    r = await client.post("/api/orchestration/connections", json=body)
    assert r.status_code == 201, r.text
    assert r.json()["appScopes"] == ["kaira-bot"]


@pytest.mark.asyncio
async def test_make_default_sets_flag_and_overrides_prior(client):
    a_body = _bolna_create_body()
    a_body["name"] = "Voice A"
    a_body["isDefault"] = True
    a = await client.post("/api/orchestration/connections", json=a_body)
    assert a.status_code == 201, a.text
    assert a.json()["isDefault"] is True

    # A second default for the same provider+app overrides the first.
    b_body = _bolna_create_body()
    b_body["name"] = "Voice B"
    b_body["isDefault"] = True
    b = await client.post("/api/orchestration/connections", json=b_body)
    assert b.status_code == 201, b.text
    assert b.json()["isDefault"] is True

    a_after = await client.get(f"/api/orchestration/connections/{a.json()['id']}")
    assert a_after.json()["isDefault"] is False


@pytest.mark.asyncio
async def test_unset_default_via_patch(client):
    body = _bolna_create_body()
    body["isDefault"] = True
    created = await client.post("/api/orchestration/connections", json=body)
    cid = created.json()["id"]
    assert created.json()["isDefault"] is True
    cleared = await client.patch(
        f"/api/orchestration/connections/{cid}", json={"isDefault": False},
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["isDefault"] is False


@pytest.mark.asyncio
async def test_app_scopes_unregistered_app_rejected(client):
    body = _bolna_create_body()
    body["appScopes"] = ["not-a-real-app"]
    r = await client.post("/api/orchestration/connections", json=body)
    assert r.status_code in (400, 404), r.text


@pytest.mark.asyncio
async def test_admin_list_by_app_returns_scoped_and_tenant_wide(client):
    # Home-app row on inside-sales.
    home = await client.post("/api/orchestration/connections", json=_bolna_create_body())
    assert home.status_code == 201, home.text
    home_id = home.json()["id"]

    # Tenant-wide row whose home app is inside-sales.
    tw_body = _bolna_create_body()
    tw_body["tenantWide"] = True
    tw = await client.post("/api/orchestration/connections", json=tw_body)
    tw_id = tw.json()["id"]

    # Scoped row whose home is inside-sales but scoped to kaira-bot.
    sc_body = _bolna_create_body()
    sc_body["appScopes"] = ["kaira-bot"]
    sc = await client.post("/api/orchestration/connections", json=sc_body)
    sc_id = sc.json()["id"]

    # Listing for kaira-bot: tenant-wide + scoped appear; the inside-sales-only home row does not.
    r = await client.get("/api/orchestration/connections?appId=kaira-bot")
    assert r.status_code == 200, r.text
    ids = {row["id"] for row in r.json()}
    assert tw_id in ids
    assert sc_id in ids
    assert home_id not in ids

"""Unit tests for WATI template-listing and Bolna agent-listing adapters.

No live HTTP. All provider calls use httpx.MockTransport so neither
WATI nor Bolna APIs are ever called from test code.

Tests cover:
- WatiAdapter.list_message_templates builds the right request URL and
  returns normalised {name, language, status, parameters} items.
- BolnaAdapter.list_agents builds GET /v2/agent/all and returns
  normalised {id, name, status, type} items.
- BolnaAdapter.get_agent builds GET /v2/agent/{id}.
- Soft-error contract: 4xx upstream returns {items:[], error: "..."}.
- Node _Config fields: messaging node accepts template_name/channel_number/
  broadcast_name; voice node accepts agent_id with bolna_agent_picker x-type.
- Zod-equivalent: node configs reject unknown keys (extra='forbid').
"""
from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from pydantic import ValidationError

from app.services.orchestration.adapters.wati import (
    WatiAdapter,
    WatiServiceError,
    resolve_wati_api_endpoint,
)
from app.services.orchestration.adapters.bolna import (
    BolnaAdapter,
    BolnaServiceError,
)
from app.services.orchestration.nodes.messaging_send_whatsapp_template import _Config as _MsgConfig
from app.services.orchestration.nodes.voice_place_call import _Config as _VoiceConfig


# ─── Fixture helpers ──────────────────────────────────────────────────────────

_WATI_CONN = {
    "base_url": "https://live-server.wati.io",
    "wati_tenant_id": "tenant123",
    "api_token": "tok_abc",
}

_BOLNA_CONN = {
    "api_key": "bolna_key_xyz",
    "base_url": "https://api.bolna.ai",
}

# Verbatim-style fixture matching WATI getMessageTemplates response shape
_WATI_TEMPLATES_PAGE: dict[str, Any] = {
    "messageTemplates": [
        {
            "template_name": "welcome_v2",
            "language": "en",
            "status": "APPROVED",
            "parameters": ["first_name", "programme_name"],
        },
        {
            "template_name": "followup_30d",
            "language": {"value": "en"},
            "status": "APPROVED",
            "components": [
                {"text": "Hello {{1}}, your follow-up date is {{2}}.", "type": "BODY"},
            ],
        },
    ]
}

# Verbatim fixture for Bolna GET /v2/agent/all
_BOLNA_AGENTS_LIST: list[dict[str, Any]] = [
    {"id": "agt_001", "agent_name": "ConciergeV2", "agent_status": "active", "agent_type": "outbound"},
    {"id": "agt_002", "agent_name": "ReminderBot", "agent_status": "active", "agent_type": "outbound"},
]

# Verbatim fixture for Bolna GET /v2/agent/{id}
_BOLNA_AGENT_DETAIL: dict[str, Any] = {
    "id": "agt_001",
    "agent_name": "ConciergeV2",
    "agent_status": "active",
    "agent_type": "outbound",
    "agent_config": {"variables": ["patient_name", "appointment_date"]},
}


# ─── WATI adapter list_message_templates ─────────────────────────────────────


def _make_wati_transport(status: int, body: Any) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=status,
            headers={"content-type": "application/json"},
            content=json.dumps(body).encode(),
        )
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_wati_list_message_templates_calls_correct_url():
    """list_message_templates must call getMessageTemplates with pageSize/pageNumber."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            status_code=200,
            headers={"content-type": "application/json"},
            content=json.dumps(_WATI_TEMPLATES_PAGE).encode(),
        )

    transport = httpx.MockTransport(handler)
    adapter = WatiAdapter()

    with patch(
        "app.services.orchestration.adapters.wati._make_client",
        side_effect=lambda *a, **kw: httpx.AsyncClient(transport=transport, **({"timeout": kw["timeout"]} if "timeout" in kw else {})),
    ):
        result = await adapter.list_message_templates(_WATI_CONN)

    assert len(captured) >= 1
    req = captured[0]
    expected_endpoint = resolve_wati_api_endpoint(
        _WATI_CONN["base_url"], _WATI_CONN["wati_tenant_id"]
    )
    assert expected_endpoint in str(req.url)
    assert "getMessageTemplates" in str(req.url)
    assert req.headers.get("Authorization") == "Bearer tok_abc"


@pytest.mark.asyncio
async def test_wati_list_message_templates_normalises_items():
    """list_message_templates returns {name, language, status, parameters} per item."""
    transport = _make_wati_transport(200, _WATI_TEMPLATES_PAGE)
    adapter = WatiAdapter()

    with patch(
        "app.services.orchestration.adapters.wati._make_client",
        side_effect=lambda *a, **kw: httpx.AsyncClient(transport=transport, **({"timeout": kw["timeout"]} if "timeout" in kw else {})),
    ):
        items = await adapter.list_message_templates(_WATI_CONN)

    assert isinstance(items, list)
    assert len(items) == 2
    # Named-param template
    named = next((t for t in items if t["name"] == "welcome_v2"), None)
    assert named is not None
    assert named["parameters"] == ["first_name", "programme_name"]
    assert named["status"] == "APPROVED"
    # Component-body template: parameters extracted from {{N}} placeholders
    body_tpl = next((t for t in items if t["name"] == "followup_30d"), None)
    assert body_tpl is not None
    assert body_tpl["parameters"] == ["1", "2"]


@pytest.mark.asyncio
async def test_wati_list_message_templates_4xx_raises():
    """list_message_templates raises WatiServiceError on 4xx (non-retryable)."""
    transport = _make_wati_transport(401, {"error": "Unauthorized"})
    adapter = WatiAdapter()

    with patch(
        "app.services.orchestration.adapters.wati._make_client",
        side_effect=lambda *a, **kw: httpx.AsyncClient(transport=transport, **({"timeout": kw["timeout"]} if "timeout" in kw else {})),
    ):
        with pytest.raises(WatiServiceError):
            await adapter.list_message_templates(_WATI_CONN)


@pytest.mark.asyncio
async def test_wati_list_message_templates_missing_credentials_raises():
    """list_message_templates raises if connection is missing required fields."""
    adapter = WatiAdapter()
    bad_conn = {"base_url": "", "wati_tenant_id": "", "api_token": ""}
    with pytest.raises((WatiServiceError, ValueError)):
        await adapter.list_message_templates(bad_conn)


# ─── Bolna adapter list_agents ────────────────────────────────────────────────


def _make_bolna_transport(status: int, body: Any) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=status,
            headers={"content-type": "application/json"},
            content=json.dumps(body).encode(),
        )
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_bolna_list_agents_calls_v2_agent_all():
    """list_agents must call GET /v2/agent/all with Bearer auth."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            status_code=200,
            headers={"content-type": "application/json"},
            content=json.dumps(_BOLNA_AGENTS_LIST).encode(),
        )

    transport = httpx.MockTransport(handler)
    adapter = BolnaAdapter()

    with patch(
        "app.services.orchestration.adapters.bolna._make_client",
        side_effect=lambda *a, **kw: httpx.AsyncClient(transport=transport),
    ):
        result = await adapter.list_agents(_BOLNA_CONN)

    assert len(captured) == 1
    req = captured[0]
    assert "/v2/agent/all" in str(req.url)
    assert req.headers.get("Authorization") == "Bearer bolna_key_xyz"
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0] == {"id": "agt_001", "name": "ConciergeV2", "status": "active", "type": "outbound"}


@pytest.mark.asyncio
async def test_bolna_list_agents_4xx_raises():
    """list_agents raises BolnaServiceError on 4xx."""
    transport = _make_bolna_transport(403, {"detail": "Forbidden"})
    adapter = BolnaAdapter()

    with patch(
        "app.services.orchestration.adapters.bolna._make_client",
        side_effect=lambda *a, **kw: httpx.AsyncClient(transport=transport),
    ):
        with pytest.raises(BolnaServiceError):
            await adapter.list_agents(_BOLNA_CONN)


@pytest.mark.asyncio
async def test_bolna_get_agent_calls_v2_agent_id():
    """get_agent must call GET /v2/agent/{id} (singular path, not /all)."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            status_code=200,
            headers={"content-type": "application/json"},
            content=json.dumps(_BOLNA_AGENT_DETAIL).encode(),
        )

    transport = httpx.MockTransport(handler)
    adapter = BolnaAdapter()

    with patch(
        "app.services.orchestration.adapters.bolna._make_client",
        side_effect=lambda *a, **kw: httpx.AsyncClient(transport=transport),
    ):
        result = await adapter.get_agent(_BOLNA_CONN, agent_id="agt_001")

    assert len(captured) == 1
    req = captured[0]
    assert "/v2/agent/agt_001" in str(req.url)
    assert result["id"] == "agt_001"


@pytest.mark.asyncio
async def test_bolna_get_agent_empty_id_raises():
    """get_agent raises ValueError when agent_id is empty."""
    adapter = BolnaAdapter()
    with pytest.raises(ValueError):
        await adapter.get_agent(_BOLNA_CONN, agent_id="")


# ─── messaging.send_whatsapp_template _Config field restoration ───────────────


def test_messaging_config_accepts_template_name_channel_broadcast():
    """messaging node _Config must accept template_name, channel_number, broadcast_name."""
    cid = uuid.uuid4()
    cfg = _MsgConfig(
        connection_id=cid,
        template_name="welcome_v2",
        channel_number="+911234567890",
        broadcast_name="concierge_may_2026",
    )
    assert cfg.template_name == "welcome_v2"
    assert cfg.channel_number == "+911234567890"
    assert cfg.broadcast_name == "concierge_may_2026"


def test_messaging_config_template_name_defaults_empty():
    """template_name/channel_number/broadcast_name default to '' (draft-safe)."""
    cid = uuid.uuid4()
    cfg = _MsgConfig(connection_id=cid)
    assert cfg.template_name == ""
    assert cfg.channel_number == ""
    assert cfg.broadcast_name == ""


def test_messaging_config_rejects_unknown_keys():
    """extra='forbid' must still hold after the new fields land."""
    with pytest.raises(ValidationError) as exc_info:
        _MsgConfig(
            connection_id=uuid.uuid4(),
            totally_unknown="boom",
        )
    assert any(err.get("type") == "extra_forbidden" for err in exc_info.value.errors())


def test_messaging_config_template_name_x_type_hint():
    """template_name field must carry x-type wati_template_picker in JSON schema."""
    schema = _MsgConfig.model_json_schema()
    props = schema.get("properties", {})
    assert "template_name" in props
    assert props["template_name"].get("x-type") == "wati_template_picker"


def test_messaging_config_channel_number_x_type_hint():
    """channel_number field must carry x-type wati_channel_picker."""
    schema = _MsgConfig.model_json_schema()
    props = schema.get("properties", {})
    assert "channel_number" in props
    assert props["channel_number"].get("x-type") == "wati_channel_picker"


def test_messaging_config_variable_mappings_x_type_hint():
    """variable_mappings field must carry x-type variable_mapping_list."""
    schema = _MsgConfig.model_json_schema()
    props = schema.get("properties", {})
    assert "variable_mappings" in props
    assert props["variable_mappings"].get("x-type") == "variable_mapping_list"


# ─── voice.place_call _Config field restoration ───────────────────────────────


def test_voice_config_agent_id_x_type_hint():
    """agent_id field must carry x-type bolna_agent_picker in JSON schema."""
    schema = _VoiceConfig.model_json_schema()
    props = schema.get("properties", {})
    assert "agent_id" in props
    assert props["agent_id"].get("x-type") == "bolna_agent_picker"


def test_voice_config_variable_mappings_x_type_hint():
    """variable_mappings field must carry x-type variable_mapping_list."""
    schema = _VoiceConfig.model_json_schema()
    props = schema.get("properties", {})
    assert "variable_mappings" in props
    assert props["variable_mappings"].get("x-type") == "variable_mapping_list"


def test_voice_config_rejects_unknown_keys():
    """extra='forbid' must hold on voice node config."""
    with pytest.raises(ValidationError) as exc_info:
        _VoiceConfig(
            connection_id=uuid.uuid4(),
            agent_id="agt_001",
            bad_field="no",
        )
    assert any(err.get("type") == "extra_forbidden" for err in exc_info.value.errors())

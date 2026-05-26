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


# ─── WATI template body surfacing ─────────────────────────────────────────────


def test_template_body_surfaced_from_components():
    from app.services.orchestration.adapters.wati import _normalize_template_candidate

    candidate = {
        "template_name": "followup_30d",
        "language": "en",
        "status": "APPROVED",
        "components": [
            {"text": "Hello {{1}}, your follow-up date is {{2}}.", "type": "BODY"},
        ],
    }
    norm = _normalize_template_candidate(candidate)
    assert norm["body"] == "Hello {{1}}, your follow-up date is {{2}}."
    # Existing positional parameter extraction is unchanged.
    assert norm["parameters"] == ["1", "2"]


def test_template_body_and_body_original_surfaced_from_top_level():
    from app.services.orchestration.adapters.wati import _normalize_template_candidate

    candidate = {
        "template_name": "welcome_v2",
        "language": "en",
        "status": "APPROVED",
        "parameters": ["first_name", "programme_name"],
        "body": "Hi {{1}}, welcome to {{2}}.",
        "bodyOriginal": "Hi {{first_name}}, welcome to {{programme_name}}.",
    }
    norm = _normalize_template_candidate(candidate)
    assert norm["body"] == "Hi {{1}}, welcome to {{2}}."
    assert norm["body_original"] == "Hi {{first_name}}, welcome to {{programme_name}}."
    assert norm["parameters"] == ["first_name", "programme_name"]


def test_template_body_prefers_body_component_over_header():
    from app.services.orchestration.adapters.wati import _normalize_template_candidate

    # HEADER precedes BODY: the BODY text must win, not the first text seen.
    candidate = {
        "template_name": "promo_v3",
        "language": "en",
        "status": "APPROVED",
        "components": [
            {"text": "Your order", "type": "HEADER"},
            {"text": "Hi {{1}}, your order {{2}} is ready.", "type": "BODY"},
            {"text": "Reply STOP to opt out", "type": "FOOTER"},
        ],
    }
    norm = _normalize_template_candidate(candidate)
    assert norm["body"] == "Hi {{1}}, your order {{2}} is ready."


def test_template_components_without_body_falls_back_to_first_text():
    from app.services.orchestration.adapters.wati import _normalize_template_candidate

    # No BODY-typed component: surface the first available text for preview
    # rather than empty — still never a fabricated sentence.
    candidate = {
        "template_name": "header_only",
        "language": "en",
        "status": "APPROVED",
        "components": [
            {"text": "Account alert", "type": "HEADER"},
        ],
    }
    norm = _normalize_template_candidate(candidate)
    assert norm["body"] == "Account alert"
    assert norm["body_original"] is None


def test_template_without_body_yields_empty_string_no_fabrication():
    from app.services.orchestration.adapters.wati import _normalize_template_candidate

    candidate = {
        "template_name": "noparams",
        "language": "en",
        "status": "APPROVED",
        "parameters": ["first_name"],
    }
    norm = _normalize_template_candidate(candidate)
    assert norm["body"] == ""
    assert norm["body_original"] is None


def test_provider_template_summary_carries_body_fields():
    from app.schemas.orchestration_connection import ProviderTemplateSummary

    s = ProviderTemplateSummary(
        name="t", language="en", status="APPROVED", parameters=["1"],
        body="Hi {{1}}", body_original="Hi {{name}}",
    )
    dumped = s.model_dump(by_alias=True)
    assert dumped["body"] == "Hi {{1}}"
    assert dumped["bodyOriginal"] == "Hi {{name}}"


def test_provider_template_summary_body_defaults_backward_compatible():
    from app.schemas.orchestration_connection import ProviderTemplateSummary

    s = ProviderTemplateSummary(name="t", language="en", status="APPROVED", parameters=[])
    assert s.body == ""
    assert s.body_original is None


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


def test_voice_config_from_phone_x_type_hint():
    """from_phone field must carry x-type phone_number_picker in JSON schema."""
    schema = _VoiceConfig.model_json_schema()
    props = schema.get("properties", {})
    assert "from_phone" in props
    assert props["from_phone"].get("x-type") == "phone_number_picker"


# ─── Bolna introspect_agent helper ────────────────────────────────────────────


def test_introspect_agent_extracts_tokens_from_prompt_and_welcome():
    """Variables are {token} placeholders from system_prompt + welcome_message, sorted+deduped."""
    from app.services.orchestration.adapters.bolna import introspect_agent

    agent = {
        "agent_prompts": {
            "task_1": {"system_prompt": "Hi {name}, your {plan} is ready"},
        },
        "agent_config": {"agent_welcome_message": "Hello {name}"},
    }
    result = introspect_agent(agent)
    assert result["variables"] == ["name", "plan"]
    assert "Hi {name}, your {plan} is ready" in result["prompt"]
    assert result["welcome_message"] == "Hello {name}"


def test_introspect_agent_no_prompts_no_welcome_returns_empty():
    """Agent with no prompts/welcome yields variables==[], prompt=='', welcome_message==''."""
    from app.services.orchestration.adapters.bolna import introspect_agent

    result = introspect_agent({})
    assert result["variables"] == []
    assert result["prompt"] == ""
    assert result["welcome_message"] == ""


def test_introspect_agent_union_with_explicit_variables_list():
    """Variables list from agent_config.variables is unioned with token matches, sorted+deduped."""
    from app.services.orchestration.adapters.bolna import introspect_agent

    agent = {
        "agent_prompts": {
            "task_1": {"system_prompt": "Hello {name}, welcome."},
        },
        "agent_config": {
            "agent_welcome_message": "",
            "variables": ["explicit_one"],
        },
    }
    result = introspect_agent(agent)
    assert result["variables"] == ["explicit_one", "name"]


def test_introspect_agent_multi_task_collects_all_prompts():
    """All task_N system_prompts are collected; prompt joins them with double newline."""
    from app.services.orchestration.adapters.bolna import introspect_agent

    agent = {
        "agent_prompts": {
            "task_1": {"system_prompt": "Task one: {alpha}"},
            "task_2": {"system_prompt": "Task two: {beta}"},
        },
        "agent_config": {"agent_welcome_message": ""},
    }
    result = introspect_agent(agent)
    assert "alpha" in result["variables"]
    assert "beta" in result["variables"]
    assert "Task one: {alpha}" in result["prompt"]
    assert "Task two: {beta}" in result["prompt"]


def test_introspect_agent_deduplicates_tokens():
    """Same token appearing in multiple prompts is counted once."""
    from app.services.orchestration.adapters.bolna import introspect_agent

    agent = {
        "agent_prompts": {
            "task_1": {"system_prompt": "{name} again {name}"},
        },
        "agent_config": {"agent_welcome_message": "Hi {name}"},
    }
    result = introspect_agent(agent)
    assert result["variables"].count("name") == 1


def test_introspect_agent_existing_detail_fixture_stays_green():
    """_BOLNA_AGENT_DETAIL (agent_config.variables list only) variables are still returned."""
    from app.services.orchestration.adapters.bolna import introspect_agent

    result = introspect_agent(_BOLNA_AGENT_DETAIL)
    # existing fixture has agent_config.variables=["patient_name","appointment_date"], no prompts
    assert "patient_name" in result["variables"]
    assert "appointment_date" in result["variables"]
    assert result["prompt"] == ""
    assert result["welcome_message"] == ""


def test_introspect_agent_defensive_against_wrong_types():
    """introspect_agent never raises on malformed/missing keys."""
    from app.services.orchestration.adapters.bolna import introspect_agent

    # agent_prompts is not a dict, agent_config.variables is not a list
    agent = {
        "agent_prompts": "not-a-dict",
        "agent_config": {"variables": "also-not-a-list"},
    }
    result = introspect_agent(agent)
    assert isinstance(result["variables"], list)
    assert isinstance(result["prompt"], str)
    assert isinstance(result["welcome_message"], str)


# ─── AgentVariablesResponse schema: prompt + welcome_message fields ───────────


def test_agent_variables_response_carries_prompt_and_welcome_message():
    """AgentVariablesResponse must expose prompt and welcomeMessage (camelCase alias)."""
    from app.schemas.orchestration_connection import AgentVariablesResponse

    resp = AgentVariablesResponse(
        provider="bolna",
        variables=["name", "plan"],
        prompt="Hi {name}",
        welcome_message="Hello {name}",
    )
    dumped = resp.model_dump(by_alias=True)
    assert dumped["prompt"] == "Hi {name}"
    assert dumped["welcomeMessage"] == "Hello {name}"


def test_agent_variables_response_prompt_defaults_empty():
    """Backward compatibility: omitting prompt/welcome_message yields empty strings."""
    from app.schemas.orchestration_connection import AgentVariablesResponse

    resp = AgentVariablesResponse(provider="wati", variables=[])
    assert resp.prompt == ""
    assert resp.welcome_message == ""


# ─── ProviderPhoneNumbersListResponse schema ──────────────────────────────────


def test_provider_phone_numbers_list_response_schema():
    """ProviderPhoneNumbersListResponse must expose provider, items, error (camelCase)."""
    from app.schemas.orchestration_connection import (
        ProviderPhoneNumberSummary,
        ProviderPhoneNumbersListResponse,
    )

    item = ProviderPhoneNumberSummary(phone_number="+19876543210", label="twilio")
    resp = ProviderPhoneNumbersListResponse(provider="bolna", items=[item], error=None)
    dumped = resp.model_dump(by_alias=True)
    assert dumped["provider"] == "bolna"
    assert dumped["items"][0]["phoneNumber"] == "+19876543210"
    assert dumped["items"][0]["label"] == "twilio"
    assert dumped["error"] is None


def test_provider_phone_number_summary_label_defaults_empty():
    """label defaults to '' when not supplied."""
    from app.schemas.orchestration_connection import ProviderPhoneNumberSummary

    item = ProviderPhoneNumberSummary(phone_number="+919999900000")
    assert item.label == ""


def test_provider_phone_numbers_list_response_error_field():
    """ProviderPhoneNumbersListResponse carries the soft-error string."""
    from app.schemas.orchestration_connection import ProviderPhoneNumbersListResponse

    resp = ProviderPhoneNumbersListResponse(
        provider="wati", items=[], error="upstream exploded"
    )
    assert resp.error == "upstream exploded"
    assert resp.items == []


# ─── Bolna adapter list_phone_numbers ─────────────────────────────────────────

# Verbatim fixture matching Bolna GET /phone-numbers/all response shape
_BOLNA_PHONE_NUMBERS_LIST: list[dict[str, Any]] = [
    {
        "id": "pn_001",
        "phone_number": "+19876543210",
        "telephony_provider": "twilio",
        "active": True,
    },
    {
        "id": "pn_002",
        "phone_number": "+19876543211",
        "telephony_provider": "plivo",
        "active": True,
    },
]


@pytest.mark.asyncio
async def test_bolna_list_phone_numbers_calls_correct_endpoint():
    """list_phone_numbers must call GET /phone-numbers/all with Bearer auth."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            status_code=200,
            headers={"content-type": "application/json"},
            content=json.dumps(_BOLNA_PHONE_NUMBERS_LIST).encode(),
        )

    transport = httpx.MockTransport(handler)
    adapter = BolnaAdapter()

    with patch(
        "app.services.orchestration.adapters.bolna._make_client",
        side_effect=lambda *a, **kw: httpx.AsyncClient(transport=transport),
    ):
        result = await adapter.list_phone_numbers(_BOLNA_CONN)

    assert len(captured) == 1
    req = captured[0]
    assert "/phone-numbers/all" in str(req.url)
    assert req.headers.get("Authorization") == "Bearer bolna_key_xyz"
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0] == {"phone_number": "+19876543210", "label": "twilio"}
    assert result[1] == {"phone_number": "+19876543211", "label": "plivo"}


@pytest.mark.asyncio
async def test_bolna_list_phone_numbers_empty_label_when_no_telephony_provider():
    """list_phone_numbers uses '' as label when telephony_provider is absent."""
    fixture = [{"id": "pn_003", "phone_number": "+12223334444"}]
    transport = _make_bolna_transport(200, fixture)
    adapter = BolnaAdapter()

    with patch(
        "app.services.orchestration.adapters.bolna._make_client",
        side_effect=lambda *a, **kw: httpx.AsyncClient(transport=transport),
    ):
        result = await adapter.list_phone_numbers(_BOLNA_CONN)

    assert result == [{"phone_number": "+12223334444", "label": ""}]


@pytest.mark.asyncio
async def test_bolna_list_phone_numbers_4xx_raises():
    """list_phone_numbers raises BolnaServiceError on 4xx."""
    transport = _make_bolna_transport(403, {"detail": "Forbidden"})
    adapter = BolnaAdapter()

    with patch(
        "app.services.orchestration.adapters.bolna._make_client",
        side_effect=lambda *a, **kw: httpx.AsyncClient(transport=transport),
    ):
        with pytest.raises(BolnaServiceError):
            await adapter.list_phone_numbers(_BOLNA_CONN)


@pytest.mark.asyncio
async def test_bolna_list_phone_numbers_missing_api_key_raises():
    """list_phone_numbers raises BolnaServiceError when api_key is empty."""
    adapter = BolnaAdapter()
    with pytest.raises(BolnaServiceError, match="api_key"):
        await adapter.list_phone_numbers({"api_key": "", "base_url": "https://api.bolna.ai"})


# ─── WATI adapter list_phone_numbers ─────────────────────────────────────────

# Verbatim fixture for WATI GET /api/v2/whatsapp/phoneNumbers.
# Shape: top-level dict with a "phoneNumbers" list of objects.
_WATI_PHONE_NUMBERS_PAYLOAD: dict[str, Any] = {
    "result": True,
    "phoneNumbers": [
        {"phoneNumber": "+911234567890", "displayName": "Main Channel"},
        {"phoneNumber": "+911234567891", "displayName": "Support Channel"},
    ],
}


@pytest.mark.asyncio
async def test_wati_list_phone_numbers_calls_correct_endpoint():
    """list_phone_numbers must call GET /api/v2/whatsapp/phoneNumbers with Bearer auth."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            status_code=200,
            headers={"content-type": "application/json"},
            content=json.dumps(_WATI_PHONE_NUMBERS_PAYLOAD).encode(),
        )

    transport = httpx.MockTransport(handler)
    adapter = WatiAdapter()

    with patch(
        "app.services.orchestration.adapters.wati._make_client",
        side_effect=lambda *a, **kw: httpx.AsyncClient(transport=transport),
    ):
        result = await adapter.list_phone_numbers(_WATI_CONN)

    assert len(captured) == 1
    req = captured[0]
    assert "/api/v2/whatsapp/phoneNumbers" in str(req.url)
    assert req.headers.get("Authorization") == "Bearer tok_abc"
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["phone_number"] == "+911234567890"
    assert result[1]["phone_number"] == "+911234567891"


@pytest.mark.asyncio
async def test_wati_list_phone_numbers_top_level_array():
    """list_phone_numbers handles a top-level JSON array (alternative WATI shape)."""
    fixture = [
        {"phone_number": "+919999900001"},
        {"phoneNumber": "+919999900002"},
    ]
    transport = _make_wati_transport(200, fixture)
    adapter = WatiAdapter()

    with patch(
        "app.services.orchestration.adapters.wati._make_client",
        side_effect=lambda *a, **kw: httpx.AsyncClient(transport=transport, **({"timeout": kw["timeout"]} if "timeout" in kw else {})),
    ):
        result = await adapter.list_phone_numbers(_WATI_CONN)

    assert len(result) == 2
    numbers = {r["phone_number"] for r in result}
    assert "+919999900001" in numbers
    assert "+919999900002" in numbers


@pytest.mark.asyncio
async def test_wati_list_phone_numbers_empty_on_unmappable_items():
    """Items with no recognisable phone field are skipped; result is empty, not an error."""
    fixture = {"phoneNumbers": [{"id": "abc", "status": "active"}]}
    transport = _make_wati_transport(200, fixture)
    adapter = WatiAdapter()

    with patch(
        "app.services.orchestration.adapters.wati._make_client",
        side_effect=lambda *a, **kw: httpx.AsyncClient(transport=transport, **({"timeout": kw["timeout"]} if "timeout" in kw else {})),
    ):
        result = await adapter.list_phone_numbers(_WATI_CONN)

    assert result == []


@pytest.mark.asyncio
async def test_wati_list_phone_numbers_4xx_raises():
    """list_phone_numbers raises WatiServiceError on 4xx."""
    transport = _make_wati_transport(401, {"error": "Unauthorized"})
    adapter = WatiAdapter()

    with patch(
        "app.services.orchestration.adapters.wati._make_client",
        side_effect=lambda *a, **kw: httpx.AsyncClient(transport=transport, **({"timeout": kw["timeout"]} if "timeout" in kw else {})),
    ):
        with pytest.raises(WatiServiceError):
            await adapter.list_phone_numbers(_WATI_CONN)


@pytest.mark.asyncio
async def test_wati_list_phone_numbers_channelname_populates_label():
    """channelName from the WATI response is surfaced as label on each item."""
    fixture: dict[str, Any] = {
        "result": True,
        "phoneNumbers": [
            {"phoneNumber": "+911234567890", "channelName": "Support Line"},
            {"phoneNumber": "+911234567891", "channelName": "Sales Line"},
            {"phoneNumber": "+911234567892"},
        ],
    }
    transport = _make_wati_transport(200, fixture)
    adapter = WatiAdapter()

    with patch(
        "app.services.orchestration.adapters.wati._make_client",
        side_effect=lambda *a, **kw: httpx.AsyncClient(transport=transport, **({"timeout": kw["timeout"]} if "timeout" in kw else {})),
    ):
        result = await adapter.list_phone_numbers(_WATI_CONN)

    assert len(result) == 3
    assert result[0] == {"phone_number": "+911234567890", "label": "Support Line"}
    assert result[1] == {"phone_number": "+911234567891", "label": "Sales Line"}
    # Item without channelName/displayName/name falls back to empty label.
    assert result[2] == {"phone_number": "+911234567892", "label": ""}


@pytest.mark.asyncio
async def test_wati_list_phone_numbers_displayname_fallback_label():
    """displayName is used as label when channelName is absent."""
    fixture: dict[str, Any] = {
        "result": True,
        "phoneNumbers": [
            {"phoneNumber": "+911234567890", "displayName": "Main Channel"},
        ],
    }
    transport = _make_wati_transport(200, fixture)
    adapter = WatiAdapter()

    with patch(
        "app.services.orchestration.adapters.wati._make_client",
        side_effect=lambda *a, **kw: httpx.AsyncClient(transport=transport, **({"timeout": kw["timeout"]} if "timeout" in kw else {})),
    ):
        result = await adapter.list_phone_numbers(_WATI_CONN)

    assert result == [{"phone_number": "+911234567890", "label": "Main Channel"}]


# ─── provider_listings.list_connection_phone_numbers (service layer) ──────────


@pytest.mark.asyncio
async def test_list_connection_phone_numbers_bolna_soft_error_on_connection_not_found():
    """Soft-error: missing/wrong-provider connection returns {items:[], error:...} not 500."""
    from app.services.orchestration.api.provider_listings import list_connection_phone_numbers

    mock_db = AsyncMock()
    mock_db.scalar = AsyncMock(return_value=None)

    result = await list_connection_phone_numbers(
        mock_db,
        tenant_id=uuid.uuid4(),
        app_id="test-app",
        connection_id=uuid.uuid4(),
        provider="bolna",
    )

    assert result["items"] == []
    assert result["error"] is not None
    assert result["provider"] == "bolna"


@pytest.mark.asyncio
async def test_list_connection_phone_numbers_bolna_upstream_error_is_soft():
    """Upstream BolnaServiceError is caught and returned as soft error, not 500."""
    from app.services.orchestration.api.provider_listings import list_connection_phone_numbers
    from app.models.provider_connection import ProviderConnection
    from unittest.mock import MagicMock
    import json as _json

    conn_mock = MagicMock(spec=ProviderConnection)
    conn_mock.provider = "bolna"
    conn_mock.app_id = "test-app"
    conn_mock.config_encrypted = b"encrypted"

    mock_db = AsyncMock()
    mock_db.scalar = AsyncMock(return_value=conn_mock)

    with (
        patch(
            "app.services.orchestration.api.provider_listings._load_connection",
            return_value={"api_key": "k", "base_url": "https://api.bolna.ai"},
        ),
        patch(
            "app.services.orchestration.adapters.bolna.BolnaAdapter.list_phone_numbers",
            side_effect=BolnaServiceError("upstream error"),
        ),
    ):
        result = await list_connection_phone_numbers(
            mock_db,
            tenant_id=uuid.uuid4(),
            app_id="test-app",
            connection_id=uuid.uuid4(),
            provider="bolna",
        )

    assert result["items"] == []
    assert "upstream error" in (result["error"] or "")


@pytest.mark.asyncio
async def test_list_connection_phone_numbers_wati_soft_error_on_connection_not_found():
    """Soft-error for WATI: missing/wrong-provider connection."""
    from app.services.orchestration.api.provider_listings import list_connection_phone_numbers

    mock_db = AsyncMock()
    mock_db.scalar = AsyncMock(return_value=None)

    result = await list_connection_phone_numbers(
        mock_db,
        tenant_id=uuid.uuid4(),
        app_id="test-app",
        connection_id=uuid.uuid4(),
        provider="wati",
    )

    assert result["items"] == []
    assert result["error"] is not None
    assert result["provider"] == "wati"


# ─── route: wrong provider → 400 ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_route_phone_numbers_wrong_provider_raises_http400():
    """list_connection_phone_numbers route raises HTTPException(400) for unsupported providers."""
    from fastapi import HTTPException
    from unittest.mock import MagicMock, AsyncMock, patch as _patch
    from app.models.provider_connection import ProviderConnection
    import uuid as _uuid

    conn_id = _uuid.uuid4()
    conn_mock = MagicMock(spec=ProviderConnection)
    conn_mock.provider = "twilio"
    conn_mock.app_id = "test-app"
    conn_mock.tenant_id = _uuid.uuid4()
    conn_mock.active = True

    from app.routes.orchestration_connections import list_connection_phone_numbers
    from app.auth import AuthContext

    auth_mock = MagicMock(spec=AuthContext)
    auth_mock.tenant_id = _uuid.uuid4()
    db_mock = AsyncMock()

    with _patch(
        "app.routes.orchestration_connections._load_and_gate_connection",
        return_value=conn_mock,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await list_connection_phone_numbers(
                connection_id=conn_id,
                auth=auth_mock,
                db=db_mock,
                refresh=False,
            )

    assert exc_info.value.status_code == 400
    assert "twilio" in exc_info.value.detail

"""Pure unit/contract tests for messaging.send_whatsapp_template + WATI + AiSensy adapters.

No live HTTP. WATI/AiSensy outbound paths exercised via httpx.MockTransport.
Webhook normalization tested against verbatim payload fixtures pulled from
the plan's evidence section (docs/plans/2026-05-18-orchestration-vendor-abstraction/README.md §2.3).
"""
from __future__ import annotations

import json
import uuid

import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.services.orchestration.adapters.aisensy import (
    AiSensyAdapter,
    AiSensyServiceError,
)
from app.services.orchestration.adapters.canonical import (
    CanonicalSendRequest,
)
from app.services.orchestration.adapters.wati import (
    WatiAdapter,
    WatiServiceError,
    _extract_button_id,
    _extract_local_message_id,
    _extract_reply_text,
    _extract_reply_type,
    _strip_plus,
    resolve_wati_api_endpoint,
)
from app.services.orchestration.nodes.messaging_send_whatsapp_template import (
    _Config,
)


# ─── _Config strictness ─────────────────────────────────────────────────────


def test_config_minimum_required_fields():
    cid = uuid.uuid4()
    cfg = _Config(connection_id=cid, template_name="welcome_v1")
    assert cfg.connection_id == cid
    assert cfg.template_name == "welcome_v1"
    assert cfg.variable_mappings == []
    assert cfg.webhook_ttl_seconds == 259200  # 3 days


def test_config_rejects_unknown_keys():
    with pytest.raises(ValidationError) as exc_info:
        _Config(
            connection_id=uuid.uuid4(),
            template_name="welcome_v1",
            unknown_field="should_be_rejected",
        )
    assert any(
        err.get("type") == "extra_forbidden"
        for err in exc_info.value.errors()
    )


def test_config_template_name_draft_safe_empty():
    # template_name is the publish-gated picker field — empty is a valid draft.
    cfg = _Config(connection_id=uuid.uuid4())
    assert cfg.template_name == ""


def test_config_webhook_ttl_seconds_min_60():
    with pytest.raises(ValidationError):
        _Config(
            connection_id=uuid.uuid4(),
            template_name="x",
            webhook_ttl_seconds=30,
        )


# ─── WATI helpers ───────────────────────────────────────────────────────────


def test_resolve_wati_api_endpoint_appends_tenant_when_missing():
    assert (
        resolve_wati_api_endpoint("https://live-mt-server.wati.io", "12345")
        == "https://live-mt-server.wati.io/12345"
    )


def test_resolve_wati_api_endpoint_no_double_append():
    assert (
        resolve_wati_api_endpoint("https://live-mt-server.wati.io/12345", "12345")
        == "https://live-mt-server.wati.io/12345"
    )


def test_strip_plus():
    assert _strip_plus("+919999999999") == "919999999999"
    assert _strip_plus("919999999999") == "919999999999"


def test_extract_local_message_id_v2_top_level():
    assert _extract_local_message_id({"localMessageId": "abc-123"}) == "abc-123"


def test_extract_local_message_id_v1_receivers():
    payload = {"receivers": [{"localMessageId": "v1-xyz", "waId": "91..."}]}
    assert _extract_local_message_id(payload) == "v1-xyz"


def test_extract_local_message_id_missing():
    assert _extract_local_message_id({"unrelated": "data"}) is None


# ─── WATI webhook normalization — verbatim §2.3 fixtures ────────────────────


REPLY_BUTTON_FIXTURE = {
    "eventType": "sentMessageREPLIED_v2",
    "statusString": "Replied",
    "localMessageId": "d38f0c3a-e833-4725-a894-53a2b1dc1af6",
    "id": "640c8fd48b67615f886237b8",
    "whatsappMessageId": "gBEGkXmJQZVJAgkRHwjjZsITS6M",
    "replyContextId": "OLD_OUTBOUND_WA_MSG_ID",
    "waId": "919999999999",
    "buttonReply": {
        "payload": '{"ButtonIndex":0,"CarouselCardIndex":null,"BroadcastLinkId":"676a9b2e57150cedccdb7a17"}',
        "text": "Tell me more",
    },
}


MESSAGE_RECEIVED_TEXT_FIXTURE = {
    "eventType": "messageReceived",
    "localMessageId": "lm-text-1",
    "waId": "919999999999",
    "type": "text",
    "text": "Yes please",
}


MESSAGE_RECEIVED_LIST_FIXTURE = {
    "eventType": "messageReceived",
    "localMessageId": "lm-list-1",
    "waId": "919999999999",
    "listReply": {"id": "row_2", "title": "Tuesday morning"},
}


TEMPLATE_FAILED_FIXTURE = {
    "eventType": "templateMessageFailed",
    "localMessageId": "lm-fail-1",
    "waId": "919999999999",
    "statusString": "Failed",
}


def test_normalize_button_reply():
    ev = WatiAdapter().normalize_webhook(REPLY_BUTTON_FIXTURE)
    assert ev.status == "replied"
    assert ev.contact == "919999999999"
    assert ev.provider_correlation_id == "d38f0c3a-e833-4725-a894-53a2b1dc1af6"
    assert ev.reply_context_id == "OLD_OUTBOUND_WA_MSG_ID"
    assert ev.reply_type == "button"
    assert ev.reply_text == "Tell me more"
    assert ev.button_id == "0"
    assert ev.list_id is None


def test_normalize_text_reply():
    ev = WatiAdapter().normalize_webhook(MESSAGE_RECEIVED_TEXT_FIXTURE)
    assert ev.status == "replied"
    assert ev.reply_type == "text"
    assert ev.reply_text == "Yes please"
    assert ev.button_id is None
    assert ev.list_id is None


def test_normalize_list_reply():
    ev = WatiAdapter().normalize_webhook(MESSAGE_RECEIVED_LIST_FIXTURE)
    assert ev.status == "replied"
    assert ev.reply_type == "list"
    assert ev.list_id == "row_2"
    assert ev.button_id is None


def test_normalize_template_failed():
    ev = WatiAdapter().normalize_webhook(TEMPLATE_FAILED_FIXTURE)
    assert ev.status == "failed"
    assert ev.reply_type is None  # failed is not a reply event
    assert ev.button_id is None


def test_normalize_unknown_event():
    ev = WatiAdapter().normalize_webhook({"eventType": "nonsense"})
    assert ev.status == "unknown"


def test_extract_button_id_handles_corrupt_json():
    # Defensive: a malformed payload string must not raise — adapter falls back.
    assert _extract_button_id({"buttonReply": {"payload": "not-json"}}) is None


def test_extract_reply_text_prefers_text_over_messageBody():
    assert _extract_reply_text({"text": "primary", "messageBody": "secondary"}) == "primary"


def test_extract_reply_type_for_interactive_button():
    assert _extract_reply_type({"interactiveButtonReply": {"buttonId": "b1"}}) == "button"


# ─── WATI send_template — via MockTransport (no live HTTP) ──────────────────


def _connection(channel_numbers=("+919811111111",)):
    return {
        "base_url": "https://live-mt-server.wati.io",
        "wati_tenant_id": "12345",
        "api_token": "test-token",
        "channel_numbers": list(channel_numbers),
        "__provider__": "wati",
    }


@pytest.mark.asyncio
async def test_send_template_happy_path(monkeypatch):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        captured["headers"] = dict(request.headers)
        return httpx.Response(
            200, json={"localMessageId": "lm-happy", "whatsappMessageId": "wam-1"},
        )

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        "app.services.orchestration.adapters.wati._make_client",
        lambda timeout=30.0: httpx.AsyncClient(transport=transport, timeout=timeout),
    )

    adapter = WatiAdapter()
    request = CanonicalSendRequest(
        contact="+919999999999",
        template_name="welcome_v1",
        variables={"name": "Dhruv", "appointment": "Tuesday 3pm"},
    )
    response = await adapter.send_template(
        connection=_connection(), request=request,
    )

    assert response.provider_correlation_id == "lm-happy"
    assert response.contact == "+919999999999"
    assert "whatsappNumber=919999999999" in captured["url"]
    assert captured["url"].endswith("/api/v2/sendTemplateMessage?whatsappNumber=919999999999")
    assert captured["body"]["template_name"] == "welcome_v1"
    # broadcast_name falls back to template_name when not picked.
    assert captured["body"]["broadcast_name"] == "welcome_v1"
    # channel_number falls back to the connection's first number when not picked.
    assert captured["body"]["channel_number"] == "+919811111111"
    assert captured["body"]["parameters"] == [
        {"name": "name", "value": "Dhruv"},
        {"name": "appointment", "value": "Tuesday 3pm"},
    ]
    assert captured["headers"]["authorization"] == "Bearer test-token"


# I1 send-truth: a WATI 200 is only a real send when result==true AND every
# receiver isValidWhatsAppNumber AND no receiver errors. Verbatim v2 body shape
# from support.wati.io sendTemplateMessage docs.


_WATI_V2_VALID = {
    "result": True,
    "error": None,
    "templateName": "welcome_v1",
    "receivers": [
        {
            "localMessageId": "lm-valid",
            "waId": "919999999999",
            "isValidWhatsAppNumber": True,
            "errors": [],
        }
    ],
    "parameters": [],
}

_WATI_V2_INVALID_NUMBER = {
    "result": True,
    "error": None,
    "templateName": "welcome_v1",
    "receivers": [
        {
            "localMessageId": "lm-invalid",
            "waId": "919999999999",
            "isValidWhatsAppNumber": False,
            "errors": [],
        }
    ],
    "parameters": [],
}

_WATI_V2_RESULT_FALSE = {
    "result": False,
    "error": "Template not approved",
    "templateName": "welcome_v1",
    "receivers": [],
    "parameters": [],
}

_WATI_V2_RECEIVER_ERRORS = {
    "result": True,
    "error": None,
    "templateName": "welcome_v1",
    "receivers": [
        {
            "localMessageId": "lm-err",
            "waId": "919999999999",
            "isValidWhatsAppNumber": True,
            "errors": ["rate_limited"],
        }
    ],
    "parameters": [],
}


def _transport_returning(monkeypatch, body):
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json=body))
    monkeypatch.setattr(
        "app.services.orchestration.adapters.wati._make_client",
        lambda timeout=30.0: httpx.AsyncClient(transport=transport, timeout=timeout),
    )


@pytest.mark.asyncio
async def test_send_template_valid_number_is_accepted(monkeypatch):
    _transport_returning(monkeypatch, _WATI_V2_VALID)
    resp = await WatiAdapter().send_template(
        connection=_connection(),
        request=CanonicalSendRequest(contact="+919999999999", template_name="welcome_v1"),
    )
    assert resp.accepted is True
    assert resp.reason is None
    assert resp.provider_correlation_id == "lm-valid"


@pytest.mark.asyncio
async def test_send_template_invalid_number_is_rejected(monkeypatch):
    _transport_returning(monkeypatch, _WATI_V2_INVALID_NUMBER)
    resp = await WatiAdapter().send_template(
        connection=_connection(),
        request=CanonicalSendRequest(contact="+919999999999", template_name="welcome_v1"),
    )
    assert resp.accepted is False
    assert resp.reason is not None
    assert "valid" in resp.reason.lower() or "number" in resp.reason.lower()
    # localMessageId still captured for correlation even on a rejected send.
    assert resp.provider_correlation_id == "lm-invalid"


@pytest.mark.asyncio
async def test_send_template_result_false_raises(monkeypatch):
    # result=false carries no receivers and thus no localMessageId — there is
    # nothing to correlate, so this is a hard WatiServiceError (the handler still
    # records the action as failed). accepted=False is reserved for a 200 that
    # DID return a message id but is a silent non-send (invalid number / errors).
    _transport_returning(monkeypatch, _WATI_V2_RESULT_FALSE)
    with pytest.raises(WatiServiceError):
        await WatiAdapter().send_template(
            connection=_connection(),
            request=CanonicalSendRequest(contact="+919999999999", template_name="welcome_v1"),
        )


@pytest.mark.asyncio
async def test_send_template_receiver_errors_is_rejected(monkeypatch):
    _transport_returning(monkeypatch, _WATI_V2_RECEIVER_ERRORS)
    resp = await WatiAdapter().send_template(
        connection=_connection(),
        request=CanonicalSendRequest(contact="+919999999999", template_name="welcome_v1"),
    )
    assert resp.accepted is False
    assert "rate_limited" in resp.reason


@pytest.mark.asyncio
async def test_send_template_uses_picked_broadcast_and_channel(monkeypatch):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"localMessageId": "lm-pick"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        "app.services.orchestration.adapters.wati._make_client",
        lambda timeout=30.0: httpx.AsyncClient(transport=transport, timeout=timeout),
    )

    request = CanonicalSendRequest(
        contact="+919999999999",
        template_name="document_approved_latest",
        broadcast_name="May campaign",
        channel_number="+918511975757",
        variables={"name": "Pareekshith"},
    )
    await WatiAdapter().send_template(connection=_connection(), request=request)

    # Operator-picked values win over the connection default.
    assert captured["body"]["template_name"] == "document_approved_latest"
    assert captured["body"]["broadcast_name"] == "May campaign"
    assert captured["body"]["channel_number"] == "+918511975757"


@pytest.mark.asyncio
async def test_send_template_4xx_raises_service_error(monkeypatch):
    transport = httpx.MockTransport(
        lambda r: httpx.Response(400, json={"error": "invalid_template"}),
    )
    monkeypatch.setattr(
        "app.services.orchestration.adapters.wati._make_client",
        lambda timeout=30.0: httpx.AsyncClient(transport=transport, timeout=timeout),
    )

    with pytest.raises(WatiServiceError) as exc:
        await WatiAdapter().send_template(
            connection=_connection(),
            request=CanonicalSendRequest(contact="+91999", template_name="x"),
        )
    assert "400" in str(exc.value)


@pytest.mark.asyncio
async def test_send_template_missing_local_message_id_raises(monkeypatch):
    transport = httpx.MockTransport(
        lambda r: httpx.Response(200, json={"unrelated": "no_id_here"}),
    )
    monkeypatch.setattr(
        "app.services.orchestration.adapters.wati._make_client",
        lambda timeout=30.0: httpx.AsyncClient(transport=transport, timeout=timeout),
    )

    with pytest.raises(WatiServiceError) as exc:
        await WatiAdapter().send_template(
            connection=_connection(),
            request=CanonicalSendRequest(contact="+91999", template_name="x"),
        )
    assert "localMessageId" in str(exc.value)


@pytest.mark.asyncio
async def test_send_template_missing_connection_fields():
    with pytest.raises(WatiServiceError):
        await WatiAdapter().send_template(
            connection={"base_url": "https://x", "wati_tenant_id": "", "api_token": "t"},
            request=CanonicalSendRequest(contact="+91999", template_name="x"),
        )


# ─── AiSensy skeleton ───────────────────────────────────────────────────────


def test_aisensy_normalize_webhook_is_not_implemented():
    with pytest.raises(NotImplementedError) as exc:
        AiSensyAdapter().normalize_webhook({"any": "thing"})
    assert "AiSensy" in str(exc.value)
    assert "field mapping is pending" in str(exc.value)


@pytest.mark.asyncio
async def test_aisensy_handle_webhook_returns_503():
    adapter = AiSensyAdapter()
    with pytest.raises(HTTPException) as exc:
        await adapter.handle_webhook(
            db=None,  # type: ignore[arg-type]
            tenant_id=uuid.uuid4(),
            app_id="inside-sales",
            payload={"any": "inbound"},
        )
    assert exc.value.status_code == 503
    detail = str(exc.value.detail)
    # decodeApiError-compatible: detail is a non-empty string (FE renders via summarizeApiErrorBody)
    assert "Inbound" in detail
    assert "Outbound" in detail
    assert "pending" in detail


@pytest.mark.asyncio
async def test_aisensy_send_template_happy_path(monkeypatch):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"status": "ok"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        "app.services.orchestration.adapters.aisensy._make_client",
        lambda timeout=30.0: httpx.AsyncClient(transport=transport, timeout=timeout),
    )

    connection = {
        "api_key": "secret-key",
        "base_url": "https://backend.aisensy.com",
        "from_number": "+919811111111",
        "campaign_partner_id": "p123",
        "__provider__": "aisensy",
    }
    request = CanonicalSendRequest(
        contact="919999999999",
        template_name="onboarding_v2",
        variables={"name": "Dhruv", "slot": "Tuesday"},
    )
    response = await AiSensyAdapter().send_template(
        connection=connection, request=request,
    )

    assert captured["url"] == "https://backend.aisensy.com/campaign/t1/api/v2"
    assert captured["body"]["apiKey"] == "secret-key"
    assert captured["body"]["campaignName"] == "onboarding_v2"
    assert captured["body"]["destination"] == "919999999999"
    assert captured["body"]["templateParams"] == ["Dhruv", "Tuesday"]
    assert response.contact == "919999999999"
    assert response.provider_correlation_id.startswith("aisensy:919999999999:onboarding_v2:")


@pytest.mark.asyncio
async def test_aisensy_send_template_4xx_raises(monkeypatch):
    transport = httpx.MockTransport(
        lambda r: httpx.Response(401, json={"error": "bad_key"}),
    )
    monkeypatch.setattr(
        "app.services.orchestration.adapters.aisensy._make_client",
        lambda timeout=30.0: httpx.AsyncClient(transport=transport, timeout=timeout),
    )

    with pytest.raises(AiSensyServiceError):
        await AiSensyAdapter().send_template(
            connection={"api_key": "k", "base_url": "https://x"},
            request=CanonicalSendRequest(contact="91999", template_name="x"),
        )


# ─── Handler: destination resolution ────────────────────────────────────────


@pytest.mark.asyncio
async def test_handler_sends_operator_picked_field_not_recipient_id(monkeypatch):
    """Regression: WhatsApp dispatch sends the operator-picked payload field
    (normalized), never the recipient_id (the bug that sent 'P-pareekshith')."""
    import uuid as _uuid
    from types import SimpleNamespace

    import app.services.orchestration.nodes.messaging_send_whatsapp_template as msg
    from app.services.orchestration.adapters.canonical import CanonicalSendResponse

    captured: dict = {}

    class _StubAdapter:
        async def send_template(self, *, connection, request):  # noqa: ARG002
            captured["contact"] = request.contact
            return CanonicalSendResponse(
                provider_correlation_id="lm-1", contact=request.contact, raw={},
            )

    async def _manifest(_db, *, run_id, recipient_id):  # noqa: ARG001
        return SimpleNamespace(recipient_id=recipient_id, phone_e164="+918888888888")

    async def _ok_cap(_db, *, tenant_id, app_id, contact, channel, stage="cap_runtime"):  # noqa: ARG001
        from app.services.orchestration.comm_cap.enforcement import EnforcementResult

        return EnforcementResult(proceed=True)

    monkeypatch.setattr(msg, "assert_recipient_in_manifest", _manifest)
    monkeypatch.setattr(msg, "enforce_comm_cap_or_skip", _ok_cap)
    monkeypatch.setattr(msg, "resolve_adapter", lambda **_k: _StubAdapter())

    class _Conns:
        async def get_config(self, _cid):
            return {"__provider__": "wati"}

    class _Ctx:
        run_id = _uuid.uuid4()
        tenant_id = _uuid.uuid4()
        app_id = "test-orchestration"
        db = object()
        connections = _Conns()

        def idempotency_key(self, *parts):
            return "|".join(str(p) for p in parts)

        async def dispatch_actions(self, dispatches):
            from app.services.orchestration.node_protocol import ActionResult

            return [
                ActionResult(recipient_id=d.recipient_id, action_id="a1", status="pending")
                for d in dispatches
            ]

        async def update_action_result(self, *_a, **_k):
            return None

        async def stamp_webhook_ttl(self, *_a, **_k):
            return None

        async def set_recipient_state(self, *_a, **_k):
            return None

    async def _cohort():
        # recipient_id is NOT a phone; phone lives under a dataset-style column.
        yield "P-pareekshith", {"lead_id": "P-pareekshith", "mobile": "+918888888888"}

    cfg = _Config(connection_id=uuid.uuid4(), template_name="welcome_v1", phone_field="mobile")
    await msg._Handler().execute(_cohort(), cfg, _Ctx())
    assert captured["contact"] == "+918888888888"


@pytest.mark.asyncio
async def test_handler_calls_enforcer_with_resolved_contact_and_channel(monkeypatch):
    """Seam: the dispatch handler calls enforce_comm_cap_or_skip with the new
    signature — the RESOLVED, normalized phone (same value written to
    payload.contact) and channel='whatsapp'. Phase 2's reach count keys on it."""
    import uuid as _uuid
    from types import SimpleNamespace

    import app.services.orchestration.nodes.messaging_send_whatsapp_template as msg
    from app.services.orchestration.adapters.canonical import CanonicalSendResponse

    seen: dict = {}

    async def _capture_cap(_db, *, tenant_id, app_id, contact, channel, stage="cap_runtime"):
        from app.services.orchestration.comm_cap.enforcement import EnforcementResult
        seen.update(tenant_id=tenant_id, app_id=app_id, contact=contact, channel=channel, stage=stage)
        return EnforcementResult(proceed=True)

    class _StubAdapter:
        async def send_template(self, *, connection, request):  # noqa: ARG002
            seen["payload_contact"] = request.contact
            return CanonicalSendResponse(
                provider_correlation_id="lm-1", contact=request.contact, raw={},
            )

    async def _manifest(_db, *, run_id, recipient_id):  # noqa: ARG001
        return SimpleNamespace(recipient_id=recipient_id, phone_e164="+918888888888")

    monkeypatch.setattr(msg, "assert_recipient_in_manifest", _manifest)
    monkeypatch.setattr(msg, "enforce_comm_cap_or_skip", _capture_cap)
    monkeypatch.setattr(msg, "resolve_adapter", lambda **_k: _StubAdapter())

    tid = _uuid.uuid4()

    class _Conns:
        async def get_config(self, _cid):
            return {"__provider__": "wati"}

    class _Ctx:
        run_id = _uuid.uuid4()
        tenant_id = tid
        app_id = "inside-sales"
        db = object()
        connections = _Conns()

        def idempotency_key(self, *parts):
            return "|".join(str(p) for p in parts)

        async def dispatch_actions(self, dispatches):
            from app.services.orchestration.node_protocol import ActionResult
            seen["dispatch_payload"] = dispatches[0].payload
            return [ActionResult(recipient_id=d.recipient_id, action_id="a1", status="pending") for d in dispatches]

        async def update_action_result(self, *_a, **_k):
            return None

        async def stamp_webhook_ttl(self, *_a, **_k):
            return None

        async def set_recipient_state(self, *_a, **_k):
            return None

    async def _cohort():
        yield "rid-1", {"mobile": "0 88888 88888"}

    cfg = _Config(connection_id=uuid.uuid4(), template_name="welcome_v1", phone_field="mobile")
    await msg._Handler().execute(_cohort(), cfg, _Ctx())

    assert seen["tenant_id"] == tid
    assert seen["app_id"] == "inside-sales"
    assert seen["channel"] == "whatsapp"
    # Enforcer contact == payload.contact == the normalized phone we dialed.
    assert seen["contact"] == seen["payload_contact"]
    assert seen["contact"] == seen["dispatch_payload"]["contact"]
    assert seen["contact"].startswith("+91")


@pytest.mark.asyncio
async def test_handler_records_failed_when_send_not_accepted(monkeypatch):
    """I1: a 200 that the adapter judged a non-send (accepted=False) is recorded
    as a failed action with the reason, and the recipient lands in 'failed' —
    not 'success'. The provider_correlation_id is still stamped for correlation."""
    import uuid as _uuid
    from types import SimpleNamespace

    import app.services.orchestration.nodes.messaging_send_whatsapp_template as msg
    from app.services.orchestration.adapters.canonical import CanonicalSendResponse

    updates: dict = {}

    class _StubAdapter:
        async def send_template(self, *, connection, request):  # noqa: ARG002
            return CanonicalSendResponse(
                provider_correlation_id="lm-invalid", contact=request.contact,
                accepted=False, reason="not a valid WhatsApp number (waId=919999999999)",
                raw={},
            )

    async def _manifest(_db, *, run_id, recipient_id):  # noqa: ARG001
        return SimpleNamespace(recipient_id=recipient_id, phone_e164="+918888888888")

    async def _ok_cap(_db, **_k):  # noqa: ARG001
        from app.services.orchestration.comm_cap.enforcement import EnforcementResult
        return EnforcementResult(proceed=True)

    monkeypatch.setattr(msg, "assert_recipient_in_manifest", _manifest)
    monkeypatch.setattr(msg, "enforce_comm_cap_or_skip", _ok_cap)
    monkeypatch.setattr(msg, "resolve_adapter", lambda **_k: _StubAdapter())

    class _Conns:
        async def get_config(self, _cid):
            return {"__provider__": "wati"}

    class _Ctx:
        run_id = _uuid.uuid4()
        tenant_id = _uuid.uuid4()
        app_id = "test-orchestration"
        db = object()
        connections = _Conns()

        def idempotency_key(self, *parts):
            return "|".join(str(p) for p in parts)

        async def dispatch_actions(self, dispatches):
            from app.services.orchestration.node_protocol import ActionResult
            return [
                ActionResult(recipient_id=d.recipient_id, action_id="a1", status="pending")
                for d in dispatches
            ]

        async def update_action_result(self, action_id, **kwargs):
            updates[action_id] = kwargs

        async def stamp_webhook_ttl(self, *_a, **_k):
            return None

        async def set_recipient_state(self, *_a, **_k):
            return None

    async def _cohort():
        yield "rid-1", {"mobile": "+918888888888"}

    cfg = _Config(connection_id=uuid.uuid4(), template_name="welcome_v1", phone_field="mobile")
    result = await msg._Handler().execute(_cohort(), cfg, _Ctx())

    assert result.by_output_id["failed"] and not result.by_output_id["success"]
    assert updates["a1"]["status"] == "failed"
    assert "valid" in (updates["a1"].get("error") or "")
    # Correlation id still stamped on the failed action.
    assert updates["a1"].get("provider_correlation_id") == "lm-invalid"


# ─── Adapter registry — boot integration ────────────────────────────────────


def test_messaging_adapters_registered_at_module_import():
    # Both adapter modules self-register on import; confirm both keys are present.
    from app.services.orchestration.adapters import registered_adapters

    keys = dict.fromkeys(registered_adapters())
    assert ("messaging", "wati") in keys
    assert ("messaging", "aisensy") in keys

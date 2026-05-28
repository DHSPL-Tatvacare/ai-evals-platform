"""Pure unit/contract tests for voice.place_call + BolnaAdapter.

No live HTTP. Bolna outbound paths exercised via httpx.MockTransport.
Webhook normalization tested against verbatim payload fixtures matching
the field set documented at https://www.bolna.ai/docs.
"""
from __future__ import annotations

import uuid

import httpx
import pytest
from pydantic import ValidationError

from app.services.orchestration.adapters import (
    registered_adapters,
    resolve_adapter,
)
from app.services.orchestration.adapters.bolna import (
    BolnaAdapter,
    BolnaServiceError,
    _build_batch_csv,
    _extract_capture,
    _normalize_cost_scalar,
    _resolve_from_phone,
    classify_outcome,
    is_terminal,
)
from app.services.orchestration.adapters.canonical import (
    CanonicalVoiceRequest,
)
from app.services.orchestration.nodes.voice_place_call import _Config


# ─── _Config strictness ─────────────────────────────────────────────────────


def test_config_minimum_required_fields():
    cid = uuid.uuid4()
    cfg = _Config(connection_id=cid, agent_id="agent_xyz")
    assert cfg.connection_id == cid
    assert cfg.agent_id == "agent_xyz"
    assert cfg.variable_mappings == []
    assert cfg.from_phone is None
    assert cfg.webhook_ttl_seconds == 259200


def test_config_rejects_unknown_keys():
    with pytest.raises(ValidationError) as exc_info:
        _Config(
            connection_id=uuid.uuid4(),
            agent_id="agent_xyz",
            unknown_field="boom",
        )
    assert any(
        err.get("type") == "extra_forbidden"
        for err in exc_info.value.errors()
    )


def test_config_agent_id_required_non_empty():
    with pytest.raises(ValidationError):
        _Config(connection_id=uuid.uuid4(), agent_id="")


def test_config_webhook_ttl_seconds_min_60():
    with pytest.raises(ValidationError):
        _Config(
            connection_id=uuid.uuid4(),
            agent_id="a",
            webhook_ttl_seconds=30,
        )


def test_config_accepts_from_phone():
    cfg = _Config(
        connection_id=uuid.uuid4(),
        agent_id="a",
        from_phone="+919999999999",
    )
    assert cfg.from_phone == "+919999999999"


def test_config_mode_defaults_to_auto():
    cfg = _Config(connection_id=uuid.uuid4(), agent_id="a")
    assert cfg.mode == "auto"


@pytest.mark.parametrize("mode", ["auto", "single", "batch"])
def test_config_mode_accepts_valid_values(mode):
    cfg = _Config(connection_id=uuid.uuid4(), agent_id="a", mode=mode)
    assert cfg.mode == mode


def test_config_mode_rejects_unknown_values():
    with pytest.raises(ValidationError):
        _Config(connection_id=uuid.uuid4(), agent_id="a", mode="parallel")


def test_config_bypass_call_guardrails_defaults_false():
    cfg = _Config(connection_id=uuid.uuid4(), agent_id="a")
    assert cfg.bypass_call_guardrails is False


def test_config_bypass_call_guardrails_accepted():
    cfg = _Config(
        connection_id=uuid.uuid4(), agent_id="a", bypass_call_guardrails=True,
    )
    assert cfg.bypass_call_guardrails is True


def test_config_bypass_field_is_dev_only_in_schema():
    schema = _Config.model_json_schema()
    assert schema["properties"]["bypass_call_guardrails"].get("x-dev-only") is True


# ─── classify_outcome (lifted, pure function) ───────────────────────────────


@pytest.mark.parametrize("status,reason,expected", [
    ("completed", None, "bolna_answered"),
    ("answered", None, "bolna_answered"),
    ("success", None, "bolna_answered"),
    ("completed", "user-hangup", "bolna_answered"),
    # RNR family
    ("completed", "no-answer", "bolna_rnr"),
    ("no-answer", None, "bolna_rnr"),
    ("rnr", None, "bolna_rnr"),
    ("busy", None, "bolna_rnr"),
    ("completed", "rnr", "bolna_rnr"),
    # Failure family
    ("failed", None, "bolna_failed"),
    ("error", None, "bolna_failed"),
    ("balance-low", None, "bolna_failed"),
    ("canceled", None, "bolna_failed"),
    (None, None, "bolna_failed"),
])
def test_classify_outcome(status, reason, expected):
    assert classify_outcome(status, reason) == expected


@pytest.mark.parametrize("status,expected", [
    ("completed", True), ("answered", True), ("failed", True),
    ("no-answer", True), ("rnr", True), ("busy", True),
    ("queued", False), ("in-progress", False), ("ringing", False),
    (None, False), ("", False),
])
def test_is_terminal(status, expected):
    assert is_terminal(status) is expected


# ─── from_phone three-tier fallback ─────────────────────────────────────────


def test_from_phone_per_call_override_wins():
    assert _resolve_from_phone(
        override="+911111111111", connection_default="+922222222222",
    ) == "+911111111111"


def test_from_phone_connection_default_used_when_override_empty():
    assert _resolve_from_phone(
        override="", connection_default="+922222222222",
    ) == "+922222222222"


def test_from_phone_connection_default_used_when_override_whitespace():
    assert _resolve_from_phone(
        override="   ", connection_default="+922222222222",
    ) == "+922222222222"


def test_from_phone_delegates_to_agent_default_when_both_empty():
    assert _resolve_from_phone(override="", connection_default="") is None
    assert _resolve_from_phone(override=None, connection_default=None) is None
    assert _resolve_from_phone(override="  ", connection_default="  ") is None


def test_from_phone_override_none_falls_to_connection():
    assert _resolve_from_phone(
        override=None, connection_default="+922222222222",
    ) == "+922222222222"


# ─── Cost normalization (subunits → major units) ───────────────────────────


def test_normalize_cost_scalar_subunit_conversion():
    # Bolna: 27.04 displayed dashboard value 0.2704
    assert _normalize_cost_scalar(27.04) == 0.2704
    assert _normalize_cost_scalar("27.04") == 0.2704
    assert _normalize_cost_scalar(0) == 0.0
    assert _normalize_cost_scalar(None) is None
    assert _normalize_cost_scalar(True) is True  # bool passthrough


# ─── _extract_capture against verbatim Bolna webhook fixture ───────────────


_BOLNA_COMPLETED_FIXTURE = {
    "execution_id": "exec_abc123",
    "status": "completed",
    "status_reason": "user-hangup",
    "recipient_phone_number": "+919999999999",
    "duration": 42,
    "transcript": "Agent: Hi. User: Hello.",
    "recording_url": "https://bolna.s3/abc.mp3",
    "total_cost": 27.04,
    "cost_breakdown": {"llm": 10.0, "synthesizer": {"tts": 5.0}, "transcriber": 2.0},
    "extracted_data": {"intent": "interested", "callback_at": "evening"},
    "telephony_provider": "twilio",
    "user_data": {"recipient_id": "rid-1", "lead_name": "Aman"},
}

_BOLNA_NOANSWER_FIXTURE = {
    "execution_id": "exec_def456",
    "status": "no-answer",
    "status_reason": "no-answer",
    "recipient_phone_number": "+919999999999",
    "duration": 0,
    "user_data": {"recipient_id": "rid-2"},
}

_BOLNA_FAILED_FIXTURE = {
    "execution_id": "exec_ghi789",
    "status": "failed",
    "status_reason": "balance-low",
    "recipient_phone_number": "+919999999999",
    "user_data": {"recipient_id": "rid-3"},
}


def test_extract_capture_pulls_top_level_fields():
    out = _extract_capture(_BOLNA_COMPLETED_FIXTURE)
    assert out["transcript"] == "Agent: Hi. User: Hello."
    assert out["recording_url"] == "https://bolna.s3/abc.mp3"
    assert out["duration_sec"] == 42
    assert out["total_cost"] == 0.2704
    assert out["hangup_reason"] == "user-hangup"


def test_extract_capture_includes_cost_breakdown_extracted_data_provider():
    out = _extract_capture(_BOLNA_COMPLETED_FIXTURE)
    # cost_breakdown is recursively subunit-normalized (÷100), nesting preserved
    assert out["cost_breakdown"] == {
        "llm": 0.1,
        "synthesizer": {"tts": 0.05},
        "transcriber": 0.02,
    }
    assert out["extracted_data"] == {"intent": "interested", "callback_at": "evening"}
    assert out["telephony_provider"] == "twilio"


def test_extract_capture_handles_telephony_data_nesting():
    raw = {
        "execution_id": "exec_x",
        "status": "completed",
        "telephony_data": {
            "duration_seconds": 17,
            "recording_url": "https://bolna.s3/tele.mp3",
        },
    }
    out = _extract_capture(raw)
    assert out["duration_sec"] == 17
    assert out["recording_url"] == "https://bolna.s3/tele.mp3"


# ─── normalize_webhook ──────────────────────────────────────────────────────


def test_normalize_webhook_completed_event():
    adapter = BolnaAdapter()
    ev = adapter.normalize_webhook(_BOLNA_COMPLETED_FIXTURE)
    assert ev.outcome == "answered"
    assert ev.contact == "+919999999999"
    assert ev.provider_correlation_id == "exec_abc123"
    assert ev.duration_sec == 42
    assert ev.transcript == "Agent: Hi. User: Hello."
    assert ev.recording_url == "https://bolna.s3/abc.mp3"
    assert ev.vendor_raw == _BOLNA_COMPLETED_FIXTURE


def test_normalize_webhook_noanswer_event():
    adapter = BolnaAdapter()
    ev = adapter.normalize_webhook(_BOLNA_NOANSWER_FIXTURE)
    assert ev.outcome == "no_answer"
    assert ev.provider_correlation_id == "exec_def456"
    assert ev.duration_sec == 0


def test_normalize_webhook_failed_event():
    adapter = BolnaAdapter()
    ev = adapter.normalize_webhook(_BOLNA_FAILED_FIXTURE)
    assert ev.outcome == "failed"
    assert ev.provider_correlation_id == "exec_ghi789"


def test_normalize_webhook_falls_to_batch_id_when_no_execution_id():
    raw = {
        "batch_id": "batch_xyz",
        "status": "completed",
        "recipient_phone_number": "+919999999999",
    }
    ev = BolnaAdapter().normalize_webhook(raw)
    assert ev.provider_correlation_id == "batch_xyz"


# ─── place_call via httpx.MockTransport ─────────────────────────────────────


def _client_with_transport(transport: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=transport, timeout=10.0)


@pytest.mark.asyncio
async def test_place_call_single_happy_path(monkeypatch):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["method"] = request.method
        captured["headers"] = dict(request.headers)
        import json as _json
        captured["body"] = _json.loads(request.content.decode())
        return httpx.Response(200, json={
            "message": "queued", "status": "queued",
            "execution_id": "exec_abc123",
        })

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        "app.services.orchestration.adapters.bolna._make_client",
        lambda timeout=30.0: _client_with_transport(transport),
    )

    adapter = BolnaAdapter()
    resp = await adapter.place_call(
        connection={"api_key": "k", "base_url": "https://api.bolna.ai", "from_phone": "+91999"},
        request=CanonicalVoiceRequest(
            contact="+919999999999",
            agent_id="agent_xyz",
            variables={"lead_name": "Aman", "recipient_id": "rid-1"},
            from_phone=None,
        ),
    )
    assert resp.provider_correlation_id == "exec_abc123"
    assert resp.contact == "+919999999999"
    assert resp.mode == "single"
    assert captured["url"] == "https://api.bolna.ai/call"
    assert captured["headers"]["authorization"] == "Bearer k"
    assert captured["body"]["agent_id"] == "agent_xyz"
    assert captured["body"]["recipient_phone_number"] == "+919999999999"
    # Connection from_phone used (override empty)
    assert captured["body"]["from_phone_number"] == "+91999"
    assert captured["body"]["user_data"]["lead_name"] == "Aman"
    assert captured["body"]["user_data"]["recipient_id"] == "rid-1"


@pytest.mark.asyncio
async def test_place_call_per_call_from_phone_overrides_connection(monkeypatch):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json
        captured["body"] = _json.loads(request.content.decode())
        return httpx.Response(200, json={"execution_id": "exec_x"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        "app.services.orchestration.adapters.bolna._make_client",
        lambda timeout=30.0: _client_with_transport(transport),
    )

    adapter = BolnaAdapter()
    await adapter.place_call(
        connection={"api_key": "k", "from_phone": "+91999"},
        request=CanonicalVoiceRequest(
            contact="+91888",
            agent_id="a",
            variables={},
            from_phone="+91777",
        ),
    )
    assert captured["body"]["from_phone_number"] == "+91777"


@pytest.mark.asyncio
async def test_place_call_no_from_phone_anywhere_omits_field(monkeypatch):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json
        captured["body"] = _json.loads(request.content.decode())
        return httpx.Response(200, json={"execution_id": "exec_x"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        "app.services.orchestration.adapters.bolna._make_client",
        lambda timeout=30.0: _client_with_transport(transport),
    )

    adapter = BolnaAdapter()
    await adapter.place_call(
        connection={"api_key": "k"},
        request=CanonicalVoiceRequest(
            contact="+91888", agent_id="a", variables={}, from_phone=None,
        ),
    )
    assert "from_phone_number" not in captured["body"]


@pytest.mark.asyncio
async def test_place_call_bypass_true_emits_top_level_flag(monkeypatch):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json
        captured["body"] = _json.loads(request.content.decode())
        return httpx.Response(200, json={"execution_id": "exec_x"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        "app.services.orchestration.adapters.bolna._make_client",
        lambda timeout=30.0: _client_with_transport(transport),
    )

    adapter = BolnaAdapter()
    await adapter.place_call(
        connection={"api_key": "k"},
        request=CanonicalVoiceRequest(
            contact="+91", agent_id="a", variables={},
            bypass_call_guardrails=True,
        ),
    )
    assert captured["body"]["bypass_call_guardrails"] is True


@pytest.mark.asyncio
async def test_place_call_bypass_false_omits_flag(monkeypatch):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json
        captured["body"] = _json.loads(request.content.decode())
        return httpx.Response(200, json={"execution_id": "exec_x"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        "app.services.orchestration.adapters.bolna._make_client",
        lambda timeout=30.0: _client_with_transport(transport),
    )

    adapter = BolnaAdapter()
    await adapter.place_call(
        connection={"api_key": "k"},
        request=CanonicalVoiceRequest(
            contact="+91", agent_id="a", variables={},
            bypass_call_guardrails=False,
        ),
    )
    assert "bypass_call_guardrails" not in captured["body"]


@pytest.mark.asyncio
async def test_place_call_batch_bypass_true_emits_form_field(monkeypatch):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["content"] = request.content
        return httpx.Response(200, json={"batch_id": "batch_xyz"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        "app.services.orchestration.adapters.bolna._make_client",
        lambda timeout=60.0: _client_with_transport(transport),
    )

    adapter = BolnaAdapter()
    await adapter.place_call_batch(
        connection={"api_key": "k"},
        requests=[CanonicalVoiceRequest(
            contact="+91", agent_id="a", variables={},
            bypass_call_guardrails=True,
        )],
        recipient_ids=["r1"],
    )
    body = captured["content"].decode(errors="ignore")
    assert "bypass_call_guardrails" in body


@pytest.mark.asyncio
async def test_place_call_batch_bypass_false_omits_field(monkeypatch):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["content"] = request.content
        return httpx.Response(200, json={"batch_id": "batch_xyz"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        "app.services.orchestration.adapters.bolna._make_client",
        lambda timeout=60.0: _client_with_transport(transport),
    )

    adapter = BolnaAdapter()
    await adapter.place_call_batch(
        connection={"api_key": "k"},
        requests=[CanonicalVoiceRequest(
            contact="+91", agent_id="a", variables={},
            bypass_call_guardrails=False,
        )],
        recipient_ids=["r1"],
    )
    body = captured["content"].decode(errors="ignore")
    assert "bypass_call_guardrails" not in body


@pytest.mark.asyncio
async def test_place_call_4xx_raises_bolna_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"detail": "bad agent"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        "app.services.orchestration.adapters.bolna._make_client",
        lambda timeout=30.0: _client_with_transport(transport),
    )

    adapter = BolnaAdapter()
    with pytest.raises(BolnaServiceError, match="Bolna 400"):
        await adapter.place_call(
            connection={"api_key": "k"},
            request=CanonicalVoiceRequest(
                contact="+91", agent_id="a", variables={}, from_phone=None,
            ),
        )


@pytest.mark.asyncio
async def test_place_call_missing_execution_id_raises(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": "queued"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        "app.services.orchestration.adapters.bolna._make_client",
        lambda timeout=30.0: _client_with_transport(transport),
    )

    adapter = BolnaAdapter()
    with pytest.raises(BolnaServiceError, match="missing execution_id"):
        await adapter.place_call(
            connection={"api_key": "k"},
            request=CanonicalVoiceRequest(
                contact="+91", agent_id="a", variables={}, from_phone=None,
            ),
        )


# ─── place_call_batch ───────────────────────────────────────────────────────


def test_build_batch_csv_columns_stable():
    reqs = [
        CanonicalVoiceRequest(
            contact="+9111", agent_id="a", variables={"name": "A", "city": "Mumbai"},
        ),
        CanonicalVoiceRequest(
            contact="+9112", agent_id="a", variables={"name": "B", "city": "Pune"},
        ),
    ]
    csv_bytes = _build_batch_csv(requests=reqs, recipient_ids=["r1", "r2"])
    text = csv_bytes.decode()
    lines = text.strip().split("\r\n") if "\r\n" in text else text.strip().split("\n")
    header = lines[0].split(",")
    assert "contact_number" in header
    assert "recipient_id" in header
    assert "city" in header
    assert "name" in header
    # Verify cohort rows
    assert any("+9111" in line and "r1" in line for line in lines[1:])
    assert any("+9112" in line and "r2" in line for line in lines[1:])


@pytest.mark.asyncio
async def test_place_call_batch_happy_path(monkeypatch):
    # Keyed by request URL so the schedule POST doesn't overwrite the create capture.
    captured: dict[str, dict] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        captured[url] = {
            "method": request.method,
            "headers": dict(request.headers),
            "content": request.content,
        }
        return httpx.Response(200, json={"batch_id": "batch_xyz", "message": "queued"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        "app.services.orchestration.adapters.bolna._make_client",
        lambda timeout=60.0: _client_with_transport(transport),
    )

    adapter = BolnaAdapter()
    reqs = [
        CanonicalVoiceRequest(
            contact=f"+9111111111{i}", agent_id="agent_xyz",
            variables={"recipient_id": f"r{i}"},
        )
        for i in range(10)
    ]
    rids = [f"r{i}" for i in range(10)]

    responses = await adapter.place_call_batch(
        connection={"api_key": "k", "base_url": "https://api.bolna.ai", "from_phone": "+91999"},
        requests=reqs,
        recipient_ids=rids,
    )

    assert len(responses) == 10
    assert all(r.provider_correlation_id == "batch_xyz" for r in responses)
    assert all(r.mode == "batch" for r in responses)
    create_url = "https://api.bolna.ai/batches"
    assert create_url in captured, f"create URL not hit; saw: {list(captured)}"
    # Multipart upload — content includes both form fields and CSV
    body = captured[create_url]["content"].decode(errors="ignore")
    assert "agent_id" in body
    assert "agent_xyz" in body
    assert "+91999" in body  # from_phone passed through


@pytest.mark.asyncio
async def test_place_call_batch_empty_returns_empty():
    adapter = BolnaAdapter()
    out = await adapter.place_call_batch(
        connection={"api_key": "k"}, requests=[], recipient_ids=[],
    )
    assert out == []


@pytest.mark.asyncio
async def test_place_call_batch_4xx_raises(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"detail": "bad csv"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        "app.services.orchestration.adapters.bolna._make_client",
        lambda timeout=60.0: _client_with_transport(transport),
    )

    adapter = BolnaAdapter()
    with pytest.raises(BolnaServiceError, match="Bolna 422"):
        await adapter.place_call_batch(
            connection={"api_key": "k"},
            requests=[CanonicalVoiceRequest(contact="+91", agent_id="a", variables={})],
            recipient_ids=["r1"],
        )


@pytest.mark.asyncio
async def test_place_call_batch_mismatched_lengths_raises():
    adapter = BolnaAdapter()
    with pytest.raises(BolnaServiceError, match="length mismatch"):
        await adapter.place_call_batch(
            connection={"api_key": "k"},
            requests=[CanonicalVoiceRequest(contact="+91", agent_id="a", variables={})],
            recipient_ids=["r1", "r2"],
        )


# ─── Handler enforcement: bypass gated on settings.is_dev ───────────────────


class _StubConnections:
    async def get_config(self, _connection_id):
        return {"__provider__": "bolna", "api_key": "k"}


class _StubCtx:
    def __init__(self):
        self.connections = _StubConnections()
        self.run_id = uuid.uuid4()
        self.tenant_id = uuid.uuid4()
        self.app_id = "test-orchestration"
        self.db = object()
        self._action_seq = 0

    def idempotency_key(self, *parts):
        return "|".join(str(p) for p in parts)

    async def set_recipient_state(self, *_a, **_k):
        return None

    async def dispatch_actions(self, dispatches):
        from app.services.orchestration.node_protocol import ActionResult

        out = []
        for d in dispatches:
            self._action_seq += 1
            out.append(ActionResult(
                recipient_id=d.recipient_id,
                action_id=str(uuid.uuid4()),
                status="pending",
            ))
        return out

    async def update_action_result(self, *_a, **_k):
        return None

    async def stamp_webhook_ttl(self, *_a, **_k):
        return None


async def _single_recipient_cohort():
    yield "rid-1", {"contact": "+919999999999"}


async def _run_handler_capture_request(monkeypatch, *, app_env: str, config_flag: bool):
    import app.services.orchestration.nodes.voice_place_call as vpc

    monkeypatch.setattr(vpc.settings, "APP_ENVIRONMENT", app_env)

    async def _ok_manifest(_db, *, run_id, recipient_id):  # noqa: ARG001
        from types import SimpleNamespace

        return SimpleNamespace(recipient_id=recipient_id, phone_e164="+919999999999")

    async def _ok_cap(_db, *, tenant_id, app_id, contact, channel, stage="cap_runtime"):  # noqa: ARG001
        from app.services.orchestration.comm_cap.enforcement import EnforcementResult

        return EnforcementResult(proceed=True)

    monkeypatch.setattr(vpc, "assert_recipient_in_manifest", _ok_manifest)
    monkeypatch.setattr(vpc, "enforce_comm_cap_or_skip", _ok_cap)

    captured: dict = {}

    def http_handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        captured["body"] = _json.loads(request.content.decode())
        return httpx.Response(200, json={"execution_id": "exec_x"})

    transport = httpx.MockTransport(http_handler)
    monkeypatch.setattr(
        "app.services.orchestration.adapters.bolna._make_client",
        lambda timeout=30.0: _client_with_transport(transport),
    )

    handler = vpc._Handler()
    cfg = vpc._Config(
        connection_id=uuid.uuid4(),
        agent_id="agent_xyz",
        phone_field="contact",
        mode="single",
        bypass_call_guardrails=config_flag,
    )
    await handler.execute(_single_recipient_cohort(), cfg, _StubCtx())
    return captured["body"]


@pytest.mark.asyncio
async def test_handler_prod_ignores_stored_bypass_true(monkeypatch):
    body = await _run_handler_capture_request(
        monkeypatch, app_env="production", config_flag=True,
    )
    assert "bypass_call_guardrails" not in body


@pytest.mark.asyncio
async def test_handler_dev_honors_bypass_true(monkeypatch):
    body = await _run_handler_capture_request(
        monkeypatch, app_env="local", config_flag=True,
    )
    assert body["bypass_call_guardrails"] is True


@pytest.mark.asyncio
async def test_handler_dials_operator_picked_field_not_recipient_id(monkeypatch):
    """Regression: the destination is the operator-picked payload field
    (normalized), never the recipient_id (the bug that dialed 'P-pareekshith')."""
    import app.services.orchestration.nodes.voice_place_call as vpc
    from types import SimpleNamespace

    async def _manifest(_db, *, run_id, recipient_id):  # noqa: ARG001
        return SimpleNamespace(recipient_id=recipient_id, phone_e164=None)

    async def _ok_cap(_db, *, tenant_id, app_id, contact, channel, stage="cap_runtime"):  # noqa: ARG001
        from app.services.orchestration.comm_cap.enforcement import EnforcementResult

        return EnforcementResult(proceed=True)

    monkeypatch.setattr(vpc, "assert_recipient_in_manifest", _manifest)
    monkeypatch.setattr(vpc, "enforce_comm_cap_or_skip", _ok_cap)

    captured: dict = {}

    def http_handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        captured["body"] = _json.loads(request.content.decode())
        return httpx.Response(200, json={"execution_id": "exec_x"})

    monkeypatch.setattr(
        "app.services.orchestration.adapters.bolna._make_client",
        lambda timeout=30.0: _client_with_transport(httpx.MockTransport(http_handler)),
    )

    async def _cohort():
        # recipient_id is NOT a phone; phone lives under a dataset-style column.
        yield "P-pareekshith", {"lead_id": "P-pareekshith", "mobile": "+918888888888"}

    cfg = vpc._Config(
        connection_id=uuid.uuid4(), agent_id="agent_xyz",
        phone_field="mobile", mode="single",
    )
    await vpc._Handler().execute(_cohort(), cfg, _StubCtx())
    assert captured["body"]["recipient_phone_number"] == "+918888888888"


@pytest.mark.asyncio
async def test_handler_calls_enforcer_with_resolved_contact_and_voice_channel(monkeypatch):
    """Seam: voice dispatch calls enforce_comm_cap_or_skip with the resolved
    phone (== payload.contact) and channel='voice'."""
    import app.services.orchestration.nodes.voice_place_call as vpc
    from types import SimpleNamespace

    seen: dict = {}

    async def _capture_cap(_db, *, tenant_id, app_id, contact, channel, stage="cap_runtime"):
        from app.services.orchestration.comm_cap.enforcement import EnforcementResult
        seen.update(tenant_id=tenant_id, app_id=app_id, contact=contact, channel=channel)
        return EnforcementResult(proceed=True)

    async def _manifest(_db, *, run_id, recipient_id):  # noqa: ARG001
        return SimpleNamespace(recipient_id=recipient_id, phone_e164=None)

    monkeypatch.setattr(vpc, "assert_recipient_in_manifest", _manifest)
    monkeypatch.setattr(vpc, "enforce_comm_cap_or_skip", _capture_cap)

    def http_handler(request: httpx.Request) -> httpx.Response:
        import json as _json
        seen["body"] = _json.loads(request.content.decode())
        return httpx.Response(200, json={"execution_id": "exec_x"})

    monkeypatch.setattr(
        "app.services.orchestration.adapters.bolna._make_client",
        lambda timeout=30.0: _client_with_transport(httpx.MockTransport(http_handler)),
    )

    async def _cohort():
        yield "rid-1", {"mobile": "0 88888 88888"}

    ctx = _StubCtx()
    cfg = vpc._Config(
        connection_id=uuid.uuid4(), agent_id="agent_xyz",
        phone_field="mobile", mode="single",
    )
    await vpc._Handler().execute(_cohort(), cfg, ctx)
    assert seen["channel"] == "voice"
    assert seen["tenant_id"] == ctx.tenant_id
    assert seen["app_id"] == ctx.app_id
    # Enforcer contact == the normalized phone dialed (== payload.contact).
    assert seen["contact"] == seen["body"]["recipient_phone_number"] == "+918888888888"


@pytest.mark.asyncio
async def test_handler_records_failed_when_place_call_not_accepted(monkeypatch):
    """A voice response with accepted=False is recorded failed with the reason."""
    import app.services.orchestration.nodes.voice_place_call as vpc
    from types import SimpleNamespace

    from app.services.orchestration.adapters.canonical import CanonicalVoiceResponse

    updates: dict = {}

    class _StubAdapter:
        async def place_call(self, *, connection, request):  # noqa: ARG002
            return CanonicalVoiceResponse(
                provider_correlation_id="exec_x", contact=request.contact, mode="single",
                accepted=False, reason="agent unavailable", raw={},
            )

    async def _manifest(_db, *, run_id, recipient_id):  # noqa: ARG001
        return SimpleNamespace(recipient_id=recipient_id, phone_e164=None)

    async def _ok_cap(_db, *, tenant_id, app_id, contact, channel, stage="cap_runtime"):  # noqa: ARG001
        from app.services.orchestration.comm_cap.enforcement import EnforcementResult
        return EnforcementResult(proceed=True)

    monkeypatch.setattr(vpc, "assert_recipient_in_manifest", _manifest)
    monkeypatch.setattr(vpc, "enforce_comm_cap_or_skip", _ok_cap)
    monkeypatch.setattr(vpc, "resolve_adapter", lambda **_k: _StubAdapter())

    ctx = _StubCtx()

    async def _capture_update(action_id, **kwargs):
        updates[action_id] = kwargs

    ctx.update_action_result = _capture_update  # type: ignore[assignment]

    async def _cohort():
        yield "rid-1", {"mobile": "+918888888888"}

    cfg = vpc._Config(
        connection_id=uuid.uuid4(), agent_id="agent_xyz",
        phone_field="mobile", mode="single",
    )
    result = await vpc._Handler().execute(_cohort(), cfg, ctx)
    assert result.by_output_id["failed"] and not result.by_output_id["success"]
    settled = next(iter(updates.values()))
    assert settled["status"] == "failed"
    assert settled["error"] == "agent unavailable"
    assert settled["provider_correlation_id"] == "exec_x"


# ─── Registry integration ──────────────────────────────────────────────────


def test_bolna_adapter_registered():
    # Importing the module above triggers register_adapter().
    assert ("voice", "bolna") in registered_adapters()
    adapter = resolve_adapter(capability="voice", vendor="bolna")
    assert adapter.capability == "voice"
    assert adapter.vendor == "bolna"
    assert adapter.batch_threshold == 10


# ─── fetch_batch_executions — bare-array response (Change A) ────────────────


@pytest.mark.asyncio
async def test_fetch_batch_executions_bare_array_partial_page(monkeypatch):
    """Live Bolna GET /batches/{id}/executions returns a bare JSON array, not a
    dict with a 'data' key.  Two rows < page_size=50 → has_more False."""
    fixture = [
        {"id": "exec1", "status": "completed",
         "context_details": {"recipient_data": {"recipient_id": "r1"}}},
        {"id": "exec2", "status": "no-answer",
         "context_details": {"recipient_data": {"recipient_id": "r2"}}},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=fixture)

    monkeypatch.setattr(
        "app.services.orchestration.adapters.bolna._make_client",
        lambda timeout=30.0: _client_with_transport(httpx.MockTransport(handler)),
    )

    adapter = BolnaAdapter()
    result = await adapter.fetch_batch_executions(
        connection={"api_key": "k"}, batch_id="batch_abc",
    )
    assert result["data"] == fixture
    assert result["has_more"] is False


@pytest.mark.asyncio
async def test_fetch_batch_executions_bare_array_full_page(monkeypatch):
    """A full page (len == page_size) → has_more True (inferred, not from body)."""
    fixture = [
        {"id": f"exec{i}", "status": "completed",
         "context_details": {"recipient_data": {"recipient_id": f"r{i}"}}}
        for i in range(2)
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=fixture)

    monkeypatch.setattr(
        "app.services.orchestration.adapters.bolna._make_client",
        lambda timeout=30.0: _client_with_transport(httpx.MockTransport(handler)),
    )

    adapter = BolnaAdapter()
    result = await adapter.fetch_batch_executions(
        connection={"api_key": "k"}, batch_id="batch_abc",
        page_number=1, page_size=2,
    )
    assert len(result["data"]) == 2
    assert result["has_more"] is True


@pytest.mark.asyncio
async def test_fetch_batch_executions_404_returns_empty(monkeypatch):
    """404 → empty result with has_more False."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "not found"})

    monkeypatch.setattr(
        "app.services.orchestration.adapters.bolna._make_client",
        lambda timeout=30.0: _client_with_transport(httpx.MockTransport(handler)),
    )

    adapter = BolnaAdapter()
    result = await adapter.fetch_batch_executions(
        connection={"api_key": "k"}, batch_id="batch_missing",
    )
    assert result == {"data": [], "has_more": False}


# ─── place_call_batch schedule step (Change B) ──────────────────────────────


@pytest.mark.asyncio
async def test_place_call_batch_schedules_after_create(monkeypatch):
    """After creating the batch, place_call_batch must POST to /batches/{id}/schedule."""
    from datetime import datetime, timezone

    urls_seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls_seen.append(str(request.url))
        if "/schedule" in str(request.url):
            return httpx.Response(200, json={"state": "scheduled at 2026-05-28T10:30:00+00:00"})
        return httpx.Response(200, json={"batch_id": "batch_xyz"})

    monkeypatch.setattr(
        "app.services.orchestration.adapters.bolna._make_client",
        lambda timeout=60.0: _client_with_transport(httpx.MockTransport(handler)),
    )

    adapter = BolnaAdapter()
    responses = await adapter.place_call_batch(
        connection={"api_key": "k"},
        requests=[CanonicalVoiceRequest(contact="+91", agent_id="a", variables={})],
        recipient_ids=["r1"],
    )

    assert any("/schedule" in u for u in urls_seen), f"schedule URL not hit; saw: {urls_seen}"
    assert all(r.provider_correlation_id == "batch_xyz" for r in responses)


@pytest.mark.asyncio
async def test_place_call_batch_schedule_at_format(monkeypatch):
    """scheduled_at must end with +00:00, never Z, and be ≥ ~2 min in the future."""
    import re as _re
    import urllib.parse as _up
    from datetime import datetime, timezone, timedelta

    schedule_raw: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if "/schedule" in str(request.url):
            schedule_raw["body"] = request.content.decode(errors="ignore")
            return httpx.Response(200, json={"state": "scheduled"})
        return httpx.Response(200, json={"batch_id": "batch_format_test"})

    monkeypatch.setattr(
        "app.services.orchestration.adapters.bolna._make_client",
        lambda timeout=60.0: _client_with_transport(httpx.MockTransport(handler)),
    )

    before = datetime.now(timezone.utc)
    adapter = BolnaAdapter()
    await adapter.place_call_batch(
        connection={"api_key": "k"},
        requests=[CanonicalVoiceRequest(contact="+91", agent_id="a", variables={})],
        recipient_ids=["r1"],
    )

    raw_body = schedule_raw.get("body", "")
    # URL-decode so %2B→+ and %3A→: are visible for assertion.
    decoded = _up.unquote(raw_body)
    assert "+00:00" in decoded, f"scheduled_at must end with +00:00; decoded={decoded!r}"
    # No bare Z after the time portion.
    assert not _re.search(r"\d{2}:\d{2}Z", decoded), \
        f"scheduled_at must not use Z suffix; decoded={decoded!r}"
    # Extract timestamp and verify it is ≥ 2 min in the future.
    m = _re.search(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00)", decoded)
    assert m, f"Could not find ISO timestamp in schedule body: {decoded!r}"
    scheduled_dt = datetime.fromisoformat(m.group(1))
    assert scheduled_dt >= before + timedelta(minutes=2) - timedelta(seconds=1), \
        f"scheduled_at {scheduled_dt} is not ≥ 2 min after {before}"


@pytest.mark.asyncio
async def test_place_call_batch_schedule_bypass_true(monkeypatch):
    """bypass_call_guardrails=True → schedule multipart includes bypass_call_guardrails field."""
    schedule_body: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if "/schedule" in str(request.url):
            schedule_body["content"] = request.content.decode(errors="ignore")
            return httpx.Response(200, json={"state": "scheduled"})
        return httpx.Response(200, json={"batch_id": "batch_bypass"})

    monkeypatch.setattr(
        "app.services.orchestration.adapters.bolna._make_client",
        lambda timeout=60.0: _client_with_transport(httpx.MockTransport(handler)),
    )

    adapter = BolnaAdapter()
    await adapter.place_call_batch(
        connection={"api_key": "k"},
        requests=[CanonicalVoiceRequest(
            contact="+91", agent_id="a", variables={},
            bypass_call_guardrails=True,
        )],
        recipient_ids=["r1"],
    )
    assert "bypass_call_guardrails" in schedule_body.get("content", "")


@pytest.mark.asyncio
async def test_place_call_batch_schedule_bypass_false(monkeypatch):
    """bypass_call_guardrails=False → schedule multipart does NOT include bypass field."""
    schedule_body: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if "/schedule" in str(request.url):
            schedule_body["content"] = request.content.decode(errors="ignore")
            return httpx.Response(200, json={"state": "scheduled"})
        return httpx.Response(200, json={"batch_id": "batch_no_bypass"})

    monkeypatch.setattr(
        "app.services.orchestration.adapters.bolna._make_client",
        lambda timeout=60.0: _client_with_transport(httpx.MockTransport(handler)),
    )

    adapter = BolnaAdapter()
    await adapter.place_call_batch(
        connection={"api_key": "k"},
        requests=[CanonicalVoiceRequest(
            contact="+91", agent_id="a", variables={},
            bypass_call_guardrails=False,
        )],
        recipient_ids=["r1"],
    )
    assert "bypass_call_guardrails" not in schedule_body.get("content", "")


@pytest.mark.asyncio
async def test_place_call_batch_schedule_4xx_raises(monkeypatch):
    """schedule returning 400 (e.g. Z-suffix reject) → BolnaServiceError raised."""
    def handler(request: httpx.Request) -> httpx.Response:
        if "/schedule" in str(request.url):
            return httpx.Response(400, json={"detail": "invalid scheduled_at format"})
        return httpx.Response(200, json={"batch_id": "batch_err"})

    monkeypatch.setattr(
        "app.services.orchestration.adapters.bolna._make_client",
        lambda timeout=60.0: _client_with_transport(httpx.MockTransport(handler)),
    )

    adapter = BolnaAdapter()
    with pytest.raises(BolnaServiceError, match="Bolna 400"):
        await adapter.place_call_batch(
            connection={"api_key": "k"},
            requests=[CanonicalVoiceRequest(contact="+91", agent_id="a", variables={})],
            recipient_ids=["r1"],
        )

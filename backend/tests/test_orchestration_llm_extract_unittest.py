"""Pure unit/contract tests for llm.extract.

No live LLM. The provider is a fake injected by monkeypatching the node's
``_build_llm`` seam; ``generate_json`` returns verbatim fixture dicts. Tests
assert call counts (1 recipient → 1 call, N → N bounded by the semaphore),
template rendering from payload, output namespacing, per-recipient error
routing to the ``error`` edge, resume idempotency, and that a usage row is
recorded through the wrapper's usage callback.
"""
from __future__ import annotations

import asyncio
import uuid

import pytest
from pydantic import ValidationError

import app.services.orchestration.nodes.llm_extract as node_mod
from app.services.orchestration.cohort_stream import CohortStream
from app.services.orchestration.nodes.llm_extract import _Config, _Handler


# ─── _Config strictness ─────────────────────────────────────────────────────


def _schema_field(key="sentiment"):
    return {"key": key, "type": "text", "description": "Overall sentiment"}


def test_config_minimum_required_fields():
    cfg = _Config(prompt="Classify: {{message}}", output_schema=[_schema_field()])
    assert cfg.prompt == "Classify: {{message}}"
    assert cfg.output_namespace == ""
    assert cfg.input_template is None
    assert cfg.provider_override is None
    assert cfg.model_override is None


def test_config_rejects_unknown_keys():
    with pytest.raises(ValidationError) as exc_info:
        _Config(
            prompt="x",
            output_schema=[_schema_field()],
            bogus_field="nope",
        )
    assert any(e.get("type") == "extra_forbidden" for e in exc_info.value.errors())


def test_config_draft_safe_empty_prompt():
    cfg = _Config()
    assert cfg.prompt == ""
    assert cfg.output_schema == []


# ─── Fake provider + ctx harness ────────────────────────────────────────────


class _FakeProvider:
    """Records every generate_json call; returns a per-call canned dict."""

    def __init__(self, responses):
        self._responses = responses
        self.calls: list[dict] = []
        self.usage_events: list[dict] = []

    async def generate_json(self, prompt, system_prompt=None, json_schema=None, **kwargs):
        self.calls.append(
            {"prompt": prompt, "system_prompt": system_prompt, "json_schema": json_schema}
        )
        idx = len(self.calls) - 1
        resp = self._responses[idx % len(self._responses)]
        if isinstance(resp, Exception):
            raise resp
        return resp


class _Ctx:
    def __init__(self, *, job_id=None):
        self.db = object()
        self.tenant_id = uuid.uuid4()
        self.user_id = uuid.uuid4()
        self.app_id = "test-orchestration"
        self.run_id = uuid.uuid4()
        self.job_id = job_id
        self.current_node_id = "node-llm-1"
        self.states: dict[str, dict] = {}

    async def set_recipient_state(self, recipient_id, **kwargs):
        self.states.setdefault(recipient_id, {}).update(kwargs)


def _patch_llm(monkeypatch, provider):
    async def _fake_build(ctx, config):  # noqa: ARG001
        return provider

    monkeypatch.setattr(node_mod, "_build_llm", _fake_build)


# ─── Red→green behavior ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_one_recipient_one_call_namespaced_output(monkeypatch):
    provider = _FakeProvider([{"sentiment": "positive"}])
    _patch_llm(monkeypatch, provider)

    cfg = _Config(
        prompt="Classify: {{message}}",
        output_schema=[_schema_field()],
        input_template="{{message}}",
        output_namespace="extracted",
    )
    cohort = CohortStream([("r1", {"message": "I love it"})])

    result = await _Handler().execute(cohort, cfg, _Ctx())

    assert len(provider.calls) == 1
    # Template renders {{field}} from the payload.
    assert provider.calls[0]["prompt"] == "Classify: I love it" or \
        "I love it" in provider.calls[0]["prompt"]
    succ = result.by_output_id["success"]
    assert len(succ) == 1
    assert succ[0].recipient_id == "r1"
    # Output is written as flat dotted keys so the existing flat readers resolve it.
    assert succ[0].payload_delta == {"extracted.sentiment": "positive"}
    assert not result.by_output_id["error"]


@pytest.mark.asyncio
async def test_namespace_defaults_to_node_id(monkeypatch):
    provider = _FakeProvider([{"sentiment": "neutral"}])
    _patch_llm(monkeypatch, provider)

    cfg = _Config(prompt="{{message}}", output_schema=[_schema_field()])
    cohort = CohortStream([("r1", {"message": "meh"})])
    ctx = _Ctx()

    result = await _Handler().execute(cohort, cfg, ctx)
    succ = result.by_output_id["success"]
    assert succ[0].payload_delta == {f"{ctx.current_node_id}.sentiment": "neutral"}


@pytest.mark.asyncio
async def test_n_output_fields_become_n_flat_keys(monkeypatch):
    provider = _FakeProvider([{"intent": "refill", "sentiment": "positive"}])
    _patch_llm(monkeypatch, provider)

    cfg = _Config(
        prompt="{{message}}",
        output_schema=[_schema_field("intent"), _schema_field("sentiment")],
        input_template="{{message}}",
        output_namespace="enrich",
    )
    cohort = CohortStream([("r1", {"message": "need a refill"})])
    result = await _Handler().execute(cohort, cfg, _Ctx())

    delta = result.by_output_id["success"][0].payload_delta
    assert delta == {"enrich.intent": "refill", "enrich.sentiment": "positive"}


@pytest.mark.asyncio
async def test_array_value_stored_whole_under_flat_key(monkeypatch):
    # An array output field's list value is stored whole under the flat key;
    # deeper item access is out of scope.
    provider = _FakeProvider([{"tags": ["a", "b"]}])
    _patch_llm(monkeypatch, provider)

    cfg = _Config(
        prompt="{{message}}",
        output_schema=[{"key": "tags", "type": "array", "description": "labels"}],
        input_template="{{message}}",
        output_namespace="enrich",
    )
    cohort = CohortStream([("r1", {"message": "x"})])
    result = await _Handler().execute(cohort, cfg, _Ctx())

    delta = result.by_output_id["success"][0].payload_delta
    assert delta == {"enrich.tags": ["a", "b"]}


def test_flat_key_resolves_through_all_three_readers():
    # Regression: the flat write makes {{enrich.intent}} resolve with ZERO reader
    # changes — template render, predicate leaf, and request-body $payload ref.
    from app.services.orchestration.nodes import _template
    from app.services.orchestration import predicate_contract, request_body_contract

    payload = {"enrich.intent": "refill"}

    assert _template.render("{{enrich.intent}}", payload) == "refill"
    assert predicate_contract.evaluate(
        {"field": "enrich.intent", "op": "eq", "value": "refill"}, payload
    ) is True
    assert request_body_contract.resolve({"$payload": "enrich.intent"}, payload) == "refill"


@pytest.mark.asyncio
async def test_whole_payload_json_fallback_when_no_template(monkeypatch):
    provider = _FakeProvider([{"sentiment": "positive"}])
    _patch_llm(monkeypatch, provider)

    cfg = _Config(prompt="Read the record.", output_schema=[_schema_field()])
    cohort = CohortStream([("r1", {"message": "hi", "lead_id": "L-1"})])
    await _Handler().execute(cohort, cfg, _Ctx())

    # No input_template → whole payload serialized as JSON appended to the prompt.
    prompt = provider.calls[0]["prompt"]
    assert "lead_id" in prompt and "L-1" in prompt
    assert "Read the record." in prompt


@pytest.mark.asyncio
async def test_n_recipients_n_calls_bounded_by_semaphore(monkeypatch):
    n = 5
    provider = _FakeProvider([{"sentiment": "positive"}])

    in_flight = 0
    peak = 0

    async def _fake_build(ctx, config):  # noqa: ARG001
        return provider

    orig = provider.generate_json

    async def _tracked(prompt, system_prompt=None, json_schema=None, **kwargs):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.01)
        try:
            return await orig(prompt, system_prompt, json_schema, **kwargs)
        finally:
            in_flight -= 1

    provider.generate_json = _tracked  # type: ignore[method-assign]
    monkeypatch.setattr(node_mod, "_build_llm", _fake_build)

    cfg = _Config(
        prompt="{{message}}",
        output_schema=[_schema_field()],
        input_template="{{message}}",
        output_namespace="x",
        concurrency=2,
    )
    cohort = CohortStream([(f"r{i}", {"message": f"m{i}"}) for i in range(n)])

    result = await _Handler().execute(cohort, cfg, _Ctx())

    assert len(provider.calls) == n
    assert len(result.by_output_id["success"]) == n
    assert peak <= 2, f"semaphore breached: peak in-flight={peak}"


@pytest.mark.asyncio
async def test_invalid_output_routes_to_error(monkeypatch):
    # Missing the required 'sentiment' key → schema validation fails → error edge.
    provider = _FakeProvider([{"wrong_key": "oops"}])
    _patch_llm(monkeypatch, provider)

    cfg = _Config(
        prompt="{{message}}",
        output_schema=[_schema_field()],
        input_template="{{message}}",
        output_namespace="x",
    )
    cohort = CohortStream([("r1", {"message": "hi"})])
    result = await _Handler().execute(cohort, cfg, _Ctx())

    assert not result.by_output_id["success"]
    err = result.by_output_id["error"]
    assert len(err) == 1 and err[0].recipient_id == "r1"


@pytest.mark.asyncio
async def test_per_recipient_error_isolated(monkeypatch):
    # r1 raises; r2 succeeds. r1 → error, r2 → success.
    provider = _FakeProvider([RuntimeError("boom"), {"sentiment": "positive"}])
    _patch_llm(monkeypatch, provider)

    cfg = _Config(
        prompt="{{message}}",
        output_schema=[_schema_field()],
        input_template="{{message}}",
        output_namespace="x",
    )
    cohort = CohortStream([("r1", {"message": "a"}), ("r2", {"message": "b"})])
    result = await _Handler().execute(cohort, cfg, _Ctx())

    assert [o.recipient_id for o in result.by_output_id["error"]] == ["r1"]
    assert [o.recipient_id for o in result.by_output_id["success"]] == ["r2"]


@pytest.mark.asyncio
async def test_skips_recipient_already_carrying_namespace(monkeypatch):
    provider = _FakeProvider([{"sentiment": "positive"}])
    _patch_llm(monkeypatch, provider)

    cfg = _Config(
        prompt="{{message}}",
        output_schema=[_schema_field()],
        input_template="{{message}}",
        output_namespace="extracted",
    )
    # r1 already carries a flat namespace-prefixed key (a prior partial run) → skip, no call.
    cohort = CohortStream([
        ("r1", {"message": "a", "extracted.sentiment": "old"}),
        ("r2", {"message": "b"}),
    ])
    result = await _Handler().execute(cohort, cfg, _Ctx())

    assert len(provider.calls) == 1
    assert [o.recipient_id for o in result.by_output_id["success"]] == ["r2"]


@pytest.mark.asyncio
async def test_job_id_none_does_not_crash(monkeypatch):
    # Test/None mode: run_parallel cancellation checks must tolerate job_id=None.
    provider = _FakeProvider([{"sentiment": "positive"}])
    _patch_llm(monkeypatch, provider)

    cfg = _Config(
        prompt="{{message}}",
        output_schema=[_schema_field()],
        input_template="{{message}}",
        output_namespace="x",
    )
    cohort = CohortStream([("r1", {"message": "hi"})])
    result = await _Handler().execute(cohort, cfg, _Ctx(job_id=None))
    assert len(result.by_output_id["success"]) == 1


@pytest.mark.asyncio
async def test_usage_callback_wired_owner_job(monkeypatch):
    # The real builder must construct a LoggingLLMWrapper with a usage callback
    # bound to owner_type="job". We assert the wiring by capturing make_usage_callback.
    captured: dict = {}

    import app.services.evaluators.runner_utils as ru

    real_make = ru.make_usage_callback

    def _spy(**kwargs):
        captured.update(kwargs)
        return real_make(**kwargs)

    monkeypatch.setattr(ru, "make_usage_callback", _spy)

    # Stub resolve_llm_call + create_llm_provider so no live provider is built.
    import app.services.llm_credentials as creds
    import app.services.evaluators.llm_base as llm_base

    class _Resolved:
        provider = "openai"
        model = "gpt-4o-mini"
        api_version = None

        class credentials:
            secret = {"api_key": "k"}
            service_account_path = None
            extra_config = {}

    async def _fake_resolve(db, tenant_id, call_site, **kw):  # noqa: ARG001
        assert call_site == "workflow_llm_extract"
        return _Resolved()

    monkeypatch.setattr(creds, "resolve_llm_call", _fake_resolve)
    monkeypatch.setattr(
        llm_base, "create_llm_provider",
        lambda **kw: _FakeProvider([{"sentiment": "positive"}]),
    )

    # Real job_id exercises run_parallel; stub the cancellation poller so the
    # unit test never touches a live DB session.
    import app.services.evaluators.parallel_engine as pe

    async def _never_cancelled(job_id, tenant_id=None):  # noqa: ARG001
        return False

    monkeypatch.setattr(pe, "is_job_cancelled", _never_cancelled)

    cfg = _Config(
        prompt="{{message}}",
        output_schema=[_schema_field()],
        input_template="{{message}}",
        output_namespace="x",
    )
    ctx = _Ctx(job_id=uuid.uuid4())
    cohort = CohortStream([("r1", {"message": "hi"})])
    result = await _Handler().execute(cohort, cfg, ctx)

    assert len(result.by_output_id["success"]) == 1
    assert captured.get("owner_type") == "job"
    assert captured.get("owner_id") == ctx.job_id
    assert captured.get("tenant_id") == ctx.tenant_id


# ─── Registration + edges ───────────────────────────────────────────────────


def test_handler_output_edges_and_category():
    h = _Handler()
    assert h.node_type == "llm.extract"
    assert h.output_edges == ["success", "error"]
    assert h.category == "mutation"

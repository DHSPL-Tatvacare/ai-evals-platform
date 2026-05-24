"""llm.extract dry-run endpoint — render parity, structured output, cost tag.

The dry-run reuses the node's own ``_build_prompt`` / ``_build_llm`` seams on one
sample payload (parity with the runtime) and resolves the same
``workflow_llm_extract`` call site. Cost rows are tagged
``call_purpose='workflow_llm_extract:builder_test'`` via the existing
set_call_purpose path — no migration, no new column.

No live external LLM: the render/schema tests patch ``_build_llm`` with a
recorder fake; the cost-tag test patches only the provider factory + call-site
resolver so the real LoggingLLMWrapper + cost recorder run against a fake inner.
"""
from __future__ import annotations

import uuid

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.auth import AuthContext, get_auth_context
from app.constants import SYSTEM_USER_ID
from app.database import get_db
from app.main import app as fastapi_app
from app.models.tenant import Tenant
from app.services.evaluators.schema_generator import generate_json_schema
from app.services.orchestration.nodes import llm_extract as node_mod

APP_ID = "inside-sales"
BUILDER_TEST_PURPOSE = "workflow_llm_extract:builder_test"

_CONFIG_DICT = {
    "prompt": "Classify {{last_message}} from {{first_name}}.",
    "output_schema": [
        {"key": "sentiment", "type": "enum", "enumValues": ["pos", "neg"]},
        {"key": "confidence", "type": "number"},
    ],
    "output_namespace": "analysis",
}
_SAMPLE = {"first_name": "Asha", "last_message": "I want to cancel"}


# ─── recorder fake (no network) ──────────────────────────────────────────────


class _RecorderLLM:
    """Captures the prompt + json_schema generate_json is called with."""

    def __init__(self):
        self.prompt = None
        self.json_schema = None
        self.call_purpose = None

    def set_call_purpose(self, purpose, stage_index=None):
        self.call_purpose = purpose

    async def generate_json(self, prompt, system_prompt=None, json_schema=None, **kwargs):
        self.prompt = prompt
        self.json_schema = json_schema
        return {"sentiment": "neg", "confidence": 0.9}


def _make_config():
    return node_mod._Config.model_validate(_CONFIG_DICT)


# ─── service: render parity + structured output ──────────────────────────────


@pytest.mark.asyncio
async def test_dry_run_render_matches_runtime_build_prompt(monkeypatch):
    from app.services.orchestration.llm_extract_dry_run import run_llm_extract_dry_run

    recorder = _RecorderLLM()

    async def _fake_build(ctx, config):
        return recorder

    monkeypatch.setattr(node_mod, "_build_llm", _fake_build)
    config = _make_config()

    out = await run_llm_extract_dry_run(
        db=object(), tenant_id=uuid.uuid4(), user_id=uuid.uuid4(),
        app_id=APP_ID, config=config, sample=_SAMPLE,
    )

    expected = node_mod._build_prompt(config, _SAMPLE)
    assert out["prompt"] == expected
    assert recorder.prompt == expected
    # parity with _render_template: tokens are substituted from the sample.
    assert "Asha" in out["prompt"] and "I want to cancel" in out["prompt"]


@pytest.mark.asyncio
async def test_dry_run_uses_output_schema_json_schema(monkeypatch):
    from app.services.orchestration.llm_extract_dry_run import run_llm_extract_dry_run

    recorder = _RecorderLLM()

    async def _fake_build(ctx, config):
        return recorder

    monkeypatch.setattr(node_mod, "_build_llm", _fake_build)
    config = _make_config()

    await run_llm_extract_dry_run(
        db=object(), tenant_id=uuid.uuid4(), user_id=uuid.uuid4(),
        app_id=APP_ID, config=config, sample=_SAMPLE,
    )

    expected_schema = generate_json_schema([f.model_dump() for f in config.output_schema])
    assert recorder.json_schema == expected_schema
    assert recorder.call_purpose == BUILDER_TEST_PURPOSE


# ─── service: cost row tagged builder_test (real recorder, fake inner) ────────


class _FakeInner:
    """Inner provider stand-in: no network; exposes the usage envelope the
    LoggingLLMWrapper forwards to the cost recorder."""

    model_name = "gpt-4o-dry-run-test"

    def __init__(self, response):
        self._response = response
        self._last_metadata = {
            "input_tokens": 12, "output_tokens": 4, "api_surface": "responses",
        }

    def set_timeouts(self, timeouts):
        pass

    async def generate_json(self, prompt, system_prompt=None, json_schema=None, **kwargs):
        return self._response


class _FakeCred:
    secret = {"api_key": ""}
    service_account_path = ""
    extra_config: dict = {}


class _FakeResolved:
    call_site = "workflow_llm_extract"
    provider = "openai"
    model = "gpt-4o-dry-run-test"
    credentials = _FakeCred()
    api_version = None
    capabilities = frozenset()


@pytest.mark.asyncio
async def test_dry_run_writes_cost_row_with_builder_test_purpose(monkeypatch):
    from app.services.orchestration.llm_extract_dry_run import run_llm_extract_dry_run

    tenant_id = uuid.uuid4()

    async def _fake_resolve(db, tid, call_site, **kwargs):
        return _FakeResolved()

    def _fake_factory(**kwargs):
        return _FakeInner({"sentiment": "neg", "confidence": 0.9})

    # Patch only the provider factory + call-site resolver — the real
    # LoggingLLMWrapper + make_usage_callback + record_llm_usage still run.
    monkeypatch.setattr(
        "app.services.llm_credentials.resolve_llm_call", _fake_resolve, raising=False,
    )
    monkeypatch.setattr(
        "app.services.evaluators.llm_base.create_llm_provider", _fake_factory, raising=False,
    )

    # record_llm_usage commits on its OWN session and tenant_id has an FK to
    # platform.tenants — seed a committed tenant, then clean up everything.
    engine = create_async_engine(
        "postgresql+asyncpg://evals_user:evals_pass@localhost:5432/ai_evals_platform"
    )
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO platform.tenants (id, name, slug, is_active) "
                    "VALUES (:id, :n, :s, true)"
                ),
                {"id": str(tenant_id), "n": f"dr-cost-{tenant_id.hex[:8]}",
                 "s": f"dr-cost-{tenant_id.hex[:8]}"},
            )

        await run_llm_extract_dry_run(
            db=object(), tenant_id=tenant_id, user_id=None,
            app_id=APP_ID, config=_make_config(), sample=_SAMPLE,
        )

        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text(
                        "SELECT call_purpose FROM analytics.fact_llm_generation "
                        "WHERE tenant_id = :t AND call_purpose = :p"
                    ),
                    {"t": str(tenant_id), "p": BUILDER_TEST_PURPOSE},
                )
            ).first()
            assert row is not None, "dry-run must write a fact_llm_generation row"
            assert row[0] == BUILDER_TEST_PURPOSE
    finally:
        async with engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM analytics.fact_llm_generation WHERE tenant_id = :t"),
                {"t": str(tenant_id)},
            )
            await conn.execute(
                text("DELETE FROM analytics.agg_llm_usage_daily WHERE tenant_id = :t"),
                {"t": str(tenant_id)},
            )
            await conn.execute(
                text("DELETE FROM platform.tenants WHERE id = :t"),
                {"t": str(tenant_id)},
            )
        await engine.dispose()


# ─── route ───────────────────────────────────────────────────────────────────


def _override_db(db_session):
    async def _g():
        yield db_session
    fastapi_app.dependency_overrides[get_db] = _g
    db_session.commit = db_session.flush  # type: ignore[assignment]


def _make_auth(tenant_id: uuid.UUID) -> AuthContext:
    return AuthContext(
        user_id=SYSTEM_USER_ID, tenant_id=tenant_id,
        email="dry-run@orchestration.local", role_id=uuid.uuid4(),
        is_owner=True, permissions=frozenset(),
        app_access=frozenset({"voice-rx", "kaira-bot", "inside-sales"}),
    )


@pytest_asyncio.fixture
async def route_tenant_id(db_session) -> uuid.UUID:
    tenant_id = uuid.uuid4()
    db_session.add(Tenant(
        id=tenant_id, name=f"dr-{tenant_id.hex[:8]}",
        slug=f"dr-{tenant_id.hex[:8]}", is_active=True,
    ))
    await db_session.flush()
    return tenant_id


@pytest_asyncio.fixture
async def client(db_session, route_tenant_id):
    _override_db(db_session)
    fastapi_app.dependency_overrides[get_auth_context] = lambda: _make_auth(route_tenant_id)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=fastapi_app), base_url="http://test",
        ) as c:
            yield c
    finally:
        fastapi_app.dependency_overrides.pop(get_db, None)
        fastapi_app.dependency_overrides.pop(get_auth_context, None)


@pytest_asyncio.fixture
async def unauth_client(db_session):
    _override_db(db_session)
    fastapi_app.dependency_overrides.pop(get_auth_context, None)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=fastapi_app), base_url="http://test",
        ) as c:
            yield c
    finally:
        fastapi_app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_route_requires_auth(unauth_client):
    r = await unauth_client.post(
        "/api/orchestration/nodes/llm-extract/test",
        json={"appId": APP_ID, "config": _CONFIG_DICT, "sample": _SAMPLE},
    )
    assert r.status_code in (401, 403), r.text


@pytest.mark.asyncio
async def test_route_returns_prompt_and_result(client, monkeypatch):
    recorder = _RecorderLLM()

    async def _fake_build(ctx, config):
        return recorder

    monkeypatch.setattr(node_mod, "_build_llm", _fake_build)

    r = await client.post(
        "/api/orchestration/nodes/llm-extract/test",
        json={"appId": APP_ID, "config": _CONFIG_DICT, "sample": _SAMPLE},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "Asha" in body["prompt"]
    assert body["result"] == {"sentiment": "neg", "confidence": 0.9}

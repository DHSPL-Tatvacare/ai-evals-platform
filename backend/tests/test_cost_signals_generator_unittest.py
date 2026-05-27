"""Cost-signal generator: aggregate input shape, defensive parse, registration.

``build_signal_input`` runs against the live local docker Postgres (FactLlmGeneration
has an FK to platform.tenants), mirroring the cost-signals route test harness.
``parse_signals`` and the registry assertion are pure — no DB, no LLM.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from app.models.cost import FactLlmGeneration
from app.models.tenant import Tenant
from app.services.cost_tracking.signals_service import build_signal_input, parse_signals


@pytest_asyncio.fixture
async def gen_tenant_id(db_session) -> uuid.UUID:
    tenant_id = uuid.uuid4()
    db_session.add(Tenant(
        id=tenant_id,
        name=f'cost-gen-{tenant_id.hex[:8]}',
        slug=f'cost-gen-{tenant_id.hex[:8]}',
        is_active=True,
    ))
    await db_session.flush()
    return tenant_id


def _fact(tenant_id, *, created_at, cost, in_tok, out_tok, status='ok',
          pricing_fallback=False, app_id='voice-rx', model='gpt-5.4', purpose='critique'):
    return FactLlmGeneration(
        id=uuid.uuid4(),
        created_at=created_at,
        tenant_id=tenant_id,
        user_id=None,
        app_id=app_id,
        subsystem='cost_signals',
        owner_type='job',
        owner_id=None,
        provider='azure_openai',
        model=model,
        call_purpose=purpose,
        input_tokens=in_tok,
        output_tokens=out_tok,
        cost_usd=cost,
        status=status,
        pricing_fallback=pricing_fallback,
    )


@pytest.mark.asyncio
async def test_build_signal_input_kpis_deltas_top_groups(db_session, gen_tenant_id):
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=7)
    end = now
    prior_start = start - (end - start)

    # Current window: 3 requests, one error, one unpriced.
    db_session.add(_fact(gen_tenant_id, created_at=start + timedelta(hours=1),
                         cost='1.0', in_tok=100, out_tok=50, app_id='voice-rx', model='gpt-5.4'))
    db_session.add(_fact(gen_tenant_id, created_at=start + timedelta(hours=2),
                         cost='2.0', in_tok=200, out_tok=100, status='error',
                         app_id='kaira-bot', model='gpt-4o'))
    db_session.add(_fact(gen_tenant_id, created_at=start + timedelta(hours=3),
                         cost='0.5', in_tok=10, out_tok=5, pricing_fallback=True,
                         app_id='voice-rx', model='gpt-5.4', purpose='transcription'))
    # Prior window: 1 request, lower cost — backs the delta calc.
    db_session.add(_fact(gen_tenant_id, created_at=prior_start + timedelta(hours=1),
                         cost='1.0', in_tok=100, out_tok=50))
    await db_session.flush()

    result = await build_signal_input(db_session, gen_tenant_id, start, end)

    kpis = result['kpis']
    assert kpis['apiRequests'] == 3
    assert kpis['errorRequests'] == 1
    assert kpis['unpricedRequests'] == 1
    assert kpis['costUsd'] == pytest.approx(3.5)
    assert kpis['tokens'] == 100 + 50 + 200 + 100 + 10 + 5

    prior = result['prior']
    assert prior['apiRequests'] == 1
    assert prior['costUsd'] == pytest.approx(1.0)

    deltas = result['deltas']
    # cost 1.0 -> 3.5 = +250%; requests 1 -> 3 = +200%.
    assert deltas['costPct'] == pytest.approx(250.0)
    assert deltas['requestsPct'] == pytest.approx(200.0)

    # top groups: each entry is {key, costUsd, requests}, ordered by cost desc.
    # kaira-bot=2.0 outranks voice-rx=1.0+0.5=1.5.
    assert result['topApps'][0]['key'] == 'kaira-bot'
    assert result['topApps'][0]['costUsd'] == pytest.approx(2.0)
    apps_by_key = {a['key']: a for a in result['topApps']}
    assert apps_by_key['voice-rx']['costUsd'] == pytest.approx(1.5)
    assert apps_by_key['voice-rx']['requests'] == 2
    assert set(apps_by_key) == {'voice-rx', 'kaira-bot'}
    # gpt-4o=2.0 outranks gpt-5.4=1.5.
    assert result['topModels'][0]['key'] == 'gpt-4o'
    assert {m['key'] for m in result['topModels']} == {'gpt-4o', 'gpt-5.4'}
    purposes = {p['key'] for p in result['topPurposes']}
    assert purposes == {'critique', 'transcription'}


@pytest.mark.asyncio
async def test_build_signal_input_zero_prior_yields_null_deltas(db_session, gen_tenant_id):
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=7)
    end = now
    db_session.add(_fact(gen_tenant_id, created_at=start + timedelta(hours=1),
                         cost='1.0', in_tok=100, out_tok=50))
    await db_session.flush()

    result = await build_signal_input(db_session, gen_tenant_id, start, end)
    assert result['prior']['apiRequests'] == 0
    # /0 guard → null
    assert result['deltas']['costPct'] is None
    assert result['deltas']['requestsPct'] is None


def test_parse_signals_drops_malformed_and_caps_at_four():
    result = {
        "signals": [
            {"severity": "warning", "title": "Spend up", "detail": "Cost rose 20%",
             "metric": {"label": "Δ cost", "value": "20%"}},
            {"severity": "info", "title": "Stable", "detail": "No anomalies"},
            {"severity": "bogus", "title": "Bad sev", "detail": "dropped"},   # invalid severity
            {"severity": "critical", "title": "", "detail": "empty title"},   # empty title
            {"severity": "critical", "title": "No detail", "detail": "  "},   # blank detail
            "not-a-dict",                                                     # not a dict
            {"severity": "critical", "title": "C", "detail": "c"},
            {"severity": "info", "title": "D", "detail": "d"},
            {"severity": "warning", "title": "E-overflow", "detail": "should be capped out"},
        ]
    }
    signals = parse_signals(result)

    assert len(signals) == 4
    titles = [s["title"] for s in signals]
    assert titles == ["Spend up", "Stable", "C", "D"]
    # metric preserved with label + value, value coerced to str.
    assert signals[0]["metric"] == {"label": "Δ cost", "value": "20%"}
    # entries without a well-formed metric carry no metric key.
    assert "metric" not in signals[1]


def test_parse_signals_non_dict_returns_empty():
    assert parse_signals(None) == []
    assert parse_signals("nope") == []
    assert parse_signals({"signals": "not-a-list"}) == []
    assert parse_signals({}) == []


def test_generate_cost_signals_registered_with_cost_manage_permission():
    from app.services.job_worker import JOB_HANDLERS, required_permissions_for_job

    assert "generate-cost-signals" in JOB_HANDLERS
    assert required_permissions_for_job("generate-cost-signals") == ("cost:manage",)

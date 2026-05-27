"""Per-tenant LLM cost-signal generator.

A scheduled platform job builds a compact summary of one tenant's LLM cost
window (with prior-period comparison + top app/purpose/model breakdowns) and
asks the tenant's ``chat_text`` model to surface the few "signals to watch".
The result is persisted as a ``CostSignalSnapshot``; the Cost Overview surface
reads the latest row.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cost import CostSignalSnapshot, FactLlmGeneration

logger = logging.getLogger(__name__)

_VALID_SEVERITIES = {"info", "warning", "critical"}
_MAX_SIGNALS = 4


SIGNALS_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "signals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "severity": {"type": "string", "enum": ["info", "warning", "critical"]},
                    "title": {"type": "string"},
                    "detail": {"type": "string"},
                    "metric": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string"},
                            "value": {"type": "string"},
                        },
                        "required": ["label", "value"],
                    },
                },
                "required": ["severity", "title", "detail"],
            },
        }
    },
    "required": ["signals"],
}


SIGNALS_SYSTEM_PROMPT = (
    "You are a FinOps analyst for an LLM platform. Given a JSON summary of one "
    "workspace's LLM cost and usage for a period (with prior-period comparison), "
    "identify the 2-4 most important signals a platform owner should act on: cost "
    "spikes, spend concentrated in one app/model/purpose, rising error rate, or "
    "unpriced models inflating untracked cost. Be specific and quantitative - cite "
    "the number and % change. Never invent data not in the input. If nothing "
    'notable, return an empty list. Use the word "requests", never "calls". '
    "Respond with JSON only matching the schema."
)


def _round_money(value: Any) -> float:
    return round(float(value or 0), 4)


def _pct_delta(current: float, prior: float) -> float | None:
    """Percent change of ``current`` vs ``prior``; guard /0 → None."""
    if not prior:
        return None
    return round(((current - prior) / prior) * 100, 2)


async def _kpis_for_window(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    start: datetime,
    end: datetime,
) -> dict[str, Any]:
    """Aggregate the core KPIs over ``[start, end)`` for one tenant."""
    filters = [
        FactLlmGeneration.tenant_id == tenant_id,
        FactLlmGeneration.created_at >= start,
        FactLlmGeneration.created_at < end,
    ]
    stmt = select(
        func.coalesce(func.sum(FactLlmGeneration.cost_usd), 0).label("cost_usd"),
        func.coalesce(func.sum(FactLlmGeneration.total_tokens), 0).label("tokens"),
        func.count(FactLlmGeneration.id).label("api_requests"),
        func.sum(case((FactLlmGeneration.status != "ok", 1), else_=0)).label("error_requests"),
        func.sum(case((FactLlmGeneration.pricing_fallback.is_(True), 1), else_=0)).label(
            "unpriced_requests"
        ),
    ).where(and_(*filters))
    row = (await db.execute(stmt)).one()
    return {
        "costUsd": _round_money(row[0]),
        "tokens": int(row[1] or 0),
        "apiRequests": int(row[2] or 0),
        "errorRequests": int(row[3] or 0),
        "unpricedRequests": int(row[4] or 0),
    }


async def _top_by_cost(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    start: datetime,
    end: datetime,
    key_column,
) -> list[dict[str, Any]]:
    """Top 5 ``key_column`` values by cost over ``[start, end)`` for one tenant."""
    filters = [
        FactLlmGeneration.tenant_id == tenant_id,
        FactLlmGeneration.created_at >= start,
        FactLlmGeneration.created_at < end,
    ]
    stmt = (
        select(
            key_column.label("key"),
            func.coalesce(func.sum(FactLlmGeneration.cost_usd), 0).label("cost_usd"),
            func.count(FactLlmGeneration.id).label("requests"),
        )
        .where(and_(*filters))
        .group_by(key_column)
        .order_by(func.sum(FactLlmGeneration.cost_usd).desc())
        .limit(5)
    )
    rows = (await db.execute(stmt)).all()
    return [
        {"key": r[0], "costUsd": _round_money(r[1]), "requests": int(r[2] or 0)}
        for r in rows
    ]


async def build_signal_input(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    start: datetime,
    end: datetime,
) -> dict[str, Any]:
    """Build a compact LLM input dict for one tenant's cost window.

    Self-contained, tenant-scoped queries — does NOT reuse the auth-coupled
    route helpers. ``[start, end)`` is the current window; the immediately
    preceding equal-length window backs the prior-period comparison.
    """
    window = end - start
    prior_start = start - window
    prior_end = start

    kpis = await _kpis_for_window(db, tenant_id, start, end)
    prior = await _kpis_for_window(db, tenant_id, prior_start, prior_end)

    deltas = {
        "costPct": _pct_delta(kpis["costUsd"], prior["costUsd"]),
        "requestsPct": _pct_delta(kpis["apiRequests"], prior["apiRequests"]),
    }

    top_apps = await _top_by_cost(db, tenant_id, start, end, FactLlmGeneration.app_id)
    top_purposes = await _top_by_cost(
        db,
        tenant_id,
        start,
        end,
        func.coalesce(FactLlmGeneration.call_purpose, "unspecified"),
    )
    top_models = await _top_by_cost(db, tenant_id, start, end, FactLlmGeneration.model)

    return {
        "kpis": kpis,
        "prior": prior,
        "deltas": deltas,
        "topApps": top_apps,
        "topPurposes": top_purposes,
        "topModels": top_models,
    }


def parse_signals(result: Any) -> list[dict[str, Any]]:
    """Defensively parse a ``generate_json`` result into well-formed signals.

    Keeps only entries with a valid severity and non-empty title + detail; an
    optional ``metric`` is preserved when it carries label + value. Caps at 4.
    """
    if not isinstance(result, dict):
        return []
    raw_signals = result.get("signals", [])
    if not isinstance(raw_signals, list):
        return []

    cleaned: list[dict[str, Any]] = []
    for entry in raw_signals:
        if not isinstance(entry, dict):
            continue
        severity = entry.get("severity")
        title = entry.get("title")
        detail = entry.get("detail")
        if severity not in _VALID_SEVERITIES:
            continue
        if not isinstance(title, str) or not title.strip():
            continue
        if not isinstance(detail, str) or not detail.strip():
            continue
        signal: dict[str, Any] = {
            "severity": severity,
            "title": title.strip(),
            "detail": detail.strip(),
        }
        metric = entry.get("metric")
        if isinstance(metric, dict):
            label = metric.get("label")
            value = metric.get("value")
            if isinstance(label, str) and label.strip() and value is not None:
                signal["metric"] = {"label": label.strip(), "value": str(value)}
        cleaned.append(signal)
        if len(cleaned) >= _MAX_SIGNALS:
            break
    return cleaned


async def generate_signals_for_tenant(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    job_id,
    *,
    period: str,
    start: datetime,
    end: datetime,
) -> CostSignalSnapshot | None:
    """Generate and persist a cost-signal snapshot for one tenant.

    Skips (returns None) when the window has zero usage. One tenant's LLM
    failure is swallowed (logged) so the platform job never aborts wholesale.
    """
    from app.services.evaluators.llm_base import LoggingLLMWrapper, create_llm_provider
    from app.services.evaluators.runner_utils import make_usage_callback
    from app.services.llm_credentials import (
        CallSiteCapabilityMismatch,
        CallSiteCapabilityUnknown,
        CallSiteNotConfiguredError,
        ProviderNotConfiguredError,
        resolve_llm_call,
    )

    signal_input = await build_signal_input(db, tenant_id, start, end)
    if signal_input["kpis"]["apiRequests"] == 0:
        return None

    try:
        resolved = await resolve_llm_call(db, str(tenant_id), "chat_text")
    except (
        CallSiteNotConfiguredError,
        CallSiteCapabilityMismatch,
        CallSiteCapabilityUnknown,
        ProviderNotConfiguredError,
    ) as exc:
        logger.warning("cost_signals.resolve_failed tenant_id=%s err=%s", tenant_id, exc)
        return None

    try:
        provider_kwargs: dict[str, Any] = {}
        if resolved.provider == "azure_openai":
            provider_kwargs["azure_endpoint"] = (
                resolved.credentials.extra_config.get("base_url") or ""
            )
            provider_kwargs["api_version"] = (
                resolved.api_version
                or resolved.credentials.extra_config.get("api_version")
                or "2025-03-01-preview"
            )

        inner = create_llm_provider(
            provider=resolved.provider,
            model_name=resolved.model,
            api_key=resolved.credentials.secret.get("api_key", ""),
            service_account_path=resolved.credentials.service_account_path or "",
            **provider_kwargs,
        )

        usage_cb = make_usage_callback(
            tenant_id=tenant_id,
            user_id=None,
            app_id="",
            owner_type="job",
            owner_id=job_id,
            subsystem="cost_signals",
        )
        wrapped = LoggingLLMWrapper(inner, usage_callback=usage_cb)
        wrapped.set_call_purpose("cost_signals")

        result = await wrapped.generate_json(
            prompt=json.dumps(signal_input),
            system_prompt=SIGNALS_SYSTEM_PROMPT,
            json_schema=SIGNALS_JSON_SCHEMA,
        )
    except Exception as exc:
        logger.warning("cost_signals.generation_failed tenant_id=%s err=%s", tenant_id, exc)
        return None

    signals = parse_signals(result)

    snapshot = CostSignalSnapshot(
        tenant_id=tenant_id,
        generated_at=datetime.now(timezone.utc),
        model=resolved.model,
        period=period,
        signals=signals,
    )
    db.add(snapshot)
    await db.flush()
    return snapshot

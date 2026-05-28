"""Per-(tenant, app) LLM-generated orchestration-signal generator.

A scheduled platform job builds a compact 30-day summary of one (tenant, app)
orchestration window from the analytics read service and asks the tenant's
``chat_text`` model to surface the few "signals to watch". The result is
persisted as an ``OrchestrationSignalSnapshot``; the analytics dashboard reads
the latest row.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orchestration_signal import OrchestrationSignalSnapshot
from app.services.orchestration.analytics import read_service

logger = logging.getLogger(__name__)

_VALID_SEVERITIES = {"info", "warning", "critical"}
_MAX_SIGNALS = 4
_WINDOW_DAYS = 30
_BREAKDOWN_DIMENSIONS = ("campaign", "channel", "connection")


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
    "You are an outreach-operations analyst. Given a JSON summary of one "
    "workspace's automated outreach over the last 30 days (overall reach / "
    "positive / no-response / failed counts, spend, and per-campaign / "
    "per-channel / per-connection breakdowns), identify the 2-4 most important "
    "signals an operator should act on: a campaign or channel with poor reach, "
    "a spike in failures, spend concentrated in one connection, or a large "
    "no-response cohort. Be specific and quantitative - cite the number and, "
    "where relevant, the share. Never invent data not in the input. If nothing "
    "notable, return an empty list. Respond with JSON only matching the schema."
)


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


def _overview_dict(result) -> dict[str, Any]:
    return {
        "campaigns": result.campaigns,
        "runs": result.runs,
        "recipients": result.recipients,
        "uniqueContacts": result.unique_contacts,
        "positive": result.positive,
        "reached": result.reached,
        "noResponse": result.no_response,
        "failed": result.failed,
        "inFlight": result.in_flight,
        "spend": round(float(result.spend or 0), 4),
    }


def _breakdown_rows(rows) -> list[dict[str, Any]]:
    return [
        {
            "key": r.key,
            "label": r.label,
            "provider": r.provider,
            "recipients": r.recipients,
            "dispatched": r.dispatched,
            "positive": r.positive,
            "reached": r.reached,
            "noResponse": r.no_response,
            "failed": r.failed,
            "inFlight": r.in_flight,
            "cost": round(float(r.cost or 0), 4),
        }
        for r in rows
    ]


async def build_orchestration_signal_input(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    app_id: str,
) -> dict[str, Any]:
    """Assemble a compact 30-day aggregate dict for one (tenant, app).

    Reuses the analytics read service (tenant-wide scope) for the overview KPIs
    and the campaign / channel / connection breakdowns.
    """
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=_WINDOW_DAYS)
    scope_clause = read_service.WORKFLOW_TENANT_ALL(tenant_id)

    overview = await read_service.overview(
        db, tenant_id=tenant_id, app_id=app_id, scope_clause=scope_clause,
        date_from=start, date_to=end,
    )
    breakdowns: dict[str, Any] = {}
    for dimension in _BREAKDOWN_DIMENSIONS:
        rows = await read_service.breakdown(
            db, dimension=dimension, tenant_id=tenant_id, app_id=app_id,
            scope_clause=scope_clause, date_from=start, date_to=end,
        )
        breakdowns[dimension] = _breakdown_rows(rows)

    return {
        "period": f"{_WINDOW_DAYS}d",
        "overview": _overview_dict(overview),
        "breakdowns": breakdowns,
    }


async def _run_signal_llm(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    app_id: str,
    signal_input: dict[str, Any],
    job_id=None,
) -> tuple[Any, str | None]:
    """Resolve ``chat_text``, run the generation, return (raw_result, model).

    Isolated so tests can patch the LLM seam without touching read-service logic.
    """
    from app.services.evaluators.llm_base import LoggingLLMWrapper, create_llm_provider
    from app.services.evaluators.runner_utils import make_usage_callback
    from app.services.llm_credentials import resolve_llm_call

    resolved = await resolve_llm_call(db, str(tenant_id), "chat_text")

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
        app_id=app_id,
        owner_type="job",
        owner_id=job_id,
        subsystem="orchestration_signals",
    )
    wrapped = LoggingLLMWrapper(inner, usage_callback=usage_cb)
    wrapped.set_call_purpose("orchestration_signals")

    result = await wrapped.generate_json(
        prompt=json.dumps(signal_input),
        system_prompt=SIGNALS_SYSTEM_PROMPT,
        json_schema=SIGNALS_JSON_SCHEMA,
    )
    return result, resolved.model


async def generate_orchestration_signals(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    app_id: str,
    *,
    job_id=None,
) -> OrchestrationSignalSnapshot | None:
    """Generate and persist a signal snapshot for one (tenant, app).

    Skips (returns None) when the 30-day window has no recipients. One app's LLM
    failure is swallowed (logged) so the platform job never aborts wholesale.
    """
    from app.services.llm_credentials import (
        CallSiteCapabilityMismatch,
        CallSiteCapabilityUnknown,
        CallSiteNotConfiguredError,
        ProviderNotConfiguredError,
    )

    signal_input = await build_orchestration_signal_input(db, tenant_id, app_id)
    if signal_input["overview"]["recipients"] == 0:
        return None

    try:
        result, model = await _run_signal_llm(db, tenant_id, app_id, signal_input, job_id)
    except (
        CallSiteNotConfiguredError,
        CallSiteCapabilityMismatch,
        CallSiteCapabilityUnknown,
        ProviderNotConfiguredError,
    ) as exc:
        logger.warning(
            "orchestration_signals.resolve_failed tenant_id=%s app_id=%s err=%s",
            tenant_id, app_id, exc,
        )
        return None
    except Exception as exc:
        logger.warning(
            "orchestration_signals.generation_failed tenant_id=%s app_id=%s err=%s",
            tenant_id, app_id, exc,
        )
        return None

    snapshot = OrchestrationSignalSnapshot(
        tenant_id=tenant_id,
        app_id=app_id,
        generated_at=datetime.now(timezone.utc),
        model=model,
        period=signal_input["period"],
        signals=parse_signals(result),
    )
    db.add(snapshot)
    await db.flush()
    return snapshot

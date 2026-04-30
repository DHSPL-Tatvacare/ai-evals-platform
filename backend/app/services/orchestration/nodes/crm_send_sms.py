"""crm.send_sms — minimal SMS sender (Gupshup / Twilio configurable).

Provider selection by SMS_PROVIDER env. Body templating uses {{var}} substitution
against payload. For v1 this is a thin POST with no provider service class.

Tests monkeypatch _make_client to inject httpx.MockTransport.
"""
from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel

from app.config import settings
from app.services.orchestration.integrations.template_resolver import (
    TemplateNotFound,
    resolve_template,
)
from app.services.orchestration.node_protocol import (
    ActionDispatch,
    NodeResult,
    RecipientOutcome,
)
from app.services.orchestration.node_registry import register_node


class _Config(BaseModel):
    template_slug: str
    phone_field: str = "phone"


def _render(template: str, vars_: dict[str, Any]) -> str:
    out = template
    for k, v in vars_.items():
        out = out.replace("{{" + k + "}}", str(v) if v is not None else "")
    return out


def _make_client(timeout: float = 15.0) -> httpx.AsyncClient:
    """Hook for tests."""
    return httpx.AsyncClient(timeout=timeout)


_PROVIDER_CONFIG: dict[str, dict[str, Any]] = {
    "gupshup": {
        "url": "https://api.gupshup.io/sm/api/v1/msg",
        "method": "POST",
        "auth_header": "apikey",
    },
    "twilio": {
        "url": None,  # operator must set SMS_BASE_URL fully (incl. AccountSID)
        "method": "POST",
        "auth_header": None,  # twilio uses HTTP basic; out of v1 scope
    },
}


@register_node(workflow_type="crm", node_type="crm.send_sms")
class _Handler:
    node_type = "crm.send_sms"
    config_schema = _Config
    output_edges = ["success", "failed"]
    category = "action"

    async def execute(self, input_cohort, config: _Config, ctx) -> NodeResult:
        provider = settings.SMS_PROVIDER
        if not provider or provider not in _PROVIDER_CONFIG:
            raise RuntimeError(
                f"crm.send_sms: SMS_PROVIDER not configured or unsupported: {provider!r}"
            )

        try:
            tmpl = await resolve_template(
                ctx.db, tenant_id=ctx.tenant_id, app_id=ctx.app_id,
                channel="sms", slug=config.template_slug,
            )
        except TemplateNotFound as exc:
            raise RuntimeError(f"crm.send_sms: {exc}") from exc

        body_template = tmpl.payload_schema.get("body", "")
        success: list[RecipientOutcome] = []
        failed: list[RecipientOutcome] = []
        pcfg = _PROVIDER_CONFIG[provider]

        async with _make_client() as client:
            async for rid, payload in input_cohort:
                phone = payload.get(config.phone_field)
                if not phone:
                    failed.append(RecipientOutcome(recipient_id=rid))
                    continue
                msg = _render(body_template, payload)
                idem = ctx.idempotency_key(rid, "sms", config.template_slug)
                results = await ctx.dispatch_actions([
                    ActionDispatch(
                        recipient_id=rid,
                        channel="sms",
                        action_type="sms_dispatched",
                        idempotency_key=idem,
                        payload={"phone": phone, "body": msg, "provider": provider},
                    )
                ])
                r = results[0]
                if r.status != "pending":
                    (success if r.status == "success" else failed).append(
                        RecipientOutcome(recipient_id=rid)
                    )
                    continue

                try:
                    if provider == "gupshup":
                        headers = {pcfg["auth_header"]: settings.SMS_API_KEY}
                        resp = await client.post(
                            pcfg["url"],
                            headers=headers,
                            data={
                                "channel": "sms",
                                "source": settings.SMS_BASE_URL or "TATVA",
                                "destination": phone,
                                "message": msg,
                            },
                        )
                    else:  # twilio
                        if not settings.SMS_BASE_URL:
                            raise RuntimeError("crm.send_sms (twilio): SMS_BASE_URL must be set to the Messages.json URL")
                        resp = await client.post(
                            settings.SMS_BASE_URL,
                            data={
                                "From": settings.BOLNA_FROM_PHONE,
                                "To": phone,
                                "Body": msg,
                            },
                        )

                    if 200 <= resp.status_code < 300:
                        await ctx.update_action_result(
                            r.action_id, status="success",
                            response={"status_code": resp.status_code},
                        )
                        success.append(RecipientOutcome(recipient_id=rid))
                    else:
                        await ctx.update_action_result(
                            r.action_id, status="failed",
                            error=f"HTTP {resp.status_code}: {resp.text[:200]}",
                        )
                        failed.append(RecipientOutcome(recipient_id=rid))
                except httpx.HTTPError as exc:
                    await ctx.update_action_result(
                        r.action_id, status="failed", error=repr(exc),
                    )
                    failed.append(RecipientOutcome(recipient_id=rid))

        return NodeResult(
            by_edge_label={"success": success, "failed": failed},
            summary={
                "success_count": len(success),
                "failed_count": len(failed),
                "template_slug": config.template_slug,
            },
        )

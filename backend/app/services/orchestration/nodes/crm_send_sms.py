"""crm.send_sms — sends an SMS per recipient via the connection's provider.

Phase 10 commit 2: provider + credentials come from
``ctx.connections.get_config(config.connection_id)``; the provider on the
connection row decides the dispatch shape (``msg91`` or ``aisensy``).
The legacy ``settings.SMS_*`` env vars are no longer read.

Body templating uses ``{{var}}`` substitution against the recipient
payload. Tests monkeypatch ``_make_client`` to inject ``httpx.MockTransport``.
"""
from __future__ import annotations

import uuid
from typing import Any

import httpx
from pydantic import BaseModel, Field

from app.services.orchestration.connections.resolver import (
    ConnectionProviderMismatch,
)
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


_SUPPORTED_SMS_PROVIDERS = ("msg91", "aisensy")


class _Config(BaseModel):
    connection_id: uuid.UUID = Field(
        ...,
        json_schema_extra={
            "x-type": "connection_picker",
            "x-providers": list(_SUPPORTED_SMS_PROVIDERS),
        },
    )
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


def _build_msg91_request(
    config: dict[str, Any], *, phone: str, body: str,
) -> tuple[str, dict[str, str], dict[str, Any]]:
    """Returns (url, headers, json_body) for an MSG91 flow-API send."""
    auth_key = config.get("auth_key") or ""
    flow_id = config.get("flow_id") or ""
    sender_id = config.get("sender_id") or ""
    if not auth_key or not flow_id:
        raise RuntimeError("crm.send_sms (msg91): connection missing auth_key/flow_id")
    url = "https://control.msg91.com/api/v5/flow/"
    headers = {"authkey": auth_key, "Content-Type": "application/json"}
    payload: dict[str, Any] = {
        "flow_id": flow_id,
        "sender": sender_id,
        "recipients": [{"mobiles": phone, "body": body}],
    }
    return url, headers, payload


def _build_aisensy_request(
    config: dict[str, Any], *, phone: str, body: str,
) -> tuple[str, dict[str, str], dict[str, Any]]:
    """Returns (url, headers, json_body) for an AiSensy SMS send."""
    api_key = config.get("api_key") or ""
    base_url = (config.get("base_url") or "").rstrip("/")
    partner_id = config.get("campaign_partner_id") or ""
    sender = config.get("from_number") or ""
    if not api_key or not base_url:
        raise RuntimeError(
            "crm.send_sms (aisensy): connection missing api_key/base_url"
        )
    url = f"{base_url}/v1/{partner_id}/sms/send" if partner_id else f"{base_url}/v1/sms/send"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload: dict[str, Any] = {
        "from": sender,
        "to": phone,
        "body": body,
    }
    return url, headers, payload


@register_node(workflow_type="crm", node_type="crm.send_sms")
class _Handler:
    node_type = "crm.send_sms"
    config_schema = _Config
    output_edges = ["success", "failed"]
    category = "action"

    async def execute(self, input_cohort, config: _Config, ctx) -> NodeResult:
        if ctx.connections is None:
            raise RuntimeError(
                "crm.send_sms requires ctx.connections — wire ConnectionResolver in run_handler"
            )
        try:
            conn_config = await ctx.connections.get_config(config.connection_id)
        except ConnectionProviderMismatch as exc:  # pragma: no cover — get_config without expected_provider can't raise this
            raise RuntimeError(f"crm.send_sms: {exc}") from exc

        provider = conn_config.get("__provider__", "")
        if provider not in _SUPPORTED_SMS_PROVIDERS:
            raise RuntimeError(
                f"crm.send_sms: connection provider={provider!r} is not an SMS provider; "
                f"expected one of {_SUPPORTED_SMS_PROVIDERS}"
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
                    if provider == "msg91":
                        url, headers, json_body = _build_msg91_request(
                            conn_config, phone=phone, body=msg,
                        )
                    else:  # aisensy
                        url, headers, json_body = _build_aisensy_request(
                            conn_config, phone=phone, body=msg,
                        )
                    resp = await client.post(url, headers=headers, json=json_body)

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
                "provider": provider,
            },
        )

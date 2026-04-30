"""crm.send_wati — resolves a WATI template + sends per recipient via WatiService.

Persists one workflow_run_recipient_actions row per recipient with
action_type='wa_dispatched'. Idempotency key is deterministic from
(workflow_version_id, node_id, recipient_id, "wati", template_slug).
Emits 'success' / 'failed' edges.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.services.orchestration.integrations.template_resolver import (
    TemplateNotFound,
    resolve_template,
)
from app.services.orchestration.integrations.wati import WatiServiceError
from app.services.orchestration.node_protocol import (
    ActionDispatch,
    NodeResult,
    RecipientOutcome,
)
from app.services.orchestration.node_registry import register_node


class _Config(BaseModel):
    template_slug: str
    phone_field: str = "whatsapp_number"  # E.164 digits, no '+'


@register_node(workflow_type="crm", node_type="crm.send_wati")
class _Handler:
    node_type = "crm.send_wati"
    config_schema = _Config
    output_edges = ["success", "failed"]
    category = "action"

    async def execute(self, input_cohort, config: _Config, ctx) -> NodeResult:
        if ctx.services.wati is None:
            raise RuntimeError(
                "crm.send_wati requires WATI service — set WATI_BASE_URL + WATI_TENANT_ID + WATI_API_TOKEN"
            )

        try:
            template = await resolve_template(
                ctx.db, tenant_id=ctx.tenant_id, app_id=ctx.app_id,
                channel="wati", slug=config.template_slug,
            )
        except TemplateNotFound as exc:
            raise RuntimeError(f"crm.send_wati: {exc}") from exc

        success: list[RecipientOutcome] = []
        failed: list[RecipientOutcome] = []

        async for rid, payload in input_cohort:
            wa_number = payload.get(config.phone_field)
            if not wa_number:
                failed.append(RecipientOutcome(recipient_id=rid))
                continue

            params_built = _build_parameters(
                template.payload_schema.get("parameter_map", []), payload
            )

            idem = ctx.idempotency_key(rid, "wati", config.template_slug)
            results = await ctx.dispatch_actions([
                ActionDispatch(
                    recipient_id=rid,
                    channel="wati",
                    action_type="wa_dispatched",
                    idempotency_key=idem,
                    payload={
                        "template_name": template.payload_schema["template_name"],
                        "broadcast_name": template.payload_schema.get("broadcast_name", "concierge"),
                        "parameters": params_built,
                        "whatsapp_number": wa_number,
                    },
                )
            ])
            r = results[0]
            if r.status != "pending":
                (success if r.status == "success" else failed).append(
                    RecipientOutcome(recipient_id=rid)
                )
                continue

            try:
                resp = await ctx.services.wati.send_template(
                    whatsapp_number=wa_number,
                    template_name=template.payload_schema["template_name"],
                    broadcast_name=template.payload_schema.get("broadcast_name", "concierge"),
                    parameters=params_built,
                )
                await ctx.update_action_result(r.action_id, status="success", response=resp)
                success.append(RecipientOutcome(recipient_id=rid))
            except WatiServiceError as exc:
                await ctx.update_action_result(r.action_id, status="failed", error=str(exc))
                failed.append(RecipientOutcome(recipient_id=rid))

        return NodeResult(
            by_edge_label={"success": success, "failed": failed},
            summary={
                "success_count": len(success),
                "failed_count": len(failed),
                "template_slug": config.template_slug,
            },
        )


def _build_parameters(
    parameter_map: list[dict[str, str]], payload: dict[str, Any]
) -> list[dict[str, str]]:
    """parameter_map entries: {"name": "<wati_param_name>", "source": "<payload_field>"}."""
    out: list[dict[str, str]] = []
    for entry in parameter_map:
        src = entry.get("source")
        val = payload.get(src) if src else None
        out.append({"name": entry["name"], "value": str(val) if val is not None else ""})
    return out

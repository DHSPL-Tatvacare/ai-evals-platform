"""crm.place_bolna_call — resolves a Bolna template + places one outbound voice call per recipient.

Action row: action_type='bolna_queued'. Bolna's own retry_config governs
provider-side retries; this handler places the call once per node visit.
Emits 'success' / 'failed'.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.services.orchestration.integrations.bolna import BolnaServiceError
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
    phone_field: str = "phone"  # E.164 with '+'


@register_node(workflow_type="crm", node_type="crm.place_bolna_call")
class _Handler:
    node_type = "crm.place_bolna_call"
    config_schema = _Config
    output_edges = ["success", "failed"]
    category = "action"

    async def execute(self, input_cohort, config: _Config, ctx) -> NodeResult:
        if ctx.services.bolna is None:
            raise RuntimeError(
                "crm.place_bolna_call requires Bolna service — set BOLNA_API_KEY"
            )

        try:
            tmpl = await resolve_template(
                ctx.db, tenant_id=ctx.tenant_id, app_id=ctx.app_id,
                channel="bolna", slug=config.template_slug,
            )
        except TemplateNotFound as exc:
            raise RuntimeError(f"crm.place_bolna_call: {exc}") from exc

        success: list[RecipientOutcome] = []
        failed: list[RecipientOutcome] = []

        async for rid, payload in input_cohort:
            phone = payload.get(config.phone_field)
            if not phone:
                failed.append(RecipientOutcome(recipient_id=rid))
                continue

            user_data = _build_user_data(
                tmpl.payload_schema.get("user_data_map", []), payload
            )
            idem = ctx.idempotency_key(rid, "bolna", config.template_slug)
            results = await ctx.dispatch_actions([
                ActionDispatch(
                    recipient_id=rid,
                    channel="bolna",
                    action_type="bolna_queued",
                    idempotency_key=idem,
                    payload={
                        "agent_id": tmpl.payload_schema["agent_id"],
                        "recipient_phone": phone,
                        "user_data": user_data,
                        "retry_config": tmpl.payload_schema.get("retry_config"),
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
                resp = await ctx.services.bolna.place_call(
                    agent_id=tmpl.payload_schema["agent_id"],
                    recipient_phone=phone,
                    user_data=user_data,
                    retry_config=tmpl.payload_schema.get("retry_config"),
                )
                await ctx.update_action_result(r.action_id, status="success", response=resp)
                success.append(RecipientOutcome(recipient_id=rid))
            except BolnaServiceError as exc:
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


def _build_user_data(
    user_data_map: list[dict[str, str]], payload: dict[str, Any]
) -> dict[str, str]:
    out: dict[str, str] = {}
    for entry in user_data_map:
        src = entry.get("source", "")
        out[entry["name"]] = str(payload.get(src, "")) if src else ""
    return out

"""crm.place_bolna_call — resolves a Bolna template + places one outbound voice call per recipient.

Phase 10 commit 2: the Bolna service is resolved per-call from
``ctx.connections.bolna(config.connection_id)`` rather than read off
``ctx.services.bolna``. Node config gains:

* ``connection_id``: required UUID pointing at an active
  ``orchestration.provider_connections`` row with ``provider='bolna'``.
* ``variable_mappings``: optional list of agent-variable bindings. Each
  row binds an agent-defined variable to either a recipient payload field
  or a static value; absent mappings fall back to the template's
  ``user_data_map`` for backwards compatibility with older seeds.

Action row: action_type='bolna_queued'. Bolna's own retry_config governs
provider-side retries; this handler places the call once per node visit.
Emits 'success' / 'failed'.
"""
from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field

from app.services.orchestration.connections.variable_mapping import (
    apply_variable_mappings_dict,
)
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
    connection_id: uuid.UUID = Field(
        ...,
        json_schema_extra={"x-type": "connection_picker", "x-provider": "bolna"},
    )
    template_slug: str
    phone_field: str = "phone"  # E.164 with '+'
    variable_mappings: list[dict[str, Any]] = Field(
        default_factory=list,
        json_schema_extra={"x-type": "variable_mapping_list"},
    )


@register_node(workflow_type="crm", node_type="crm.place_bolna_call")
class _Handler:
    node_type = "crm.place_bolna_call"
    config_schema = _Config
    output_edges = ["success", "failed"]
    category = "action"

    async def execute(self, input_cohort, config: _Config, ctx) -> NodeResult:
        if ctx.connections is None:
            raise RuntimeError(
                "crm.place_bolna_call requires ctx.connections — wire ConnectionResolver in run_handler"
            )
        service = await ctx.connections.bolna(config.connection_id)

        try:
            tmpl = await resolve_template(
                ctx.db, tenant_id=ctx.tenant_id, app_id=ctx.app_id,
                channel="bolna", slug=config.template_slug,
            )
        except TemplateNotFound as exc:
            raise RuntimeError(f"crm.place_bolna_call: {exc}") from exc

        template_user_map = tmpl.payload_schema.get("user_data_map", []) or []

        success: list[RecipientOutcome] = []
        failed: list[RecipientOutcome] = []

        async for rid, payload in input_cohort:
            phone = payload.get(config.phone_field)
            if not phone:
                failed.append(RecipientOutcome(recipient_id=rid))
                continue

            user_data = apply_variable_mappings_dict(
                config.variable_mappings,
                payload,
                template_fallback=template_user_map,
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
                resp = await service.place_call(
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

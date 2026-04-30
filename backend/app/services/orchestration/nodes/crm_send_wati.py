"""crm.send_wati — resolves a WATI template + sends per recipient via WatiService.

Phase 10 commit 2: the WATI service is resolved per-call from
``ctx.connections.wati(config.connection_id)`` rather than read off
``ctx.services.wati``. Node config gains:

* ``connection_id``: required UUID pointing at an active
  ``orchestration.provider_connections`` row with ``provider='wati'``.
* ``variable_mappings``: optional list overriding the template's
  ``parameter_map``. When empty the handler falls back to the template
  default so older seed JSON keeps working.

Persists one workflow_run_recipient_actions row per recipient with
action_type='wa_dispatched'. Idempotency key is deterministic from
(workflow_version_id, node_id, recipient_id, "wati", template_slug).
Emits 'success' / 'failed' edges.
"""
from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field

from app.services.orchestration.connections.variable_mapping import (
    apply_variable_mappings_list,
)
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
    connection_id: uuid.UUID = Field(
        ...,
        json_schema_extra={"x-type": "connection_picker", "x-provider": "wati"},
    )
    template_slug: str
    phone_field: str = "whatsapp_number"  # E.164 digits, no '+'
    variable_mappings: list[dict[str, Any]] = Field(
        default_factory=list,
        json_schema_extra={"x-type": "variable_mapping_list"},
    )


@register_node(workflow_type="crm", node_type="crm.send_wati")
class _Handler:
    node_type = "crm.send_wati"
    config_schema = _Config
    output_edges = ["success", "failed"]
    category = "action"

    async def execute(self, input_cohort, config: _Config, ctx) -> NodeResult:
        if ctx.connections is None:
            raise RuntimeError(
                "crm.send_wati requires ctx.connections — wire ConnectionResolver in run_handler"
            )
        service = await ctx.connections.wati(config.connection_id)

        try:
            template = await resolve_template(
                ctx.db, tenant_id=ctx.tenant_id, app_id=ctx.app_id,
                channel="wati", slug=config.template_slug,
            )
        except TemplateNotFound as exc:
            raise RuntimeError(f"crm.send_wati: {exc}") from exc

        template_param_map = template.payload_schema.get("parameter_map", []) or []

        success: list[RecipientOutcome] = []
        failed: list[RecipientOutcome] = []

        async for rid, payload in input_cohort:
            wa_number = payload.get(config.phone_field)
            if not wa_number:
                failed.append(RecipientOutcome(recipient_id=rid))
                continue

            params_built = apply_variable_mappings_list(
                config.variable_mappings,
                payload,
                template_fallback=template_param_map,
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
                resp = await service.send_template(
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

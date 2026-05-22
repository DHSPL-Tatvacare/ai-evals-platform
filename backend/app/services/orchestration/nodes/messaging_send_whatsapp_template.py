"""messaging.send_whatsapp_template — capability-named WhatsApp dispatch node.

Vendor is selected by the bound ProviderConnection (wati / aisensy). All
vendor-specific HTTP shaping lives in the MessagingAdapter resolved at
execute-time via ``resolve_adapter(capability='messaging', vendor=...)``.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field

from app.services.orchestration._config_strictness import strict_node_config_dict
from app.services.orchestration.adapters import (
    AdapterNotRegisteredError,
    CanonicalSendRequest,
    resolve_adapter,
)
from app.services.orchestration.comm_cap.enforcement import enforce_comm_cap_or_skip
from app.services.orchestration.errors import RecipientNotInManifestError
from app.services.orchestration.node_protocol import (
    ActionDispatch,
    NodeResult,
    RecipientOutcome,
)
from app.services.orchestration.connections.variable_mapping import (
    VariableMappingRow,
    apply_variable_mappings_dict,
)
from app.services.orchestration.node_registry import register_node
from app.services.orchestration.recipient_freezer import normalise_phone_e164
from app.services.orchestration.recipient_manifest import assert_recipient_in_manifest


class _Config(BaseModel):
    model_config = strict_node_config_dict()

    connection_id: uuid.UUID = Field(
        ...,
        description="WhatsApp connection to send through.",
        json_schema_extra={
            "x-type": "connection_picker",
            "x-providers": ["wati", "aisensy"],
        },
    )
    # Picker fields — required at publish time; empty string is draft-safe.
    phone_field: str = Field(
        "",
        title="Phone Number Field",
        description="Pick the contact field that holds each recipient's phone number.",
        json_schema_extra={"x-type": "recipient_field_picker"},
    )
    template_name: str = Field(
        "",
        title="WhatsApp Template",
        description="Pick the live template the cohort receives.",
        json_schema_extra={"x-type": "wati_template_picker"},
    )
    channel_number: str = Field(
        "",
        title="Channel Number",
        description="Pick the WhatsApp sender number this campaign goes from.",
        json_schema_extra={"x-type": "wati_channel_picker"},
    )
    broadcast_name: str = Field(
        "",
        title="Broadcast Name",
        description="Campaign label sent to WATI as broadcast_name.",
    )
    variable_mappings: list[VariableMappingRow] = Field(
        default_factory=list,
        description="Template placeholders — each bound to a static value or a recipient field.",
        json_schema_extra={"x-type": "variable_mapping_list"},
    )
    webhook_ttl_seconds: int = Field(
        default=259200,
        ge=60,
        description="Ignore replies arriving after this many seconds. Defaults to 3 days.",
    )


@register_node(workflow_type="*", node_type="messaging.send_whatsapp_template")
class _Handler:
    node_type = "messaging.send_whatsapp_template"
    config_schema = _Config
    output_edges = ["success", "failed"]
    category = "action"

    async def execute(self, input_cohort, config: _Config, ctx) -> NodeResult:
        if ctx.connections is None:
            raise RuntimeError(
                "messaging.send_whatsapp_template requires ctx.connections — "
                "wire ConnectionResolver in run_handler"
            )
        connection = await ctx.connections.get_config(config.connection_id)
        vendor = connection.get("__provider__", "")
        try:
            adapter = resolve_adapter(capability="messaging", vendor=vendor)
        except AdapterNotRegisteredError as exc:
            raise RuntimeError(
                f"no messaging adapter registered for provider {vendor!r}; "
                f"connection {config.connection_id} cannot dispatch"
            ) from exc

        success: list[RecipientOutcome] = []
        failed: list[RecipientOutcome] = []
        ttl_deadline = datetime.now(timezone.utc) + timedelta(
            seconds=config.webhook_ttl_seconds
        )

        async for rid, payload in input_cohort:
            try:
                recipient_row = await assert_recipient_in_manifest(
                    ctx.db, run_id=ctx.run_id, recipient_id=rid,
                )
            except RecipientNotInManifestError:
                await ctx.set_recipient_state(rid, status="skipped")
                continue
            cap_result = await enforce_comm_cap_or_skip(
                ctx.db, recipient=recipient_row, stage="cap_runtime",
            )
            if not cap_result.proceed:
                continue
            # Destination = the operator-picked payload field, normalized. One
            # contract, no hardcoded field names — works for cohort and dataset
            # payloads alike. Recipients whose picked field is missing/invalid skip.
            contact = normalise_phone_e164(payload.get(config.phone_field))
            if not contact:
                await ctx.set_recipient_state(rid, status="skipped_invalid_phone")
                continue
            request = CanonicalSendRequest(
                contact=contact,
                template_name=config.template_name,
                broadcast_name=config.broadcast_name,
                channel_number=config.channel_number,
                variables=apply_variable_mappings_dict(
                    [m.model_dump() for m in config.variable_mappings], payload,
                ),
            )
            idem = ctx.idempotency_key(rid, "whatsapp_template", config.template_name)
            dispatch = await ctx.dispatch_actions([
                ActionDispatch(
                    recipient_id=rid,
                    channel="whatsapp",
                    action_type="wa_dispatched",
                    idempotency_key=idem,
                    payload={"contact": contact, "template_name": config.template_name},
                )
            ])
            action_id = dispatch[0].action_id
            if dispatch[0].status != "pending":
                bucket = success if dispatch[0].status == "success" else failed
                bucket.append(RecipientOutcome(recipient_id=rid))
                continue

            try:
                response = await adapter.send_template(
                    connection=connection, request=request,
                )
            except Exception as exc:  # noqa: BLE001 — vendor error surfaced verbatim
                await ctx.update_action_result(
                    action_id, status="failed", error=str(exc),
                )
                failed.append(RecipientOutcome(recipient_id=rid))
                continue

            await ctx.update_action_result(
                action_id,
                status="success",
                response={
                    "raw": response.raw,
                    "provider_correlation_id": response.provider_correlation_id,
                },
                provider_correlation_id=response.provider_correlation_id,
            )
            await ctx.stamp_webhook_ttl(rid, deadline=ttl_deadline)
            success.append(RecipientOutcome(recipient_id=rid))

        return NodeResult(
            by_output_id={"success": success, "failed": failed},
            summary={
                "success_count": len(success),
                "failed_count": len(failed),
            },
        )


__all__ = ["_Config", "_Handler"]

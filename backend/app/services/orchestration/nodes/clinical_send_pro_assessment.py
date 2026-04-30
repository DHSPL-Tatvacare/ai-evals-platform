"""clinical.send_pro_assessment — enqueues a PRO instrument link via the outbox.

Outbox-backed; no live SMS/email sending in v1. Downstream channel adapter
will translate the payload into the appropriate delivery API.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.services.orchestration.node_protocol import (
    ActionDispatch,
    NodeResult,
    RecipientOutcome,
)
from app.services.orchestration.node_registry import register_node


class _Config(BaseModel):
    instrument: Literal["PHQ9", "DDS", "MMAS", "EQ5D", "PROMIS"] = "PHQ9"
    delivery_channel: Literal["sms", "email", "wa"] = "wa"


@register_node(workflow_type="clinical", node_type="clinical.send_pro_assessment")
class _Handler:
    node_type = "clinical.send_pro_assessment"
    config_schema = _Config
    output_edges = ["success", "failed"]
    category = "action"

    async def execute(self, input_cohort, config: _Config, ctx) -> NodeResult:
        if ctx.services.clinical_outbox is None:
            raise RuntimeError("clinical.send_pro_assessment requires ClinicalOutboxWriter")

        success: list[RecipientOutcome] = []
        failed: list[RecipientOutcome] = []
        async for rid, _payload in input_cohort:
            idem = ctx.idempotency_key(rid, "pro", config.instrument)
            outbox_payload = {
                "instrument": config.instrument,
                "delivery_channel": config.delivery_channel,
            }
            results = await ctx.dispatch_actions([
                ActionDispatch(
                    recipient_id=rid,
                    channel="system",
                    action_type="clinical.send_pro_assessment",
                    idempotency_key=idem,
                    payload=outbox_payload,
                )
            ])
            r = results[0]
            if r.status != "pending":
                (success if r.status == "success" else failed).append(
                    RecipientOutcome(recipient_id=rid)
                )
                continue
            try:
                await ctx.services.clinical_outbox.enqueue(
                    ctx.db,
                    tenant_id=ctx.tenant_id,
                    app_id=ctx.app_id,
                    recipient_id=rid,
                    action_type="clinical.send_pro_assessment",
                    idempotency_key=idem,
                    payload=outbox_payload,
                )
                await ctx.update_action_result(
                    r.action_id, status="success", response={"queued": True}
                )
                success.append(RecipientOutcome(recipient_id=rid))
            except Exception as exc:  # pragma: no cover — defensive
                await ctx.update_action_result(
                    r.action_id, status="failed", error=repr(exc)
                )
                failed.append(RecipientOutcome(recipient_id=rid))

        return NodeResult(
            by_edge_label={"success": success, "failed": failed},
            summary={
                "instrument": config.instrument,
                "success_count": len(success),
                "failed_count": len(failed),
            },
        )

"""clinical.escalation_uptier — escalates to physician/specialist via the outbox.

category='escalation' so the palette can colour-code this distinctly from
plain action nodes (the run-canvas overlay reads the same category).
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
    target_role: Literal["physician", "specialist", "ed", "crisis_team"] = "physician"
    urgency: Literal["same_day", "48h", "next_review", "next_month"] = "same_day"
    reason: str


@register_node(workflow_type="clinical", node_type="clinical.escalation_uptier")
class _Handler:
    node_type = "clinical.escalation_uptier"
    config_schema = _Config
    output_edges = ["success", "failed"]
    category = "escalation"

    async def execute(self, input_cohort, config: _Config, ctx) -> NodeResult:
        if ctx.services.clinical_outbox is None:
            raise RuntimeError("clinical.escalation_uptier requires ClinicalOutboxWriter")

        success: list[RecipientOutcome] = []
        failed: list[RecipientOutcome] = []
        async for rid, _payload in input_cohort:
            idem = ctx.idempotency_key(rid, "escalation", config.urgency, config.target_role)
            outbox_payload = {
                "target_role": config.target_role,
                "urgency": config.urgency,
                "reason": config.reason,
            }
            results = await ctx.dispatch_actions([
                ActionDispatch(
                    recipient_id=rid,
                    channel="system",
                    action_type="clinical.escalation_uptier",
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
                    action_type="clinical.escalation_uptier",
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
                "target_role": config.target_role,
                "urgency": config.urgency,
                "success_count": len(success),
                "failed_count": len(failed),
            },
        )

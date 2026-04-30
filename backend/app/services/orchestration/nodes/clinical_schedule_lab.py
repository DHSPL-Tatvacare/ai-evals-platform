"""clinical.schedule_lab — enqueues a lab order in log_clinical_action_outbox.

Phase 9 ships outbox-backed clinical handlers. v1 has no consumers — the
outbox row IS the integration. A future EMR-sync worker will read pending
rows, place actual lab orders, and flip status='consumed'.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.services.orchestration.node_protocol import (
    ActionDispatch,
    NodeResult,
    RecipientOutcome,
)
from app.services.orchestration.node_registry import register_node


class _Config(BaseModel):
    test_code: str = Field(..., description="Lab test code (LOINC or local).")
    test_name: str
    frequency: Literal["once", "monthly", "quarterly", "biannual", "annual"] = "once"
    notify_roles: list[Literal["care_manager", "physician", "pharmacist"]] = Field(
        default_factory=lambda: ["care_manager"]
    )
    urgency: Literal["routine", "urgent", "stat"] = "routine"


@register_node(workflow_type="clinical", node_type="clinical.schedule_lab")
class _Handler:
    node_type = "clinical.schedule_lab"
    config_schema = _Config
    output_edges = ["success", "failed"]
    category = "action"

    async def execute(self, input_cohort, config: _Config, ctx) -> NodeResult:
        if ctx.services.clinical_outbox is None:
            raise RuntimeError("clinical.schedule_lab requires ClinicalOutboxWriter")

        success: list[RecipientOutcome] = []
        failed: list[RecipientOutcome] = []
        async for rid, _payload in input_cohort:
            idem = ctx.idempotency_key(rid, "lab", config.test_code)
            outbox_payload = {
                "test_code": config.test_code,
                "test_name": config.test_name,
                "frequency": config.frequency,
                "notify_roles": list(config.notify_roles),
                "urgency": config.urgency,
            }
            results = await ctx.dispatch_actions([
                ActionDispatch(
                    recipient_id=rid,
                    channel="system",
                    action_type="clinical.schedule_lab",
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
                    action_type="clinical.schedule_lab",
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
                "test_code": config.test_code,
                "success_count": len(success),
                "failed_count": len(failed),
            },
        )

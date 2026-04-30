"""clinical.assign_care_team_task — enqueues a care-team task in the outbox.

Same shape as clinical.schedule_lab — config + payload → outbox row + audit
action — different config schema and idempotency key prefix.
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
    role: Literal["care_manager", "physician", "pharmacist", "nutritionist"] = "care_manager"
    task_label: str
    cadence: Literal["once", "weekly", "monthly"] = "once"
    sla_hours: int = 24


@register_node(workflow_type="clinical", node_type="clinical.assign_care_team_task")
class _Handler:
    node_type = "clinical.assign_care_team_task"
    config_schema = _Config
    output_edges = ["success", "failed"]
    category = "action"

    async def execute(self, input_cohort, config: _Config, ctx) -> NodeResult:
        if ctx.services.clinical_outbox is None:
            raise RuntimeError("clinical.assign_care_team_task requires ClinicalOutboxWriter")

        success: list[RecipientOutcome] = []
        failed: list[RecipientOutcome] = []
        async for rid, _payload in input_cohort:
            idem = ctx.idempotency_key(rid, "care_task", config.task_label)
            outbox_payload = {
                "role": config.role,
                "task_label": config.task_label,
                "cadence": config.cadence,
                "sla_hours": config.sla_hours,
            }
            results = await ctx.dispatch_actions([
                ActionDispatch(
                    recipient_id=rid,
                    channel="system",
                    action_type="clinical.assign_care_team_task",
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
                    action_type="clinical.assign_care_team_task",
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
                "role": config.role,
                "success_count": len(success),
                "failed_count": len(failed),
            },
        )

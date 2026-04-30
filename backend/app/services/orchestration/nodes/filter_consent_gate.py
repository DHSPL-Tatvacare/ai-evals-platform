"""filter.consent_gate — checks workflow_consent_records for the channel.

require_explicit_optin:
  False — opted_out blocks; unknown allows (implicit consent treated as opt-in)
  True  — only opted_in allows; everything else blocks (strict, for sensitive channels)
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel
from sqlalchemy import select

from app.models.orchestration import WorkflowConsentRecord
from app.services.orchestration.node_protocol import NodeResult, RecipientOutcome
from app.services.orchestration.node_registry import register_node


class _Config(BaseModel):
    channel: Literal["wa", "voice", "sms", "email"]
    require_explicit_optin: bool = False


@register_node(workflow_type="*", node_type="filter.consent_gate")
class _Handler:
    node_type = "filter.consent_gate"
    config_schema = _Config
    output_edges = ["allowed", "blocked"]
    category = "filter"

    async def execute(self, input_cohort, config: _Config, ctx) -> NodeResult:
        recipient_ids: list[str] = []
        async for rid, _ in input_cohort:
            recipient_ids.append(rid)
        if not recipient_ids:
            return NodeResult(by_edge_label={"allowed": [], "blocked": []})

        stmt = (
            select(
                WorkflowConsentRecord.recipient_id,
                WorkflowConsentRecord.status,
            )
            .where(
                WorkflowConsentRecord.tenant_id == ctx.tenant_id,
                WorkflowConsentRecord.app_id == ctx.app_id,
                WorkflowConsentRecord.channel == config.channel,
                WorkflowConsentRecord.recipient_id.in_(recipient_ids),
            )
            .distinct(WorkflowConsentRecord.recipient_id)
            .order_by(
                WorkflowConsentRecord.recipient_id,
                WorkflowConsentRecord.created_at.desc(),
            )
        )
        result = await ctx.db.execute(stmt)
        latest: dict[str, str] = dict(result.all())

        allowed: list[RecipientOutcome] = []
        blocked: list[RecipientOutcome] = []
        for rid in recipient_ids:
            status = latest.get(rid)
            if config.require_explicit_optin:
                if status == "opted_in":
                    allowed.append(RecipientOutcome(recipient_id=rid))
                else:
                    blocked.append(RecipientOutcome(recipient_id=rid))
            else:
                if status == "opted_out":
                    blocked.append(RecipientOutcome(recipient_id=rid))
                else:
                    allowed.append(RecipientOutcome(recipient_id=rid))

        return NodeResult(
            by_edge_label={"allowed": allowed, "blocked": blocked},
            summary={"allowed_count": len(allowed), "blocked_count": len(blocked)},
        )

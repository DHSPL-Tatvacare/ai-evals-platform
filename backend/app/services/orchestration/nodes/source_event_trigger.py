"""source.event_trigger — entry from a webhook event. Seeds named recipients into the cohort."""
from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select, update

from app.models.orchestration import WorkflowRun, WorkflowRunRecipientState
from app.services.orchestration.node_protocol import NodeResult
from app.services.orchestration.node_registry import register_node


class _Config(BaseModel):
    next_node_id: str


@register_node(workflow_type="*", node_type="source.event_trigger")
class _Handler:
    node_type = "source.event_trigger"
    config_schema = _Config
    output_edges = ["default"]
    category = "source"

    async def execute(self, input_cohort, config: _Config, ctx) -> NodeResult:
        result = await ctx.db.execute(
            select(WorkflowRun.params).where(WorkflowRun.id == ctx.run_id)
        )
        run_params: dict[str, Any] = result.scalar() or {}
        event_payload = run_params.get("event_payload") or {}
        recipients: list[dict[str, Any]] = event_payload.get("recipients", [])

        for r in recipients:
            ctx.db.add(WorkflowRunRecipientState(
                id=uuid.uuid4(), tenant_id=ctx.tenant_id, app_id=ctx.app_id,
                workflow_id=ctx.workflow_id, workflow_version_id=ctx.workflow_version_id,
                run_id=ctx.run_id,
                recipient_id=r["recipient_id"],
                current_node_id=config.next_node_id,
                status="ready",
                payload=r.get("payload") or {},
            ))

        await ctx.db.execute(
            update(WorkflowRun).where(WorkflowRun.id == ctx.run_id)
            .values(cohort_size_at_entry=len(recipients))
        )
        await ctx.db.flush()
        return NodeResult(summary={"cohort_size": len(recipients)})

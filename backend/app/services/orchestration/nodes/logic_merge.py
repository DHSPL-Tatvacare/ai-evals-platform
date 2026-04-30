"""logic.merge — combines multiple input cohorts. Optional dedupe by recipient_id."""
from __future__ import annotations

from pydantic import BaseModel

from app.services.orchestration.node_protocol import NodeResult, RecipientOutcome
from app.services.orchestration.node_registry import register_node


class _Config(BaseModel):
    dedupe: bool = True


@register_node(workflow_type="*", node_type="logic.merge")
class _Handler:
    node_type = "logic.merge"
    config_schema = _Config
    output_edges = ["default"]
    category = "logic"

    async def execute(self, input_cohort, config: _Config, ctx) -> NodeResult:
        seen: set[str] = set()
        outs: list[RecipientOutcome] = []
        async for rid, _ in input_cohort:
            if config.dedupe:
                if rid in seen:
                    continue
                seen.add(rid)
            outs.append(RecipientOutcome(recipient_id=rid))
        return NodeResult(by_edge_label={"default": outs}, summary={"merged_count": len(outs)})

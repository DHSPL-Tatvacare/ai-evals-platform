"""logic.conditional — true/false branch by predicate over recipient payload."""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel

from app.services.orchestration.node_protocol import NodeResult, RecipientOutcome
from app.services.orchestration.node_registry import register_node
from app.services.orchestration.nodes._predicate import evaluate_predicate


class _Config(BaseModel):
    predicate: dict[str, Any]


@register_node(workflow_type="*", node_type="logic.conditional")
class _Handler:
    node_type = "logic.conditional"
    config_schema = _Config
    output_edges = ["true", "false"]
    category = "logic"

    async def execute(self, input_cohort, config: _Config, ctx) -> NodeResult:
        true_outs: list[RecipientOutcome] = []
        false_outs: list[RecipientOutcome] = []
        async for rid, payload in input_cohort:
            (true_outs if evaluate_predicate(config.predicate, payload) else false_outs).append(
                RecipientOutcome(recipient_id=rid)
            )
        return NodeResult(
            by_edge_label={"true": true_outs, "false": false_outs},
            summary={"true_count": len(true_outs), "false_count": len(false_outs)},
        )

"""logic.conditional — N-way criteria router over recipient payload.

Branches are evaluated in order; each recipient routes to the first branch
whose predicate matches. Unmatched recipients fall to the implicit
``default`` output. Branch ids are stable routing keys (matching edge
``output_id``); labels are display-only. Outputs are dynamic, mirroring
``logic.split``.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, ValidationInfo, model_validator

from app.services.orchestration._config_strictness import strict_node_config_dict
from app.services.orchestration.node_protocol import NodeResult, RecipientOutcome
from app.services.orchestration.node_registry import register_node
from app.services.orchestration.predicate_contract import (
    evaluate as evaluate_predicate,
    parse as parse_predicate,
)

_DEFAULT_OUTPUT_ID = "default"


class _Branch(BaseModel):
    model_config = strict_node_config_dict()

    id: str
    label: str
    predicate: dict[str, Any]

    @model_validator(mode="after")
    def _validate_predicate(self) -> "_Branch":
        parse_predicate(self.predicate)
        return self


class _Config(BaseModel):
    model_config = strict_node_config_dict()

    branches: list[_Branch] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_branch_ids(self, info: ValidationInfo) -> "_Config":
        ids = [b.id for b in self.branches]
        if len(set(ids)) != len(ids):
            raise ValueError(f"conditional branch ids must be unique: {ids}")
        if _DEFAULT_OUTPUT_ID in ids:
            raise ValueError(f"branch id {_DEFAULT_OUTPUT_ID!r} is reserved for the implicit default output")
        return self


def output_edges_for_config(config: _Config) -> list[str]:
    """Dynamic output-edge ids: each branch id, then the implicit default."""
    return [b.id for b in config.branches] + [_DEFAULT_OUTPUT_ID]


@register_node(workflow_type="*", node_type="logic.conditional")
class _Handler:
    node_type = "logic.conditional"
    config_schema = _Config
    output_edges: list[str] = []  # populated dynamically per config
    category = "logic"

    async def execute(self, input_cohort, config: _Config, ctx) -> NodeResult:
        buckets: dict[str, list[RecipientOutcome]] = {b.id: [] for b in config.branches}
        buckets[_DEFAULT_OUTPUT_ID] = []
        async for rid, payload in input_cohort:
            target = _DEFAULT_OUTPUT_ID
            for branch in config.branches:
                if evaluate_predicate(branch.predicate, payload):
                    target = branch.id
                    break
            buckets[target].append(RecipientOutcome(recipient_id=rid))
        return NodeResult(
            by_output_id=buckets,
            summary={f"{bid}_count": len(outs) for bid, outs in buckets.items()},
        )

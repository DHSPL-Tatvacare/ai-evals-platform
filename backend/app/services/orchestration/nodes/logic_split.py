"""logic.split — N-way split by field value (deterministic) or by random weights (A/B)."""
from __future__ import annotations

import hashlib
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.services.orchestration.node_protocol import NodeResult, RecipientOutcome
from app.services.orchestration.node_registry import register_node


class _Branch(BaseModel):
    label: str
    match: Optional[str] = None  # for mode='by_field'
    weight: Optional[int] = None  # for mode='random'


class _Config(BaseModel):
    mode: Literal["by_field", "random"]
    field: Optional[str] = None
    branches: list[_Branch] = Field(min_length=2)
    default_branch: Optional[str] = None


@register_node(workflow_type="*", node_type="logic.split")
class _Handler:
    node_type = "logic.split"
    config_schema = _Config
    output_edges: list[str] = []  # populated dynamically per config
    category = "logic"

    async def execute(self, input_cohort, config: _Config, ctx) -> NodeResult:
        buckets: dict[str, list[RecipientOutcome]] = {b.label: [] for b in config.branches}
        if config.mode == "by_field":
            assert config.field, "field required when mode='by_field'"
            match_to_label = {b.match: b.label for b in config.branches if b.match is not None}
            async for rid, payload in input_cohort:
                v = payload.get(config.field)
                label = match_to_label.get(v) if v is not None else None
                if label is None:
                    label = config.default_branch
                if label is None:
                    continue
                buckets[label].append(RecipientOutcome(recipient_id=rid))
        else:  # random
            total_weight = sum(b.weight or 0 for b in config.branches)
            assert total_weight > 0, "branches must have positive weight in random mode"
            async for rid, _payload in input_cohort:
                # Deterministic per (run_id, recipient_id) — retries land in the same bucket.
                seed = hashlib.sha256(f"{ctx.run_id}|{rid}".encode()).digest()
                bucket = int.from_bytes(seed[:4], "big") % total_weight
                acc = 0
                for b in config.branches:
                    acc += (b.weight or 0)
                    if bucket < acc:
                        buckets[b.label].append(RecipientOutcome(recipient_id=rid))
                        break

        return NodeResult(
            by_edge_label=buckets,
            summary={f"{lbl}_count": len(outs) for lbl, outs in buckets.items()},
        )

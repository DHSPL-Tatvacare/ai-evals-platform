"""logic.split — N-way split into disjoint branches."""
from __future__ import annotations

import hashlib
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, ValidationInfo, model_validator

from app.services.orchestration._config_strictness import strict_node_config_dict
from app.services.orchestration.node_protocol import NodeResult, RecipientOutcome
from app.services.orchestration.node_registry import register_node

# Reserved edge id for holdout/control recipients.
CONTROL_EDGE_ID = "control"


class _Branch(BaseModel):
    model_config = strict_node_config_dict()
    """One branch on a split.

    ``id`` is the stable routing key — matches the source edge's
    ``output_id``. ``label`` is display-only and may change freely.
    ``match`` is used by ``mode='by_field'``; ``weight`` by ``mode='random'``;
    ``percent`` by ``mode='percentage'``.

    Legacy back-compat: a branch dict supplied with only ``label`` (no
    ``id``) gets ``id`` defaulted to ``label``.
    """
    id: str
    label: str
    match: Optional[str] = None
    weight: Optional[int] = None
    percent: Optional[int] = None

    @model_validator(mode="before")
    @classmethod
    def _default_id_to_label(cls, raw: Any) -> Any:
        if not isinstance(raw, dict):
            return raw
        if not raw.get("id") and raw.get("label"):
            raw = {**raw, "id": raw["label"]}
        return raw


class _Config(BaseModel):
    model_config = strict_node_config_dict()

    mode: Literal["by_field", "random", "percentage"]
    field: Optional[str] = None
    branches: list[_Branch] = Field(min_length=2)
    default_branch_id: Optional[str] = None
    drop_unmatched: bool = False
    # percentage mode: optional holdout routed to the reserved 'control' edge.
    holdout_percent: Optional[int] = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_legacy_default(cls, raw: Any) -> Any:
        """Lift legacy ``default_branch`` (a label) to ``default_branch_id``."""
        if not isinstance(raw, dict):
            return raw
        if "default_branch" in raw and "default_branch_id" not in raw:
            label = raw.pop("default_branch")
            for b in raw.get("branches") or []:
                if isinstance(b, dict) and (b.get("label") == label or b.get("id") == label):
                    raw["default_branch_id"] = b.get("id") or b.get("label")
                    break
            else:
                raw["default_branch_id"] = label
        return raw

    @model_validator(mode="after")
    def _check_config(self, info: ValidationInfo) -> "_Config":
        is_draft = bool(info.context and info.context.get("mode") == "draft")
        ids = [b.id for b in self.branches]

        if len(set(ids)) != len(ids):
            raise ValueError(f"split branch ids must be unique: {ids}")

        # 'control' is only reserved in percentage mode (it's the holdout output edge).
        if self.mode == "percentage" and CONTROL_EDGE_ID in ids:
            raise ValueError(
                f"branch id {CONTROL_EDGE_ID!r} is reserved for the holdout edge"
            )

        if self.default_branch_id is not None and self.default_branch_id not in ids:
            raise ValueError(
                f"default_branch_id={self.default_branch_id!r} not present in branches {ids}"
            )

        if self.mode == "by_field":
            return self._check_by_field(is_draft)
        if self.mode == "random":
            return self._check_random(is_draft)
        if self.mode == "percentage":
            return self._check_percentage(is_draft)
        return self

    def _check_by_field(self, is_draft: bool) -> "_Config":
        if not is_draft and not self.field:
            raise ValueError("'field' required when mode='by_field'")
        if not is_draft and any(not (b.match or "").strip() for b in self.branches):
            raise ValueError("branches in by_field mode must declare non-empty 'match' values")
        if any(b.weight is not None for b in self.branches):
            raise ValueError("branches in by_field mode must not carry random 'weight' values")
        if any(b.percent is not None for b in self.branches):
            raise ValueError("branches in by_field mode must not carry 'percent' values")
        if self.holdout_percent is not None:
            raise ValueError("'holdout_percent' is not allowed when mode='by_field'")
        return self

    def _check_random(self, is_draft: bool) -> "_Config":
        if self.field is not None:
            raise ValueError("'field' is not allowed when mode='random'")
        if self.default_branch_id is not None:
            raise ValueError("'default_branch_id' is not allowed when mode='random'")
        if self.drop_unmatched:
            raise ValueError("'drop_unmatched' is not allowed when mode='random'")
        if any(b.match is not None for b in self.branches):
            raise ValueError("branches in random mode must not carry by_field 'match' values")
        if any(b.percent is not None for b in self.branches):
            raise ValueError("branches in random mode must not carry 'percent' values")
        if self.holdout_percent is not None:
            raise ValueError("'holdout_percent' is not allowed when mode='random'")
        if not is_draft and any((b.weight or 0) <= 0 for b in self.branches):
            raise ValueError("branches in random mode must have positive weight on every branch")
        if not is_draft:
            total = sum(b.weight or 0 for b in self.branches)
            if total <= 0:
                raise ValueError("branches must have positive weight in random mode")
        return self

    def _check_percentage(self, is_draft: bool) -> "_Config":
        if self.field is not None:
            raise ValueError("'field' is not allowed when mode='percentage'")
        if self.default_branch_id is not None:
            raise ValueError("'default_branch_id' is not allowed when mode='percentage'")
        if self.drop_unmatched:
            raise ValueError("'drop_unmatched' is not allowed when mode='percentage'")
        if any(b.match is not None for b in self.branches):
            raise ValueError("branches in percentage mode must not carry 'match' values")
        if any(b.weight is not None for b in self.branches):
            raise ValueError("branches in percentage mode must not carry 'weight' values")
        if not is_draft:
            branch_total = sum((b.percent or 0) for b in self.branches)
            holdout = self.holdout_percent or 0
            total = branch_total + holdout
            if total != 100:
                raise ValueError(
                    f"branch percentages plus holdout must sum to 100, got {total}"
                )
        return self


@register_node(workflow_type="*", node_type="logic.split")
class _Handler:
    node_type = "logic.split"
    config_schema = _Config
    output_edges: list[str] = []  # populated dynamically per config
    category = "logic"

    async def execute(self, input_cohort, config: _Config, ctx) -> NodeResult:
        if config.mode == "by_field":
            return await self._execute_by_field(input_cohort, config)
        if config.mode == "random":
            return await self._execute_random(input_cohort, config, ctx)
        return await self._execute_percentage(input_cohort, config, ctx)

    async def _execute_by_field(self, input_cohort, config: _Config) -> NodeResult:
        buckets: dict[str, list[RecipientOutcome]] = {b.id: [] for b in config.branches}
        assert config.field, "field required when mode='by_field'"
        match_to_id = {b.match: b.id for b in config.branches if b.match is not None}
        async for rid, payload in input_cohort:
            v = payload.get(config.field)
            branch_id = match_to_id.get(v) if v is not None else None
            if branch_id is None:
                if config.drop_unmatched:
                    continue
                branch_id = config.default_branch_id
            if branch_id is None:
                continue
            buckets[branch_id].append(RecipientOutcome(recipient_id=rid))
        return NodeResult(
            by_output_id=buckets,
            summary={f"{bid}_count": len(outs) for bid, outs in buckets.items()},
        )

    async def _execute_random(self, input_cohort, config: _Config, ctx) -> NodeResult:
        buckets: dict[str, list[RecipientOutcome]] = {b.id: [] for b in config.branches}
        total_weight = sum(b.weight or 0 for b in config.branches)
        async for rid, _payload in input_cohort:
            seed = hashlib.sha256(f"{ctx.run_id}|{rid}".encode()).digest()
            bucket = int.from_bytes(seed[:4], "big") % total_weight
            acc = 0
            for b in config.branches:
                acc += (b.weight or 0)
                if bucket < acc:
                    buckets[b.id].append(RecipientOutcome(recipient_id=rid))
                    break
        return NodeResult(
            by_output_id=buckets,
            summary={f"{bid}_count": len(outs) for bid, outs in buckets.items()},
        )

    async def _execute_percentage(self, input_cohort, config: _Config, ctx) -> NodeResult:
        # Build the full slot list: named branches + optional control holdout.
        buckets: dict[str, list[RecipientOutcome]] = {b.id: [] for b in config.branches}
        if config.holdout_percent:
            buckets[CONTROL_EDGE_ID] = []

        # Build cumulative ranges over [0, 100).
        # Order: holdout first (so control recipients are deterministically
        # in the lowest bucket range), then branches in declaration order.
        slots: list[tuple[str, int]] = []  # (edge_id, cumulative_upper_exclusive)
        acc = 0
        if config.holdout_percent:
            acc += config.holdout_percent
            slots.append((CONTROL_EDGE_ID, acc))
        for b in config.branches:
            acc += (b.percent or 0)
            slots.append((b.id, acc))

        async for rid, _payload in input_cohort:
            seed = hashlib.sha256(f"{ctx.run_id}|{rid}".encode()).digest()
            # Map to [0, 100) bucket.
            pos = int.from_bytes(seed[:4], "big") % 100
            for edge_id, upper in slots:
                if pos < upper:
                    buckets[edge_id].append(RecipientOutcome(recipient_id=rid))
                    break

        return NodeResult(
            by_output_id=buckets,
            summary={f"{bid}_count": len(outs) for bid, outs in buckets.items()},
        )

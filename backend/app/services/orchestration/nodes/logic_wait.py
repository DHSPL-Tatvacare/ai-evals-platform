"""logic.wait — suspends recipients for a duration. Resume poller wakes them (Phase 4)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel, model_validator

from app.services.orchestration.node_protocol import NodeResult
from app.services.orchestration.node_registry import register_node


class _Config(BaseModel):
    duration_hours: Optional[float] = None
    until_datetime: Optional[datetime] = None  # alternative — wake at exact UTC datetime

    @model_validator(mode="after")
    def _exactly_one(self) -> "_Config":
        if (self.duration_hours is None) == (self.until_datetime is None):
            raise ValueError("exactly one of duration_hours or until_datetime must be set")
        return self


@register_node(workflow_type="*", node_type="logic.wait")
class _Handler:
    node_type = "logic.wait"
    config_schema = _Config
    output_edges = ["wakeup"]
    category = "logic"

    async def execute(self, input_cohort, config: _Config, ctx) -> NodeResult:
        if config.duration_hours is not None:
            wakeup_at = datetime.now(timezone.utc) + timedelta(hours=config.duration_hours)
        else:
            assert config.until_datetime is not None
            wakeup_at = config.until_datetime
            if wakeup_at.tzinfo is None:
                wakeup_at = wakeup_at.replace(tzinfo=timezone.utc)

        count = 0
        async for rid, _ in input_cohort:
            await ctx.set_recipient_state(rid, status="waiting", wakeup_at=wakeup_at)
            count += 1
        return NodeResult(suspended=True, summary={"suspended_count": count, "wakeup_at": wakeup_at.isoformat()})

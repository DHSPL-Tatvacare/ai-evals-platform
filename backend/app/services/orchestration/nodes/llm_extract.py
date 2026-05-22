"""llm.extract — scaffold placeholder. Replaced by Track T1 via TDD."""
from __future__ import annotations

from pydantic import BaseModel

from app.services.orchestration._config_strictness import strict_node_config_dict
from app.services.orchestration.node_protocol import NodeResult
from app.services.orchestration.node_registry import register_node


class _Config(BaseModel):
    model_config = strict_node_config_dict()


@register_node(workflow_type="*", node_type="llm.extract")
class _Handler:
    node_type = "llm.extract"
    config_schema = _Config
    output_edges = ["success", "error"]
    category = "mutation"

    async def execute(self, input_cohort, config: _Config, ctx) -> NodeResult:
        raise NotImplementedError("llm.extract scaffold placeholder — implemented in Track T1")

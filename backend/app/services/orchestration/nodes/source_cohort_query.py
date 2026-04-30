"""source.cohort_query — entry node. Materializes the entry cohort via one CTE."""
from __future__ import annotations

from sqlalchemy import text, update

from app.models.orchestration import WorkflowRun
from app.services.orchestration.node_protocol import NodeResult
from app.services.orchestration.node_registry import register_node
from app.services.orchestration.nodes._cohort_query_compiler import (
    CohortQueryConfig as _CompilerConfig,
    compile_cohort_query,
)


class _Config(_CompilerConfig):
    """Adds next_node_id — the target node recipients flow to after this entry node."""
    next_node_id: str


@register_node(workflow_type="*", node_type="source.cohort_query")
class _Handler:
    node_type = "source.cohort_query"
    config_schema = _Config
    output_edges = ["default"]
    category = "source"

    async def execute(self, input_cohort, config: _Config, ctx) -> NodeResult:
        sql, params = compile_cohort_query(
            config,
            run_id=ctx.run_id,
            workflow_id=ctx.workflow_id,
            workflow_version_id=ctx.workflow_version_id,
            tenant_id=ctx.tenant_id,
            app_id=ctx.app_id,
            next_node_id=config.next_node_id,
        )
        result = await ctx.db.execute(text(sql), params)
        rows = result.all()
        cohort_size = len(rows)
        await ctx.db.execute(
            update(WorkflowRun)
            .where(WorkflowRun.id == ctx.run_id)
            .values(cohort_size_at_entry=cohort_size)
        )
        await ctx.db.flush()
        return NodeResult(summary={"cohort_size": cohort_size})

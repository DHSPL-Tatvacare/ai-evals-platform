"""source.dataset — entry node bound to a specific cohort_dataset_versions row.

Snapshot semantics (D2/D8): the dataset version pins the recipient set, so
re-running the same workflow against the same dataset version produces an
identical recipient list. Delegates to the shared ``_cohort_query_compiler``
dataset branch.
"""
from __future__ import annotations

import uuid

from typing import Literal, Optional

from pydantic import BaseModel, Field
from sqlalchemy import select, text

from app.models.orchestration import WorkflowRun, WorkflowRunRecipientState
from app.services.orchestration._config_strictness import strict_node_config_dict
from app.services.orchestration.node_protocol import NodeResult
from app.services.orchestration.node_registry import register_node
from app.services.orchestration.nodes._cohort_query_compiler import (
    CohortQueryConfig,
    compile_cohort_query,
)
from app.services.orchestration.recipient_freezer import register_run_recipients
from app.services.orchestration.source_catalog import (
    DatasetSource,
    SourceCatalogError,
    _DATASET_PREFIX,
    resolve_source,
)


def _extract_phone(payload) -> str | None:
    if not payload:
        return None
    return payload.get("contact") or payload.get("phone")


class SourceDatasetConfig(BaseModel):
    model_config = strict_node_config_dict()
    dataset_version_id: uuid.UUID
    sample_limit: Optional[int] = Field(default=None, ge=1, le=10000)
    sample_strategy: Literal["random", "first"] = "random"


_Config = SourceDatasetConfig


class DatasetVersionNotFound(Exception):
    """Raised when the pinned dataset_version_id is missing or not owned
    by the running tenant."""


@register_node(workflow_type="*", node_type="source.dataset")
class _Handler:
    node_type = "source.dataset"
    config_schema = SourceDatasetConfig
    output_edges = ["default"]
    category = "source"

    async def execute(
        self,
        input_cohort,
        config: SourceDatasetConfig,
        ctx,
    ) -> NodeResult:
        next_node_id = ctx.resolve_default_target()

        source_ref = f"{_DATASET_PREFIX}{config.dataset_version_id}"
        try:
            resolved = await resolve_source(
                source_ref, db=ctx.db, tenant_id=ctx.tenant_id,
            )
        except SourceCatalogError as exc:
            raise DatasetVersionNotFound(str(exc)) from exc
        if not isinstance(resolved, DatasetSource):
            raise DatasetVersionNotFound(
                f"dataset_version_id {config.dataset_version_id} did not resolve "
                f"to a dataset source"
            )

        query_config = CohortQueryConfig(source_ref=source_ref)

        sql, params = compile_cohort_query(
            query_config,
            run_id=ctx.run_id,
            workflow_id=ctx.workflow_id,
            workflow_version_id=ctx.workflow_version_id,
            tenant_id=ctx.tenant_id,
            app_id=ctx.app_id,
            next_node_id=next_node_id,
            resolved_source=resolved,
        )
        result = await ctx.db.execute(text(sql), params)
        cohort_size = len(result.all())

        provenance = {"enrolled_dataset_version_id": str(config.dataset_version_id)}
        await ctx.db.execute(
            text(
                "UPDATE orchestration.workflow_runs "
                "SET params = COALESCE(params, '{}'::jsonb) || "
                "    jsonb_build_object('enrolled_dataset_version_id', (:vid)::text), "
                "    cohort_size_at_entry = (:size)::int "
                "WHERE id = (:run_id)::uuid"
            ),
            {
                "vid": str(config.dataset_version_id),
                "size": cohort_size,
                "run_id": ctx.run_id,
            },
        )

        # Register membership into the single choke table so dispatch nodes'
        # manifest guard passes for dataset recipients.
        run_row = (
            await ctx.db.execute(
                select(WorkflowRun).where(WorkflowRun.id == ctx.run_id)
            )
        ).scalar_one()
        state_rows = (
            await ctx.db.execute(
                select(
                    WorkflowRunRecipientState.recipient_id,
                    WorkflowRunRecipientState.payload,
                ).where(WorkflowRunRecipientState.run_id == ctx.run_id)
            )
        ).all()
        receipt = await register_run_recipients(
            ctx.db,
            run=run_row,
            ingress_kind="dataset",
            resolved_rows=[
                (row.recipient_id, _extract_phone(row.payload)) for row in state_rows
            ],
            provenance=provenance,
        )
        await ctx.db.flush()
        return NodeResult(
            summary={"cohort_size": cohort_size, "registered": receipt.registered_count}
        )

"""source.cohort — entry node that materializes a recipient set in inline or saved mode."""
from __future__ import annotations

import json
import uuid
from typing import Literal, Optional

from pydantic import BaseModel, Field, ValidationInfo, model_validator
from sqlalchemy import select, text

from app.models.orchestration import (
    CohortDefinitionVersion,
    WorkflowRun,
    WorkflowRunRecipientState,
)
from app.services.orchestration._config_strictness import strict_node_config_dict
from app.services.orchestration.node_protocol import NodeResult
from app.services.orchestration.node_registry import register_node
from app.services.orchestration.nodes._cohort_query_compiler import (
    CohortQueryConfig,
    CohortQueryFilter,
    compile_cohort_query,
)
from app.services.orchestration.recipient_freezer import freeze_recipients
from app.services.orchestration.run_preview import run_cap_preview
from app.services.orchestration.source_catalog import (
    ResolvedSource,
    SourceCatalogError,
    resolve_source,
)


CohortMode = Literal["inline", "saved"]


class SourceCohortConfig(BaseModel):
    """Flat union — only the fields valid for the chosen ``mode`` are required.

    The ``model_validator`` enforces shape per mode so authoring tools surface
    clear errors. Draft defers the cross-field completeness checks (the bare
    ``mode`` may be absent in a half-authored node).
    """
    model_config = strict_node_config_dict()

    mode: Optional[CohortMode] = None

    # saved selector
    cohort_definition_version_id: Optional[uuid.UUID] = None

    # inline selector
    source_ref: Optional[str] = None
    payload_fields: list[str] = Field(default_factory=list)
    filters: list[CohortQueryFilter] = Field(default_factory=list)
    lookback_hours: Optional[int] = None
    lookback_column: Optional[str] = None
    consent_gate_channel: Optional[str] = None

    @model_validator(mode="after")
    def _check_mode_fields(self, info: ValidationInfo) -> "SourceCohortConfig":
        if info.context and info.context.get("mode") == "draft":
            return self
        if self.mode is None:
            raise ValueError("source.cohort config requires 'mode' ('inline' or 'saved')")
        if self.mode == "saved":
            if self.cohort_definition_version_id is None:
                raise ValueError(
                    "'cohort_definition_version_id' required when mode='saved'"
                )
        elif self.mode == "inline":
            if not self.source_ref:
                raise ValueError("'source_ref' required when mode='inline'")
        return self


_Config = SourceCohortConfig


class CohortSourceNotFound(Exception):
    """Raised when the pinned cohort version or inline source is missing or
    not owned by the running tenant. Bubbles up as a structured run failure."""


async def _load_version(ctx, version_id: uuid.UUID) -> CohortDefinitionVersion:
    stmt = select(CohortDefinitionVersion).where(
        CohortDefinitionVersion.id == version_id,
        CohortDefinitionVersion.tenant_id == ctx.tenant_id,
    )
    result = await ctx.db.execute(stmt)
    version = result.scalar_one_or_none()
    if version is None:
        raise CohortSourceNotFound(
            f"cohort_definition_version not found or not owned by tenant: {version_id}"
        )
    return version


def _query_config_from_version(version: CohortDefinitionVersion) -> CohortQueryConfig:
    # The saved version row is the canonical source of truth for the
    # predicate; rebuild the transient config from it, not from any cached
    # copy on the node.
    return CohortQueryConfig(
        source_ref=version.source_ref,
        payload_fields=list(version.payload_fields or []),
        filters=list(version.filters or []),
        lookback_hours=version.lookback_hours,
        lookback_column=version.lookback_column,
        consent_gate_channel=version.consent_gate_channel,
    )


def _query_config_from_inline(config: SourceCohortConfig) -> CohortQueryConfig:
    return CohortQueryConfig(
        source_ref=config.source_ref,
        payload_fields=list(config.payload_fields),
        filters=list(config.filters),
        lookback_hours=config.lookback_hours,
        lookback_column=config.lookback_column,
        consent_gate_channel=config.consent_gate_channel,
    )


async def _materialize_cohort(
    ctx,
    *,
    query_config: CohortQueryConfig,
    source_ref: str,
    cohort_version: Optional[CohortDefinitionVersion],
    provenance: dict[str, str],
) -> NodeResult:
    """Shared tail: resolve → compile → insert → stamp → freeze → cap preview.

    ``cohort_version`` is passed to the freezer for saved mode and is None for
    inline mode (the freezer hashes the resolved query shape instead).
    ``provenance`` is merged into ``workflow_runs.params`` so logs and
    reporting can join back to the cohort that produced this recipient set.
    """
    next_node_id = ctx.resolve_default_target()

    try:
        resolved: ResolvedSource = await resolve_source(
            source_ref, db=ctx.db, tenant_id=ctx.tenant_id,
        )
    except SourceCatalogError as exc:
        raise CohortSourceNotFound(str(exc)) from exc

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

    await ctx.db.execute(
        text(
            "UPDATE orchestration.workflow_runs "
            "SET params = COALESCE(params, '{}'::jsonb) || (:provenance)::jsonb, "
            "    cohort_size_at_entry = :size "
            "WHERE id = :run_id"
        ),
        {
            "provenance": json.dumps(provenance),
            "size": cohort_size,
            "run_id": ctx.run_id,
        },
    )

    # Freeze the (recipient_id, phone) manifest from the just-written rows in
    # the same transaction so the snapshot is immune to source mutations after T0.
    run_row = (
        await ctx.db.execute(select(WorkflowRun).where(WorkflowRun.id == ctx.run_id))
    ).scalar_one()
    state_rows = (
        await ctx.db.execute(
            select(
                WorkflowRunRecipientState.recipient_id,
                WorkflowRunRecipientState.payload,
            ).where(WorkflowRunRecipientState.run_id == ctx.run_id)
        )
    ).all()
    resolved_rows = [
        (row.recipient_id, _extract_phone(row.payload)) for row in state_rows
    ]
    freeze_receipt = await freeze_recipients(
        ctx.db,
        run=run_row,
        cohort_version=cohort_version,
        resolved_rows=resolved_rows,
        inline_predicate=query_config.model_dump(mode="json") if cohort_version is None else None,
    )

    # T0 cap preview: walk the frozen manifest and pre-flip any recipient
    # already over the active (tenant, app) comm cap.
    capped_count = await run_cap_preview(ctx.db, run=run_row)
    await ctx.db.execute(
        text(
            "UPDATE orchestration.workflow_runs "
            "SET params = COALESCE(params, '{}'::jsonb) || "
            "    jsonb_build_object('preview', jsonb_build_object("
            "        'cappedCount', (:capped)::int, "
            "        'invalidPhoneCount', (:invalid)::int)) "
            "WHERE id = (:run_id)::uuid"
        ),
        {
            "capped": capped_count,
            "invalid": freeze_receipt.invalid_phone_count,
            "run_id": ctx.run_id,
        },
    )

    await ctx.db.flush()
    return NodeResult(
        summary={
            "cohort_size": cohort_size,
            "frozen": freeze_receipt.frozen_count,
            "invalid_phone": freeze_receipt.invalid_phone_count,
            "capped": capped_count,
        }
    )


@register_node(workflow_type="*", node_type="source.cohort")
class _Handler:
    node_type = "source.cohort"
    config_schema = SourceCohortConfig
    output_edges = ["default"]
    category = "source"

    async def execute(self, input_cohort, config: SourceCohortConfig, ctx) -> NodeResult:
        if config.mode == "saved":
            assert config.cohort_definition_version_id is not None
            version = await _load_version(ctx, config.cohort_definition_version_id)
            return await _materialize_cohort(
                ctx,
                query_config=_query_config_from_version(version),
                source_ref=version.source_ref,
                cohort_version=version,
                provenance={
                    "enrolled_cohort_definition_version_id": str(version.id),
                },
            )

        assert config.source_ref is not None
        return await _materialize_cohort(
            ctx,
            query_config=_query_config_from_inline(config),
            source_ref=config.source_ref,
            cohort_version=None,
            provenance={"enrolled_source_ref": config.source_ref},
        )


def _extract_phone(payload) -> str | None:
    if not payload:
        return None
    return payload.get("contact") or payload.get("phone")

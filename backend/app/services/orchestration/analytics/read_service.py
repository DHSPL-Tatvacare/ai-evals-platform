"""Provider-agnostic read queries over the orchestration tall-fact.

Every query joins ``WorkflowRunRecipientAction`` → ``WorkflowRun`` → ``Workflow``
so the caller's scope clause (over ``Workflow``) and the tenant/app/date window
gate the same rows for overview, breakdowns, runs, and run detail. Buckets are
the Phase 0 ``outcome_bucket`` values; spend sums ``response->>'total_cost'``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Numeric, String, case, distinct, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orchestration import (
    Workflow,
    WorkflowRun,
    WorkflowRunNodeStep,
    WorkflowRunRecipientAction,
    WorkflowVersion,
)
from app.models.provider_connection import ProviderConnection
from app.services.orchestration.analytics.outcomes import EngagementBucket


def WORKFLOW_TENANT_ALL(tenant_id):
    """Scope clause covering every workflow in a tenant (tests/admin tenant scope)."""
    return Workflow.tenant_id == tenant_id


_COST_EXPR = func.coalesce(
    func.sum(
        func.cast(WorkflowRunRecipientAction.response["total_cost"].astext, Numeric)
    ),
    0,
)


def _bucket_count(bucket: EngagementBucket):
    return func.coalesce(
        func.sum(
            case((WorkflowRunRecipientAction.outcome_bucket == bucket.value, 1), else_=0)
        ),
        0,
    )


def _base_join(stmt):
    return (
        stmt.select_from(WorkflowRunRecipientAction)
        .join(WorkflowRun, WorkflowRunRecipientAction.run_id == WorkflowRun.id)
        .join(Workflow, WorkflowRun.workflow_id == Workflow.id)
    )


def _scope_filters(stmt, *, tenant_id, app_id, scope_clause, date_from, date_to):
    stmt = stmt.where(
        WorkflowRunRecipientAction.tenant_id == tenant_id,
        WorkflowRunRecipientAction.app_id == app_id,
        scope_clause,
    )
    if date_from is not None:
        stmt = stmt.where(WorkflowRun.started_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(WorkflowRun.started_at <= date_to)
    return stmt


@dataclass
class OverviewResult:
    campaigns: int
    runs: int
    recipients: int
    unique_contacts: int
    positive: int
    reached: int
    no_response: int
    failed: int
    in_flight: int
    spend: float
    in_flight_runs: int


async def overview(
    db: AsyncSession,
    *,
    tenant_id,
    app_id: str,
    scope_clause,
    date_from: Optional[datetime],
    date_to: Optional[datetime],
) -> OverviewResult:
    """KPI rollup across the scoped, date-windowed action fact."""
    recipient_pair = func.count(
        distinct(
            tuple_(
                WorkflowRunRecipientAction.run_id,
                WorkflowRunRecipientAction.recipient_id,
            )
        )
    )
    stmt = select(
        func.count(distinct(WorkflowRunRecipientAction.workflow_id)),
        func.count(distinct(WorkflowRunRecipientAction.run_id)),
        recipient_pair,
        func.count(distinct(WorkflowRunRecipientAction.contact_phone_e164)),
        _bucket_count(EngagementBucket.positive),
        _bucket_count(EngagementBucket.reached),
        _bucket_count(EngagementBucket.no_response),
        _bucket_count(EngagementBucket.failed),
        _bucket_count(EngagementBucket.in_flight),
        _COST_EXPR,
    )
    stmt = _base_join(stmt)
    stmt = _scope_filters(
        stmt, tenant_id=tenant_id, app_id=app_id, scope_clause=scope_clause,
        date_from=date_from, date_to=date_to,
    )
    row = (await db.execute(stmt)).one()

    in_flight_stmt = select(
        func.count(distinct(WorkflowRun.id))
    )
    in_flight_stmt = _base_join(in_flight_stmt)
    in_flight_stmt = _scope_filters(
        in_flight_stmt, tenant_id=tenant_id, app_id=app_id,
        scope_clause=scope_clause, date_from=date_from, date_to=date_to,
    ).where(WorkflowRun.status.in_(("running", "waiting", "pending")))
    in_flight_runs = (await db.execute(in_flight_stmt)).scalar() or 0

    return OverviewResult(
        campaigns=int(row[0] or 0),
        runs=int(row[1] or 0),
        recipients=int(row[2] or 0),
        unique_contacts=int(row[3] or 0),
        positive=int(row[4] or 0),
        reached=int(row[5] or 0),
        no_response=int(row[6] or 0),
        failed=int(row[7] or 0),
        in_flight=int(row[8] or 0),
        spend=float(row[9] or 0),
        in_flight_runs=int(in_flight_runs),
    )

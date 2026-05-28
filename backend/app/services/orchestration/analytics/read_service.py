"""Provider-agnostic read queries over the orchestration tall-fact.

Every query joins ``WorkflowRunRecipientAction`` → ``WorkflowRun`` → ``Workflow``
so the caller's scope clause (over ``Workflow``) and the tenant/app/date window
gate the same rows for overview, breakdowns, runs, and run detail. Buckets are
the Phase 0 ``outcome_bucket`` values; spend sums ``response->>'total_cost'``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Numeric, case, distinct, func, select, tuple_
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


# ── Breakdown ────────────────────────────────────────────────────────


@dataclass
class BreakdownRow:
    key: str
    label: str
    provider: Optional[str]
    recipients: int
    dispatched: int
    positive: int
    reached: int
    no_response: int
    failed: int
    in_flight: int
    cost: float


_DISPATCH_NODE_TYPES = ("voice.place_call", "messaging.send_whatsapp_template", "core.webhook_out")


def _bucket_columns():
    return [
        _bucket_count(EngagementBucket.positive),
        _bucket_count(EngagementBucket.reached),
        _bucket_count(EngagementBucket.no_response),
        _bucket_count(EngagementBucket.failed),
        _bucket_count(EngagementBucket.in_flight),
        _COST_EXPR,
    ]


def _recipient_count():
    return func.count(
        distinct(
            tuple_(
                WorkflowRunRecipientAction.run_id,
                WorkflowRunRecipientAction.recipient_id,
            )
        )
    )


def _dispatched_count():
    return func.count(WorkflowRunRecipientAction.id)


async def breakdown(
    db: AsyncSession,
    *,
    dimension: str,
    tenant_id,
    app_id: str,
    scope_clause,
    date_from: Optional[datetime],
    date_to: Optional[datetime],
) -> list[BreakdownRow]:
    """Per-dimension bucket/cost rollup. dimension in {campaign, channel, connection}."""
    if dimension == "connection":
        return await _connection_breakdown(
            db, tenant_id=tenant_id, app_id=app_id, scope_clause=scope_clause,
            date_from=date_from, date_to=date_to,
        )

    if dimension == "campaign":
        group_key, group_label = Workflow.id, Workflow.name
    elif dimension == "channel":
        group_key = group_label = WorkflowRunRecipientAction.channel
    else:
        raise ValueError(f"unknown breakdown dimension: {dimension}")

    stmt = select(
        group_key, group_label, _recipient_count(), _dispatched_count(), *_bucket_columns()
    )
    stmt = _base_join(stmt)
    stmt = _scope_filters(
        stmt, tenant_id=tenant_id, app_id=app_id, scope_clause=scope_clause,
        date_from=date_from, date_to=date_to,
    ).group_by(group_key, group_label)
    rows = (await db.execute(stmt)).all()
    return [
        BreakdownRow(
            key=str(r[0]), label=str(r[1]), provider=None,
            recipients=int(r[2] or 0), dispatched=int(r[3] or 0),
            positive=int(r[4] or 0), reached=int(r[5] or 0),
            no_response=int(r[6] or 0), failed=int(r[7] or 0),
            in_flight=int(r[8] or 0), cost=float(r[9] or 0),
        )
        for r in rows
    ]


def _extract_connection_ids(definition: dict[str, Any]) -> dict[str, str]:
    """Map node_id -> connection_id for dispatch nodes in a version definition."""
    out: dict[str, str] = {}
    for node in (definition or {}).get("nodes") or []:
        if node.get("type") not in _DISPATCH_NODE_TYPES:
            continue
        conn = (node.get("config") or {}).get("connection_id")
        if conn:
            out[str(node.get("id"))] = str(conn)
    return out


async def _connection_breakdown(
    db, *, tenant_id, app_id, scope_clause, date_from, date_to,
) -> list[BreakdownRow]:
    # 1. Aggregate actions by (version, node_id) — node_id is where connection_id lives.
    stmt = select(
        WorkflowRunRecipientAction.workflow_version_id,
        WorkflowRunNodeStep.node_id,
        _recipient_count(),
        _dispatched_count(),
        *_bucket_columns(),
    )
    stmt = stmt.select_from(WorkflowRunRecipientAction).join(
        WorkflowRunNodeStep,
        WorkflowRunRecipientAction.node_step_id == WorkflowRunNodeStep.id,
    ).join(
        WorkflowRun, WorkflowRunRecipientAction.run_id == WorkflowRun.id
    ).join(Workflow, WorkflowRun.workflow_id == Workflow.id)
    stmt = _scope_filters(
        stmt, tenant_id=tenant_id, app_id=app_id, scope_clause=scope_clause,
        date_from=date_from, date_to=date_to,
    ).group_by(
        WorkflowRunRecipientAction.workflow_version_id, WorkflowRunNodeStep.node_id
    )
    node_rows = (await db.execute(stmt)).all()
    if not node_rows:
        return []

    # 2. Resolve each (version, node_id) to its connection_id via the version definition.
    version_ids = {r[0] for r in node_rows}
    defs = (
        await db.execute(
            select(WorkflowVersion.id, WorkflowVersion.definition).where(
                WorkflowVersion.id.in_(version_ids)
            )
        )
    ).all()
    node_to_conn: dict[tuple, str] = {}
    for version_id, definition in defs:
        for node_id, conn_id in _extract_connection_ids(definition).items():
            node_to_conn[(version_id, node_id)] = conn_id

    # 3. Batch-load provider + name for the resolved connection ids.
    conn_ids = {v for v in node_to_conn.values()}
    conn_meta: dict[str, tuple[str, str]] = {}
    if conn_ids:
        conn_uuids = [_uuid_or_none(c) for c in conn_ids if _uuid_or_none(c)]
        if conn_uuids:
            for cid, provider, name in (
                await db.execute(
                    select(
                        ProviderConnection.id,
                        ProviderConnection.provider,
                        ProviderConnection.name,
                    ).where(ProviderConnection.id.in_(conn_uuids))
                )
            ).all():
                conn_meta[str(cid)] = (provider, name)

    # 4. Re-aggregate node rows by connection_id; unresolved nodes fold into "unmapped".
    acc: dict[str, list] = {}
    for r in node_rows:
        conn_id = node_to_conn.get((r[0], r[1]))
        key = conn_id or "unmapped"
        bucket = acc.setdefault(key, [0, 0, 0, 0, 0, 0, 0.0])
        bucket[0] += int(r[2] or 0)  # recipients
        bucket[1] += int(r[3] or 0)  # dispatched
        bucket[2] += int(r[4] or 0)  # positive
        bucket[3] += int(r[5] or 0)  # reached
        bucket[4] += int(r[6] or 0)  # no_response
        bucket[5] += int(r[7] or 0)  # failed
        bucket[6] += float(r[9] or 0)  # cost (r[8] is in_flight)

    out: list[BreakdownRow] = []
    for key, b in acc.items():
        provider, name = conn_meta.get(key, (None, None))
        out.append(BreakdownRow(
            key=key,
            label=name or ("Unmapped connection" if key == "unmapped" else key),
            provider=provider,
            recipients=b[0], dispatched=b[1], positive=b[2], reached=b[3],
            no_response=b[4], failed=b[5], in_flight=0, cost=b[6],
        ))
    return out


def _uuid_or_none(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


# ── Runs list ────────────────────────────────────────────────────────


@dataclass
class RunRow:
    run_id: Any
    workflow_id: Any
    workflow_name: str
    channel: Optional[str]
    triggered_by: str
    status: str
    cohort_size: int
    reached: int
    positive: int
    cost: float
    started_at: Optional[datetime]


@dataclass
class RunsResult:
    rows: list[RunRow]
    total: int
    page: int
    page_size: int


async def runs(
    db: AsyncSession,
    *,
    tenant_id,
    app_id: str,
    scope_clause,
    date_from: Optional[datetime],
    date_to: Optional[datetime],
    page: int = 1,
    page_size: int = 20,
) -> RunsResult:
    """Paginated run rows with reach/positive/cost rolled up from the action fact."""
    reached_expr = func.coalesce(
        func.sum(
            case(
                (
                    WorkflowRunRecipientAction.outcome_bucket.in_(
                        (EngagementBucket.positive.value, EngagementBucket.reached.value)
                    ),
                    1,
                ),
                else_=0,
            )
        ),
        0,
    )
    channel_expr = func.max(WorkflowRunRecipientAction.channel)

    base = (
        select(
            WorkflowRun.id,
            WorkflowRun.workflow_id,
            Workflow.name,
            channel_expr,
            WorkflowRun.triggered_by,
            WorkflowRun.status,
            WorkflowRun.cohort_size_at_entry,
            reached_expr,
            _bucket_count(EngagementBucket.positive),
            _COST_EXPR,
            WorkflowRun.started_at,
        )
        .select_from(WorkflowRun)
        .join(Workflow, WorkflowRun.workflow_id == Workflow.id)
        .join(
            WorkflowRunRecipientAction,
            WorkflowRunRecipientAction.run_id == WorkflowRun.id,
            isouter=True,
        )
        .where(
            WorkflowRun.tenant_id == tenant_id,
            WorkflowRun.app_id == app_id,
            scope_clause,
        )
        .group_by(WorkflowRun.id, Workflow.name)
        .order_by(WorkflowRun.started_at.desc().nullslast())
    )
    if date_from is not None:
        base = base.where(WorkflowRun.started_at >= date_from)
    if date_to is not None:
        base = base.where(WorkflowRun.started_at <= date_to)

    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    paged = base.limit(page_size).offset((page - 1) * page_size)
    rows = (await db.execute(paged)).all()
    return RunsResult(
        rows=[
            RunRow(
                run_id=r[0], workflow_id=r[1], workflow_name=str(r[2]),
                channel=r[3], triggered_by=r[4], status=r[5],
                cohort_size=int(r[6] or 0), reached=int(r[7] or 0),
                positive=int(r[8] or 0), cost=float(r[9] or 0), started_at=r[10],
            )
            for r in rows
        ],
        total=int(total),
        page=page,
        page_size=page_size,
    )


# ── Run detail ───────────────────────────────────────────────────────


@dataclass
class RunBuckets:
    positive: int
    reached: int
    no_response: int
    failed: int
    in_flight: int


@dataclass
class RunNodeStep:
    node_step_id: Any
    node_id: str
    node_type: str
    status: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]


@dataclass
class RunActionRow:
    action_id: Any
    recipient_id: str
    channel: str
    action_type: str
    status: str
    outcome_bucket: Optional[str]
    contact: Optional[str]
    cost: Optional[float]
    created_at: Optional[datetime]


@dataclass
class RunDetailResult:
    run_id: Any
    workflow_id: Any
    workflow_name: str
    status: str
    triggered_by: str
    cohort_size: int
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    buckets: RunBuckets
    spend: float
    node_steps: list[RunNodeStep]
    actions: list[RunActionRow]
    actions_total: int


async def run_detail(
    db: AsyncSession,
    *,
    run_id,
    tenant_id,
    scope_clause,
    page: int = 1,
    page_size: int = 50,
) -> Optional[RunDetailResult]:
    """Bucket rollup + node steps + paginated action log for one scoped run."""
    head_stmt = (
        select(
            WorkflowRun.id,
            WorkflowRun.workflow_id,
            Workflow.name,
            WorkflowRun.status,
            WorkflowRun.triggered_by,
            WorkflowRun.cohort_size_at_entry,
            WorkflowRun.started_at,
            WorkflowRun.completed_at,
        )
        .select_from(WorkflowRun)
        .join(Workflow, WorkflowRun.workflow_id == Workflow.id)
        .where(
            WorkflowRun.id == run_id,
            WorkflowRun.tenant_id == tenant_id,
            scope_clause,
        )
    )
    head = (await db.execute(head_stmt)).first()
    if head is None:
        return None

    bucket_stmt = (
        select(*_bucket_columns())
        .select_from(WorkflowRunRecipientAction)
        .where(
            WorkflowRunRecipientAction.run_id == run_id,
            WorkflowRunRecipientAction.tenant_id == tenant_id,
        )
    )
    b = (await db.execute(bucket_stmt)).one()

    steps = (
        await db.execute(
            select(WorkflowRunNodeStep)
            .where(
                WorkflowRunNodeStep.run_id == run_id,
                WorkflowRunNodeStep.tenant_id == tenant_id,
            )
            .order_by(WorkflowRunNodeStep.started_at.asc().nullslast())
        )
    ).scalars().all()

    actions_total = (
        await db.execute(
            select(func.count(WorkflowRunRecipientAction.id)).where(
                WorkflowRunRecipientAction.run_id == run_id,
                WorkflowRunRecipientAction.tenant_id == tenant_id,
            )
        )
    ).scalar() or 0

    action_rows = (
        await db.execute(
            select(WorkflowRunRecipientAction)
            .where(
                WorkflowRunRecipientAction.run_id == run_id,
                WorkflowRunRecipientAction.tenant_id == tenant_id,
            )
            .order_by(WorkflowRunRecipientAction.created_at.asc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
    ).scalars().all()

    def _action_cost(a):
        raw = (a.response or {}).get("total_cost") if a.response else None
        try:
            return float(raw) if raw is not None else None
        except (TypeError, ValueError):
            return None

    return RunDetailResult(
        run_id=head[0],
        workflow_id=head[1],
        workflow_name=str(head[2]),
        status=head[3],
        triggered_by=head[4],
        cohort_size=int(head[5] or 0),
        started_at=head[6],
        completed_at=head[7],
        buckets=RunBuckets(
            positive=int(b[0] or 0), reached=int(b[1] or 0),
            no_response=int(b[2] or 0), failed=int(b[3] or 0),
            in_flight=int(b[4] or 0),
        ),
        spend=float(b[5] or 0),
        node_steps=[
            RunNodeStep(
                node_step_id=s.id, node_id=s.node_id, node_type=s.node_type,
                status=s.status, started_at=s.started_at, completed_at=s.completed_at,
            )
            for s in steps
        ],
        actions=[
            RunActionRow(
                action_id=a.id, recipient_id=a.recipient_id, channel=a.channel,
                action_type=a.action_type, status=a.status,
                outcome_bucket=a.outcome_bucket, contact=(a.payload or {}).get("contact"),
                cost=_action_cost(a), created_at=a.created_at,
            )
            for a in action_rows
        ],
        actions_total=int(actions_total),
    )

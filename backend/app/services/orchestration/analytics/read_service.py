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

from sqlalchemy import Numeric, case, distinct, func, literal, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orchestration import (
    Workflow,
    WorkflowRun,
    WorkflowRunNodeStep,
    WorkflowRunRecipientAction,
    WorkflowRunRecipientState,
    WorkflowVersion,
)
from app.models.provider_connection import ProviderConnection
from app.services.orchestration.adapters import registered_adapter_instances
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


# Most-advanced wins: a recipient's representative bucket is the highest-ranked
# outcome across its rows so the five buckets partition recipients.
_BUCKET_RANK = {
    EngagementBucket.positive.value: 5,
    EngagementBucket.reached.value: 4,
    EngagementBucket.no_response.value: 3,
    EngagementBucket.failed.value: 2,
    EngagementBucket.in_flight.value: 1,
}
_RANK_TO_BUCKET = {rank: value for value, rank in _BUCKET_RANK.items()}


def _action_type_to_bucket_map() -> dict[str, str]:
    """Merged action_type -> bucket value, assembled from the adapter registry.

    Recovers pre-column child rows whose outcome_bucket is NULL by re-deriving the
    bucket from action_type — vendor maps live in the adapters, never inline here.
    """
    merged: dict[str, str] = {}
    for adapter in registered_adapter_instances():
        for action_type, bucket in getattr(adapter, "ACTION_OUTCOME_MAP", {}).items():
            merged[action_type] = bucket.value
    return merged


def _derived_bucket_expr():
    """outcome_bucket, falling back to the action_type-derived bucket when NULL."""
    mapping = _action_type_to_bucket_map()
    if not mapping:
        return WorkflowRunRecipientAction.outcome_bucket
    return func.coalesce(
        WorkflowRunRecipientAction.outcome_bucket,
        case(
            *[
                (WorkflowRunRecipientAction.action_type == k, literal(v))
                for k, v in mapping.items()
            ],
            else_=None,
        ),
    )


def _bucket_rank_expr():
    """Map a row's derived bucket to its rank; null buckets rank 0 (ignored)."""
    derived = _derived_bucket_expr()
    return case(
        *[
            (derived == value, literal(rank))
            for value, rank in _BUCKET_RANK.items()
        ],
        else_=literal(0),
    )


def _collapsed_bucket_count(rep_bucket_col, bucket: EngagementBucket):
    return func.coalesce(
        func.sum(case((rep_bucket_col == bucket.value, 1), else_=0)), 0
    )


def _collapsed_recipient_subquery(
    *, tenant_id, app_id, scope_clause, date_from, date_to, extra_group_cols=()
):
    """Per (run_id, recipient_id [, extra dims]) max-rank outcome bucket.

    Counts each recipient once by its most-advanced outcome so the five buckets
    partition recipients. Rows with a null outcome_bucket rank 0 and never win a
    terminal bucket; a recipient with only pending dispatch rows yields max_rank 0.
    """
    group_cols = [
        WorkflowRunRecipientAction.run_id,
        WorkflowRunRecipientAction.recipient_id,
        *extra_group_cols,
    ]
    stmt = select(
        *group_cols,
        func.max(_bucket_rank_expr()).label("max_rank"),
    )
    stmt = _base_join(stmt)
    stmt = _scope_filters(
        stmt, tenant_id=tenant_id, app_id=app_id, scope_clause=scope_clause,
        date_from=date_from, date_to=date_to,
    ).group_by(*group_cols)
    return stmt.subquery()


def _rep_bucket_from_rank(max_rank_col):
    """Translate a recipient's max rank back to its bucket value string."""
    return case(
        *[(max_rank_col == rank, literal(value)) for rank, value in _RANK_TO_BUCKET.items()],
        else_=literal(None),
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
        stmt = stmt.where(WorkflowRun.started_at < date_to)
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
    cohort_total: int


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
        _COST_EXPR,
    )
    stmt = _base_join(stmt)
    stmt = _scope_filters(
        stmt, tenant_id=tenant_id, app_id=app_id, scope_clause=scope_clause,
        date_from=date_from, date_to=date_to,
    )
    row = (await db.execute(stmt)).one()

    collapsed = _collapsed_recipient_subquery(
        tenant_id=tenant_id, app_id=app_id, scope_clause=scope_clause,
        date_from=date_from, date_to=date_to,
    )
    rep = _rep_bucket_from_rank(collapsed.c.max_rank)
    bucket_stmt = select(
        _collapsed_bucket_count(rep, EngagementBucket.positive),
        _collapsed_bucket_count(rep, EngagementBucket.reached),
        _collapsed_bucket_count(rep, EngagementBucket.no_response),
        _collapsed_bucket_count(rep, EngagementBucket.failed),
        _collapsed_bucket_count(rep, EngagementBucket.in_flight),
    ).select_from(collapsed)
    brow = (await db.execute(bucket_stmt)).one()

    # In-flight is a status snapshot, not a windowed metric: running/just-started
    # runs have started_at IS NULL and would drop out of any started_at predicate.
    in_flight_stmt = select(func.count(distinct(WorkflowRun.id)))
    in_flight_stmt = _base_join(in_flight_stmt).where(
        WorkflowRunRecipientAction.tenant_id == tenant_id,
        WorkflowRunRecipientAction.app_id == app_id,
        scope_clause,
        WorkflowRun.status.in_(("running", "waiting", "pending")),
    )
    in_flight_runs = (await db.execute(in_flight_stmt)).scalar() or 0

    # True cohort top of funnel: sum cohort_size_at_entry once per scoped+windowed
    # run, so opted-out / never-dispatched recipients (no action rows) stay visible.
    cohort_stmt = select(
        func.coalesce(func.sum(WorkflowRun.cohort_size_at_entry), 0)
    ).select_from(WorkflowRun).join(
        Workflow, WorkflowRun.workflow_id == Workflow.id
    ).where(
        WorkflowRun.tenant_id == tenant_id,
        WorkflowRun.app_id == app_id,
        scope_clause,
    )
    if date_from is not None:
        cohort_stmt = cohort_stmt.where(WorkflowRun.started_at >= date_from)
    if date_to is not None:
        cohort_stmt = cohort_stmt.where(WorkflowRun.started_at < date_to)
    cohort_total = (await db.execute(cohort_stmt)).scalar() or 0

    return OverviewResult(
        campaigns=int(row[0] or 0),
        runs=int(row[1] or 0),
        recipients=int(row[2] or 0),
        unique_contacts=int(row[3] or 0),
        positive=int(brow[0] or 0),
        reached=int(brow[1] or 0),
        no_response=int(brow[2] or 0),
        failed=int(brow[3] or 0),
        in_flight=int(brow[4] or 0),
        spend=float(row[4] or 0),
        in_flight_runs=int(in_flight_runs),
        cohort_total=int(cohort_total),
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
    cost_rows: int


_DISPATCH_NODE_TYPES = ("voice.place_call", "messaging.send_whatsapp_template", "core.webhook_out")


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
    """Dispatch attempts = parent dispatch rows, not lifecycle-event children."""
    return func.coalesce(
        func.sum(
            case((WorkflowRunRecipientAction.parent_action_id.is_(None), 1), else_=0)
        ),
        0,
    )


def _cost_rows_count():
    """Rows carrying a cost — the denominator for cost-per-request, since cost lives on terminal rows."""
    return func.coalesce(
        func.sum(
            case(
                (WorkflowRunRecipientAction.response["total_cost"].astext.isnot(None), 1),
                else_=0,
            )
        ),
        0,
    )


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
        dim_col = WorkflowRunRecipientAction.workflow_id
    elif dimension == "channel":
        group_key = group_label = WorkflowRunRecipientAction.channel
        dim_col = WorkflowRunRecipientAction.channel
    else:
        raise ValueError(f"unknown breakdown dimension: {dimension}")

    # Row-level aggregate: recipients (distinct), dispatched (parent rows), cost.
    stmt = select(
        group_key, group_label, _recipient_count(), _dispatched_count(),
        _COST_EXPR, _cost_rows_count(),
    )
    stmt = _base_join(stmt)
    stmt = _scope_filters(
        stmt, tenant_id=tenant_id, app_id=app_id, scope_clause=scope_clause,
        date_from=date_from, date_to=date_to,
    ).group_by(group_key, group_label)
    rows = (await db.execute(stmt)).all()

    # Collapsed bucket counts: one most-advanced bucket per recipient, per dimension.
    collapsed = _collapsed_recipient_subquery(
        tenant_id=tenant_id, app_id=app_id, scope_clause=scope_clause,
        date_from=date_from, date_to=date_to,
        extra_group_cols=(dim_col.label("dim_key"),),
    )
    rep = _rep_bucket_from_rank(collapsed.c.max_rank)
    bucket_stmt = select(
        collapsed.c.dim_key,
        _collapsed_bucket_count(rep, EngagementBucket.positive),
        _collapsed_bucket_count(rep, EngagementBucket.reached),
        _collapsed_bucket_count(rep, EngagementBucket.no_response),
        _collapsed_bucket_count(rep, EngagementBucket.failed),
        _collapsed_bucket_count(rep, EngagementBucket.in_flight),
    ).select_from(collapsed).group_by(collapsed.c.dim_key)
    buckets_by_key = {
        str(b[0]): (int(b[1] or 0), int(b[2] or 0), int(b[3] or 0), int(b[4] or 0), int(b[5] or 0))
        for b in (await db.execute(bucket_stmt)).all()
    }

    out: list[BreakdownRow] = []
    for r in rows:
        pos, rch, nr, fail, infl = buckets_by_key.get(str(r[0]), (0, 0, 0, 0, 0))
        out.append(BreakdownRow(
            key=str(r[0]), label=str(r[1]), provider=None,
            recipients=int(r[2] or 0), dispatched=int(r[3] or 0),
            positive=pos, reached=rch, no_response=nr, failed=fail,
            in_flight=infl, cost=float(r[4] or 0), cost_rows=int(r[5] or 0),
        ))
    return out


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
        _COST_EXPR,
        _cost_rows_count(),
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

    # Collapsed buckets per (version, node_id): one most-advanced bucket per recipient.
    bucket_inner = select(
        WorkflowRunRecipientAction.run_id,
        WorkflowRunRecipientAction.recipient_id,
        WorkflowRunRecipientAction.workflow_version_id.label("ver"),
        WorkflowRunNodeStep.node_id.label("nid"),
        func.max(_bucket_rank_expr()).label("max_rank"),
    ).select_from(WorkflowRunRecipientAction).join(
        WorkflowRunNodeStep,
        WorkflowRunRecipientAction.node_step_id == WorkflowRunNodeStep.id,
    ).join(
        WorkflowRun, WorkflowRunRecipientAction.run_id == WorkflowRun.id
    ).join(Workflow, WorkflowRun.workflow_id == Workflow.id)
    bucket_inner = _scope_filters(
        bucket_inner, tenant_id=tenant_id, app_id=app_id, scope_clause=scope_clause,
        date_from=date_from, date_to=date_to,
    ).group_by(
        WorkflowRunRecipientAction.run_id,
        WorkflowRunRecipientAction.recipient_id,
        WorkflowRunRecipientAction.workflow_version_id,
        WorkflowRunNodeStep.node_id,
    ).subquery()
    rep = _rep_bucket_from_rank(bucket_inner.c.max_rank)
    bucket_stmt = select(
        bucket_inner.c.ver,
        bucket_inner.c.nid,
        _collapsed_bucket_count(rep, EngagementBucket.positive),
        _collapsed_bucket_count(rep, EngagementBucket.reached),
        _collapsed_bucket_count(rep, EngagementBucket.no_response),
        _collapsed_bucket_count(rep, EngagementBucket.failed),
        _collapsed_bucket_count(rep, EngagementBucket.in_flight),
    ).select_from(bucket_inner).group_by(bucket_inner.c.ver, bucket_inner.c.nid)
    node_buckets = {
        (b[0], b[1]): (int(b[2] or 0), int(b[3] or 0), int(b[4] or 0), int(b[5] or 0), int(b[6] or 0))
        for b in (await db.execute(bucket_stmt)).all()
    }

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
        pos, rch, nr, fail, infl = node_buckets.get((r[0], r[1]), (0, 0, 0, 0, 0))
        bucket = acc.setdefault(key, [0, 0, 0, 0, 0, 0, 0.0, 0])
        bucket[0] += int(r[2] or 0)  # recipients
        bucket[1] += int(r[3] or 0)  # dispatched
        bucket[2] += pos
        bucket[3] += rch
        bucket[4] += nr
        bucket[5] += fail
        bucket[6] += float(r[4] or 0)  # cost
        bucket[7] += int(r[5] or 0)  # cost-bearing rows

    out: list[BreakdownRow] = []
    for key, b in acc.items():
        provider, name = conn_meta.get(key, (None, None))
        out.append(BreakdownRow(
            key=key,
            label=name or ("Unmapped connection" if key == "unmapped" else key),
            provider=provider,
            recipients=b[0], dispatched=b[1], positive=b[2], reached=b[3],
            no_response=b[4], failed=b[5], in_flight=0, cost=b[6], cost_rows=b[7],
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
    channel_expr = func.max(WorkflowRunRecipientAction.channel)

    # Per-run reach/positive: collapse each recipient to its most-advanced bucket,
    # then count runs' recipients so reach/positive can't exceed recipient count.
    collapsed = _collapsed_recipient_subquery(
        tenant_id=tenant_id, app_id=app_id, scope_clause=scope_clause,
        date_from=date_from, date_to=date_to,
        extra_group_cols=(),
    )
    rep = _rep_bucket_from_rank(collapsed.c.max_rank)
    run_buckets = select(
        collapsed.c.run_id.label("rb_run_id"),
        func.coalesce(
            func.sum(
                case(
                    (rep.in_((EngagementBucket.positive.value, EngagementBucket.reached.value)), 1),
                    else_=0,
                )
            ),
            0,
        ).label("reached"),
        _collapsed_bucket_count(rep, EngagementBucket.positive).label("positive"),
    ).select_from(collapsed).group_by(collapsed.c.run_id).subquery()

    base = (
        select(
            WorkflowRun.id,
            WorkflowRun.workflow_id,
            Workflow.name,
            channel_expr,
            WorkflowRun.triggered_by,
            WorkflowRun.status,
            WorkflowRun.cohort_size_at_entry,
            func.coalesce(func.max(run_buckets.c.reached), 0),
            func.coalesce(func.max(run_buckets.c.positive), 0),
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
        .join(
            run_buckets,
            run_buckets.c.rb_run_id == WorkflowRun.id,
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
        base = base.where(WorkflowRun.started_at < date_to)

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


# ── Trend ────────────────────────────────────────────────────────────


@dataclass
class TrendPoint:
    date: datetime
    positive: int
    reached: int
    no_response: int
    failed: int


async def trend(
    db: AsyncSession,
    *,
    tenant_id,
    app_id: str,
    scope_clause,
    date_from: Optional[datetime],
    date_to: Optional[datetime],
) -> list[TrendPoint]:
    """Per-day bucket counts; each recipient counted once by its most-advanced outcome."""
    day_col = func.date_trunc("day", WorkflowRun.started_at).label("day")
    collapsed = _collapsed_recipient_subquery(
        tenant_id=tenant_id, app_id=app_id, scope_clause=scope_clause,
        date_from=date_from, date_to=date_to,
        extra_group_cols=(day_col,),
    )
    rep = _rep_bucket_from_rank(collapsed.c.max_rank)
    stmt = select(
        collapsed.c.day,
        _collapsed_bucket_count(rep, EngagementBucket.positive),
        _collapsed_bucket_count(rep, EngagementBucket.reached),
        _collapsed_bucket_count(rep, EngagementBucket.no_response),
        _collapsed_bucket_count(rep, EngagementBucket.failed),
    ).select_from(collapsed).group_by(collapsed.c.day).order_by(collapsed.c.day)
    rows = (await db.execute(stmt)).all()
    return [
        TrendPoint(
            date=r[0], positive=int(r[1] or 0), reached=int(r[2] or 0),
            no_response=int(r[3] or 0), failed=int(r[4] or 0),
        )
        for r in rows
    ]


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

    # Collapse each recipient to its most-advanced bucket for this run.
    rep_inner = (
        select(
            WorkflowRunRecipientAction.recipient_id,
            func.max(_bucket_rank_expr()).label("max_rank"),
        )
        .select_from(WorkflowRunRecipientAction)
        .where(
            WorkflowRunRecipientAction.run_id == run_id,
            WorkflowRunRecipientAction.tenant_id == tenant_id,
        )
        .group_by(WorkflowRunRecipientAction.recipient_id)
        .subquery()
    )
    rep = _rep_bucket_from_rank(rep_inner.c.max_rank)
    bucket_stmt = select(
        _collapsed_bucket_count(rep, EngagementBucket.positive),
        _collapsed_bucket_count(rep, EngagementBucket.reached),
        _collapsed_bucket_count(rep, EngagementBucket.no_response),
        _collapsed_bucket_count(rep, EngagementBucket.failed),
        _collapsed_bucket_count(rep, EngagementBucket.in_flight),
    ).select_from(rep_inner)
    b = (await db.execute(bucket_stmt)).one()

    spend_row = (
        await db.execute(
            select(_COST_EXPR)
            .select_from(WorkflowRunRecipientAction)
            .where(
                WorkflowRunRecipientAction.run_id == run_id,
                WorkflowRunRecipientAction.tenant_id == tenant_id,
            )
        )
    ).scalar() or 0

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

    bucket_map = _action_type_to_bucket_map()

    def _derived_bucket(a):
        return a.outcome_bucket or bucket_map.get(a.action_type)

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
        spend=float(spend_row or 0),
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
                outcome_bucket=_derived_bucket(a), contact=(a.payload or {}).get("contact"),
                cost=_action_cost(a), created_at=a.created_at,
            )
            for a in action_rows
        ],
        actions_total=int(actions_total),
    )


# ── Run report (per-run funnel + recipients) ─────────────────────────


@dataclass
class RunReportFunnelStage:
    key: str
    label: str
    count: int


@dataclass
class RunReportChannel:
    capability: str
    vendor: Optional[str]
    connection_label: Optional[str]
    stages: list[RunReportFunnelStage]
    metrics: dict[str, Any]


@dataclass
class RunReportRecipientChannel:
    capability: str
    outcome_bucket: Optional[str]
    stage_reached: Optional[str]
    summary: Optional[str]
    metrics: dict[str, Any]


@dataclass
class RunReportRecipient:
    recipient_id: str
    display_name: Optional[str]
    contact_last4: Optional[str]
    attributes: dict[str, Any]
    channels: list[RunReportRecipientChannel]


@dataclass
class RunReportResult:
    run_id: Any
    workflow_id: Any
    workflow_name: str
    app_id: str
    status: str
    triggered_by: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_seconds: Optional[int]
    recipients_total: int
    spend: float
    buckets: RunBuckets
    channels: list[RunReportChannel]
    recipients: list[RunReportRecipient]
    recipients_total_count: int


# Recipient-state payload keys that are framework book-keeping, not dataset attrs.
_RESERVED_PAYLOAD_KEYS = frozenset({"contact", "steps", "last_outcome", "last_event_at"})


def _capability_index():
    """Registry-derived maps: action_type→capability, action_type→bucket, capability→adapter."""
    type_to_cap: dict[str, str] = {}
    type_to_bucket: dict[str, str] = {}
    cap_adapter: dict[str, Any] = {}
    for adapter in registered_adapter_instances():
        capability = getattr(adapter, "capability", None)
        outcome_map = getattr(adapter, "ACTION_OUTCOME_MAP", None)
        if not capability or not outcome_map:
            continue
        cap_adapter.setdefault(capability, adapter)
        for action_type, bucket in outcome_map.items():
            type_to_cap[action_type] = capability
            type_to_bucket[action_type] = bucket.value
    return type_to_cap, type_to_bucket, cap_adapter


def _stage_counts(adapter, bucket_counts: dict[str, int]) -> list[RunReportFunnelStage]:
    """Cumulative funnel: stages ordered weakest→strongest map onto the engagement
    bucket ranks (strongest stage = positive). Each stage counts recipients whose
    most-advanced bucket reached at-or-above that stage's rank."""
    stages = list(adapter.funnel_stages())
    if not stages:
        return []
    # Terminal buckets strongest→weakest; in_flight excluded from funnel reach.
    ordered_buckets = [
        EngagementBucket.positive.value, EngagementBucket.reached.value,
        EngagementBucket.no_response.value, EngagementBucket.failed.value,
    ]
    # Align the strongest stage with positive; weaker stages fold in lower ranks.
    n = len(stages)
    out: list[RunReportFunnelStage] = []
    for i, stage in enumerate(stages):
        # Stage i (0=weakest) includes recipients at-or-above this stage. The
        # strongest stage maps to positive only; weaker stages add lower buckets.
        depth = n - 1 - i
        cutoff = min(depth, len(ordered_buckets) - 1)
        count = sum(bucket_counts.get(b, 0) for b in ordered_buckets[: cutoff + 1])
        out.append(RunReportFunnelStage(key=stage.key, label=stage.label, count=count))
    return out


def _parse_step_fields(payload: dict) -> dict[str, dict[str, Any]]:
    """Group flat ``steps.<capability>.<node>.<field>`` payload keys by capability."""
    by_cap: dict[str, dict[str, Any]] = {}
    for key, val in payload.items():
        if not key.startswith("steps."):
            continue
        parts = key.split(".")
        if len(parts) < 4:
            continue
        by_cap.setdefault(parts[1], {})[parts[-1]] = val
    return by_cap


def _channel_detail(field_bag: dict[str, Any], stage_keys: list[str]) -> dict[str, Any]:
    """Per-recipient channel outcome/stage/summary/duration from a step-field bag.
    Fields matched by suffix (outcome|status, duration_sec, transcript|summary) so no
    provider field name is hardcoded."""
    outcome = duration = summary = None
    for field, val in field_bag.items():
        f = field.lower()
        if outcome is None and (f.endswith("outcome") or f.endswith("status")):
            outcome = str(val) if val is not None else None
        elif f.endswith("duration_sec"):
            try:
                duration = int(float(val))
            except (TypeError, ValueError):
                duration = None
        elif summary is None and (f.endswith("transcript") or f.endswith("summary")):
            summary = str(val) if val else None
    stage_reached = None
    if outcome is not None and stage_keys:
        if outcome in stage_keys:
            stage_reached = outcome
        elif outcome in ("answered", "positive", "connected", "completed"):
            stage_reached = "answered" if "answered" in stage_keys else stage_keys[-1]
        else:
            stage_reached = stage_keys[0]
    metrics = {"durationSec": duration} if duration and duration > 0 else {}
    return {"outcome": outcome, "stage_reached": stage_reached, "summary": summary, "metrics": metrics}


def _recipient_display(payload: dict) -> tuple[Optional[str], dict[str, Any]]:
    """Clean dataset attributes (no step bags / framework keys) + best-guess display name."""
    attrs = {
        k: v for k, v in payload.items()
        if not k.startswith("steps.") and k not in _RESERVED_PAYLOAD_KEYS
    }
    display_name = None
    name_key = None
    for k, v in attrs.items():
        lk = k.lower()
        if lk.endswith("name") and "plan" not in lk and v:
            display_name, name_key = str(v), k
            break
    clean = {
        k: v for k, v in attrs.items()
        if k != name_key and "phone" not in k.lower()
    }
    return display_name, clean


async def _resolve_channel_providers(db: AsyncSession, run_id) -> dict[str, tuple]:
    """capability -> (provider, connection_name) from the run's version node configs."""
    import uuid as _uuid

    row = (
        await db.execute(
            select(WorkflowVersion.definition)
            .join(WorkflowRun, WorkflowRun.workflow_version_id == WorkflowVersion.id)
            .where(WorkflowRun.id == run_id)
        )
    ).first()
    definition = row[0] if row else None
    if not definition:
        return {}
    cap_conn: dict[str, str] = {}
    for node in definition.get("nodes") or []:
        ntype = node.get("type") or ""
        cap = ntype.split(".")[0] if "." in ntype else None
        conn = (node.get("config") or {}).get("connection_id")
        if cap and conn:
            cap_conn.setdefault(cap, str(conn))
    if not cap_conn:
        return {}
    conn_uuids = []
    for c in set(cap_conn.values()):
        try:
            conn_uuids.append(_uuid.UUID(c))
        except (ValueError, TypeError):
            pass
    meta: dict[str, tuple] = {}
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
            meta[str(cid)] = (provider, name)
    return {cap: meta.get(conn, (None, None)) for cap, conn in cap_conn.items()}


async def run_report(
    db: AsyncSession,
    *,
    run_id,
    tenant_id,
    scope_clause,
    recipient_limit: int = 50,
) -> Optional[RunReportResult]:
    """Per-run engagement report: head+buckets+spend reuse ``run_detail``; per-channel
    funnel + talk-time + recipient rows are layered on. Provider-agnostic throughout."""
    detail = await run_detail(
        db, run_id=run_id, tenant_id=tenant_id, scope_clause=scope_clause,
        page=1, page_size=1,
    )
    if detail is None:
        return None

    duration_seconds: Optional[int] = None
    if detail.started_at is not None and detail.completed_at is not None:
        duration_seconds = max(0, int((detail.completed_at - detail.started_at).total_seconds()))

    # App id off the run head (run_detail does not surface it).
    app_id = (
        await db.execute(
            select(WorkflowRun.app_id).where(WorkflowRun.id == run_id)
        )
    ).scalar()

    type_to_cap, type_to_bucket, cap_adapter = _capability_index()

    # All action rows for the run — derive per-recipient capability + bucket.
    actions = (
        await db.execute(
            select(WorkflowRunRecipientAction).where(
                WorkflowRunRecipientAction.run_id == run_id,
                WorkflowRunRecipientAction.tenant_id == tenant_id,
            )
        )
    ).scalars().all()

    bucket_rank = _BUCKET_RANK
    # (recipient_id, capability) -> best bucket value; talk-time accumulators per cap.
    rep_bucket: dict[tuple[str, str], str] = {}
    talk_total: dict[str, float] = {}
    talk_count: dict[str, int] = {}
    caps_present: set[str] = set()
    for a in actions:
        capability = type_to_cap.get(a.action_type)
        if capability is None:
            continue
        caps_present.add(capability)
        bucket = a.outcome_bucket or type_to_bucket.get(a.action_type)
        if bucket is not None:
            key = (a.recipient_id, capability)
            prior = rep_bucket.get(key)
            if prior is None or bucket_rank.get(bucket, 0) > bucket_rank.get(prior, 0):
                rep_bucket[key] = bucket
        # Talk-time: any answered (positive) action carrying a duration on its response.
        if bucket == EngagementBucket.positive.value:
            raw = (a.response or {}).get("duration_sec") if a.response else None
            try:
                secs = float(raw) if raw is not None else None
            except (TypeError, ValueError):
                secs = None
            if secs is not None:
                talk_total[capability] = talk_total.get(capability, 0.0) + secs
                talk_count[capability] = talk_count.get(capability, 0) + 1

    cap_providers = await _resolve_channel_providers(db, run_id)
    channels: list[RunReportChannel] = []
    for capability in sorted(caps_present):
        adapter = cap_adapter.get(capability)
        if adapter is None:
            continue
        provider, conn_name = cap_providers.get(capability, (None, None))
        bucket_counts: dict[str, int] = {}
        for (_rid, cap), bucket in rep_bucket.items():
            if cap == capability:
                bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        metrics: dict[str, Any] = {}
        if capability in talk_total:
            total = int(round(talk_total[capability]))
            n = talk_count.get(capability, 0)
            metrics = {
                "totalDurationSec": total,
                "avgDurationSec": int(round(talk_total[capability] / n)) if n else 0,
            }
        channels.append(RunReportChannel(
            capability=capability, vendor=provider, connection_label=conn_name,
            stages=_stage_counts(adapter, bucket_counts), metrics=metrics,
        ))

    # Recipients: dataset attributes + per-channel outcome, engagement-first.
    states = (
        await db.execute(
            select(WorkflowRunRecipientState).where(
                WorkflowRunRecipientState.run_id == run_id,
                WorkflowRunRecipientState.tenant_id == tenant_id,
            )
        )
    ).scalars().all()
    recipients_total_count = len(states)

    def _best_rank(recipient_id: str) -> int:
        return max(
            (bucket_rank.get(b, 0) for (rid, _c), b in rep_bucket.items() if rid == recipient_id),
            default=0,
        )

    SUMMARY_MAX = 160
    ordered = sorted(states, key=lambda s: _best_rank(s.recipient_id), reverse=True)
    recipients: list[RunReportRecipient] = []
    for s in ordered[:recipient_limit]:
        payload = s.payload or {}
        display_name, attributes = _recipient_display(payload)
        contact = payload.get("contact")
        last4 = str(contact)[-4:] if contact else None
        step_bags = _parse_step_fields(payload)
        rec_caps = {cap for (rid, cap) in rep_bucket if rid == s.recipient_id} | set(step_bags)
        rec_channels: list[RunReportRecipientChannel] = []
        for cap in sorted(rec_caps):
            adapter = cap_adapter.get(cap)
            stage_keys = [st.key for st in adapter.funnel_stages()] if adapter else []
            ch = _channel_detail(step_bags.get(cap, {}), stage_keys)
            summary = ch["summary"]
            if summary and len(summary) > SUMMARY_MAX:
                summary = summary[:SUMMARY_MAX].rstrip() + "…"
            rec_channels.append(RunReportRecipientChannel(
                capability=cap,
                outcome_bucket=ch["outcome"] or rep_bucket.get((s.recipient_id, cap)),
                stage_reached=ch["stage_reached"],
                summary=summary,
                metrics=ch["metrics"],
            ))
        recipients.append(RunReportRecipient(
            recipient_id=s.recipient_id, display_name=display_name,
            contact_last4=last4, attributes=attributes, channels=rec_channels,
        ))

    return RunReportResult(
        run_id=detail.run_id, workflow_id=detail.workflow_id,
        workflow_name=detail.workflow_name, app_id=str(app_id or ""),
        status=detail.status, triggered_by=detail.triggered_by,
        started_at=detail.started_at, completed_at=detail.completed_at,
        duration_seconds=duration_seconds, recipients_total=detail.cohort_size,
        spend=detail.spend, buckets=detail.buckets, channels=channels,
        recipients=recipients, recipients_total_count=recipients_total_count,
    )

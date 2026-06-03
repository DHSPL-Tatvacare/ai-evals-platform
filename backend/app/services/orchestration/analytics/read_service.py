"""Provider-agnostic read queries over the workflow-engagement analytics layer.

Overview / runs / trend read the recipient-collapsed ``analytics.agg_workflow_run`` matview;
breakdown + run-report funnel/talk-time ``GROUP BY`` the flat ``analytics.fact_workflow_engagement``
fact; ``in_flight_runs`` / ``cohort_total`` / never-dispatched runs read the ``workflow_runs`` header.
The per-action log and the run-report recipient rows / transcripts stay on the TXN spine (operational
detail). The populator owns bucket rank + connection resolution; this module only reads + shapes.
Bucket counts gate on ``bucket_resolved`` so pure-dispatch recipients stay uncounted (rank-0 parity).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import and_, case, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics_workflow_facts import AggWorkflowRun, FactWorkflowEngagement
from app.models.orchestration import (
    Workflow,
    WorkflowRun,
    WorkflowRunNodeStep,
    WorkflowRunRecipientAction,
    WorkflowRunRecipientState,
)
from app.services.orchestration.adapters import registered_adapter_instances
from app.services.orchestration.analytics.outcomes import EngagementBucket


def WORKFLOW_TENANT_ALL(tenant_id):
    """Scope clause covering every workflow in a tenant (tests/admin tenant scope)."""
    return Workflow.tenant_id == tenant_id


_BUCKET_ORDER = (
    EngagementBucket.positive.value,
    EngagementBucket.reached.value,
    EngagementBucket.no_response.value,
    EngagementBucket.failed.value,
    EngagementBucket.in_flight.value,
)
# Per-action display rank for the run-detail log + run-report recipient ordering — registry-derived.
_BUCKET_RANK = {value: rank for rank, value in enumerate(reversed(_BUCKET_ORDER), start=1)}


def _mv_scoped(stmt, *, tenant_id, app_id, scope_clause, date_from, date_to):
    """Scope + window an ``agg_workflow_run`` read (window on the denormalized ``run_started_at``)."""
    stmt = (
        stmt.select_from(AggWorkflowRun)
        .join(Workflow, AggWorkflowRun.workflow_id == Workflow.id)
        .where(
            AggWorkflowRun.tenant_id == tenant_id,
            AggWorkflowRun.app_id == app_id,
            scope_clause,
        )
    )
    if date_from is not None:
        stmt = stmt.where(AggWorkflowRun.run_started_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(AggWorkflowRun.run_started_at < date_to)
    return stmt


def _fact_scoped(stmt, *, tenant_id, app_id, scope_clause, date_from, date_to):
    """Scope + window a ``fact_workflow_engagement`` read."""
    stmt = (
        stmt.select_from(FactWorkflowEngagement)
        .join(Workflow, FactWorkflowEngagement.workflow_id == Workflow.id)
        .where(
            FactWorkflowEngagement.tenant_id == tenant_id,
            FactWorkflowEngagement.app_id == app_id,
            scope_clause,
        )
    )
    if date_from is not None:
        stmt = stmt.where(FactWorkflowEngagement.run_started_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(FactWorkflowEngagement.run_started_at < date_to)
    return stmt


def _gated(bucket: EngagementBucket):
    """Count fact rows whose RESOLVED bucket == ``bucket`` — unresolved (pure-dispatch) rows excluded."""
    return func.coalesce(
        func.sum(
            case(
                (
                    and_(
                        FactWorkflowEngagement.bucket_resolved,
                        FactWorkflowEngagement.outcome_bucket == bucket.value,
                    ),
                    1,
                ),
                else_=0,
            )
        ),
        0,
    )


def _fact_recipients():
    return func.count(distinct(func.concat(FactWorkflowEngagement.run_id, "|", FactWorkflowEngagement.recipient_id)))


# ── Overview ─────────────────────────────────────────────────────────


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
    """KPI rollup. Campaigns/runs/recipients/buckets/spend off the recipient-collapsed matview;
    unique_contacts off the fact; in_flight_runs + cohort_total off the run header."""
    mv = AggWorkflowRun
    row = (await db.execute(_mv_scoped(
        select(
            func.count(distinct(mv.workflow_id)),
            func.count(distinct(mv.run_id)),
            func.coalesce(func.sum(mv.recipients), 0),
            func.coalesce(func.sum(mv.positive), 0),
            func.coalesce(func.sum(mv.reached), 0),
            func.coalesce(func.sum(mv.no_response), 0),
            func.coalesce(func.sum(mv.failed), 0),
            func.coalesce(func.sum(mv.in_flight), 0),
            func.coalesce(func.sum(mv.cost), 0),
        ),
        tenant_id=tenant_id, app_id=app_id, scope_clause=scope_clause,
        date_from=date_from, date_to=date_to,
    ))).one()

    unique_contacts = (await db.execute(_fact_scoped(
        select(func.count(distinct(FactWorkflowEngagement.contact_e164))),
        tenant_id=tenant_id, app_id=app_id, scope_clause=scope_clause,
        date_from=date_from, date_to=date_to,
    ))).scalar() or 0

    # In-flight is a status snapshot, not a windowed metric: running/just-started runs have
    # started_at IS NULL and no engagement rows, so they read the run header directly.
    in_flight_stmt = (
        select(func.count(distinct(WorkflowRun.id)))
        .select_from(WorkflowRun)
        .join(Workflow, WorkflowRun.workflow_id == Workflow.id)
        .where(
            WorkflowRun.tenant_id == tenant_id,
            WorkflowRun.app_id == app_id,
            scope_clause,
            WorkflowRun.status.in_(("running", "waiting", "pending")),
        )
    )
    in_flight_runs = (await db.execute(in_flight_stmt)).scalar() or 0

    # True cohort top of funnel: sum cohort_size_at_entry once per scoped+windowed run so
    # opted-out / never-dispatched recipients (no engagement rows) stay visible.
    cohort_stmt = (
        select(func.coalesce(func.sum(WorkflowRun.cohort_size_at_entry), 0))
        .select_from(WorkflowRun)
        .join(Workflow, WorkflowRun.workflow_id == Workflow.id)
        .where(
            WorkflowRun.tenant_id == tenant_id,
            WorkflowRun.app_id == app_id,
            scope_clause,
        )
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
        unique_contacts=int(unique_contacts),
        positive=int(row[3] or 0),
        reached=int(row[4] or 0),
        no_response=int(row[5] or 0),
        failed=int(row[6] or 0),
        in_flight=int(row[7] or 0),
        spend=float(row[8] or 0),
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


def _fact_metric_cols():
    """Row-level fact aggregates shared by every breakdown dimension."""
    return (
        _fact_recipients(),
        func.coalesce(func.sum(FactWorkflowEngagement.dispatch_attempts), 0),
        _gated(EngagementBucket.positive),
        _gated(EngagementBucket.reached),
        _gated(EngagementBucket.no_response),
        _gated(EngagementBucket.failed),
        _gated(EngagementBucket.in_flight),
        func.coalesce(func.sum(FactWorkflowEngagement.cost), 0),
        func.coalesce(func.sum(FactWorkflowEngagement.cost_rows), 0),
    )


def _breakdown_row(key, label, provider, m) -> BreakdownRow:
    return BreakdownRow(
        key=key, label=label, provider=provider,
        recipients=int(m[0] or 0), dispatched=int(m[1] or 0),
        positive=int(m[2] or 0), reached=int(m[3] or 0), no_response=int(m[4] or 0),
        failed=int(m[5] or 0), in_flight=int(m[6] or 0),
        cost=float(m[7] or 0), cost_rows=int(m[8] or 0),
    )


def _sort_breakdown(rows: list[BreakdownRow]) -> list[BreakdownRow]:
    """Deterministic display order (was emergent DB order; FE renders server order, no client sort)."""
    return sorted(rows, key=lambda r: (-r.recipients, -r.cost, r.key))


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
    """Per-dimension bucket/cost rollup off the fact. dimension in {campaign, channel, connection}.

    ``campaign`` collapses buckets cross-capability (the matview's per-recipient collapse), so a
    recipient called AND messaged counts once. ``channel`` / ``connection`` are per-capability, so a
    recipient on two channels is two rows — matching the prior live behaviour exactly.
    """
    if dimension == "campaign":
        return await _campaign_breakdown(
            db, tenant_id=tenant_id, app_id=app_id, scope_clause=scope_clause,
            date_from=date_from, date_to=date_to,
        )

    if dimension == "channel":
        group_col = FactWorkflowEngagement.channel
        stmt = _fact_scoped(
            select(group_col, *_fact_metric_cols()),
            tenant_id=tenant_id, app_id=app_id, scope_clause=scope_clause,
            date_from=date_from, date_to=date_to,
        ).group_by(group_col)
        rows = [
            _breakdown_row(str(r[0]), str(r[0]), None, r[1:])
            for r in (await db.execute(stmt)).all()
        ]
        return _sort_breakdown(rows)

    if dimension == "connection":
        return await _connection_breakdown(
            db, tenant_id=tenant_id, app_id=app_id, scope_clause=scope_clause,
            date_from=date_from, date_to=date_to,
        )

    raise ValueError(f"unknown breakdown dimension: {dimension}")


async def _campaign_breakdown(
    db, *, tenant_id, app_id, scope_clause, date_from, date_to,
) -> list[BreakdownRow]:
    """Per-workflow: recipients/dispatched/cost off the fact; buckets cross-cap off the matview."""
    fact_stmt = _fact_scoped(
        select(
            FactWorkflowEngagement.workflow_id,
            func.max(FactWorkflowEngagement.workflow_name),
            _fact_recipients(),
            func.coalesce(func.sum(FactWorkflowEngagement.dispatch_attempts), 0),
            func.coalesce(func.sum(FactWorkflowEngagement.cost), 0),
            func.coalesce(func.sum(FactWorkflowEngagement.cost_rows), 0),
        ),
        tenant_id=tenant_id, app_id=app_id, scope_clause=scope_clause,
        date_from=date_from, date_to=date_to,
    ).group_by(FactWorkflowEngagement.workflow_id)
    fact_rows = (await db.execute(fact_stmt)).all()

    mv = AggWorkflowRun
    bucket_stmt = _mv_scoped(
        select(
            mv.workflow_id,
            func.coalesce(func.sum(mv.positive), 0),
            func.coalesce(func.sum(mv.reached), 0),
            func.coalesce(func.sum(mv.no_response), 0),
            func.coalesce(func.sum(mv.failed), 0),
            func.coalesce(func.sum(mv.in_flight), 0),
        ),
        tenant_id=tenant_id, app_id=app_id, scope_clause=scope_clause,
        date_from=date_from, date_to=date_to,
    ).group_by(mv.workflow_id)
    buckets = {
        b[0]: (int(b[1] or 0), int(b[2] or 0), int(b[3] or 0), int(b[4] or 0), int(b[5] or 0))
        for b in (await db.execute(bucket_stmt)).all()
    }

    rows: list[BreakdownRow] = []
    for r in fact_rows:
        pos, rch, nr, fail, infl = buckets.get(r[0], (0, 0, 0, 0, 0))
        rows.append(BreakdownRow(
            key=str(r[0]), label=str(r[1]), provider=None,
            recipients=int(r[2] or 0), dispatched=int(r[3] or 0),
            positive=pos, reached=rch, no_response=nr, failed=fail, in_flight=infl,
            cost=float(r[4] or 0), cost_rows=int(r[5] or 0),
        ))
    return _sort_breakdown(rows)


async def _connection_breakdown(
    db, *, tenant_id, app_id, scope_clause, date_from, date_to,
) -> list[BreakdownRow]:
    """Per-connection: the populator already resolved connection_id/label/provider onto each row."""
    f = FactWorkflowEngagement
    stmt = _fact_scoped(
        select(f.connection_id, func.max(f.connection_label), func.max(f.provider), *_fact_metric_cols()),
        tenant_id=tenant_id, app_id=app_id, scope_clause=scope_clause,
        date_from=date_from, date_to=date_to,
    ).group_by(f.connection_id)
    rows: list[BreakdownRow] = []
    for r in (await db.execute(stmt)).all():
        conn_id, label, provider = r[0], r[1], r[2]
        if conn_id is None:
            key, disp_label, prov = "unmapped", "Unmapped connection", None
        else:
            key, disp_label, prov = str(conn_id), (label or str(conn_id)), provider
        rows.append(_breakdown_row(key, disp_label, prov, r[3:]))
    return _sort_breakdown(rows)


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
    """Paginated run rows. Reach (positive+reached) / positive / cost off the matview; the run
    header + channel come from ``workflow_runs`` + the fact so never-dispatched runs still list."""
    mv = AggWorkflowRun
    chan_sq = (
        select(
            FactWorkflowEngagement.run_id.label("c_run_id"),
            func.max(FactWorkflowEngagement.channel).label("ch"),
        )
        .group_by(FactWorkflowEngagement.run_id)
        .subquery()
    )
    base = (
        select(
            WorkflowRun.id,
            WorkflowRun.workflow_id,
            Workflow.name,
            chan_sq.c.ch,
            WorkflowRun.triggered_by,
            WorkflowRun.status,
            WorkflowRun.cohort_size_at_entry,
            func.coalesce(mv.positive, 0) + func.coalesce(mv.reached, 0),
            func.coalesce(mv.positive, 0),
            func.coalesce(mv.cost, 0),
            WorkflowRun.started_at,
        )
        .select_from(WorkflowRun)
        .join(Workflow, WorkflowRun.workflow_id == Workflow.id)
        .outerjoin(mv, mv.run_id == WorkflowRun.id)
        .outerjoin(chan_sq, chan_sq.c.c_run_id == WorkflowRun.id)
        .where(
            WorkflowRun.tenant_id == tenant_id,
            WorkflowRun.app_id == app_id,
            scope_clause,
        )
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
    """Per-day bucket counts off the matview; each recipient already counted once (cross-capability)."""
    mv = AggWorkflowRun
    day_col = func.date_trunc("day", mv.run_started_at).label("day")
    stmt = _mv_scoped(
        select(
            day_col,
            func.coalesce(func.sum(mv.positive), 0),
            func.coalesce(func.sum(mv.reached), 0),
            func.coalesce(func.sum(mv.no_response), 0),
            func.coalesce(func.sum(mv.failed), 0),
        ),
        tenant_id=tenant_id, app_id=app_id, scope_clause=scope_clause,
        date_from=date_from, date_to=date_to,
    ).group_by(day_col).order_by(day_col)
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


def _action_type_to_bucket_map() -> dict[str, str]:
    """action_type → bucket value, merged from the adapter registry. Used only to display a derived
    bucket on null-bucket child rows in the per-action log; never for analytics rollups."""
    merged: dict[str, str] = {}
    for adapter in registered_adapter_instances():
        for action_type, bucket in getattr(adapter, "ACTION_OUTCOME_MAP", {}).items():
            merged[action_type] = bucket.value
    return merged


async def run_detail(
    db: AsyncSession,
    *,
    run_id,
    tenant_id,
    scope_clause,
    page: int = 1,
    page_size: int = 50,
) -> Optional[RunDetailResult]:
    """Bucket rollup + spend off the matview; node steps + paginated action log stay on TXN."""
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

    mv = AggWorkflowRun
    agg = (
        await db.execute(
            select(mv.positive, mv.reached, mv.no_response, mv.failed, mv.in_flight, mv.cost)
            .where(mv.run_id == run_id, mv.tenant_id == tenant_id)
        )
    ).first()
    buckets = RunBuckets(
        positive=int((agg[0] if agg else 0) or 0),
        reached=int((agg[1] if agg else 0) or 0),
        no_response=int((agg[2] if agg else 0) or 0),
        failed=int((agg[3] if agg else 0) or 0),
        in_flight=int((agg[4] if agg else 0) or 0),
    )
    spend = float((agg[5] if agg else 0) or 0)

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
        buckets=buckets,
        spend=spend,
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


def _cap_adapters() -> dict[str, Any]:
    """capability → adapter (for funnel stages). One adapter per capability is enough."""
    out: dict[str, Any] = {}
    for adapter in registered_adapter_instances():
        capability = getattr(adapter, "capability", None)
        if capability and getattr(adapter, "ACTION_OUTCOME_MAP", None):
            out.setdefault(capability, adapter)
    return out


def _stage_counts(adapter, bucket_counts: dict[str, int]) -> list[RunReportFunnelStage]:
    """Cumulative funnel: stages ordered weakest→strongest map onto the engagement bucket ranks
    (strongest stage = positive). Each stage counts recipients whose most-advanced bucket reached
    at-or-above that stage's rank."""
    stages = list(adapter.funnel_stages())
    if not stages:
        return []
    ordered_buckets = [
        EngagementBucket.positive.value, EngagementBucket.reached.value,
        EngagementBucket.no_response.value, EngagementBucket.failed.value,
    ]
    n = len(stages)
    out: list[RunReportFunnelStage] = []
    for i, stage in enumerate(stages):
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
    """Per-recipient channel outcome/stage/summary/duration from a step-field bag. Fields matched by
    suffix (outcome|status, duration_sec, transcript|summary) so no provider field name is hardcoded."""
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


async def run_report(
    db: AsyncSession,
    *,
    run_id,
    tenant_id,
    scope_clause,
    recipient_limit: int = 50,
) -> Optional[RunReportResult]:
    """Per-run engagement report: head/buckets/spend reuse ``run_detail``; per-channel funnel +
    talk-time come from the fact; the recipient rows / transcripts stay on the TXN state spine."""
    detail = await run_detail(
        db, run_id=run_id, tenant_id=tenant_id, scope_clause=scope_clause,
        page=1, page_size=1,
    )
    if detail is None:
        return None

    duration_seconds: Optional[int] = None
    if detail.started_at is not None and detail.completed_at is not None:
        duration_seconds = max(0, int((detail.completed_at - detail.started_at).total_seconds()))

    app_id = (
        await db.execute(select(WorkflowRun.app_id).where(WorkflowRun.id == run_id))
    ).scalar()

    cap_adapter = _cap_adapters()

    # All engagement rows for the run — capability + bucket + connection + talk-time already resolved.
    fact_rows = (
        await db.execute(
            select(FactWorkflowEngagement).where(
                FactWorkflowEngagement.run_id == run_id,
                FactWorkflowEngagement.tenant_id == tenant_id,
            )
        )
    ).scalars().all()

    # (recipient, capability) -> resolved bucket; talk-time accumulators; provider/label per cap.
    rep_bucket: dict[tuple[str, str], str] = {}
    talk_total: dict[str, float] = {}
    talk_count: dict[str, int] = {}
    caps_present: set[str] = set()
    cap_meta: dict[str, tuple[Optional[str], Optional[str]]] = {}
    for r in fact_rows:
        if r.bucket_resolved:
            caps_present.add(r.capability)
            rep_bucket[(r.recipient_id, r.capability)] = r.outcome_bucket
        cap_meta.setdefault(
            r.capability,
            (r.provider, None if r.connection_label == "unmapped" else r.connection_label),
        )
        if r.talk_count:
            talk_total[r.capability] = talk_total.get(r.capability, 0.0) + float(r.duration_sec or 0)
            talk_count[r.capability] = talk_count.get(r.capability, 0) + int(r.talk_count or 0)

    channels: list[RunReportChannel] = []
    for capability in sorted(caps_present):
        adapter = cap_adapter.get(capability)
        if adapter is None:
            continue
        provider, conn_name = cap_meta.get(capability, (None, None))
        bucket_counts: dict[str, int] = {}
        for (_rid, cap), bucket in rep_bucket.items():
            if cap == capability:
                bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        metrics: dict[str, Any] = {}
        if capability in talk_total and talk_count.get(capability):
            total = int(round(talk_total[capability]))
            n = talk_count[capability]
            metrics = {
                "totalDurationSec": total,
                "avgDurationSec": int(round(talk_total[capability] / n)) if n else 0,
            }
        channels.append(RunReportChannel(
            capability=capability, vendor=provider, connection_label=conn_name,
            stages=_stage_counts(adapter, bucket_counts), metrics=metrics,
        ))

    # Recipients: dataset attributes + per-channel outcome, engagement-first (TXN state spine).
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
            (_BUCKET_RANK.get(b, 0) for (rid, _c), b in rep_bucket.items() if rid == recipient_id),
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

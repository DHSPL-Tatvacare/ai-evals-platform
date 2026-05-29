"""Orchestration analytics API — read-only KPI / breakdown / run views.

Every endpoint requires ``insights:view`` or ``orchestration:manage``, requires the app to declare
orchestration in its config, and resolves the caller's scope at the data layer
(``mine`` owned+shared, ``tenant`` admin-only). Aggregation lives in
``analytics.read_service``; these handlers only parse the range and map shapes.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app.auth.context import AuthContext
from app.auth.permissions import require_any_permission
from app.database import get_db
from app.models.orchestration_signal import OrchestrationSignalSnapshot
from app.schemas.orchestration_analytics import (
    BreakdownResponse,
    BreakdownRowResponse,
    OverviewResponse,
    RunActionResponse,
    RunBucketsResponse,
    RunDetailResponse,
    RunNodeStepResponse,
    RunReportChannel,
    RunReportFunnelStage,
    RunReportRecipient,
    RunReportRecipientChannel,
    RunReportResponse,
    RunRowResponse,
    RunsResponse,
    SignalResponse,
    SignalsResponse,
    TrendPointResponse,
    TrendResponse,
)
from app.routes.reports import _render_pdf_via_print_route
from app.services.orchestration.analytics import read_service
from app.services.orchestration.analytics.scope import (
    ScopeForbidden,
    ensure_orchestration_enabled,
    resolve_analytics_scope,
)
from fastapi import Depends
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/orchestration/analytics", tags=["orchestration"])

_DEFAULT_RANGE_DAYS = 30


def _parse_window(
    date_from: Optional[str], date_to: Optional[str]
) -> tuple[datetime, datetime]:
    """Parse ISO ``from`` / ``to`` query params into a UTC window. Defaults to 30 days."""
    now = datetime.now(timezone.utc)
    try:
        start = (
            datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc)
            if date_from
            else now - timedelta(days=_DEFAULT_RANGE_DAYS)
        )
        if date_to:
            parsed_to = datetime.fromisoformat(date_to).replace(tzinfo=timezone.utc)
            # Date-only "to" parses to midnight; advance to the next midnight so the
            # exclusive upper bound covers the whole final day (today included).
            if parsed_to.timetz() == datetime.min.time().replace(tzinfo=timezone.utc):
                end = parsed_to + timedelta(days=1)
            else:
                end = parsed_to
        else:
            end = now
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid date range: {exc}")
    if end < start:
        raise HTTPException(status_code=400, detail="Invalid date range: to < from")
    return start, end


def _resolve_scope(auth: AuthContext, scope: str):
    try:
        return resolve_analytics_scope(auth, scope)
    except ScopeForbidden as exc:
        raise HTTPException(status_code=403, detail=str(exc))


def _avg_cost(cost: float, cost_rows: int) -> float:
    """Cost per request divides by cost-bearing rows; cost lives on terminal rows, not dispatch rows."""
    return round(cost / cost_rows, 6) if cost_rows else 0.0


@router.get("/overview", response_model=OverviewResponse)
async def get_overview(
    app_id: str = Query(..., alias="appId"),
    scope: str = Query("mine"),
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = require_any_permission("insights:view", "orchestration:manage"),
) -> OverviewResponse:
    await ensure_orchestration_enabled(db, app_id)
    scope_clause = _resolve_scope(auth, scope)
    start, end = _parse_window(date_from, date_to)
    result = await read_service.overview(
        db, tenant_id=auth.tenant_id, app_id=app_id, scope_clause=scope_clause,
        date_from=start, date_to=end,
    )
    return OverviewResponse(
        campaigns=result.campaigns, runs=result.runs, recipients=result.recipients,
        unique_contacts=result.unique_contacts, positive=result.positive,
        reached=result.reached, no_response=result.no_response, failed=result.failed,
        in_flight=result.in_flight, spend=result.spend, in_flight_runs=result.in_flight_runs,
        cohort_total=result.cohort_total,
    )


@router.get("/breakdown", response_model=BreakdownResponse)
async def get_breakdown(
    dimension: str = Query(...),
    app_id: str = Query(..., alias="appId"),
    scope: str = Query("mine"),
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = require_any_permission("insights:view", "orchestration:manage"),
) -> BreakdownResponse:
    if dimension not in ("campaign", "channel", "connection"):
        raise HTTPException(status_code=400, detail=f"Unsupported dimension: {dimension}")
    await ensure_orchestration_enabled(db, app_id)
    scope_clause = _resolve_scope(auth, scope)
    start, end = _parse_window(date_from, date_to)
    rows = await read_service.breakdown(
        db, dimension=dimension, tenant_id=auth.tenant_id, app_id=app_id,
        scope_clause=scope_clause, date_from=start, date_to=end,
    )
    return BreakdownResponse(
        dimension=dimension,
        rows=[
            BreakdownRowResponse(
                key=r.key, label=r.label, provider=r.provider,
                recipients=r.recipients, dispatched=r.dispatched,
                positive=r.positive, reached=r.reached, no_response=r.no_response,
                failed=r.failed, in_flight=r.in_flight,
                avg_cost=_avg_cost(r.cost, r.cost_rows), cost=r.cost,
            )
            for r in rows
        ],
    )


@router.get("/trend", response_model=TrendResponse)
async def get_trend(
    app_id: str = Query(..., alias="appId"),
    scope: str = Query("mine"),
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = require_any_permission("insights:view", "orchestration:manage"),
) -> TrendResponse:
    await ensure_orchestration_enabled(db, app_id)
    scope_clause = _resolve_scope(auth, scope)
    start, end = _parse_window(date_from, date_to)
    points = await read_service.trend(
        db, tenant_id=auth.tenant_id, app_id=app_id, scope_clause=scope_clause,
        date_from=start, date_to=end,
    )
    return TrendResponse(
        points=[
            TrendPointResponse(
                date=p.date, positive=p.positive, reached=p.reached,
                no_response=p.no_response, failed=p.failed,
            )
            for p in points
        ],
    )


@router.get("/runs", response_model=RunsResponse)
async def get_runs(
    app_id: str = Query(..., alias="appId"),
    scope: str = Query("mine"),
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200, alias="pageSize"),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = require_any_permission("insights:view", "orchestration:manage"),
) -> RunsResponse:
    await ensure_orchestration_enabled(db, app_id)
    scope_clause = _resolve_scope(auth, scope)
    start, end = _parse_window(date_from, date_to)
    result = await read_service.runs(
        db, tenant_id=auth.tenant_id, app_id=app_id, scope_clause=scope_clause,
        date_from=start, date_to=end, page=page, page_size=page_size,
    )
    return RunsResponse(
        rows=[
            RunRowResponse(
                run_id=r.run_id, workflow_id=r.workflow_id,
                workflow_name=r.workflow_name, channel=r.channel,
                triggered_by=r.triggered_by, status=r.status,
                cohort_size=r.cohort_size, reached=r.reached,
                positive=r.positive, cost=r.cost, started_at=r.started_at,
            )
            for r in result.rows
        ],
        total=result.total, page=result.page, page_size=result.page_size,
    )


@router.get("/runs/{run_id}", response_model=RunDetailResponse)
async def get_run_detail(
    run_id: str,
    app_id: str = Query(..., alias="appId"),
    scope: str = Query("mine"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500, alias="pageSize"),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = require_any_permission("insights:view", "orchestration:manage"),
) -> RunDetailResponse:
    await ensure_orchestration_enabled(db, app_id)
    scope_clause = _resolve_scope(auth, scope)
    detail = await read_service.run_detail(
        db, run_id=run_id, tenant_id=auth.tenant_id, scope_clause=scope_clause,
        page=page, page_size=page_size,
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return RunDetailResponse(
        run_id=detail.run_id, workflow_id=detail.workflow_id,
        workflow_name=detail.workflow_name, status=detail.status,
        triggered_by=detail.triggered_by, cohort_size=detail.cohort_size,
        started_at=detail.started_at, completed_at=detail.completed_at,
        buckets=RunBucketsResponse(
            positive=detail.buckets.positive, reached=detail.buckets.reached,
            no_response=detail.buckets.no_response, failed=detail.buckets.failed,
            in_flight=detail.buckets.in_flight,
        ),
        spend=detail.spend,
        node_steps=[
            RunNodeStepResponse(
                node_step_id=s.node_step_id, node_id=s.node_id,
                node_type=s.node_type, status=s.status,
                started_at=s.started_at, completed_at=s.completed_at,
            )
            for s in detail.node_steps
        ],
        actions=[
            RunActionResponse(
                action_id=a.action_id, recipient_id=a.recipient_id,
                channel=a.channel, action_type=a.action_type, status=a.status,
                outcome_bucket=a.outcome_bucket, contact=a.contact,
                cost=a.cost, created_at=a.created_at,
            )
            for a in detail.actions
        ],
        actions_total=detail.actions_total,
    )


@router.get("/runs/{run_id}/report", response_model=RunReportResponse)
async def get_run_report(
    run_id: str,
    app_id: str = Query(..., alias="appId"),
    scope: str = Query("mine"),
    recipient_limit: int = Query(50, ge=1, le=500, alias="recipientLimit"),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = require_any_permission("insights:view", "orchestration:manage"),
) -> RunReportResponse:
    await ensure_orchestration_enabled(db, app_id)
    scope_clause = _resolve_scope(auth, scope)
    report = await read_service.run_report(
        db, run_id=run_id, tenant_id=auth.tenant_id, scope_clause=scope_clause,
        recipient_limit=recipient_limit,
    )
    if report is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return RunReportResponse(
        run_id=report.run_id, workflow_id=report.workflow_id,
        workflow_name=report.workflow_name, app_id=report.app_id,
        status=report.status, triggered_by=report.triggered_by,
        started_at=report.started_at, completed_at=report.completed_at,
        duration_seconds=report.duration_seconds,
        recipients_total=report.recipients_total, spend=report.spend,
        buckets=RunBucketsResponse(
            positive=report.buckets.positive, reached=report.buckets.reached,
            no_response=report.buckets.no_response, failed=report.buckets.failed,
            in_flight=report.buckets.in_flight,
        ),
        channels=[
            RunReportChannel(
                capability=c.capability, vendor=c.vendor,
                connection_label=c.connection_label,
                stages=[
                    RunReportFunnelStage(key=s.key, label=s.label, count=s.count)
                    for s in c.stages
                ],
                metrics=c.metrics,
            )
            for c in report.channels
        ],
        recipients=[
            RunReportRecipient(
                recipient_id=r.recipient_id, display_name=r.display_name,
                contact_last4=r.contact_last4, attributes=r.attributes,
                channels=[
                    RunReportRecipientChannel(
                        capability=rc.capability, outcome_bucket=rc.outcome_bucket,
                        stage_reached=rc.stage_reached, summary=rc.summary,
                        metrics=rc.metrics,
                    )
                    for rc in r.channels
                ],
            )
            for r in report.recipients
        ],
        recipients_total_count=report.recipients_total_count,
    )


def _campaign_pdf_meta(report) -> dict[str, str]:
    """Running header/footer text for the campaign PDF. Keys mirror
    ``_compose_pdf_header_template`` (title) / ``_compose_pdf_footer_template``
    (subtitle) in ``routes.reports``. Subtitle stays generic + data-driven —
    no app-specific copy."""
    channels = ", ".join(
        sorted({c.connection_label or c.vendor or c.capability for c in report.channels})
    )
    subtitle = (
        f"{report.recipients_total} contacts across {channels}"
        if channels
        else "Campaign run report"
    )
    return {"label": "Campaign Report", "title": report.workflow_name or "Campaign run", "subtitle": subtitle}


@router.get("/runs/{run_id}/export-pdf")
async def export_run_pdf(
    run_id: str,
    app_id: str = Query(..., alias="appId"),
    scope: str = Query("mine"),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = require_any_permission("insights:view", "orchestration:manage"),
) -> Response:
    await ensure_orchestration_enabled(db, app_id)
    scope_clause = _resolve_scope(auth, scope)
    report = await read_service.run_report(
        db, run_id=run_id, tenant_id=auth.tenant_id, scope_clause=scope_clause,
    )
    if report is None:
        raise HTTPException(status_code=404, detail="Run not found")
    pdf_bytes = await _render_pdf_via_print_route(
        print_path=f"/print/campaign-runs/{run_id}?appId={app_id}&scope={scope}",
        auth=auth,
        log_id=f"campaign run {run_id}",
        pdf_meta=_campaign_pdf_meta(report),
    )
    short_id = str(run_id)[:8]
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="campaign-run-{short_id}.pdf"',
        },
    )


@router.get("/signals", response_model=SignalsResponse)
async def get_signals(
    app_id: str = Query(..., alias="appId"),
    scope: str = Query("mine"),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = require_any_permission("insights:view", "orchestration:manage"),
) -> SignalsResponse:
    await ensure_orchestration_enabled(db, app_id)
    _resolve_scope(auth, scope)
    snapshot = (
        await db.execute(
            select(OrchestrationSignalSnapshot)
            .where(
                OrchestrationSignalSnapshot.tenant_id == auth.tenant_id,
                OrchestrationSignalSnapshot.app_id == app_id,
            )
            .order_by(desc(OrchestrationSignalSnapshot.generated_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    if snapshot is None:
        return SignalsResponse(signals=[])

    signals = [
        SignalResponse(
            severity=str(raw.get("severity", "info")),
            title=str(raw.get("title", "")),
            detail=str(raw.get("detail", "")),
            metric=raw.get("metric"),
        )
        for raw in (snapshot.signals or [])
    ]
    return SignalsResponse(signals=signals, generated_at=snapshot.generated_at)

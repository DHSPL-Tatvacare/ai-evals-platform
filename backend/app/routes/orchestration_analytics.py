"""Orchestration analytics API — read-only KPI / breakdown / run views.

Every endpoint is gated by ``orchestration:manage``, requires the app to declare
orchestration in its config, and resolves the caller's scope at the data layer
(``mine`` owned+shared, ``tenant`` admin-only). Aggregation lives in
``analytics.read_service``; these handlers only parse the range and map shapes.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.auth.context import AuthContext
from app.auth.permissions import require_permission
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
    RunRowResponse,
    RunsResponse,
    SignalResponse,
    SignalsResponse,
)
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
        end = (
            datetime.fromisoformat(date_to).replace(tzinfo=timezone.utc)
            if date_to
            else now
        )
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


def _avg_cost(cost: float, dispatched: int) -> float:
    return round(cost / dispatched, 6) if dispatched else 0.0


@router.get("/overview", response_model=OverviewResponse)
async def get_overview(
    app_id: str = Query(..., alias="appId"),
    scope: str = Query("mine"),
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = require_permission("orchestration:manage"),
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
    )


@router.get("/breakdown", response_model=BreakdownResponse)
async def get_breakdown(
    dimension: str = Query(...),
    app_id: str = Query(..., alias="appId"),
    scope: str = Query("mine"),
    date_from: Optional[str] = Query(None, alias="from"),
    date_to: Optional[str] = Query(None, alias="to"),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = require_permission("orchestration:manage"),
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
                avg_cost=_avg_cost(r.cost, r.dispatched), cost=r.cost,
            )
            for r in rows
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
    auth: AuthContext = require_permission("orchestration:manage"),
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
    auth: AuthContext = require_permission("orchestration:manage"),
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


@router.get("/signals", response_model=SignalsResponse)
async def get_signals(
    app_id: str = Query(..., alias="appId"),
    scope: str = Query("mine"),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = require_permission("orchestration:manage"),
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

"""Routes for Inside Sales call data."""

import uuid as _uuid
from datetime import datetime as _dt, timezone as _tz

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.auth.context import AuthContext, get_auth_context
from app.models.eval_run import ThreadEvaluation, EvalRun
from app.database import get_db
from app.schemas.inside_sales import (
    CallRecord, CallListResponse, LeadDetailResponse, AgentListResponse,
    LeadListRecord, LeadListResponse, LeadCallRecord, LeadDetailFullResponse,
)
from app.services.lsq_client import (
    fetch_call_activities, normalize_activity, fetch_lead_by_id,
    fetch_leads, fetch_lead_activities_for_prospect, normalize_lead,
    compute_mql_score, compute_lead_metrics, compute_drilldown_metrics,
)

router = APIRouter(prefix="/api/inside-sales", tags=["inside-sales"])


async def require_inside_sales_access(
    auth: AuthContext = Depends(get_auth_context),
) -> AuthContext:
    """Require access to the inside-sales app."""
    if auth.is_owner:
        return auth
    if "inside-sales" not in auth.app_access:
        raise HTTPException(403, "No access to app: inside-sales")
    return auth


@router.get("/agents", response_model=AgentListResponse)
async def list_agents(
    date_from: str = Query(..., description="Start date YYYY-MM-DD HH:MM:SS"),
    date_to: str = Query(..., description="End date YYYY-MM-DD HH:MM:SS"),
    auth: AuthContext = Depends(require_inside_sales_access),
):
    """Return sorted unique agent names for the given date range."""
    result = await fetch_call_activities(
        date_from=date_from,
        date_to=date_to,
        page=1,
        page_size=500,
    )
    names = sorted({
        normalize_activity(a)["agentName"]
        for a in result["activities"]
        if normalize_activity(a).get("agentName")
    })
    return AgentListResponse(agents=names)


@router.get("/calls", response_model=CallListResponse)
async def list_calls(
    date_from: str = Query(..., description="Start date YYYY-MM-DD HH:MM:SS"),
    date_to: str = Query(..., description="End date YYYY-MM-DD HH:MM:SS"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    agents: str | None = Query(None, description="Comma-separated agent names"),
    prospect_id: str | None = Query(None, description="Prospect ID substring"),
    direction: str | None = Query(None),
    status: str | None = Query(None),
    event_codes: str | None = Query(None, description="Comma-separated event codes"),
    auth: AuthContext = Depends(require_inside_sales_access),
    db: AsyncSession = Depends(get_db),
):
    """Fetch call activities from LSQ. Activity-only — no lead hydration."""
    codes = None
    if event_codes:
        codes = [int(c.strip()) for c in event_codes.split(",")]

    result = await fetch_call_activities(
        date_from=date_from,
        date_to=date_to,
        event_codes=codes,
        page=page,
        page_size=page_size,
    )

    calls = [normalize_activity(a) for a in result["activities"]]

    if agents:
        agent_set = {a.strip().lower() for a in agents.split(",") if a.strip()}
        calls = [c for c in calls if c["agentName"].lower() in agent_set]
    if prospect_id:
        calls = [c for c in calls if prospect_id.lower() in c["prospectId"].lower()]
    if direction:
        calls = [c for c in calls if c["direction"] == direction]
    if status:
        calls = [c for c in calls if c["status"].lower() == status.lower()]

    # Batch-fetch latest eval score per activity
    activity_ids = [c["activityId"] for c in calls]

    subq = (
        select(
            ThreadEvaluation.thread_id,
            func.max(ThreadEvaluation.id).label("latest_id"),
            func.count(ThreadEvaluation.id).label("eval_count"),
        )
        .join(EvalRun, ThreadEvaluation.run_id == EvalRun.id)
        .where(
            ThreadEvaluation.thread_id.in_(activity_ids),
            EvalRun.tenant_id == auth.tenant_id,
            EvalRun.user_id == auth.user_id,
            EvalRun.app_id == "inside-sales",
            EvalRun.status == "completed",
        )
        .group_by(ThreadEvaluation.thread_id)
        .subquery()
    )

    db_result = await db.execute(
        select(ThreadEvaluation, subq.c.eval_count)
        .join(subq, ThreadEvaluation.id == subq.c.latest_id)
    )
    rows = db_result.all()

    eval_map: dict[str, dict] = {}
    for te, count in rows:
        raw = te.result or {}
        evals = raw.get("evaluations") or []
        score = None
        if evals:
            out = evals[0].get("output") or {}
            score = out.get("overall_score")
            if score is None:
                score = raw.get("output", {}).get("overall_score")
        eval_map[te.thread_id] = {"score": score, "count": count}

    for call in calls:
        info = eval_map.get(call["activityId"], {})
        call["lastEvalScore"] = info.get("score")
        call["evalCount"] = info.get("count", 0)

    return CallListResponse(
        calls=[CallRecord(**c) for c in calls],
        total=result["total"],
        page=page,
        page_size=page_size,
    )


@router.get("/leads/{prospect_id}", response_model=LeadDetailResponse)
async def get_lead(
    prospect_id: str,
    refresh: bool = Query(False, description="Force re-fetch from LSQ"),
    auth: AuthContext = Depends(require_inside_sales_access),
    db: AsyncSession = Depends(get_db),
):
    """Fetch lead details by prospect ID. Cached in DB after first fetch.

    Pass ?refresh=true to force re-fetch from LSQ (resync button).
    """
    from app.models.lsq_call_cache import LsqLeadCache

    # Check DB cache first (unless refresh requested)
    if not refresh:
        result = await db.execute(
            select(LsqLeadCache).where(
                LsqLeadCache.tenant_id == auth.tenant_id,
                LsqLeadCache.prospect_id == prospect_id,
            )
        )
        cached = result.scalar_one_or_none()
        if cached:
            return LeadDetailResponse(
                prospect_id=prospect_id,
                first_name=cached.first_name,
                last_name=cached.last_name,
                phone=cached.phone,
                email=cached.email,
                cached=True,
            )

    # Fetch from LSQ
    lead = await fetch_lead_by_id(prospect_id)

    # Cache the result (upsert)
    try:
        stmt = pg_insert(LsqLeadCache).values(
            id=_uuid.uuid4(),
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            prospect_id=prospect_id,
            first_name=lead.get("FirstName", ""),
            last_name=lead.get("LastName", ""),
            phone=lead.get("Phone", ""),
            email=lead.get("EmailAddress", ""),
        ).on_conflict_do_update(
            constraint="uq_lsq_lead_cache_tenant_prospect",
            set_={
                "first_name": lead.get("FirstName", ""),
                "last_name": lead.get("LastName", ""),
                "phone": lead.get("Phone", ""),
                "email": lead.get("EmailAddress", ""),
            },
        )
        await db.execute(stmt)
        await db.commit()
    except Exception:
        await db.rollback()

    return LeadDetailResponse(
        prospect_id=prospect_id,
        first_name=lead.get("FirstName", ""),
        last_name=lead.get("LastName", ""),
        phone=lead.get("Phone", ""),
        email=lead.get("EmailAddress", ""),
        cached=False,
    )


@router.get("/leads", response_model=LeadListResponse)
async def list_leads(
    date_from: str = Query(..., description="Start date YYYY-MM-DD HH:MM:SS"),
    date_to: str = Query(..., description="End date YYYY-MM-DD HH:MM:SS"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    agents: str | None = Query(None, description="Comma-separated agent names"),
    stage: str | None = Query(None, description="Comma-separated stage values"),
    mql_min: int | None = Query(None, ge=0, le=5, description="Minimum MQL score"),
    condition: str | None = Query(None, description="Comma-separated condition values"),
    city: str | None = Query(None, description="City substring filter"),
    auth: AuthContext = Depends(require_inside_sales_access),
    db: AsyncSession = Depends(get_db),
):
    """Fetch leads from LSQ by CreatedOn range with MQL scoring."""
    result = await fetch_leads(date_from=date_from, date_to=date_to, page=page, page_size=page_size)
    raw_leads = result["leads"]

    # Server-side filters
    if agents:
        agent_set = {a.strip().lower() for a in agents.split(",") if a.strip()}
        raw_leads = [l for l in raw_leads if (l.get("OwnerIdName") or "").lower() in agent_set]
    if stage:
        stage_set = {s.strip().lower() for s in stage.split(",") if s.strip()}
        raw_leads = [l for l in raw_leads if (l.get("ProspectStage") or "").lower() in stage_set]
    if condition:
        cond_set = {c.strip().lower() for c in condition.split(",") if c.strip()}
        raw_leads = [
            l for l in raw_leads
            if any(c in (l.get("mx_utm_disease") or "").lower() for c in cond_set)
        ]
    if city:
        city_lower = city.strip().lower()
        raw_leads = [l for l in raw_leads if city_lower in (l.get("mx_City") or "").lower()]

    records: list[LeadListRecord] = []
    for raw in raw_leads:
        lead = normalize_lead(raw)
        mql_score, mql_signals = compute_mql_score(raw)

        if mql_min is not None and mql_score < mql_min:
            continue

        metrics = compute_lead_metrics(
            created_on=lead["createdOn"],
            last_activity_on=lead["lastActivityOn"],
            rnr_count=lead["rnrCount"],
            answered_count=lead["answeredCount"],
            first_activity_on=lead["firstActivityOn"],
        )

        records.append(LeadListRecord(
            prospect_id=lead["prospectId"],
            first_name=lead["firstName"],
            last_name=lead["lastName"],
            phone=lead["phone"],
            prospect_stage=lead["prospectStage"],
            city=lead["city"],
            age_group=lead["ageGroup"],
            condition=lead["condition"],
            hba1c_band=lead["hba1cBand"],
            intent_to_pay=lead["intentToPay"],
            agent_name=lead["agentName"],
            rnr_count=lead["rnrCount"],
            answered_count=lead["answeredCount"],
            total_dials=metrics["total_dials"],
            connect_rate=metrics["connect_rate"],
            frt_seconds=metrics["frt_seconds"],
            lead_age_days=metrics["lead_age_days"],
            days_since_last_contact=metrics["days_since_last_contact"],
            mql_score=mql_score,
            mql_signals=mql_signals,
            created_on=lead["createdOn"],
            last_activity_on=lead["lastActivityOn"],
            source=lead["source"],
            source_campaign=lead["sourceCampaign"],
        ))

    return LeadListResponse(
        leads=records,
        total=len(records),
        page=page,
        page_size=page_size,
    )


@router.get("/leads/{prospect_id}/detail", response_model=LeadDetailFullResponse)
async def get_lead_detail(
    prospect_id: str,
    auth: AuthContext = Depends(require_inside_sales_access),
    db: AsyncSession = Depends(get_db),
):
    """Full lead drilldown: profile + call history + eval history."""
    # 1. Fetch full lead record
    raw = await fetch_lead_by_id(prospect_id)
    if not raw:
        raise HTTPException(status_code=404, detail="Lead not found")

    lead = normalize_lead(raw)
    mql_score, mql_signals = compute_mql_score(raw)

    # 2. Fetch call history for this prospect
    created_on = lead["createdOn"] or "2020-01-01 00:00:00"
    date_to_now = _dt.now(_tz.utc).strftime("%Y-%m-%d %H:%M:%S")
    raw_activities, history_truncated = await fetch_lead_activities_for_prospect(
        prospect_id=prospect_id,
        date_from=created_on,
        date_to=date_to_now,
    )

    # Normalize activities into LeadCallRecord format
    call_history_raw: list[dict] = []
    for a in raw_activities:
        norm = normalize_activity(a)
        call_history_raw.append({
            "activityId": norm["activityId"],
            "callTime": norm["callStartTime"],
            "agentName": norm["agentName"] or None,
            "durationSeconds": norm["durationSeconds"],
            "status": norm["status"],
            "recordingUrl": norm["recordingUrl"] or None,
            "evalScore": None,   # filled in step 3
            "isCounseling": norm["durationSeconds"] >= 600,
        })

    # 3. Fetch eval scores for calls in history
    activity_ids = [c["activityId"] for c in call_history_raw]
    if activity_ids:
        # Latest ThreadEvaluation per thread_id
        subq = (
            select(
                ThreadEvaluation.thread_id,
                func.max(ThreadEvaluation.id).label("latest_id"),
            )
            .join(EvalRun, ThreadEvaluation.run_id == EvalRun.id)
            .where(
                ThreadEvaluation.thread_id.in_(activity_ids),
                EvalRun.app_id == "inside-sales",
                EvalRun.tenant_id == auth.tenant_id,
                EvalRun.status == "completed",
            )
            .group_by(ThreadEvaluation.thread_id)
            .subquery()
        )
        eval_result = await db.execute(
            select(ThreadEvaluation).join(subq, ThreadEvaluation.id == subq.c.latest_id)
        )
        te_rows = eval_result.scalars().all()

        # Build score map
        score_map: dict[str, float | None] = {}
        for te in te_rows:
            raw_result = te.result or {}
            evals = raw_result.get("evaluations") or []
            score: float | None = None
            if evals:
                out = evals[0].get("output") or {}
                score = out.get("overall_score")
                if score is None:
                    score = raw_result.get("output", {}).get("overall_score")
            score_map[te.thread_id] = score

        for c in call_history_raw:
            if c["activityId"] in score_map:
                c["evalScore"] = score_map[c["activityId"]]

    # 4. Build eval_history (all ThreadEvaluation for this prospect's calls, ordered by id desc)
    eval_history_list: list[dict] = []
    if activity_ids:
        eval_rows_result = await db.execute(
            select(ThreadEvaluation)
            .join(EvalRun, ThreadEvaluation.run_id == EvalRun.id)
            .where(
                ThreadEvaluation.thread_id.in_(activity_ids),
                EvalRun.app_id == "inside-sales",
                EvalRun.tenant_id == auth.tenant_id,
            )
            .order_by(ThreadEvaluation.id.desc())
        )
        for te in eval_rows_result.scalars().all():
            eval_history_list.append({
                "id": str(te.id),
                "threadId": te.thread_id,
                "runId": str(te.run_id),
                "result": te.result,
                "createdAt": str(te.created_at),
            })

    # 5. Compute drilldown metrics
    drilldown_metrics = compute_drilldown_metrics(
        created_on=lead["createdOn"],
        last_activity_on=lead["lastActivityOn"],
        call_history=call_history_raw,
        preferred_call_time_str=lead.get("preferredCallTime"),
    )

    call_history_records = [
        LeadCallRecord(
            activity_id=c["activityId"],
            call_time=c["callTime"],
            agent_name=c["agentName"],
            duration_seconds=c["durationSeconds"],
            status=c["status"],
            recording_url=c["recordingUrl"],
            eval_score=c["evalScore"],
            is_counseling=c["isCounseling"],
        )
        for c in call_history_raw
    ]

    return LeadDetailFullResponse(
        prospect_id=lead["prospectId"],
        first_name=lead["firstName"],
        last_name=lead["lastName"],
        phone=lead["phone"],
        email=lead.get("email"),
        prospect_stage=lead["prospectStage"],
        city=lead["city"],
        age_group=lead["ageGroup"],
        condition=lead["condition"],
        hba1c_band=lead["hba1cBand"],
        blood_sugar_band=lead["bloodSugarBand"],
        diabetes_duration=lead["diabetesDuration"],
        current_management=lead["currentManagement"],
        goal=lead["goal"],
        intent_to_pay=lead["intentToPay"],
        job_title=lead["jobTitle"],
        preferred_call_time=lead["preferredCallTime"],
        agent_name=lead["agentName"],
        source=lead["source"],
        source_campaign=lead["sourceCampaign"],
        created_on=lead["createdOn"],
        mql_score=mql_score,
        mql_signals=mql_signals,
        frt_seconds=drilldown_metrics["frt_seconds"],
        total_dials=drilldown_metrics["total_dials"],
        connect_rate=drilldown_metrics["connect_rate"],
        counseling_count=drilldown_metrics["counseling_count"],
        counseling_rate=drilldown_metrics["counseling_rate"],
        callback_adherence_seconds=drilldown_metrics["callback_adherence_seconds"],
        lead_age_days=drilldown_metrics["lead_age_days"],
        days_since_last_contact=drilldown_metrics["days_since_last_contact"],
        call_history=call_history_records,
        history_truncated=history_truncated,
        eval_history=eval_history_list,
    )

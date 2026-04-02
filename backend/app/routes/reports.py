"""Report generation endpoint."""

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from playwright.async_api import async_playwright
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from app.auth.context import AuthContext, get_auth_context
from app.auth.permissions import require_permission, require_app_access
from app.database import get_db
from app.models.app import App
from app.models.eval_run import EvalRun
from app.models.evaluation_analytics import EvaluationAnalytics
from app.schemas.app_config import AppConfig as AppConfigSchema
from app.schemas.app_analytics_config import AppAnalyticsConfig
from app.schemas.base import CamelModel
from app.services.reports.analytics_profiles.base import AnalyticsProfile
from app.services.reports.analytics_profiles.registry import get_analytics_profile
from app.services.reports.cross_run_aggregator import CrossRunAISummary
from app.services.reports.cross_run_narrator import CrossRunNarrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reports", tags=["reports"])


# --- Response schemas ---

class CrossRunAnalyticsResponse(CamelModel):
    analytics: dict
    computed_at: str
    is_stale: bool
    new_runs_since: int
    source_run_count: int


async def _load_app_analytics_config(
    db: AsyncSession,
    app_id: str,
) -> AppAnalyticsConfig:
    app_row = await db.scalar(
        select(App).where(
            App.slug == app_id,
            App.is_active == True,
        )
    )
    if not app_row:
        raise HTTPException(status_code=404, detail=f"App not found: {app_id}")
    app_config = AppConfigSchema.model_validate(app_row.config or {})
    return app_config.analytics


async def _load_analytics_profile(
    db: AsyncSession,
    app_id: str,
) -> tuple[AppAnalyticsConfig, AnalyticsProfile]:
    analytics_config = await _load_app_analytics_config(db, app_id)
    profile = get_analytics_profile(analytics_config.profile)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Reporting profile is not enabled for app: {app_id}")
    return analytics_config, profile


# --- Cross-run analytics (cached) ---

@router.get("/cross-run-analytics", response_model=CrossRunAnalyticsResponse)
async def get_cross_run_analytics(
    app_id: str = Query(...),
    auth: AuthContext = require_permission('analytics:view'),
    _app_check: AuthContext = require_app_access(),
    db: AsyncSession = Depends(get_db),
):
    """Return cached cross-run analytics scoped to tenant + app_id."""
    analytics_config, profile = await _load_analytics_profile(db, app_id)
    if not analytics_config.capabilities.cross_run_analytics or not profile.cross_run_adapter:
        raise HTTPException(status_code=404, detail=f"Cross-run analytics is not enabled for app: {app_id}")

    result = await db.execute(
        select(EvaluationAnalytics)
        .where(
            EvaluationAnalytics.tenant_id == auth.tenant_id,
            EvaluationAnalytics.app_id == app_id,
            EvaluationAnalytics.scope == "cross_run",
            EvaluationAnalytics.run_id.is_(None),
        )
    )
    cached = result.scalar_one_or_none()

    if not cached:
        raise HTTPException(
            status_code=404,
            detail="No cached cross-run analytics. Use POST /cross-run-analytics/refresh to compute.",
        )

    # Staleness: count single_run caches computed after this cross_run cache
    stale_stmt = (
        select(func.count())
        .select_from(EvaluationAnalytics)
        .where(
            EvaluationAnalytics.tenant_id == auth.tenant_id,
            EvaluationAnalytics.app_id == app_id,
            EvaluationAnalytics.scope == "single_run",
            EvaluationAnalytics.computed_at > cached.computed_at,
        )
    )
    stale_result = await db.execute(stale_stmt)
    new_runs_since = stale_result.scalar() or 0

    analytics = profile.cross_run_adapter.load_cached(cached.analytics_data)

    return CrossRunAnalyticsResponse(
        analytics=analytics.model_dump(by_alias=True),
        computed_at=cached.computed_at.isoformat() if cached.computed_at else "",
        is_stale=new_runs_since > 0,
        new_runs_since=new_runs_since,
        source_run_count=cached.source_run_count or 0,
    )


@router.post("/cross-run-analytics/refresh", response_model=CrossRunAnalyticsResponse)
async def refresh_cross_run_analytics(
    app_id: str = Query(...),
    limit: int = Query(50, ge=1, le=100),
    auth: AuthContext = require_permission('report:generate'),
    _app_check: AuthContext = require_app_access(),
    db: AsyncSession = Depends(get_db),
):
    """Recompute cross-run analytics from single_run caches for user's runs within tenant."""
    analytics_config, profile = await _load_analytics_profile(db, app_id)
    if not analytics_config.capabilities.cross_run_analytics or not profile.cross_run_adapter:
        raise HTTPException(status_code=404, detail=f"Cross-run analytics is not enabled for app: {app_id}")

    # Load single_run analytics rows scoped to tenant
    analytics_stmt = (
        select(EvaluationAnalytics)
        .where(
            EvaluationAnalytics.tenant_id == auth.tenant_id,
            EvaluationAnalytics.app_id == app_id,
            EvaluationAnalytics.scope == "single_run",
        )
        .order_by(desc(EvaluationAnalytics.computed_at))
        .limit(limit)
    )
    analytics_result = await db.execute(analytics_stmt)
    analytics_rows = list(analytics_result.scalars().all())

    if not analytics_rows:
        raise HTTPException(
            status_code=404,
            detail="No completed runs with generated reports found.",
        )

    # Load associated EvalRuns for metadata
    run_ids = [row.run_id for row in analytics_rows if row.run_id]
    runs_by_id: dict[str, EvalRun] = {}
    if run_ids:
        runs_result = await db.execute(
            select(EvalRun)
            .where(EvalRun.id.in_(run_ids))
            .options(load_only(
                EvalRun.id, EvalRun.eval_type, EvalRun.created_at,
                EvalRun.batch_metadata,
            ))
        )
        runs_by_id = {str(r.id): r for r in runs_result.scalars().all()}

    # Total runs count for coverage indicator (scoped to user within tenant)
    count_stmt = (
        select(func.count())
        .select_from(EvalRun)
        .where(
            EvalRun.tenant_id == auth.tenant_id,
            EvalRun.user_id == auth.user_id,
            EvalRun.app_id == app_id,
        )
    )
    count_result = await db.execute(count_stmt)
    all_runs_count = count_result.scalar() or 0

    # Build runs_data tuples for CrossRunAggregator
    runs_data = []
    for row in analytics_rows:
        run_id_str = str(row.run_id) if row.run_id else ""
        run = runs_by_id.get(run_id_str)
        if not run:
            continue
        runs_data.append((
            {
                "id": run_id_str,
                "eval_type": run.eval_type,
                "created_at": run.created_at.isoformat() if run.created_at else "",
                "batch_metadata": run.batch_metadata,
            },
            row.analytics_data,
        ))

    if not runs_data:
        raise HTTPException(
            status_code=404,
            detail="No completed runs with generated reports found.",
        )

    analytics = profile.cross_run_adapter.aggregate(runs_data, all_runs_count)

    now = datetime.now(timezone.utc)

    # Upsert cross_run cache scoped to tenant
    existing_result = await db.execute(
        select(EvaluationAnalytics)
        .where(
            EvaluationAnalytics.tenant_id == auth.tenant_id,
            EvaluationAnalytics.app_id == app_id,
            EvaluationAnalytics.scope == "cross_run",
            EvaluationAnalytics.run_id.is_(None),
        )
    )
    existing = existing_result.scalar_one_or_none()

    analytics_dict = analytics.model_dump()

    if existing:
        existing.analytics_data = analytics_dict
        existing.computed_at = now
        existing.source_run_count = len(runs_data)
    else:
        row = EvaluationAnalytics(
            app_id=app_id,
            scope="cross_run",
            run_id=None,
            analytics_data=analytics_dict,
            computed_at=now,
            source_run_count=len(runs_data),
            tenant_id=auth.tenant_id,
        )
        db.add(row)

    await db.commit()

    return CrossRunAnalyticsResponse(
        analytics=analytics.model_dump(by_alias=True),
        computed_at=now.isoformat(),
        is_stale=False,
        new_runs_since=0,
        source_run_count=len(runs_data),
    )


@router.get("/{run_id}/export-pdf")
async def export_report_pdf(
    run_id: str,
    auth: AuthContext = require_permission('eval:export'),
    _app_check: AuthContext = require_app_access(),
    db: AsyncSession = Depends(get_db),
):
    """Export report as PDF via headless browser rendering of self-contained HTML."""
    # Verify run ownership
    stmt = select(EvalRun).where(
        EvalRun.id == UUID(run_id),
        EvalRun.tenant_id == auth.tenant_id,
        EvalRun.user_id == auth.user_id,
    )
    result = await db.execute(stmt)
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Evaluation run not found")

    # Load cached report from evaluation_analytics
    cache_result = await db.execute(
        select(EvaluationAnalytics.analytics_data)
        .where(
            EvaluationAnalytics.scope == "single_run",
            EvaluationAnalytics.run_id == UUID(run_id),
        )
    )
    cached_data = cache_result.scalar_one_or_none()
    if not cached_data:
        raise HTTPException(
            status_code=400,
            detail="Report has not been generated yet. Generate the report first.",
        )

    analytics_config, profile = await _load_analytics_profile(db, run.app_id)
    if not analytics_config.capabilities.pdf_export or not profile.pdf_renderer or not profile.report_payload_model:
        raise HTTPException(
            status_code=400,
            detail=f"PDF export is not available for app: {run.app_id}",
        )

    # Validate into Pydantic model and re-dump with aliases.
    try:
        payload = profile.report_payload_model.model_validate(cached_data)
        camel_data = payload.model_dump(by_alias=True)
    except Exception:
        logger.warning("Report cache invalid for run %s", run_id)
        raise HTTPException(status_code=400, detail="Cached report data is corrupted.")

    html_content = profile.pdf_renderer(camel_data)

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-gpu"],
            )
            page = await browser.new_page()
            await page.set_content(html_content, wait_until="networkidle")

            pdf_bytes = await page.pdf(
                format="A4",
                print_background=True,
                margin={
                    "top": "12mm",
                    "right": "14mm",
                    "bottom": "12mm",
                    "left": "14mm",
                },
            )
            await browser.close()
    except Exception as e:
        logger.exception("PDF export failed for run %s", run_id)
        raise HTTPException(
            status_code=500,
            detail=f"PDF generation failed: {str(e)}",
        )

    short_id = run_id[:8]
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="eval-report-{short_id}.pdf"',
        },
    )


@router.get("/{run_id}")
async def get_report(
    run_id: str,
    refresh: bool = Query(False, description="Force regeneration, bypassing cache"),
    cache_only: bool = Query(False, description="Only return cached report; 404 if not cached"),
    provider: str | None = Query(None, description="LLM provider for narrative generation"),
    model: str | None = Query(None, description="LLM model for narrative generation"),
    auth: AuthContext = require_permission('analytics:view'),
    _app_check: AuthContext = require_app_access(),
    db: AsyncSession = Depends(get_db),
):
    """Generate an evaluation report for a completed run.

    Returns the report payload (shape varies by app_id). Results are cached
    after first generation; use ?refresh=true to force regeneration.
    Use ?cache_only=true to check for cached data without triggering generation.
    """
    # Verify run ownership
    run = await db.scalar(
        select(EvalRun).where(
            EvalRun.id == UUID(run_id),
            EvalRun.tenant_id == auth.tenant_id,
            EvalRun.user_id == auth.user_id,
        )
    )
    if not run:
        raise HTTPException(status_code=404, detail="Evaluation run not found")

    if cache_only:
        cache_result = await db.execute(
            select(EvaluationAnalytics.analytics_data)
            .where(
                EvaluationAnalytics.scope == "single_run",
                EvaluationAnalytics.run_id == UUID(run_id),
                EvaluationAnalytics.tenant_id == auth.tenant_id,
            )
        )
        cached_data = cache_result.scalar_one_or_none()
        if not cached_data:
            raise HTTPException(status_code=404, detail="No cached report")
        analytics_config, profile = await _load_analytics_profile(db, run.app_id)
        if not analytics_config.capabilities.single_run_report or not profile.report_payload_model:
            raise HTTPException(status_code=404, detail=f"Reporting is not enabled for app: {run.app_id}")
        return profile.report_payload_model.model_validate(cached_data)

    analytics_config, profile = await _load_analytics_profile(db, run.app_id)
    if not analytics_config.capabilities.single_run_report or not profile.report_service_cls:
        raise HTTPException(status_code=404, detail=f"Reporting is not enabled for app: {run.app_id}")
    service = profile.report_service_cls(db, tenant_id=auth.tenant_id, user_id=auth.user_id)

    try:
        return await service.generate(
            run_id,
            force_refresh=refresh,
            llm_provider=provider,
            llm_model=model,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


class CrossRunSummaryRequest(CamelModel):
    app_id: str
    stats: dict
    health_trend: list[dict]
    top_issues: list[dict]
    top_recommendations: list[dict]
    provider: str | None = None
    model: str | None = None


@router.post("/cross-run-ai-summary", response_model=CrossRunAISummary)
async def generate_cross_run_ai_summary(
    request: CrossRunSummaryRequest,
    auth: AuthContext = require_permission('report:generate'),
    _app_check: AuthContext = require_app_access(),
    db: AsyncSession = Depends(get_db),
):
    """Generate AI summary of cross-run analytics."""
    analytics_config, profile = await _load_analytics_profile(db, request.app_id)
    if not analytics_config.capabilities.cross_run_ai_summary:
        raise HTTPException(status_code=404, detail=f"Cross-run AI summary is not enabled for app: {request.app_id}")

    from app.services.evaluators.llm_base import create_llm_provider, LoggingLLMWrapper
    from app.services.evaluators.runner_utils import save_api_log
    from app.services.evaluators.settings_helper import get_llm_settings_from_db

    try:
        settings = await get_llm_settings_from_db(
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            auth_intent="managed_job",
            provider_override=request.provider or None,
        )

        effective_provider = request.provider or settings["provider"]
        effective_model = request.model or settings["selected_model"]

        if not effective_model:
            raise HTTPException(
                status_code=400,
                detail="No LLM model specified. Configure LLM settings or pass provider/model.",
            )

        provider = create_llm_provider(
            provider=effective_provider,
            api_key=settings["api_key"],
            model_name=effective_model,
            service_account_path=settings["service_account_path"],
        )

        llm = LoggingLLMWrapper(provider, log_callback=save_api_log)
        llm.set_context(run_id="cross_run_analytics", thread_id="cross_run_summary")

        narrator_cls = profile.cross_run_summary_narrator_cls or CrossRunNarrator
        narrator = narrator_cls(llm)
        result = await narrator.generate(
            stats=request.stats,
            health_trend=request.health_trend,
            top_issues=request.top_issues,
            top_recommendations=request.top_recommendations,
        )

        if not result:
            raise HTTPException(
                status_code=500,
                detail="AI summary generation failed. Check LLM configuration.",
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Cross-run AI summary failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"AI summary generation failed: {str(e)}",
        )

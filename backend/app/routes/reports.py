"""Report generation endpoint."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.reports import ReportService
from app.services.reports.schemas import ReportPayload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/{run_id}", response_model=ReportPayload)
async def get_report(
    run_id: str,
    refresh: bool = Query(False, description="Force regeneration, bypassing cache"),
    provider: str | None = Query(None, description="LLM provider for narrative generation"),
    model: str | None = Query(None, description="LLM model for narrative generation"),
    db: AsyncSession = Depends(get_db),
):
    """Generate an evaluation report for a completed run.

    Returns the full ReportPayload with metrics, distributions,
    rule compliance, exemplars, and AI narrative. Results are cached
    after first generation; use ?refresh=true to force regeneration.
    """
    service = ReportService(db)
    try:
        return await service.generate(
            run_id,
            force_refresh=refresh,
            llm_provider=provider,
            llm_model=model,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

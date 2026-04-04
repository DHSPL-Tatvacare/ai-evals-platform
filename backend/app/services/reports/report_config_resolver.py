"""Resolve visible report configs for generic report composition."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_config import ReportConfig
from app.services.access_control import readable_scope_clause


async def resolve_report_config(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    app_id: str,
    scope: str,
    report_id: str | None = None,
) -> ReportConfig:
    access_user = type(
        'AccessUser',
        (),
        {
            'tenant_id': tenant_id,
            'user_id': user_id,
            'app_access': frozenset({app_id}),
        },
    )()

    async def _load_selected(selected_report_id: str | None) -> ReportConfig | None:
        stmt = (
            select(ReportConfig)
            .where(
                ReportConfig.app_id == app_id,
                ReportConfig.scope == scope,
                ReportConfig.status == 'active',
                readable_scope_clause(ReportConfig, access_user),
            )
            .order_by(ReportConfig.updated_at.desc())
        )
        if selected_report_id:
            stmt = stmt.where(ReportConfig.report_id == selected_report_id)
        else:
            stmt = stmt.where(ReportConfig.is_default == True)
        return await db.scalar(stmt)

    selected = await _load_selected(report_id)
    if selected is not None and report_id is not None:
        return selected

    fallback = await _load_selected(None)
    if fallback is not None:
        return fallback

    target = report_id or 'default report'
    raise ValueError(f'Report config not found for app {app_id}, scope {scope}, report {target}')

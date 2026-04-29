"""Resolve visible report configs for generic report composition."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_config import ReportConfiguration
from app.services.access_control import readable_scope_clause


async def resolve_report_config(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    app_id: str,
    scope: str,
    report_id: str | None = None,
) -> ReportConfiguration:
    access_user = type(
        'AccessUser',
        (),
        {
            'tenant_id': tenant_id,
            'user_id': user_id,
            'app_access': frozenset({app_id}),
        },
    )()

    async def _load_selected(selected_report_id: str | None) -> ReportConfiguration | None:
        stmt = (
            select(ReportConfiguration)
            .where(
                ReportConfiguration.app_id == app_id,
                ReportConfiguration.scope == scope,
                ReportConfiguration.status == 'active',
                readable_scope_clause(ReportConfiguration, access_user),
            )
            .order_by(ReportConfiguration.updated_at.desc())
        )
        if selected_report_id:
            stmt = stmt.where(ReportConfiguration.report_id == selected_report_id)
        else:
            stmt = stmt.where(ReportConfiguration.is_default == True)
        return await db.scalar(stmt)

    selected = await _load_selected(report_id)
    if selected is not None and report_id is not None:
        return selected

    fallback = await _load_selected(None)
    if fallback is not None:
        return fallback

    target = report_id or 'default report'
    raise ValueError(f'Report config not found for app {app_id}, scope {scope}, report {target}')

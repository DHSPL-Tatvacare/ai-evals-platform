"""App-config gate tests for orchestration analytics endpoints."""

import uuid

import pytest
from fastapi import HTTPException

from app.models.application import Application
from app.services.orchestration.analytics.scope import ensure_orchestration_enabled


def _config(has_orchestration: bool) -> dict:
    return {
        "displayName": "X",
        "icon": "i",
        "description": "d",
        "features": {"hasOrchestration": has_orchestration},
    }


async def _seed_app(db_session, *, enabled: bool) -> str:
    slug = f"analytics-gate-{uuid.uuid4().hex[:8]}"
    db_session.add(
        Application(
            id=uuid.uuid4(),
            slug=slug,
            display_name="X",
            description="d",
            config=_config(enabled),
        )
    )
    await db_session.flush()
    return slug


@pytest.mark.asyncio
async def test_orchestration_enabled_passes(db_session):
    slug = await _seed_app(db_session, enabled=True)
    await ensure_orchestration_enabled(db_session, slug)


@pytest.mark.asyncio
async def test_orchestration_disabled_forbidden(db_session):
    slug = await _seed_app(db_session, enabled=False)
    with pytest.raises(HTTPException) as exc:
        await ensure_orchestration_enabled(db_session, slug)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_missing_app_forbidden(db_session):
    with pytest.raises(HTTPException) as exc:
        await ensure_orchestration_enabled(db_session, "does-not-exist-app")
    assert exc.value.status_code == 403

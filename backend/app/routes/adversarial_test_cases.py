"""Saved adversarial test case routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import AuthContext
from app.auth.permissions import require_permission
from app.database import get_db
from app.schemas.adversarial_test_case import (
    AdversarialSavedTestCaseCreate,
    AdversarialSavedTestCaseResponse,
    AdversarialSavedTestCaseUpdate,
)
from app.services.adversarial_test_case_service import (
    create_saved_test_case,
    get_saved_test_case,
    list_saved_test_cases,
    update_saved_test_case,
)

router = APIRouter(prefix="/api/adversarial-test-cases", tags=["adversarial-test-cases"])


@router.get("", response_model=list[AdversarialSavedTestCaseResponse])
async def list_cases(
    pinned_only: bool = Query(False),
    auth: AuthContext = require_permission("settings:edit"),
    db: AsyncSession = Depends(get_db),
):
    return await list_saved_test_cases(
        db,
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        pinned_only=pinned_only,
    )


@router.post("", response_model=AdversarialSavedTestCaseResponse, status_code=201)
async def create_case(
    body: AdversarialSavedTestCaseCreate,
    auth: AuthContext = require_permission("settings:edit"),
    db: AsyncSession = Depends(get_db),
):
    return await create_saved_test_case(
        db,
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        payload=body,
    )


@router.put("/{case_id}", response_model=AdversarialSavedTestCaseResponse)
async def update_case(
    case_id: UUID,
    body: AdversarialSavedTestCaseUpdate,
    auth: AuthContext = require_permission("settings:edit"),
    db: AsyncSession = Depends(get_db),
):
    record = await get_saved_test_case(
        db,
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        case_id=case_id,
    )
    if not record:
        raise HTTPException(status_code=404, detail="Saved adversarial test case not found")
    return await update_saved_test_case(db, record=record, payload=body)


@router.delete("/{case_id}")
async def delete_case(
    case_id: UUID,
    auth: AuthContext = require_permission("settings:edit"),
    db: AsyncSession = Depends(get_db),
):
    record = await get_saved_test_case(
        db,
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        case_id=case_id,
    )
    if not record:
        raise HTTPException(status_code=404, detail="Saved adversarial test case not found")

    await db.delete(record)
    await db.commit()
    return {"deleted": True, "id": str(case_id)}

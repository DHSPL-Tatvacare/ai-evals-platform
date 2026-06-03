"""Read schemas for the unified evaluation spine (additive; not yet wired to routes — Phase 4)."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from app.schemas.base import CamelORMModel


class EvaluationDetailRead(CamelORMModel):
    id: int
    style: str
    key: str
    label: str | None = None
    score: Decimal | None = None
    max: Decimal | None = None
    status: str | None = None
    severity: str | None = None
    locator: str | None = None
    is_main: bool = False
    weight: Decimal | None = None
    reference_text: str | None = None
    candidate_text: str | None = None
    explanation: str | None = None


class EvaluationRead(CamelORMModel):
    id: uuid.UUID
    run_id: uuid.UUID
    target_id: uuid.UUID
    evaluator_id: uuid.UUID | None = None
    evaluator_ref: dict | None = None
    status: str
    headline_key: str | None = None
    headline_score: Decimal | None = None
    headline_max: Decimal | None = None
    verdict: str | None = None
    reasoning: str | None = None
    created_at: datetime | None = None
    details: list[EvaluationDetailRead] = []


class EvaluationTargetRead(CamelORMModel):
    id: uuid.UUID
    run_id: uuid.UUID
    target_key: str
    target_type: str
    source_ref: str | None = None
    attributes: dict | None = None
    created_at: datetime | None = None
    evaluations: list[EvaluationRead] = []

"""Typed result the runners build and feed to persist_evaluation — the shared write contract."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass
class RunContext:
    """Lightweight run identity persist_evaluation needs (duck-types EvaluationRun)."""
    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    app_id: str


@dataclass
class TargetRef:
    """Identifies the thing judged within a run."""
    key: str
    type: str  # call|chat_thread|transcript|test_case
    source_ref: str | None = None
    attributes: dict | None = None


@dataclass
class EvaluatorRef:
    """Identifies the evaluator that produced the verdict."""
    id: uuid.UUID | None = None
    name: str | None = None
    version: str | None = None
    output_schema_hash: str | None = None

    def as_payload(self) -> dict | None:
        payload = {k: v for k, v in (
            ("name", self.name), ("version", self.version), ("output_schema_hash", self.output_schema_hash),
        ) if v is not None}
        return payload or None


@dataclass
class Headline:
    """Denormalized headline carried on the evaluation row."""
    key: str | None = None
    score: float | None = None
    max: float | None = None
    verdict: str | None = None
    reasoning: str | None = None


@dataclass
class DetailAtom:
    """The universal atom, discriminated by style."""
    style: str  # dimension|rule|comparison
    key: str
    label: str | None = None
    score: float | None = None
    max: float | None = None
    status: str | None = None  # PASS|FAIL|NA (rules)
    severity: str | None = None  # minor|moderate|critical (comparisons)
    locator: str | None = None
    is_main: bool = False
    weight: float | None = None
    reference_text: str | None = None
    candidate_text: str | None = None
    explanation: str | None = None


@dataclass
class EvaluationDraft:
    """One evaluator's verdict on one target, plus its detail atoms."""
    target: TargetRef
    evaluator: EvaluatorRef
    status: str  # ok|error|skipped
    headline: Headline | None = None
    details: list[DetailAtom] = field(default_factory=list)
    raw_payload: dict | None = None

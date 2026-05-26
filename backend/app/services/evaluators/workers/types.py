"""Shared types for the worker contract."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.services.evaluators.llm_base import LoggingLLMWrapper
from app.services.evaluators.selection import EvaluableCall


@dataclass(frozen=True)
class EvaluatorSpec:
    """Frozen view of one evaluator the worker should run against the record."""

    id: uuid.UUID
    name: str
    prompt: str
    output_schema: list[dict[str, Any]]


@dataclass(frozen=True)
class WorkerContext:
    """Per-record context: transcription_llm (audio) + evaluation_llm (text judge,
    also used for the optional transliteration pass), never interchanged."""

    record: EvaluableCall
    evaluators: list[EvaluatorSpec]
    transcription_llm: LoggingLLMWrapper
    evaluation_llm: LoggingLLMWrapper
    transcription_config: dict[str, Any] = field(default_factory=dict)
    tenant_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None


@dataclass(frozen=True)
class EvaluatorOutput:
    """One evaluator's output for one record."""

    evaluator_id: str
    evaluator_name: str
    output: dict[str, Any]
    score: float | None


@dataclass(frozen=True)
class WorkerOutput:
    """The shell-facing result the worker produces per record.

    Shell turns this into one EvaluationRunThreadResult row. Workers do NOT
    write to the database directly; persistence is shell-owned.
    """

    transcript: str | None
    evaluator_outputs: list[EvaluatorOutput]
    signals: list[dict[str, Any]]
    transcript_transliterated: str | None = None
    transliteration_meta: dict[str, Any] | None = None
    extra_metadata: dict[str, Any] = field(default_factory=dict)


__all__ = [
    "EvaluatorOutput",
    "EvaluatorSpec",
    "WorkerContext",
    "WorkerOutput",
]

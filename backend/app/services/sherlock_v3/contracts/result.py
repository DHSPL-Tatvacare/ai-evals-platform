"""SpecialistResult — specialist→supervisor envelope carrying full attempt history + artifacts."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.services.sherlock_v3.contracts.artifact import Artifact
from app.services.sherlock_v3.contracts.brief import Attempt
from app.services.sherlock_v3.contracts.evidence import EvidenceRef


ResultKind = Literal['data', 'retrieval', 'kg', 'action', 'error']
ResultStatus = Literal['ok', 'partial', 'empty', 'needs_clarification', 'error']


class SpecialistMeta(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    confidence: float = 0.0
    latency_ms: int = 0
    source_pack_id: str = ''


class SpecialistResult(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    kind: ResultKind
    status: ResultStatus
    summary: str
    attempts: list[Attempt] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    meta: SpecialistMeta = Field(default_factory=SpecialistMeta)

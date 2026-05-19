"""Sherlock v3 typed contracts — single vocabulary used at every surface."""
from __future__ import annotations

from app.services.sherlock_v3.contracts.artifact import (
    Artifact,
    ArtifactKind,
)
from app.services.sherlock_v3.contracts.bouncer import (
    AvailableJoin,
    Diagnostic,
    ExpectedRowBound,
    JoinKey,
    Verdict,
    VerdictStatus,
)
from app.services.sherlock_v3.contracts.brief import (
    Attempt,
    AttemptStatus,
    SpecialistBrief,
    SpecialistScope,
)
from app.services.sherlock_v3.contracts.evidence import (
    EvidenceRef,
    EvidenceSource,
)
from app.services.sherlock_v3.contracts.parts import (
    AssistantTextPart,
    CallID,
    ChartPart,
    CompactionPart,
    ErrorPart,
    EvidencePart,
    PartID,
    ReasoningPart,
    RetryPart,
    SherlockPart,
    StepFinishPart,
    StepStartPart,
    SubtaskPart,
    ToolPart,
    ToolState,
    ToolStateCompleted,
    ToolStateError,
    ToolStatePending,
    ToolStateRunning,
    UserMessagePart,
    new_part_id,
)
from app.services.sherlock_v3.contracts.result import (
    ResultKind,
    ResultStatus,
    SpecialistMeta,
    SpecialistResult,
    StateDelta,
)
from app.services.sherlock_v3.contracts.synthesis import (
    SYNTHESIS_BRIEF_JSON_SCHEMA,
    SubQuestion,
    SynthesisBrief,
    SynthesisClassification,
    SynthesisTarget,
)


__all__ = [
    # evidence
    'EvidenceRef', 'EvidenceSource',
    # artifact
    'Artifact', 'ArtifactKind',
    # bouncer
    'AvailableJoin', 'Diagnostic', 'ExpectedRowBound', 'JoinKey',
    'Verdict', 'VerdictStatus',
    # brief
    'Attempt', 'AttemptStatus', 'SpecialistBrief', 'SpecialistScope',
    # result
    'ResultKind', 'ResultStatus', 'SpecialistMeta', 'SpecialistResult',
    'StateDelta',
    # synthesis
    'SYNTHESIS_BRIEF_JSON_SCHEMA', 'SubQuestion', 'SynthesisBrief',
    'SynthesisClassification', 'SynthesisTarget',
    # parts
    'AssistantTextPart', 'CallID', 'ChartPart', 'CompactionPart',
    'ErrorPart', 'EvidencePart', 'PartID', 'ReasoningPart', 'RetryPart',
    'SherlockPart', 'StepFinishPart', 'StepStartPart', 'SubtaskPart',
    'ToolPart', 'ToolState', 'ToolStateCompleted', 'ToolStateError',
    'ToolStatePending', 'ToolStateRunning', 'UserMessagePart',
    'new_part_id',
]

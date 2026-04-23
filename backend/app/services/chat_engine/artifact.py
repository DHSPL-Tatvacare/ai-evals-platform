"""Harness-owned artifact + tool-envelope module — Phases 1 and 2.

Sherlock Harness Core carries pack-produced results as opaque ``Artifact``
triples. Harness Core never unpacks ``payload`` or ``extras`` — only the
owning capability pack does. This keeps the outer loop pack-agnostic so
future packs (pgvector, knowledge-graph, clinical workflows, ...) can
contribute artifacts without editing harness files.

Phase 1 stood up the ``Artifact`` dataclass and a minimal
``CAPABILITY_PACK_REGISTRY`` that dispatches by tool name. Phase 2 pins
the §6.2 outcome envelope (``ToolEnvelope``) that every tool handler
returns and through which the outer agent observes every deterministic
decision the backend made. Phase 3 will formalize the full
``CapabilityPack`` Protocol in ``capability_pack.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict, cast

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# §6.2 pinned outcome envelope — the single contract the outer agent sees
# ---------------------------------------------------------------------------


OutcomeKind = Literal[
    'read',
    'write',
    'mutate',
    'discovery',
    'resolution',
    'job_submitted',
    'job_completed',
    'artifact',
    'error',
]

Capability = Literal[
    'analytics',
    'report_builder',
    'vector_retrieval',
    'knowledge_graph',
    'clinical_workflow',
    'harness',
]

Status = Literal['ok', 'partial', 'error']


class ToolCounts(TypedDict, total=False):
    rows: int
    records: int
    affected: int


class ToolJob(TypedDict, total=False):
    id: str
    status: Literal['queued', 'running', 'completed', 'failed', 'cancelled']


class ToolArtifactOutcome(TypedDict, total=False):
    """Outcome-shaped metadata about the artifact the pack emitted.

    ``extras`` is the ONLY slot where a pack may attach outcome-shaped
    metadata (e.g. which chart mark the picker chose, whether a top-N
    degradation was applied). Pack-internal data (rows, spec, summary
    fields) lives in ``ToolEnvelope.payload``, never in ``extras``.
    """

    type: str
    contract: str
    extras: dict[str, Any]


class ToolOutcome(TypedDict, total=False):
    kind: OutcomeKind
    capability: Capability
    reason_code: str | None
    warnings: list[str]
    counts: ToolCounts
    job: ToolJob
    artifact: ToolArtifactOutcome


class ToolEnvelope(TypedDict, total=False):
    """§6.2 envelope — the single contract every tool handler returns."""

    status: Status
    summary: str
    outcome: ToolOutcome
    payload: dict[str, Any]


class ToolCountsModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

    rows: int = 0
    records: int = 0
    affected: int = 0


class ToolJobModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

    id: str
    status: Literal['queued', 'running', 'completed', 'failed', 'cancelled']


class ToolArtifactOutcomeModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

    type: str
    contract: str
    extras: dict[str, Any] = Field(default_factory=dict)


class ToolOutcomeModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

    kind: OutcomeKind
    capability: Capability
    reason_code: str | None = None
    warnings: list[str] = Field(default_factory=list)
    counts: ToolCountsModel = Field(default_factory=ToolCountsModel)
    job: ToolJobModel | None = None
    artifact: ToolArtifactOutcomeModel | None = None


class ToolEnvelopeModel(BaseModel):
    """Pydantic-validated form of the §6.2 tool envelope.

    Handlers return this model via ``build_envelope`` / ``error_envelope``.
    The model also exposes dict-like access so existing code paths can read
    ``result['status']`` / ``result.get('payload')`` without learning a new
    API while Phase 3 hardens the boundary.
    """

    model_config = ConfigDict(extra='forbid')

    status: Status
    summary: str
    outcome: ToolOutcomeModel
    payload: dict[str, Any] = Field(default_factory=dict)

    def as_dict(self) -> ToolEnvelope:
        return cast(ToolEnvelope, self.model_dump(mode='json'))

    def __getitem__(self, key: str) -> Any:
        return self.as_dict()[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.as_dict().get(key, default)

    def keys(self):
        return self.as_dict().keys()

    def items(self):
        return self.as_dict().items()

    def values(self):
        return self.as_dict().values()

    def __contains__(self, key: object) -> bool:
        return key in self.as_dict()

    def __iter__(self):
        return iter(self.as_dict())


def dump_tool_envelope(value: ToolEnvelopeModel | ToolEnvelope) -> ToolEnvelope:
    if isinstance(value, ToolEnvelopeModel):
        return value.as_dict()
    return value


# ---------------------------------------------------------------------------
# Envelope construction helpers (pack-agnostic at this layer)
# ---------------------------------------------------------------------------


def build_envelope(
    *,
    status: Status,
    summary: str,
    kind: OutcomeKind,
    capability: Capability,
    reason_code: str | None = None,
    warnings: list[str] | None = None,
    counts: ToolCounts | None = None,
    job: ToolJob | None = None,
    artifact: ToolArtifactOutcome | None = None,
    payload: dict[str, Any] | None = None,
) -> ToolEnvelopeModel:
    """Construct a §6.2-shaped envelope with sensible defaults.

    Packs call this once per tool return. The dispatcher persists the
    resulting JSON verbatim — no re-wrapping, no prose substitution.
    """

    outcome: ToolOutcome = {
        'kind': kind,
        'capability': capability,
        'reason_code': reason_code,
        'warnings': list(warnings or []),
        'counts': {
            'rows': (counts or {}).get('rows', 0),
            'records': (counts or {}).get('records', 0),
            'affected': (counts or {}).get('affected', 0),
        },
    }
    if job is not None:
        outcome['job'] = job
    if artifact is not None:
        outcome['artifact'] = artifact
    envelope: ToolEnvelope = {
        'status': status,
        'summary': summary,
        'outcome': outcome,
        'payload': payload or {},
    }
    return ToolEnvelopeModel.model_validate(envelope)


def error_envelope(
    *,
    capability: Capability,
    reason_code: str,
    summary: str,
    warnings: list[str] | None = None,
    payload: dict[str, Any] | None = None,
) -> ToolEnvelopeModel:
    """Short-hand for ``kind='error'`` + ``status='error'`` envelope."""

    return build_envelope(
        status='error',
        summary=summary,
        kind='error',
        capability=capability,
        reason_code=reason_code,
        warnings=warnings or [],
        payload=payload,
    )


# ---------------------------------------------------------------------------
# Artifact triple carried on SherlockContext
# ---------------------------------------------------------------------------


@dataclass
class Artifact:
    """Opaque pack-produced artifact carried through Harness Core.

    The harness keeps the triple shape ``(pack_id, contract_id, payload,
    extras)`` and nothing more. Payload and extras are validated by the
    owning pack at egress (Phase 6 will make that strict Pydantic).
    """

    pack_id: str
    contract_id: str
    payload: Any
    extras: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """JSON-safe representation for persisted metadata and SSE events."""
        return {
            'pack_id': self.pack_id,
            'contract_id': self.contract_id,
            'payload': self.payload,
            'extras': self.extras,
        }


@dataclass
class Outcome:
    """Harness dispatcher's view of a pack's tool result.

    Phase 2: built by extracting the artifact slot from the envelope
    returned by the tool handler. The harness never re-reads handler
    internals — the envelope is the canonical source.
    """

    artifact: Artifact | None = None


# ---------------------------------------------------------------------------
# Pack bridge REMOVED (post-Phase 3 cleanup).
#
# Harness Core now delegates all pack dispatch to the single registry in
# ``capability_pack.py`` (plan §6.3 — one pack registry, one contract
# owner). Each concrete ``CapabilityPack`` implements ``build_outcome``
# directly from its own contract-payload-keys mapping. Call sites that
# need a pack-id-by-tool lookup use ``capability_pack.resolve_pack_id_for_tool``.
#
# The deleted surface was: ``_CONTRACT_PAYLOAD_KEYS`` dict,
# ``_CapabilityPackBridge`` class, ``_ANALYTICS_PACK`` / ``_REPORT_BUILDER_PACK``
# module-level instances, ``CAPABILITY_PACK_REGISTRY`` dict, and the
# module-level ``resolve_pack_for`` function.
# ---------------------------------------------------------------------------

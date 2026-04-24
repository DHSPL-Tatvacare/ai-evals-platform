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

# Plan §6.3 rule 5: "Harness Core carries artifacts as opaque tuples". The
# ``capability`` field on an outcome is the pack id that produced the
# result. Pack ids are pluggable (``CAPABILITY_PACK_REGISTRY`` keys), so
# this stays a plain ``str`` at the harness layer. The owning pack is the
# one that knows which literal it uses.
#
# Known in-tree pack ids today (for documentation only, not validation):
#   'analytics', 'report_builder', 'vector_retrieval', 'knowledge_graph',
#   'clinical_workflow', 'harness'
Capability = str

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


# ---------------------------------------------------------------------------
# Phase 1 — generic recovery + state_delta contracts
#
# Both are additive and optional. Packs that do not emit them keep the
# existing envelope shape; the harness merge helpers simply no-op. This
# keeps the §6.2 contract backward compatible while giving the outer
# agent a small, typed signal about whether a non-terminal outcome is
# recoverable, and a small, typed memory patch the scratchpad can apply
# deterministically across turns.
# ---------------------------------------------------------------------------


FailureKind = Literal[
    'none',
    'ambiguous',
    'empty',
    'invalid_reference',
    'unsupported',
    'permission',
    'tool_error',
]


class ToolRecovery(TypedDict, total=False):
    """Small generic classification the outer agent observes post-call."""

    recoverable: bool
    failure_kind: FailureKind


class StateDeltaConfirmedConstraint(TypedDict, total=False):
    key: str
    value: Any
    provenance: str
    source_tool: str
    source_turn_id: str


class StateDeltaGroundedRef(TypedDict, total=False):
    kind: str
    key: str
    value: Any
    provenance: str
    source_tool: str
    source_turn_id: str


class StateDeltaOpenThread(TypedDict, total=False):
    kind: str
    key: str
    message: str


class StateDeltaLastResult(TypedDict, total=False):
    kind: str
    artifact_type: str
    row_count: int
    columns: list[str]
    reason_code: str


class StateDeltaFailureRecord(TypedDict, total=False):
    reason_code: str
    failure_kind: FailureKind
    recoverable: bool
    summary: str


class ToolStateDelta(TypedDict, total=False):
    """Small typed memory patch emitted by a pack alongside an envelope."""

    confirmed_constraints: list[StateDeltaConfirmedConstraint]
    grounded_refs: list[StateDeltaGroundedRef]
    open_threads: list[StateDeltaOpenThread]
    last_result: StateDeltaLastResult
    failure_record: StateDeltaFailureRecord


class ToolEnvelope(TypedDict, total=False):
    """§6.2 envelope — the single contract every tool handler returns.

    Phase 1 adds two optional, additive blocks that packs may emit:

    - ``recovery``: generic outcome classification so the outer agent
      can decide whether to retry / clarify / concede.
    - ``state_delta``: small typed memory patch the harness merges into
      the scratchpad. Packs must not stuff arbitrary internal state
      into this slot; the schema is fixed here.
    """

    status: Status
    summary: str
    outcome: ToolOutcome
    payload: dict[str, Any]
    recovery: ToolRecovery
    state_delta: ToolStateDelta


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


class ToolRecoveryModel(BaseModel):
    """Pydantic form of the generic ``recovery`` classification (Phase 1)."""

    model_config = ConfigDict(extra='forbid')

    recoverable: bool
    failure_kind: FailureKind


class StateDeltaConfirmedConstraintModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

    key: str
    value: Any
    provenance: str
    source_tool: str | None = None
    source_turn_id: str | None = None


class StateDeltaGroundedRefModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

    kind: str
    key: str
    value: Any
    provenance: str
    source_tool: str | None = None
    source_turn_id: str | None = None


class StateDeltaOpenThreadModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

    kind: str
    key: str
    message: str


class StateDeltaLastResultModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

    kind: str
    artifact_type: str | None = None
    row_count: int | None = None
    columns: list[str] | None = None
    reason_code: str | None = None


class StateDeltaFailureRecordModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

    reason_code: str | None = None
    failure_kind: FailureKind
    recoverable: bool
    summary: str | None = None


class ToolStateDeltaModel(BaseModel):
    """Pydantic form of the generic, typed ``state_delta`` memory patch.

    Every sub-field is optional. The harness scratchpad merger applies
    only the fields a pack actually emitted; missing fields are
    preserved untouched.
    """

    model_config = ConfigDict(extra='forbid')

    confirmed_constraints: list[StateDeltaConfirmedConstraintModel] = Field(
        default_factory=list,
    )
    grounded_refs: list[StateDeltaGroundedRefModel] = Field(default_factory=list)
    open_threads: list[StateDeltaOpenThreadModel] = Field(default_factory=list)
    last_result: StateDeltaLastResultModel | None = None
    failure_record: StateDeltaFailureRecordModel | None = None


class ToolEnvelopeModel(BaseModel):
    """Pydantic-validated form of the §6.2 tool envelope.

    Handlers return this model via ``build_envelope`` / ``error_envelope``.
    The model also exposes dict-like access so existing code paths can read
    ``result['status']`` / ``result.get('payload')`` without learning a new
    API while Phase 3 hardens the boundary.

    Phase 1 additions (``recovery`` / ``state_delta``) are optional and
    default to ``None``. Serialization via ``as_dict()`` drops the None
    values so envelopes from packs that do not emit the new fields are
    byte-identical to the pre-Phase-1 shape.
    """

    model_config = ConfigDict(extra='forbid')

    status: Status
    summary: str
    outcome: ToolOutcomeModel
    payload: dict[str, Any] = Field(default_factory=dict)
    recovery: ToolRecoveryModel | None = None
    state_delta: ToolStateDeltaModel | None = None

    def as_dict(self) -> ToolEnvelope:
        # Keep the Phase-1 ``recovery`` / ``state_delta`` fields byte-stable
        # for envelopes that did not set them: omit only those top-level
        # keys when they're ``None``, so existing callers that expect
        # ``outcome.reason_code`` to be present (even when ``None``) stay
        # unchanged. Pre-Phase-1 envelope shape is preserved exactly.
        dumped = self.model_dump(mode='json')
        if self.recovery is None:
            dumped.pop('recovery', None)
        if self.state_delta is None:
            dumped.pop('state_delta', None)
        return cast(ToolEnvelope, dumped)

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
    recovery: ToolRecovery | None = None,
    state_delta: ToolStateDelta | None = None,
) -> ToolEnvelopeModel:
    """Construct a §6.2-shaped envelope with sensible defaults.

    Packs call this once per tool return. The dispatcher persists the
    resulting JSON verbatim — no re-wrapping, no prose substitution.

    Phase 1 adds two optional, additive blocks: ``recovery`` (generic
    outcome classification) and ``state_delta`` (typed memory patch the
    harness merges into the scratchpad).
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
    envelope: dict[str, Any] = {
        'status': status,
        'summary': summary,
        'outcome': outcome,
        'payload': payload or {},
    }
    if recovery is not None:
        envelope['recovery'] = recovery
    if state_delta is not None:
        envelope['state_delta'] = state_delta
    return ToolEnvelopeModel.model_validate(envelope)


def error_envelope(
    *,
    capability: Capability,
    reason_code: str,
    summary: str,
    warnings: list[str] | None = None,
    payload: dict[str, Any] | None = None,
    recovery: ToolRecovery | None = None,
    state_delta: ToolStateDelta | None = None,
) -> ToolEnvelopeModel:
    """Short-hand for ``kind='error'`` + ``status='error'`` envelope.

    Phase 1 ``recovery`` / ``state_delta`` are optional here too so
    packs can attach an open_threads clarification or a failure_record
    alongside an error (e.g. analytics ``SQL_EXPLICIT_ONLY_UNGROUNDED``).
    """

    return build_envelope(
        status='error',
        summary=summary,
        kind='error',
        capability=capability,
        reason_code=reason_code,
        warnings=warnings or [],
        payload=payload,
        recovery=recovery,
        state_delta=state_delta,
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

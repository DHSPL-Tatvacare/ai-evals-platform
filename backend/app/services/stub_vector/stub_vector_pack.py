"""Stub vector-like capability pack — M3 extensibility proof.

Plan §9 walks through what a real pgvector pack will look like. This
module ships that exact shape for a deterministic in-memory "vector"
so the scoped-bundle extension path is proven end-to-end:

- auto-discovered by ``_discover_pack_modules`` (file ends in ``*_pack.py``);
- opt-in per app via ``App.config.chat.capabilities`` containing
  ``'stub_vector'``;
- contributes a ``PackProjection`` to the bundle (projected classes,
  tool specs, bounded enums, and a pack-owned ``semantic_slice``);
- owns its own reason codes, artifact contract, and deterministic
  handler. No DB, no network, no background work.

Zero Harness Core / Bundle / ScopeGuard files are edited to light this
pack up — adding the pack id to ``capabilities`` is the only touch.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from pydantic import BaseModel, Field

from app.services.chat_engine import reason_codes as harness_reason_codes
from app.services.chat_engine.artifact import (
    Artifact,
    Outcome,
    ToolEnvelopeModel,
    build_envelope,
    error_envelope,
)
from app.services.chat_engine.capability_pack import (
    CapabilityPack,
    TypedArgumentError,
    register_pack,
)
from app.services.sherlock.bundle_types import ClassProjection, PackProjection


# ---------------------------------------------------------------------------
# Pack-owned reason codes (plan §6.2.1 — disjoint from every other pack).
# ---------------------------------------------------------------------------


STUB_VECTOR_EMPTY_QUERY = 'STUB_VECTOR_EMPTY_QUERY'
STUB_VECTOR_UNKNOWN_CORPUS = 'STUB_VECTOR_UNKNOWN_CORPUS'

STUB_VECTOR_PACK_REASON_CODES: frozenset[str] = frozenset({
    STUB_VECTOR_EMPTY_QUERY,
    STUB_VECTOR_UNKNOWN_CORPUS,
})


# ---------------------------------------------------------------------------
# Deterministic in-memory "corpora" — frozen at import, no I/O.
# ---------------------------------------------------------------------------


_CORPUS_RUNS: tuple[dict[str, Any], ...] = (
    {
        'chunk_id': 'run-notes/001',
        'text': 'Run kaira smoke completed successfully with 42 judgments recorded.',
    },
    {
        'chunk_id': 'run-notes/002',
        'text': 'Inside sales adversarial batch flagged 3 safety regressions.',
    },
    {
        'chunk_id': 'run-notes/003',
        'text': 'Voice Rx transcription pass failed on noisy audio samples.',
    },
)

_CORPUS_EVIDENCE: tuple[dict[str, Any], ...] = (
    {
        'chunk_id': 'evidence/001',
        'text': 'The evaluator marked the empathy dimension as partial.',
    },
    {
        'chunk_id': 'evidence/002',
        'text': 'Blueprint save confirmed by user; template persisted.',
    },
)

_STUB_CORPORA: Mapping[str, tuple[dict[str, Any], ...]] = {
    'run_notes': _CORPUS_RUNS,
    'evidence': _CORPUS_EVIDENCE,
}


# ---------------------------------------------------------------------------
# Tool spec + schemas
# ---------------------------------------------------------------------------


_STUB_VECTOR_TOOL_SPECS: list[dict[str, Any]] = [
    {
        'name': 'stub_vector_search',
        'description': (
            'Deterministic read-only semantic-similarity stub over a tiny '
            'in-memory corpus. Returns the top-k chunks whose text overlaps '
            'the query tokens — no real embeddings, no I/O. Use this in '
            'tests or demos that need to prove the pack extension path.\n\n'
            '{{output_schema}}\n'
            '{{reason_codes}}\n'
            '{{limitations}}'
        ),
        'inputSchema': {
            'type': 'object',
            'properties': {
                'query': {
                    'type': 'string',
                    'description': 'Free-text query; matched token-wise against corpus chunks.',
                },
                'corpus': {
                    'type': 'string',
                    'enum': sorted(_STUB_CORPORA.keys()),
                    'description': f'One of {sorted(_STUB_CORPORA.keys())}.',
                },
                'top_k': {
                    'type': ['integer', 'null'],
                    'description': 'Optional max chunks to return (1..5). Defaults to 3.',
                },
            },
            'required': ['query', 'corpus'],
        },
    },
]


class _StubVectorHit(BaseModel):
    chunk_id: str
    text: str
    score: float = Field(ge=0.0, le=1.0)


class _StubVectorSearchOutput(BaseModel):
    corpus: str
    hits: list[_StubVectorHit]


_OUTPUT_SCHEMAS: dict[str, type[BaseModel]] = {
    'stub_vector_search': _StubVectorSearchOutput,
}


def _attach_output_schemas() -> None:
    for spec in _STUB_VECTOR_TOOL_SPECS:
        model = _OUTPUT_SCHEMAS.get(spec['name'])
        if model is not None:
            spec['outputSchema'] = model.model_json_schema()


_attach_output_schemas()


_PER_TOOL_REASON_CODES: dict[str, tuple[str, ...]] = {
    'stub_vector_search': (
        STUB_VECTOR_EMPTY_QUERY,
        STUB_VECTOR_UNKNOWN_CORPUS,
    ),
}


_PER_TOOL_LIMITATIONS: dict[str, tuple[str, ...]] = {
    'stub_vector_search': (
        'Deterministic token-overlap score. Not a real embedding model.',
        'Corpora are in-memory constants; no DB or network access.',
    ),
}


# ---------------------------------------------------------------------------
# Artifact contract (plan §9 — projects Artifact.Embedding onto pack storage)
# ---------------------------------------------------------------------------


class StubVectorEvidencePayload(BaseModel):
    """Contract ``stub_vector.evidence.v1`` — the chunks returned to the agent."""

    corpus: str
    hits: list[_StubVectorHit]


class StubVectorEvidenceExtras(BaseModel):
    """Outcome-shaped metadata (pack-internal data stays in payload)."""

    requested_top_k: int
    scored_count: int


# ---------------------------------------------------------------------------
# Handler — deterministic, read-only, no side effects.
# ---------------------------------------------------------------------------


_DEFAULT_TOP_K = 3
_MAX_TOP_K = 5
PACK_CAPABILITY = 'stub_vector'
ARTIFACT_CONTRACT_ID = 'stub_vector.evidence.v1'


def _score(query: str, text: str) -> float:
    """Cheap token-overlap "similarity" — deterministic and bounded [0, 1]."""
    q_tokens = {t for t in query.lower().split() if t}
    if not q_tokens:
        return 0.0
    t_tokens = {t for t in text.lower().split() if t}
    if not t_tokens:
        return 0.0
    overlap = len(q_tokens & t_tokens)
    return overlap / len(q_tokens)


async def handle_stub_vector_search(
    *,
    query: str,
    corpus: str,
    top_k: int | None = None,
    **_kwargs: Any,
) -> ToolEnvelopeModel:
    if not isinstance(query, str) or not query.strip():
        return error_envelope(
            capability=PACK_CAPABILITY,
            reason_code=STUB_VECTOR_EMPTY_QUERY,
            summary='stub_vector_search requires a non-empty query',
            warnings=['query must be a non-empty string'],
            payload={},
        )
    if corpus not in _STUB_CORPORA:
        return error_envelope(
            capability=PACK_CAPABILITY,
            reason_code=STUB_VECTOR_UNKNOWN_CORPUS,
            summary=f'Unknown stub corpus {corpus!r}',
            warnings=[f'corpus must be one of {sorted(_STUB_CORPORA)}'],
            payload={'allowed_corpora': sorted(_STUB_CORPORA)},
        )

    requested = top_k if isinstance(top_k, int) and top_k > 0 else _DEFAULT_TOP_K
    requested = min(requested, _MAX_TOP_K)

    scored = [
        _StubVectorHit(
            chunk_id=row['chunk_id'],
            text=row['text'],
            score=_score(query, row['text']),
        )
        for row in _STUB_CORPORA[corpus]
    ]
    scored.sort(key=lambda h: (-h.score, h.chunk_id))
    hits = scored[:requested]

    payload_model = StubVectorEvidencePayload(corpus=corpus, hits=hits)
    extras_model = StubVectorEvidenceExtras(
        requested_top_k=requested,
        scored_count=len(scored),
    )

    return build_envelope(
        status='ok',
        summary=f'Stub vector returned {len(hits)} chunk(s) from {corpus}',
        kind='artifact',
        capability=PACK_CAPABILITY,
        counts={'rows': 0, 'records': len(hits), 'affected': 0},
        artifact={
            'type': 'vector_evidence',
            'contract': ARTIFACT_CONTRACT_ID,
            'extras': extras_model.model_dump(mode='json'),
        },
        payload={'evidence': payload_model.model_dump(mode='json')},
    )


# ---------------------------------------------------------------------------
# CapabilityPack implementation
# ---------------------------------------------------------------------------


class StubVectorPack:
    """Minimal read-only vector-like pack proving bundle extensibility."""

    pack_id: str = 'stub_vector'
    # Participates in the ``BundleBuilder`` cache key (plan §7). Bump when
    # the corpus or tool surface changes.
    pack_version: str = '2026.04.24'
    reason_codes: frozenset[str] = (
        STUB_VECTOR_PACK_REASON_CODES
        | harness_reason_codes.HARNESS_SHARED_REASON_CODES
    )

    artifact_contracts: Mapping[str, type] = {
        ARTIFACT_CONTRACT_ID: StubVectorEvidencePayload,
    }
    artifact_extras_contracts: Mapping[str, type] = {
        ARTIFACT_CONTRACT_ID: StubVectorEvidenceExtras,
    }

    _CONTRACT_PAYLOAD_KEYS: Mapping[str, str] = {
        ARTIFACT_CONTRACT_ID: 'evidence',
    }

    _tool_names: frozenset[str] = frozenset({
        spec['name'] for spec in _STUB_VECTOR_TOOL_SPECS
    })

    def tool_specs(self) -> Sequence[Mapping[str, Any]]:
        return _STUB_VECTOR_TOOL_SPECS

    def tool_handlers(self) -> Mapping[str, Any]:
        return {
            'stub_vector_search': handle_stub_vector_search,
        }

    def validate_arguments(self, tool_name: str, args: Mapping[str, Any]) -> None:
        if tool_name not in self._tool_names:
            return
        if tool_name == 'stub_vector_search':
            query = args.get('query')
            if not isinstance(query, str) or not query.strip():
                raise TypedArgumentError(
                    STUB_VECTOR_EMPTY_QUERY,
                    'stub_vector_search requires a non-empty query.',
                )
            corpus = args.get('corpus')
            if corpus not in _STUB_CORPORA:
                raise TypedArgumentError(
                    STUB_VECTOR_UNKNOWN_CORPUS,
                    f'stub_vector_search requires corpus in {sorted(_STUB_CORPORA)}.',
                )

    def describe_tools(self, app_id: str) -> Mapping[str, str]:
        from app.services.chat_engine.tool_description_generator import (
            render_pack_tool_descriptions,
        )

        return render_pack_tool_descriptions(self, app_id=app_id)

    def build_outcome(self, tool_name: str, raw_result: Any) -> Outcome:
        if tool_name not in self._tool_names or not isinstance(raw_result, dict):
            return Outcome()
        outcome_block = raw_result.get('outcome') or {}
        artifact_meta = outcome_block.get('artifact') if isinstance(outcome_block, dict) else None
        if not isinstance(artifact_meta, dict):
            return Outcome()
        contract_id = artifact_meta.get('contract')
        if not isinstance(contract_id, str) or not contract_id:
            return Outcome()
        payload_key = self._CONTRACT_PAYLOAD_KEYS.get(contract_id)
        if payload_key is None:
            return Outcome()
        payload_block = raw_result.get('payload') or {}
        payload = payload_block.get(payload_key) if isinstance(payload_block, dict) else None
        if payload is None:
            return Outcome()
        extras = artifact_meta.get('extras') or {}
        if not isinstance(extras, dict):
            extras = {}
        return Outcome(
            artifact=Artifact(
                pack_id=self.pack_id,
                contract_id=contract_id,
                payload=payload,
                extras=extras,
            )
        )

    def describe_job(self, job: Any) -> str:
        from app.services.chat_engine.capability_pack import render_job_line

        return render_job_line(job)

    # ---- tool-description generator accessors ----

    def output_schema(self, tool_name: str) -> type[BaseModel] | None:
        return _OUTPUT_SCHEMAS.get(tool_name)

    def tool_reason_codes(self, tool_name: str) -> Sequence[str]:
        return _PER_TOOL_REASON_CODES.get(tool_name, ())

    def tool_limitations(self, tool_name: str) -> Sequence[str]:
        return _PER_TOOL_LIMITATIONS.get(tool_name, ())

    # ---- Phase 1 / M3 scoped-bundle projection ----

    def contribute_projection(self, scope: Any) -> PackProjection:
        """Project stub-vector ontology classes onto pack-local storage.

        Mirrors the vector-pack walk-through in plan §9: declare the
        ontology classes this pack covers (``Artifact.Embedding``,
        ``Interaction.Evidence``), name the pack-local storage, expose
        the active corpora as a pack-owned ``semantic_slice``, and hand
        the bundle our tool specs + bounded enums. Platform ontology
        still owns cross-pack safety — this pack only projects.
        """

        allowed_corpora = tuple(sorted(_STUB_CORPORA.keys()))
        projected_classes: tuple[ClassProjection, ...] = (
            ClassProjection(
                ontology_class='artifact.embedding',
                storage='stub_vector_chunks',
                identifier_field='chunk_id',
            ),
            ClassProjection(
                ontology_class='interaction.evidence',
                storage='stub_vector_chunks',
                identifier_field='chunk_id',
                contract_id=ARTIFACT_CONTRACT_ID,
            ),
        )

        return PackProjection(
            pack_id=self.pack_id,
            pack_version=self.pack_version,
            projected_classes=projected_classes,
            semantic_slice={
                'corpora': allowed_corpora,
                'chunk_counts': {
                    name: len(rows) for name, rows in _STUB_CORPORA.items()
                },
            },
            tool_specs=tuple(_STUB_VECTOR_TOOL_SPECS),
            tool_schema_enums={'corpus': allowed_corpora},
            question_hints=(
                'Use stub_vector_search for semantic-similarity lookups '
                'over the in-memory run_notes / evidence corpora.'
            ),
        )


_STUB_VECTOR_PACK = StubVectorPack()

# Protocol conformance (fails at import if the class drifts).
_: CapabilityPack = _STUB_VECTOR_PACK

harness_reason_codes.register_pack_reason_codes(
    _STUB_VECTOR_PACK.pack_id,
    _STUB_VECTOR_PACK.reason_codes,
)

register_pack(_STUB_VECTOR_PACK)

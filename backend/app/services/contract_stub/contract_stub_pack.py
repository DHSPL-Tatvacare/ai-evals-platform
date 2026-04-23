"""Concrete ``CapabilityPack`` for the contract-stub proof pack.

Plan §6.3: this pack plugs in through the registry and the generic artifact
lane only. No harness-core file is edited with stub-specific logic.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from pydantic import BaseModel

from app.services.chat_engine import reason_codes as harness_reason_codes
from app.services.chat_engine.artifact import Artifact, Outcome
from app.services.chat_engine.capability_pack import (
    CapabilityPack,
    TypedArgumentError,
    register_pack,
)
from app.services.contract_stub import reason_codes as stub_reason_codes
from app.services.contract_stub import tool_handlers as stub_handlers
from app.services.contract_stub.catalog import TEMPLATE_VARIANTS
from app.services.contract_stub.schemas import (
    StubCapabilitiesOutput,
    StubMakeNoteOutput,
    StubNoteExtras,
    StubNotePayload,
)


# ---------------------------------------------------------------------------
# Tool specs (description templates use the same {{output_schema}},
# {{reason_codes}}, {{limitations}} tokens as every other pack — the
# generator does the single-pass substitution, no pack-crossing reads.)
# ---------------------------------------------------------------------------


_STUB_TOOL_SPECS: list[dict[str, Any]] = [
    {
        'name': 'stub_capabilities',
        'description': (
            'Returns the contract-stub pack self-described limits and variants. '
            'Read-only, deterministic, no arguments.\n\n'
            '{{output_schema}}\n'
            '{{reason_codes}}\n'
            '{{limitations}}'
        ),
        'inputSchema': {
            'type': 'object',
            'properties': {},
            'required': [],
        },
    },
    {
        'name': 'stub_make_note',
        'description': (
            'Deterministically transforms (text, variant) into a note-card '
            'artifact (contract_stub.note.v1). Read-only, no DB writes.\n\n'
            '{{output_schema}}\n'
            '{{reason_codes}}\n'
            '{{limitations}}'
        ),
        'inputSchema': {
            'type': 'object',
            'properties': {
                'text': {
                    'type': 'string',
                    'description': 'Source text to wrap in the note card.',
                },
                'variant': {
                    'type': 'string',
                    'enum': list(TEMPLATE_VARIANTS),
                    'description': f'One of {list(TEMPLATE_VARIANTS)}.',
                },
            },
            'required': ['text', 'variant'],
        },
    },
]


_OUTPUT_SCHEMAS: dict[str, type[BaseModel]] = {
    'stub_capabilities': StubCapabilitiesOutput,
    'stub_make_note': StubMakeNoteOutput,
}


def _attach_output_schemas() -> None:
    for spec in _STUB_TOOL_SPECS:
        model = _OUTPUT_SCHEMAS.get(spec['name'])
        if model is not None:
            spec['outputSchema'] = model.model_json_schema()


_attach_output_schemas()


_PER_TOOL_REASON_CODES: dict[str, tuple[str, ...]] = {
    'stub_capabilities': (),
    'stub_make_note': (
        stub_reason_codes.CONTRACT_STUB_EMPTY_TEXT,
        stub_reason_codes.CONTRACT_STUB_TEXT_TOO_LONG,
        stub_reason_codes.CONTRACT_STUB_UNKNOWN_VARIANT,
    ),
}


_PER_TOOL_LIMITATIONS: dict[str, tuple[str, ...]] = {
    'stub_capabilities': ('Zero-arg read. Returns pack-declared limits only.',),
    'stub_make_note': (
        'Deterministic transform only — no side effects.',
        'text is truncated to the pack-declared MAX_TEXT_LENGTH when emitted.',
    ),
}


class ContractStubPack:
    """Minimal read-only pack proving the harness is reusable."""

    pack_id: str = 'contract_stub'
    reason_codes: frozenset[str] = (
        stub_reason_codes.CONTRACT_STUB_PACK_REASON_CODES
        | harness_reason_codes.HARNESS_SHARED_REASON_CODES
    )
    artifact_contracts: Mapping[str, type] = {
        'contract_stub.note.v1': StubNotePayload,
    }
    artifact_extras_contracts: Mapping[str, type] = {
        'contract_stub.note.v1': StubNoteExtras,
    }

    # Contract id -> ``payload`` sub-key that carries this contract's data.
    _CONTRACT_PAYLOAD_KEYS: Mapping[str, str] = {
        'contract_stub.note.v1': 'note',
    }

    _tool_names: frozenset[str] = frozenset({
        spec['name'] for spec in _STUB_TOOL_SPECS
    })

    def tool_specs(self) -> Sequence[Mapping[str, Any]]:
        return _STUB_TOOL_SPECS

    def tool_handlers(self) -> Mapping[str, Any]:
        return {
            'stub_capabilities': stub_handlers.handle_stub_capabilities,
            'stub_make_note': stub_handlers.handle_stub_make_note,
        }

    def validate_arguments(self, tool_name: str, args: Mapping[str, Any]) -> None:
        if tool_name not in self._tool_names:
            return
        if tool_name == 'stub_make_note':
            text = args.get('text')
            if not isinstance(text, str) or not text.strip():
                raise TypedArgumentError(
                    stub_reason_codes.CONTRACT_STUB_EMPTY_TEXT,
                    'stub_make_note requires non-empty text.',
                )
            variant = args.get('variant')
            if variant not in TEMPLATE_VARIANTS:
                raise TypedArgumentError(
                    stub_reason_codes.CONTRACT_STUB_UNKNOWN_VARIANT,
                    f'stub_make_note requires variant in {list(TEMPLATE_VARIANTS)}.',
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

    # ---- accessors used by the tool-description generator ----

    def output_schema(self, tool_name: str) -> type[BaseModel] | None:
        return _OUTPUT_SCHEMAS.get(tool_name)

    def tool_reason_codes(self, tool_name: str) -> Sequence[str]:
        return _PER_TOOL_REASON_CODES.get(tool_name, ())

    def tool_limitations(self, tool_name: str) -> Sequence[str]:
        return _PER_TOOL_LIMITATIONS.get(tool_name, ())


_CONTRACT_STUB_PACK = ContractStubPack()

# Protocol conformance (fails at import if the class drifts).
_: CapabilityPack = _CONTRACT_STUB_PACK
harness_reason_codes.register_pack_reason_codes(
    _CONTRACT_STUB_PACK.pack_id,
    _CONTRACT_STUB_PACK.reason_codes,
)

register_pack(_CONTRACT_STUB_PACK)

"""Phase 3 — concrete ``CapabilityPack`` for the report builder.

Owns blueprint block catalog + compose/save/list tool specs, handlers,
reason codes, and artifact contract (``report_builder.blueprint.v1``).
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from pydantic import BaseModel

from app.services.chat_engine import reason_codes
from app.services.chat_engine.artifact import Artifact, Outcome
from app.services.chat_engine.capability_pack import (
    CapabilityPack,
    TypedArgumentError,
    register_pack,
)


# ---------------------------------------------------------------------------
# Artifact-extras contract
# ---------------------------------------------------------------------------


class BlueprintArtifactExtras(BaseModel):
    """No outcome-shaped metadata beyond the contract id today."""

    pass


class BlueprintPayloadRef(BaseModel):
    """Placeholder stand-in. Phase 6 replaces this with the strict model."""

    name: str
    sections: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Tool specs (raw templated strings for the generator)
# ---------------------------------------------------------------------------

_REPORT_BUILDER_TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "blueprint_blocks",
        "description": (
            "Returns the available blueprint blocks for report composition. "
            "Optionally scopes to the current app or a specific block type.\n\n"
            "{{output_schema}}\n"
            "{{reason_codes}}\n"
            "{{limitations}}"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "app_id": {
                    "type": ["string", "null"],
                    "description": "Optional application identifier to filter supported blocks.",
                },
                "block_type": {
                    "type": ["string", "null"],
                    "description": "Optional block type to inspect in detail.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "blueprint_compose",
        "description": (
            "Validates a proposed analytics blueprint and returns a preview-ready payload. "
            "Call this when you have a candidate blueprint to show the user.\n\n"
            "{{output_schema}}\n"
            "{{reason_codes}}\n"
            "{{limitations}}"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Human-readable blueprint name.",
                },
                "sections": {
                    "type": "array",
                    "description": "Ordered list of blueprint sections.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {
                                "type": ["string", "null"],
                                "description": "Unique section identifier (e.g. 'custom-compliance').",
                            },
                            "type": {
                                "type": "string",
                                "description": "Section type key from the block catalog.",
                            },
                            "title": {
                                "type": "string",
                                "description": "Display title for this section.",
                            },
                            "variant": {
                                "type": ["string", "null"],
                                "description": "Variant hint for data selection (optional).",
                            },
                        },
                        "required": ["type", "title"],
                    },
                },
            },
            "required": ["name", "sections"],
        },
    },
    {
        "name": "blueprint_save",
        "description": (
            "Persists the current blueprint as a reusable single-run report template. "
            "Only call this when the user explicitly confirms they want to save.\n\n"
            "{{output_schema}}\n"
            "{{reason_codes}}\n"
            "{{limitations}}"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Human-readable name for the saved blueprint.",
                },
                "sections": {
                    "type": "array",
                    "description": "Finalized ordered list of blueprint sections.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": ["string", "null"]},
                            "type": {"type": "string"},
                            "title": {"type": "string"},
                            "variant": {"type": ["string", "null"]},
                        },
                        "required": ["type", "title"],
                    },
                },
            },
            "required": ["name", "sections"],
        },
    },
    {
        "name": "blueprint_list",
        "description": (
            "Lists saved analytics blueprints for the current app. Use this to browse "
            "existing templates before creating a new one.\n\n"
            "{{output_schema}}\n"
            "{{reason_codes}}\n"
            "{{limitations}}"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "app_id": {
                    "type": ["string", "null"],
                    "description": "Optional application identifier (e.g. 'kaira-bot', 'inside-sales').",
                },
            },
            "required": [],
        },
    },
]


# ---------------------------------------------------------------------------
# Output schemas
# ---------------------------------------------------------------------------


class _BlueprintBlocksOutput(BaseModel):
    blocks: list[dict[str, Any]]


class _BlueprintComposeOutput(BaseModel):
    name: str
    sections: list[dict[str, Any]]


class _BlueprintSaveOutput(BaseModel):
    name: str
    saved: bool


class _BlueprintListOutput(BaseModel):
    blueprints: list[dict[str, Any]]


_OUTPUT_SCHEMAS: dict[str, type[BaseModel]] = {
    'blueprint_blocks': _BlueprintBlocksOutput,
    'blueprint_compose': _BlueprintComposeOutput,
    'blueprint_save': _BlueprintSaveOutput,
    'blueprint_list': _BlueprintListOutput,
}


# Plan §6.3 Protocol: every spec MUST carry ``inputSchema`` AND ``outputSchema``.
def _attach_output_schemas() -> None:
    for spec in _REPORT_BUILDER_TOOL_SPECS:
        model = _OUTPUT_SCHEMAS.get(spec['name'])
        if model is not None:
            spec['outputSchema'] = model.model_json_schema()


_attach_output_schemas()


_PER_TOOL_REASON_CODES: dict[str, tuple[str, ...]] = {
    'blueprint_blocks': (),
    'blueprint_compose': (
        'BLUEPRINT_INVALID_SCHEMA',
        'BLUEPRINT_MISSING_REQUIRED_BLOCK',
        'BLUEPRINT_UNKNOWN_BLOCK_TYPE',
    ),
    'blueprint_save': (
        'BLUEPRINT_SAVE_CONFLICT',
        'BLUEPRINT_INVALID_SCHEMA',
    ),
    'blueprint_list': (),
}


_PER_TOOL_LIMITATIONS: dict[str, tuple[str, ...]] = {
    'blueprint_blocks': ('Results limited to the active app’s section catalog.',),
    'blueprint_compose': ('All section types must exist in the block catalog.',),
    'blueprint_save': ('User must explicitly confirm before calling.',),
    'blueprint_list': ('Scoped to the active tenant/app.',),
}


# ---------------------------------------------------------------------------
# CapabilityPack implementation
# ---------------------------------------------------------------------------


class ReportBuilderPack:
    pack_id: str = 'report_builder'
    reason_codes: frozenset[str] = reason_codes.REPORT_BUILDER_REASON_CODES

    artifact_contracts: Mapping[str, type] = {
        'report_builder.blueprint.v1': BlueprintPayloadRef,
    }
    artifact_extras_contracts: Mapping[str, type] = {
        'report_builder.blueprint.v1': BlueprintArtifactExtras,
    }

    # Contract id -> the key inside ``ToolEnvelope.payload`` that carries
    # this contract's data. Pack-owned (plan §6.3 rule 5).
    _CONTRACT_PAYLOAD_KEYS: Mapping[str, str] = {
        'report_builder.blueprint.v1': 'blueprint',
    }

    _tool_names: frozenset[str] = frozenset({
        spec['name'] for spec in _REPORT_BUILDER_TOOL_SPECS
    })

    def tool_specs(self) -> Sequence[Mapping[str, Any]]:
        return _REPORT_BUILDER_TOOL_SPECS

    def tool_handlers(self) -> Mapping[str, Any]:
        from app.services.report_builder import tool_handlers as th

        return {
            'blueprint_blocks': th.handle_blueprint_blocks,
            'blueprint_compose': th.handle_blueprint_compose,
            'blueprint_save': th.handle_blueprint_save,
            'blueprint_list': th.handle_blueprint_list,
        }

    def validate_arguments(self, tool_name: str, args: Mapping[str, Any]) -> None:
        if tool_name not in self._tool_names:
            return
        if tool_name in {'blueprint_compose', 'blueprint_save'}:
            name = args.get('name')
            if not isinstance(name, str) or not name.strip():
                raise TypedArgumentError(
                    reason_codes.MALFORMED_ARGS,
                    f'{tool_name} requires a non-empty name.',
                )
            sections = args.get('sections')
            if not isinstance(sections, list):
                raise TypedArgumentError(
                    reason_codes.BLUEPRINT_INVALID_SCHEMA,
                    f'{tool_name} requires a sections array.',
                )

    def describe_tools(self, app_id: str) -> Mapping[str, str]:
        from app.services.chat_engine.tool_description_generator import render_pack_tool_descriptions

        return render_pack_tool_descriptions(self, app_id=app_id)

    def build_outcome(self, tool_name: str, raw_result: Any) -> Outcome:
        """Build the harness-level ``Outcome`` triple from a parsed envelope.

        Pack-local (plan §6.3 rule 5). Mirrors the analytics pack's
        extraction logic but claims only report-builder-owned tools.
        """
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
        """Phase 7: report-builder-pack rendering of a pending platform job."""
        from app.services.chat_engine.capability_pack import render_job_line

        return render_job_line(job)

    # ---- accessors used by the tool-description generator ----

    def output_schema(self, tool_name: str) -> type[BaseModel] | None:
        return _OUTPUT_SCHEMAS.get(tool_name)

    def tool_reason_codes(self, tool_name: str) -> Sequence[str]:
        return _PER_TOOL_REASON_CODES.get(tool_name, ())

    def tool_limitations(self, tool_name: str) -> Sequence[str]:
        return _PER_TOOL_LIMITATIONS.get(tool_name, ())


_REPORT_BUILDER_PACK = ReportBuilderPack()


_: CapabilityPack = _REPORT_BUILDER_PACK  # Protocol conformance
register_pack(_REPORT_BUILDER_PACK)

"""orchestration.authoring CapabilityPack — Phase 1 skeleton.

Phase 1 ships the pack as the canonical source of truth for tool_specs
and tool_handlers. The v3 `authoring_specialist` imports from here to
construct its FunctionTool list. The boot validator
`validate_all_app_pack_ids` discovers this module via the `*_pack.py`
glob and registers `pack_id='orchestration.authoring'`.

Ownership note: this file's `tool_specs()` / `tool_handlers()` are the
ONLY place tool surface is declared. Edits here automatically flow to
the specialist; do not duplicate tool wiring elsewhere.
"""
from __future__ import annotations

import logging
from typing import Any, Mapping, Sequence

from app.services.chat_engine.artifact import (
    Outcome,
    build_envelope,
)
from app.services.chat_engine.capability_pack import register_pack
from app.services.orchestration_authoring.canvas_patch import (
    CANVAS_PATCH_CONTRACT_ID,
    CanvasPatch,
)


# Phase 3 of the design ships a dedicated `audit.py`; Phase 1 keeps the
# logger named so the call sites land on the right channel from day one.
_log = logging.getLogger('sherlock_v3.authoring')  # noqa: F841 — used by handlers in steps 2/3


PACK_ID = 'orchestration.authoring'


# Pack-scoped reason codes (Decision §R5, plan §Reason codes). Keeping
# these exhaustive at boot lets the boot validator and tests assert the
# shape without spinning up the SDK.
REASON_CODES: frozenset[str] = frozenset({
    'NO_BUILDER_CONTEXT',
    'PERMISSION_DENIED',
    'APP_FORBIDDEN',
    'WORKFLOW_NOT_FOUND',
    'UNKNOWN_NODE_TYPE',
    'NODE_CONFIG_INVALID',
    'PREDICATE_INVALID',
    'GRAPH_INVALID',
    'UUID_NOT_AUTHORIZED',
    'BASE_HASH_MISMATCH',
    'CREDENTIAL_LEAK_BLOCKED',
    'PATCH_OPS_EMPTY',
    'PATCH_TOO_LARGE',
})


class OrchestrationAuthoringPack:
    """Concrete `CapabilityPack` for orchestration authoring tools.

    Phase 1 — skeleton: tool_specs / tool_handlers are intentionally
    empty. Step 2 lands `apply_patch`; Step 3 lands the lookups.
    """

    pack_id: str = PACK_ID
    reason_codes: frozenset[str] = REASON_CODES
    artifact_contracts: Mapping[str, type] = {
        CANVAS_PATCH_CONTRACT_ID: CanvasPatch,
    }
    artifact_extras_contracts: Mapping[str, type] = {}

    def tool_specs(self) -> Sequence[Mapping[str, Any]]:
        """Tool name + JSON-schema specs for the authoring_specialist.

        Empty in Phase 1 Step 1 — Step 2 adds `apply_patch`, Step 3 adds
        the lookups. The specialist consumes this list verbatim to build
        its `FunctionTool(strict_json_schema=True)` instances.
        """
        return ()

    def tool_handlers(self) -> Mapping[str, Any]:
        """Tool name -> async ToolContext handler.

        Each handler is `async def(ctx: ToolContext, args: str) -> str`
        and returns a SpecialistResult JSON string (the same shape the
        v3 data_specialist uses, declared in
        `app.services.sherlock_v3.contracts.SpecialistResult`).
        """
        return {}

    def validate_arguments(self, tool_name: str, args: Mapping[str, Any]) -> None:
        """No-op — strict_json_schema on the SDK side rejects malformed
        arguments before they reach the handler. Per-tool semantic
        validation runs inside each handler against the pack's reason
        codes.
        """
        return None

    def describe_tools(self, app_id: str) -> Mapping[str, str]:
        """One-line tool descriptions per tool name.

        Phase 1 Step 1 is a stub; Step 2/3 fill in once the tools land.
        """
        return {}

    def build_outcome(self, tool_name: str, raw_result: Any) -> Outcome:
        """Convert a handler's raw result into a §6.2 `Outcome`.

        v3 routes the SpecialistResult JSON back through the supervisor
        directly (`extract_authoring_specialist_output` matches strictly
        on `apply_patch`); this method exists to satisfy the
        CapabilityPack Protocol surface used by the older v2 chat engine
        and any future harness auto-wiring. Phase 1 returns a minimal
        envelope.
        """
        envelope = build_envelope(
            status='ok',
            summary=f'{tool_name} ok',
            kind='artifact',
            capability=PACK_ID,
            payload=dict(raw_result) if isinstance(raw_result, dict) else {},
        )
        return envelope.outcome.model_dump()  # type: ignore[return-value]

    def describe_job(self, job: Any) -> str:
        """No async-jobs surface in Phase 1 — fallthrough renderer."""
        from app.services.chat_engine.capability_pack import render_job_line
        return render_job_line(job)


# Register the pack on import; the boot validator discovers this via
# the `*_pack.py` glob in `capability_pack._discover_pack_modules`.
register_pack(OrchestrationAuthoringPack())


__all__ = ['OrchestrationAuthoringPack', 'PACK_ID', 'REASON_CODES']

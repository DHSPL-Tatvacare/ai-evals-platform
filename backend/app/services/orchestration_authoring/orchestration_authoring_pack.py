"""orchestration.authoring CapabilityPack — Phase 1.

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

import json
import logging
import time
from typing import Any, Mapping, Sequence

# Import the orchestration nodes package so @register_node fires.
# Without this, NODE_REGISTRY is empty when the specialist boots in
# isolation (e.g. unit tests) and the node_type enum collapses.
import app.services.orchestration.nodes  # noqa: F401  (registry side-effect)
from app.services.chat_engine.artifact import (
    Outcome,
    build_envelope,
)
from app.services.chat_engine.capability_pack import register_pack
from app.services.orchestration.node_registry import (
    NODE_REGISTRY,
    NodeRegistryError,
    resolve_handler,
)
from app.services.orchestration_authoring.canvas_patch import (
    CANVAS_PATCH_CONTRACT_ID,
    CanvasPatch,
    CanvasPatchOp,
)
from app.services.orchestration_authoring.lookup_models import (
    contains_credential_fields,
)


# Phase 3 of the design ships a dedicated `audit.py`; Phase 1 keeps the
# logger named so the call sites land on the right channel from day one.
authoring_logger = logging.getLogger('sherlock_v3.authoring')


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


# Sanity caps so a confused LLM cannot DoS the canvas applier.
MAX_PATCH_OPS = 50
_VALID_OPS: frozenset[str] = frozenset({
    'add_node', 'update_node_config', 'connect', 'remove_node',
})


# ---------------------------------------------------------------------------
# Tool: apply_patch
# ---------------------------------------------------------------------------


def _node_type_enum() -> list[str]:
    """All node_type strings registered in NODE_REGISTRY, sorted.

    The specialist constructs the JSON schema with this enum so the SDK
    rejects unknown node types before the handler runs (defense in depth
    on top of the resolve_handler check).
    """
    seen: set[str] = set()
    for (_workflow_type, node_type) in NODE_REGISTRY:
        if not node_type.startswith('test.'):
            seen.add(node_type)
    return sorted(seen)


_APPLY_PATCH_SCHEMA: dict[str, Any] = {
    'type': 'object',
    'additionalProperties': False,
    'required': ['ops_json', 'rationale'],
    'properties': {
        'ops_json': {
            'type': 'string',
            'description': (
                "JSON-encoded array of ops. Each op is "
                "{op, node_id, payload}. Op shapes:\n"
                "- add_node: payload = {node_type, position?, config}\n"
                "- update_node_config: payload = {config_patch}\n"
                "- connect: payload = {source_node_id, output_id, target_node_id, edge_id}\n"
                "- remove_node: payload = {}\n"
                "Configs are JSON OBJECTS inside this string, not nested strings."
            ),
        },
        'rationale': {
            'type': 'string',
            'description': 'One-sentence reason; surfaced to the user.',
        },
    },
}


def _result_json(
    *,
    status: str,
    summary: str,
    artifacts: list[dict[str, Any]],
    started: float,
    reason_code: str | None = None,
    detail: dict[str, Any] | None = None,
) -> str:
    """Shape a SpecialistResult JSON identical to data_specialist's contract.

    `kind='action'` is the existing literal in `contracts.ResultKind`
    (no new contract enum).
    """
    meta: dict[str, Any] = {
        'confidence': 0.8 if status == 'ok' else 0.0,
        'latency_ms': int((time.monotonic() - started) * 1000),
        'source_pack_id': PACK_ID,
    }
    if reason_code is not None:
        meta['reason_code'] = reason_code
    if detail is not None:
        meta['detail'] = detail
    return json.dumps({
        'kind': 'action',
        'status': status,
        'summary': summary,
        'evidence': [],
        'artifacts': artifacts,
        'state_delta': {},
        'meta': meta,
    }, default=str)


def _error_result(
    *, reason_code: str, message: str, started: float,
    detail: dict[str, Any] | None = None,
) -> str:
    return _result_json(
        status='error',
        summary=message,
        artifacts=[],
        started=started,
        reason_code=reason_code,
        detail=detail,
    )


def _validate_op_shape(op: Any) -> tuple[CanvasPatchOp | None, str | None]:
    """Cast a raw op dict into `CanvasPatchOp`. Returns (op, error_message)."""
    if not isinstance(op, dict):
        return None, 'each op must be an object'
    op_kind = op.get('op')
    if op_kind not in _VALID_OPS:
        return None, f'unknown op {op_kind!r}'
    node_id = op.get('node_id')
    if not isinstance(node_id, str) or not node_id:
        return None, "op missing 'node_id'"
    try:
        return CanvasPatchOp(
            op=op_kind,
            node_id=node_id,
            payload=op.get('payload') or {},
        ), None
    except Exception as exc:  # pydantic ValidationError; treat as shape error
        return None, f'invalid op shape: {exc}'


def _validate_node_config(
    *,
    workflow_type: str,
    node_type: str,
    config: Any,
) -> tuple[bool, str]:
    """Resolve handler and run config_schema(**config). Returns (ok, error)."""
    try:
        handler = resolve_handler(workflow_type=workflow_type, node_type=node_type)
    except NodeRegistryError:
        return False, f'unknown node_type {node_type!r} for workflow_type {workflow_type!r}'
    if not isinstance(config, dict):
        return False, "'config' must be an object"
    try:
        handler.config_schema(**config)
    except Exception as exc:  # pydantic ValidationError surfaces here
        return False, f'config invalid for {node_type}: {exc}'
    return True, ''


async def _apply_patch_handler(ctx: Any, args: str) -> str:
    """Terminal authoring tool — validate ops + emit one CanvasPatch artifact.

    R3 / R6 / Step-9 hardening (graph preflight, UUID allowlist, egress
    filter) layer on top of this in subsequent steps. Step 2 ships the
    per-op NODE_REGISTRY validation only.
    """
    started = time.monotonic()
    sherlock_ctx = getattr(ctx, 'context', ctx)
    builder_context = getattr(sherlock_ctx, 'builder_context', None)
    auth = getattr(sherlock_ctx, 'auth', None)

    if builder_context is None:
        return _error_result(
            reason_code='NO_BUILDER_CONTEXT',
            message='Authoring tools require an active builder context.',
            started=started,
        )

    # Layered permission re-check (R3). The route gate (R1) and conditional
    # tool inclusion (R2) cover the same ground; this ensures a future bug
    # in either does not bypass the gate.
    if auth is None or 'orchestration:manage' not in getattr(auth, 'permissions', frozenset()):
        return _error_result(
            reason_code='PERMISSION_DENIED',
            message='Missing orchestration:manage permission.',
            started=started,
        )
    if builder_context.app_id not in getattr(auth, 'app_access', frozenset()):
        return _error_result(
            reason_code='APP_FORBIDDEN',
            message=f'No access to app {builder_context.app_id}.',
            started=started,
        )

    try:
        parsed = json.loads(args) if args.strip() else {}
    except json.JSONDecodeError as exc:
        return _error_result(
            reason_code='NODE_CONFIG_INVALID',
            message=f'apply_patch arguments are not valid JSON: {exc}',
            started=started,
        )

    rationale = (parsed.get('rationale') or '').strip()
    raw_ops_json = parsed.get('ops_json')
    if not isinstance(raw_ops_json, str) or not raw_ops_json.strip():
        return _error_result(
            reason_code='PATCH_OPS_EMPTY',
            message='apply_patch requires a non-empty ops_json string.',
            started=started,
        )
    try:
        raw_ops = json.loads(raw_ops_json)
    except json.JSONDecodeError as exc:
        return _error_result(
            reason_code='NODE_CONFIG_INVALID',
            message=f'ops_json is not valid JSON: {exc}',
            started=started,
        )
    if not isinstance(raw_ops, list) or len(raw_ops) == 0:
        return _error_result(
            reason_code='PATCH_OPS_EMPTY',
            message='ops_json must be a non-empty array.',
            started=started,
        )
    if len(raw_ops) > MAX_PATCH_OPS:
        return _error_result(
            reason_code='PATCH_TOO_LARGE',
            message=f'ops_json has {len(raw_ops)} ops; max is {MAX_PATCH_OPS}.',
            started=started,
        )

    workflow_type = builder_context.workflow_type
    validated_ops: list[CanvasPatchOp] = []
    for index, raw_op in enumerate(raw_ops):
        op, shape_err = _validate_op_shape(raw_op)
        if op is None:
            return _error_result(
                reason_code='NODE_CONFIG_INVALID',
                message=f'op[{index}]: {shape_err}',
                started=started,
            )
        if op.op == 'add_node':
            node_type = op.payload.get('node_type')
            if not isinstance(node_type, str) or not node_type:
                return _error_result(
                    reason_code='UNKNOWN_NODE_TYPE',
                    message=f'op[{index}] add_node: payload.node_type required',
                    started=started,
                )
            ok, err = _validate_node_config(
                workflow_type=workflow_type,
                node_type=node_type,
                config=op.payload.get('config') or {},
            )
            if not ok:
                code = (
                    'UNKNOWN_NODE_TYPE'
                    if 'unknown node_type' in err
                    else 'NODE_CONFIG_INVALID'
                )
                return _error_result(
                    reason_code=code,
                    message=f'op[{index}] {err}',
                    started=started,
                )
        elif op.op == 'update_node_config':
            patch = op.payload.get('config_patch')
            if not isinstance(patch, dict):
                return _error_result(
                    reason_code='NODE_CONFIG_INVALID',
                    message=f'op[{index}] update_node_config: payload.config_patch must be an object',
                    started=started,
                )
        elif op.op == 'connect':
            for required in ('source_node_id', 'output_id', 'target_node_id', 'edge_id'):
                if not isinstance(op.payload.get(required), str) or not op.payload.get(required):
                    return _error_result(
                        reason_code='NODE_CONFIG_INVALID',
                        message=f'op[{index}] connect: payload.{required} required',
                        started=started,
                    )
        # remove_node: no payload fields to validate at this layer
        validated_ops.append(op)

    canvas_patch = CanvasPatch(
        workflow_id=str(builder_context.workflow_id),
        version_id=(
            str(builder_context.version_id)
            if builder_context.version_id is not None else None
        ),
        base_data_hash=builder_context.data_hash,
        ops=validated_ops,
        rationale=rationale,
    )

    payload = canvas_patch.model_dump(mode='json')

    # Egress credential filter (R5) — defense in depth even on the patch
    # body. Patches reference connection_ids by UUID; a credential field
    # leaking into a config payload would be a bug, but we catch it here
    # rather than trusting upstream to be clean.
    leaked_field = contains_credential_fields(payload)
    if leaked_field is not None:
        authoring_logger.warning(
            'apply_patch egress filter blocked field=%s tenant=%s app=%s',
            leaked_field,
            getattr(auth, 'tenant_id', None),
            builder_context.app_id,
        )
        return _error_result(
            reason_code='CREDENTIAL_LEAK_BLOCKED',
            message=f'Patch payload contained forbidden field: {leaked_field}',
            started=started,
        )

    artifact = {
        'kind': CANVAS_PATCH_CONTRACT_ID,
        'payload': payload,
    }

    authoring_logger.info(
        'authoring_tool_call tool=apply_patch app_id=%s tenant_id=%s '
        'user_id=%s workflow_id=%s ops=%d duration_ms=%d',
        builder_context.app_id,
        getattr(auth, 'tenant_id', None),
        getattr(auth, 'user_id', None),
        builder_context.workflow_id,
        len(validated_ops),
        int((time.monotonic() - started) * 1000),
    )

    return _result_json(
        status='ok',
        summary=f'Proposed {len(validated_ops)} canvas op(s).',
        artifacts=[artifact],
        started=started,
    )


# ---------------------------------------------------------------------------
# Pack class
# ---------------------------------------------------------------------------


class OrchestrationAuthoringPack:
    """Concrete `CapabilityPack` for orchestration authoring tools."""

    pack_id: str = PACK_ID
    reason_codes: frozenset[str] = REASON_CODES
    artifact_contracts: Mapping[str, type] = {
        CANVAS_PATCH_CONTRACT_ID: CanvasPatch,
    }
    artifact_extras_contracts: Mapping[str, type] = {}

    def tool_specs(self) -> Sequence[Mapping[str, Any]]:
        return (
            {
                'name': 'apply_patch',
                'description': (
                    'Terminal authoring tool. Emit a single CanvasPatch '
                    'with all ops you want to apply this turn. Returns a '
                    'SpecialistResult; on status=error you may regenerate '
                    'and call once more.'
                ),
                'params_json_schema': _APPLY_PATCH_SCHEMA,
            },
        )

    def tool_handlers(self) -> Mapping[str, Any]:
        return {
            'apply_patch': _apply_patch_handler,
        }

    def validate_arguments(self, tool_name: str, args: Mapping[str, Any]) -> None:
        return None

    def describe_tools(self, app_id: str) -> Mapping[str, str]:
        # `app_id` is reserved for per-app vocabulary substitution; the
        # authoring tool surface doesn't depend on it today.
        del app_id
        return {
            'apply_patch': (
                'Propose canvas edits as one CanvasPatch. The user reviews '
                'and saves manually — never claim work is saved or live.'
            ),
        }

    def build_outcome(self, tool_name: str, raw_result: Any) -> Outcome:
        envelope = build_envelope(
            status='ok',
            summary=f'{tool_name} ok',
            kind='artifact',
            capability=PACK_ID,
            payload=dict(raw_result) if isinstance(raw_result, dict) else {},
        )
        return envelope.outcome.model_dump()  # type: ignore[return-value]

    def describe_job(self, job: Any) -> str:
        from app.services.chat_engine.capability_pack import render_job_line
        return render_job_line(job)


# Register the pack on import; the boot validator discovers this via
# the `*_pack.py` glob in `capability_pack._discover_pack_modules`.
register_pack(OrchestrationAuthoringPack())


def node_type_enum() -> list[str]:
    """Public accessor — used by the specialist when bolting the enum
    onto the tool schema."""
    return _node_type_enum()


__all__ = [
    'OrchestrationAuthoringPack',
    'PACK_ID',
    'REASON_CODES',
    'MAX_PATCH_OPS',
    'node_type_enum',
]

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
from app.services.orchestration.definition_normalizer import normalize_definition
from app.services.orchestration.definition_validator import (
    DefinitionValidationError,
    validate_definition,
)
from app.services.orchestration.node_registry import (
    NODE_REGISTRY,
)
from app.services.orchestration_authoring.audit import (
    emit_authoring_event,
    permission_denied_for,
    validation_result_for,
)
from app.services.orchestration_authoring.canvas_patch import (
    CANVAS_PATCH_CONTRACT_ID,
    CanvasPatch,
    CanvasPatchOp,
)
from app.services.orchestration_authoring.connection_resolver import (
    ConnRef,
    resolve_connection_ladder,
)
from app.services.orchestration_authoring.layout import layout_new_nodes
from app.services.orchestration_authoring.lookup_models import (
    ActionTemplateRef,
    ActionTemplatesList,
    CohortDatasetRef,
    CohortDatasetsList,
    NodeTypeRef,
    NodeTypesList,
    ProviderConnectionRef,
    ProviderConnectionsList,
    UpstreamVariables,
    contains_credential_fields,
)
from app.services.orchestration.upstream_variables import (
    UpstreamSourceNotFound,
    resolve_upstream_variables,
)
from app.services.orchestration.api.provider_listings import (
    list_connection_wati_templates,
)
from app.services.orchestration_authoring.template_resolver import match_template
from app.services.orchestration_authoring.patch_coherence import (
    check_bound_fields_carried,
)
from app.schemas.orchestration import (
    WorkflowDefinitionEdge,
    WorkflowDefinitionNode,
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
    'UNKNOWN_OUTCOME',
    'UNKNOWN_EVENT',
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


def _emit_authoring_audit(
    *,
    tool: str,
    builder_context: Any,
    auth: Any,
    started: float,
    reason_code: str | None,
    patch_op_count: int,
) -> None:
    """Stamp one R10 audit line for a tool invocation.

    Caller wraps its body in `try`/`finally` so this fires even on
    unexpected exceptions; the security team's audit trail is the only
    durable trace of authoring activity.
    """
    emit_authoring_event({
        'tool': tool,
        'app_id': str(getattr(builder_context, 'app_id', '') or ''),
        'tenant_id': str(getattr(auth, 'tenant_id', '') or ''),
        'user_id': str(getattr(auth, 'user_id', '') or ''),
        'workflow_id': str(getattr(builder_context, 'workflow_id', '') or ''),
        'patch_op_count': int(patch_op_count),
        'validation_result': validation_result_for(reason_code),
        'permission_denied': permission_denied_for(reason_code),
        'duration_ms': int((time.monotonic() - started) * 1000),
    })


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


# ---------------------------------------------------------------------------
# Graph pre-flight + UUID allowlist
# ---------------------------------------------------------------------------


# Field names inside a node config that reference an external resource
# UUID. Anything appearing under one of these names must have been
# returned by a list_* lookup earlier in the same turn.
_UUID_REFERENCE_KEYS: frozenset[str] = frozenset({
    'connection_id',
    'dataset_version_id',
    'action_template_id',
})


def _walk_uuid_references(payload: Any) -> list[tuple[str, str]]:
    """Yield every (field_name, value) where field_name is in
    `_UUID_REFERENCE_KEYS`. Recursive over dicts and lists.
    """
    out: list[tuple[str, str]] = []

    def _walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, v in value.items():
                if (
                    isinstance(key, str)
                    and key in _UUID_REFERENCE_KEYS
                    and isinstance(v, str) and v
                ):
                    out.append((key, v))
                _walk(v)
        elif isinstance(value, list):
            for item in value:
                _walk(item)

    _walk(payload)
    return out


class PatchTargetMissingError(ValueError):
    """``update_node_config`` / ``remove_node`` targeted a node that does
    not exist in the running candidate (base + prior ``add_node`` ops).

    Surfaced as ``GRAPH_INVALID`` by ``apply_patch``. Raised here instead
    of silently no-op'ing because a missing target is always a
    Sherlock-side bug, never desirable behavior.
    """

    def __init__(self, op_kind: str, node_id: str) -> None:
        self.op_kind = op_kind
        self.node_id = node_id
        super().__init__(f'{op_kind}: target node {node_id!r} does not exist')


def _apply_ops_to_definition(
    *,
    base_definition: dict[str, Any],
    ops: list[CanvasPatchOp],
) -> dict[str, Any]:
    """Replay a CanvasPatch against a copy of the canvas definition.

    Used by ``apply_patch`` to build the candidate definition handed to
    ``validate_definition(mode='draft')``. Mirrors the frontend applier
    semantics:

      - add_node:           append `{id, type, position?, data, config}`
      - update_node_config: shallow-merge `payload.config_patch` into
                            the matching node's `config`
      - connect:            append `{id, source, target, output_id}`
      - remove_node:        drop the node and any edges that touch it

    Raises :class:`PatchTargetMissingError` when ``update_node_config`` or
    ``remove_node`` references a node that does not exist in the running
    candidate. The previous behavior (silently no-op) hid a bug class.
    """
    nodes = list(base_definition.get('nodes') or [])
    edges = list(base_definition.get('edges') or [])

    by_id: dict[str, dict[str, Any]] = {n.get('id'): dict(n) for n in nodes if n.get('id')}
    new_nodes: list[dict[str, Any]] = list(by_id.values())
    new_edges: list[dict[str, Any]] = [dict(e) for e in edges]

    for op in ops:
        if op.op == 'add_node':
            node_type = op.payload.get('node_type')
            new_node = {
                'id': op.node_id,
                'type': node_type,
                'position': op.payload.get('position') or {},
                'data': {},
                'config': dict(op.payload.get('config') or {}),
            }
            by_id[op.node_id] = new_node
            new_nodes.append(new_node)
        elif op.op == 'update_node_config':
            target = by_id.get(op.node_id)
            if target is None:
                raise PatchTargetMissingError('update_node_config', op.node_id)
            cfg = dict(target.get('config') or {})
            cfg.update(op.payload.get('config_patch') or {})
            target['config'] = cfg
        elif op.op == 'connect':
            new_edges.append({
                'id': op.payload.get('edge_id'),
                'source': op.payload.get('source_node_id'),
                'target': op.payload.get('target_node_id'),
                'output_id': op.payload.get('output_id'),
            })
        elif op.op == 'remove_node':
            if op.node_id not in by_id:
                raise PatchTargetMissingError('remove_node', op.node_id)
            by_id.pop(op.node_id, None)
            new_nodes = [n for n in new_nodes if n.get('id') != op.node_id]
            new_edges = [
                e for e in new_edges
                if e.get('source') != op.node_id and e.get('target') != op.node_id
            ]

    return {
        'nodes': new_nodes,
        'edges': new_edges,
        'canvas': base_definition.get('canvas') or {},
    }


def _classify_reason_code(errors: list[dict[str, Any]]) -> str:
    """Map structured ``definition_validator`` errors to a pack reason_code.

    Scans every error and returns the highest-priority match:

      1. ``UNKNOWN_NODE_TYPE`` — any error with ``field == 'type'``. The
         validator emits this only for node-type-resolution failures
         (unknown type, missing type) — both are "Sherlock named a type
         that doesn't work."
      2. ``NODE_CONFIG_INVALID`` — any error with ``field`` starting with
         ``'config'`` (matches ``'config'`` and ``'config.foo'``).
      3. ``GRAPH_INVALID`` — everything else (edges, graph structure).

    Inspecting ``field`` only (never ``message``) keeps the classifier
    decoupled from validator error-message text.
    """
    has_config = False
    for err in errors:
        if not isinstance(err, dict):
            continue
        field = err.get('field') or ''
        if field == 'type':
            return 'UNKNOWN_NODE_TYPE'
        if field == 'config' or field.startswith('config.'):
            has_config = True
    if has_config:
        return 'NODE_CONFIG_INVALID'
    return 'GRAPH_INVALID'


def _walk_predicate_leaves(predicate: Any) -> list[tuple[str, Any]]:
    """Yield every (field, value) leaf in a raw predicate dict.

    Walks the recursive and/or/not wire-shape so a conditional value buried
    under a conjunction is checked, not just top-level leaves.
    """
    out: list[tuple[str, Any]] = []

    def _walk(node: Any) -> None:
        if not isinstance(node, dict):
            return
        if 'field' in node and 'op' in node:
            out.append((node.get('field'), node.get('value')))
            return
        for key in ('and', 'or'):
            branch = node.get(key)
            if isinstance(branch, list):
                for sub in branch:
                    _walk(sub)
        if 'not' in node:
            _walk(node.get('not'))

    _walk(predicate)
    return out


def _check_outcome_event_vocabulary(
    *,
    resolved: Any,
    node_type: str,
    config: dict[str, Any],
) -> tuple[str, str] | None:
    """Value-level guard the per-node ``extra='forbid'`` schema cannot do.

    The schema knows the field names; only the resolver knows whether a
    conditional ``value`` or a wait ``event_name`` is a REAL provider outcome /
    event for THIS canvas. Vocabulary is resolver-owned — never re-derived here.

    Returns ``(reason_code, message)`` on a vocabulary miss, else ``None``.
    For ``logic.conditional``: a predicate leaf whose ``field`` is an
    outcome-bag path must carry a ``value`` in that field's canonical outcome
    set. For ``logic.wait``: ``event_name`` must be a resolved event name.
    """
    if node_type == 'logic.conditional':
        canonicals_by_field: dict[str, set[str]] = {}
        for enum in getattr(resolved, 'outcome_enums', []) or []:
            canonicals_by_field.setdefault(enum.field, set()).add(enum.canonical)
        if not canonicals_by_field:
            return None
        for branch in config.get('branches') or []:
            if not isinstance(branch, dict):
                continue
            for field, value in _walk_predicate_leaves(branch.get('predicate')):
                allowed = canonicals_by_field.get(field)
                if allowed is None:
                    continue  # not an outcome field; schema/predicate own it
                if value not in allowed:
                    return (
                        'UNKNOWN_OUTCOME',
                        f"conditional branches on {field}={value!r} but the "
                        f"upstream producer yields only {sorted(allowed)}. Call "
                        'list_upstream_variables and use a canonical outcome.',
                    )
        return None

    if node_type == 'logic.wait':
        event_name = config.get('event_name')
        if not event_name:
            return None
        allowed_events = {
            ev.event_name for ev in (getattr(resolved, 'events', []) or [])
        }
        if not allowed_events:
            return None
        if event_name not in allowed_events:
            return (
                'UNKNOWN_EVENT',
                f"wait gates on event_name={event_name!r} but the upstream "
                f"producer emits only {sorted(allowed_events)}. Call "
                'list_upstream_variables and use a resolved event name.',
            )
    return None


async def _guard_outcome_event_values(
    *,
    candidate: dict[str, Any],
    authored_node_ids: set[str],
    auth: Any,
    builder_context: Any,
) -> tuple[str, str] | None:
    """Resolve upstream vocabulary for each authored conditional/wait node and
    value-check it. Returns ``(reason_code, message)`` on the first miss.

    Resolves once per authored node (only conditional/wait carry the value
    surfaces this guard owns), reusing the SAME resolver A-Step 1 exposed —
    no vocabulary re-derivation, no hardcoded outcome/event lists.
    """
    targets = [
        n for n in candidate.get('nodes') or []
        if n.get('id') in authored_node_ids
        and n.get('type') in ('logic.conditional', 'logic.wait')
    ]
    if not targets:
        return None

    nodes = [
        WorkflowDefinitionNode.model_validate(n)
        for n in candidate.get('nodes') or []
    ]
    edges = [
        WorkflowDefinitionEdge.model_validate(e)
        for e in candidate.get('edges') or []
    ]

    from app.database import async_session

    async with async_session() as db:
        for node in targets:
            try:
                resolved = await resolve_upstream_variables(
                    db,
                    tenant_id=auth.tenant_id,
                    app_id=builder_context.app_id,
                    workflow_type=builder_context.workflow_type,
                    nodes=nodes,
                    edges=edges,
                    target_node_id=node.get('id'),
                )
            except UpstreamSourceNotFound:
                # No resolvable producer upstream — nothing to value-check
                # against; the draft graph validator already passed.
                continue
            miss = _check_outcome_event_vocabulary(
                resolved=resolved,
                node_type=node.get('type'),
                config=node.get('config') or {},
            )
            if miss is not None:
                return miss
    return None


async def _apply_patch_handler(ctx: Any, args: str) -> str:
    """Terminal authoring tool — validate ops + emit one CanvasPatch artifact.

    Body wrapped in `try`/`finally` so the R10 audit line lands even on
    unexpected exceptions. Every reason_code path stamps `reason_code`
    before returning so the audit row reflects what actually happened.
    """
    started = time.monotonic()
    sherlock_ctx = getattr(ctx, 'context', ctx)
    builder_context = getattr(sherlock_ctx, 'builder_context', None)
    auth = getattr(sherlock_ctx, 'auth', None)
    reason_code: str | None = None
    patch_op_count = 0

    try:
        audit: dict[str, Any] = {'reason_code': None}
        check = await _check_layered_auth(sherlock_ctx, started=started, audit=audit)
        if isinstance(check, str):
            reason_code = audit.get('reason_code')
            return check
        auth, builder_context = check

        try:
            parsed = json.loads(args) if args.strip() else {}
        except json.JSONDecodeError as exc:
            reason_code = 'NODE_CONFIG_INVALID'
            return _error_result(
                reason_code=reason_code,
                message=f'apply_patch arguments are not valid JSON: {exc}',
                started=started,
            )

        rationale = (parsed.get('rationale') or '').strip()
        raw_ops_json = parsed.get('ops_json')
        if not isinstance(raw_ops_json, str) or not raw_ops_json.strip():
            reason_code = 'PATCH_OPS_EMPTY'
            return _error_result(
                reason_code=reason_code,
                message='apply_patch requires a non-empty ops_json string.',
                started=started,
            )
        try:
            raw_ops = json.loads(raw_ops_json)
        except json.JSONDecodeError as exc:
            reason_code = 'NODE_CONFIG_INVALID'
            return _error_result(
                reason_code=reason_code,
                message=f'ops_json is not valid JSON: {exc}',
                started=started,
            )
        if not isinstance(raw_ops, list) or len(raw_ops) == 0:
            reason_code = 'PATCH_OPS_EMPTY'
            return _error_result(
                reason_code=reason_code,
                message='ops_json must be a non-empty array.',
                started=started,
            )
        if len(raw_ops) > MAX_PATCH_OPS:
            reason_code = 'PATCH_TOO_LARGE'
            patch_op_count = len(raw_ops)
            return _error_result(
                reason_code=reason_code,
                message=f'ops_json has {len(raw_ops)} ops; max is {MAX_PATCH_OPS}.',
                started=started,
            )

        workflow_type = builder_context.workflow_type
        validated_ops: list[CanvasPatchOp] = []
        for index, raw_op in enumerate(raw_ops):
            op, shape_err = _validate_op_shape(raw_op)
            if op is None:
                reason_code = 'NODE_CONFIG_INVALID'
                patch_op_count = len(raw_ops)
                return _error_result(
                    reason_code=reason_code,
                    message=f'op[{index}]: {shape_err}',
                    started=started,
                )
            # Envelope-only checks: payload field shapes that the canonical
            # validator can't observe (node_type missing entirely, connect
            # payload missing edge identifiers). Schema and graph rules run
            # once against the post-patch candidate definition below.
            if op.op == 'add_node':
                node_type = op.payload.get('node_type')
                if not isinstance(node_type, str) or not node_type:
                    reason_code = 'UNKNOWN_NODE_TYPE'
                    patch_op_count = len(raw_ops)
                    return _error_result(
                        reason_code=reason_code,
                        message=f'op[{index}] add_node: payload.node_type required',
                        started=started,
                    )
                config = op.payload.get('config')
                if config is not None and not isinstance(config, dict):
                    reason_code = 'NODE_CONFIG_INVALID'
                    patch_op_count = len(raw_ops)
                    return _error_result(
                        reason_code=reason_code,
                        message=f"op[{index}] add_node: 'config' must be an object",
                        started=started,
                    )
            elif op.op == 'update_node_config':
                patch = op.payload.get('config_patch')
                if not isinstance(patch, dict):
                    reason_code = 'NODE_CONFIG_INVALID'
                    patch_op_count = len(raw_ops)
                    return _error_result(
                        reason_code=reason_code,
                        message=f'op[{index}] update_node_config: payload.config_patch must be an object',
                        started=started,
                    )
            elif op.op == 'connect':
                for required in ('source_node_id', 'output_id', 'target_node_id', 'edge_id'):
                    if not isinstance(op.payload.get(required), str) or not op.payload.get(required):
                        reason_code = 'NODE_CONFIG_INVALID'
                        patch_op_count = len(raw_ops)
                        return _error_result(
                            reason_code=reason_code,
                            message=f'op[{index}] connect: payload.{required} required',
                            started=started,
                        )
            # remove_node: no payload fields to validate at this layer
            validated_ops.append(op)
        patch_op_count = len(validated_ops)

        # ── R6: per-turn UUID allowlist enforcement ──────────────────────
        scratch = getattr(sherlock_ctx, 'scratch', {}) or {}
        authorized = scratch.get('authorized_uuids')
        if not isinstance(authorized, set):
            authorized = set(authorized or [])
        for op in validated_ops:
            for field, value in _walk_uuid_references(op.payload):
                if value not in authorized:
                    authoring_logger.warning(
                        'apply_patch UUID_NOT_AUTHORIZED field=%s value=%s '
                        'tenant=%s app=%s',
                        field, value,
                        getattr(auth, 'tenant_id', None),
                        builder_context.app_id,
                    )
                    reason_code = 'UUID_NOT_AUTHORIZED'
                    return _error_result(
                        reason_code=reason_code,
                        message=(
                            f'Patch references {field}={value} but no list_* '
                            'tool returned that UUID this turn.'
                        ),
                        started=started,
                    )

        # ── Canonical draft validation ──────────────────────────────────
        # Apply ops to the current canvas, normalize, and run the same
        # validator the publish path uses but in draft mode. This is the
        # ONE source of truth for "is this canvas legal" — no separate
        # draft-only schema, no per-op duplicate validation. The applier
        # raises ``PatchTargetMissingError`` when an update / remove op
        # targets a node that does not exist; we map that to GRAPH_INVALID
        # before reaching the validator.
        try:
            patched = _apply_ops_to_definition(
                base_definition=builder_context.definition or {},
                ops=validated_ops,
            )
        except PatchTargetMissingError as exc:
            reason_code = 'GRAPH_INVALID'
            return _error_result(
                reason_code=reason_code,
                message=str(exc),
                started=started,
                detail={'errors': [{
                    'node_id': exc.node_id,
                    'field': 'node_id',
                    'message': f'{exc.op_kind} target does not exist',
                }]},
            )
        candidate = normalize_definition(patched)
        try:
            validate_definition(
                candidate,
                workflow_type=workflow_type,
                mode='draft',
            )
        except DefinitionValidationError as exc:
            reason_code = _classify_reason_code(exc.errors)
            return _error_result(
                reason_code=reason_code,
                message='Patched canvas failed draft validation.',
                started=started,
                detail={'errors': exc.errors},
            )

        # ── Value-level outcome/event vocabulary guard ───────────────────
        # The per-node schema is extra='forbid' but cannot know whether a
        # conditional value / wait event_name is a real provider outcome /
        # event for THIS canvas. Resolve the producer vocabulary and reject
        # invented strings at author time instead of silently at runtime.
        authored_node_ids = {
            op.node_id for op in validated_ops
            if op.op in ('add_node', 'update_node_config')
        }
        vocab_miss = await _guard_outcome_event_values(
            candidate=candidate,
            authored_node_ids=authored_node_ids,
            auth=auth,
            builder_context=builder_context,
        )
        if vocab_miss is not None:
            reason_code, message = vocab_miss
            return _error_result(
                reason_code=reason_code,
                message=message,
                started=started,
            )

        # A payload-bound dispatch field must be carried by its direct upstream
        # source; an uncarried field resolves to "" silently at runtime.
        carry_violations = check_bound_fields_carried(candidate)
        if carry_violations:
            reason_code = 'NODE_CONFIG_INVALID'
            return _error_result(
                reason_code=reason_code,
                message='; '.join(carry_violations)
                + '. Add the field to the upstream source.cohort.payload_fields.',
                started=started,
            )

        # ── Deterministic auto-layout for NEW nodes ──────────────────────
        # The agent never hand-places nodes. Assign positions for add_node
        # ops by topological depth, anchored below/right of existing nodes,
        # and write them back onto the emitted ops. Existing nodes keep their
        # positions; we emit no position ops for them.
        added_node_ids = {op.node_id for op in validated_ops if op.op == 'add_node'}
        if added_node_ids:
            existing_positions = {
                n.get('id'): dict(n.get('position') or {})
                for n in (builder_context.definition or {}).get('nodes') or []
                if n.get('id')
            }
            placed = layout_new_nodes(
                nodes=candidate.get('nodes') or [],
                edges=candidate.get('edges') or [],
                new_node_ids=added_node_ids,
                existing_positions=existing_positions,
            )
            for op in validated_ops:
                if op.op == 'add_node' and op.node_id in placed:
                    op.payload['position'] = placed[op.node_id]

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
            reason_code = 'CREDENTIAL_LEAK_BLOCKED'
            return _error_result(
                reason_code=reason_code,
                message=f'Patch payload contained forbidden field: {leaked_field}',
                started=started,
            )

        artifact = {
            'kind': CANVAS_PATCH_CONTRACT_ID,
            'payload': payload,
        }

        return _result_json(
            status='ok',
            summary=f'Proposed {len(validated_ops)} canvas op(s).',
            artifacts=[artifact],
            started=started,
        )
    finally:
        _emit_authoring_audit(
            tool='apply_patch',
            builder_context=builder_context,
            auth=auth,
            started=started,
            reason_code=reason_code,
            patch_op_count=patch_op_count,
        )


# ---------------------------------------------------------------------------
# Lookup tools — tenant + app scoped (R4) and credential-stripped (R5)
# ---------------------------------------------------------------------------


_LIST_PROVIDER_CONNECTIONS_SCHEMA: dict[str, Any] = {
    'type': 'object',
    'additionalProperties': False,
    'required': ['provider'],
    'properties': {
        'provider': {
            'type': 'string',
            'enum': ['wati', 'bolna', 'sms', 'lsq', 'msg91', 'aisensy'],
            'description': 'Provider type to filter on.',
        },
    },
}

_LIST_ACTION_TEMPLATES_SCHEMA: dict[str, Any] = {
    'type': 'object',
    'additionalProperties': False,
    'required': ['channel'],
    'properties': {
        'channel': {
            'type': 'string',
            'description': "Channel slug (e.g. 'whatsapp', 'voice', 'sms', 'lsq').",
        },
    },
}

_LIST_COHORT_DATASETS_SCHEMA: dict[str, Any] = {
    'type': 'object',
    'additionalProperties': False,
    'properties': {},
}

_RESOLVE_TEMPLATE_SCHEMA: dict[str, Any] = {
    'type': 'object',
    'additionalProperties': False,
    'required': ['connection_id', 'intent'],
    'properties': {
        'connection_id': {
            'type': 'string',
            'description': (
                'WhatsApp (WATI) provider connection UUID. MUST have been '
                'returned by list_provider_connections / resolve_connection '
                'earlier this turn.'
            ),
        },
        'intent': {
            'type': 'string',
            'description': (
                'Free-text description of the WhatsApp template to use '
                '(e.g. its name or what it says).'
            ),
        },
    },
}

_RESOLVE_CONNECTION_SCHEMA: dict[str, Any] = {
    'type': 'object',
    'additionalProperties': False,
    'required': ['channel'],
    'properties': {
        'channel': {
            'type': 'string',
            'description': "Channel slug (e.g. 'whatsapp', 'voice').",
        },
        'hint': {
            'type': 'string',
            'description': (
                'Optional free-text hint (provider name or connection name) '
                'to disambiguate when the app has several connections.'
            ),
        },
    },
}

_LIST_COHORT_FIELDS_SCHEMA: dict[str, Any] = {
    'type': 'object',
    'additionalProperties': False,
    'required': ['source_ref'],
    'properties': {
        'source_ref': {
            'type': 'string',
            'description': (
                "Cohort source key (e.g. 'crm.lead_record', "
                "'clinical.dim_patient'). Returns each field's name, type, "
                'allowed values, PII flag, and whether it is filterable.'
            ),
        },
    },
}

_MAP_TEMPLATE_VARIABLES_SCHEMA: dict[str, Any] = {
    'type': 'object',
    'additionalProperties': False,
    'required': ['placeholders', 'source_ref'],
    'properties': {
        'placeholders': {
            'type': 'array',
            'items': {'type': 'string'},
            'description': (
                'Template placeholder names to match (e.g. from a resolved '
                'WhatsApp template). Each is bound to a cohort field or '
                'returned as unmatched.'
            ),
        },
        'source_ref': {
            'type': 'string',
            'description': (
                "Cohort source key (e.g. 'crm.lead_record') whose fields are "
                'matched against the placeholders.'
            ),
        },
    },
}

_LIST_NODE_TYPES_SCHEMA: dict[str, Any] = {
    'type': 'object',
    'additionalProperties': False,
    'properties': {
        'category': {
            'type': 'string',
            'description': "Optional category filter (e.g. 'source', 'sink').",
        },
    },
}

_LIST_UPSTREAM_VARIABLES_SCHEMA: dict[str, Any] = {
    'type': 'object',
    'additionalProperties': False,
    'required': ['target_node_id'],
    'properties': {
        'target_node_id': {
            'type': 'string',
            'description': (
                'Id of the node to resolve upstream variables for. Resolution '
                'walks the current canvas backward from this node.'
            ),
        },
    },
}


def _record_authorized_uuids(scratch: dict[str, Any], uuids: list[str]) -> None:
    """Add returned UUIDs to the per-turn allowlist (R6).

    `apply_patch` will reject any patch whose connection_id /
    dataset_version_id / action_template_id is not in this set. Step 9
    enforces; lookups populate.
    """
    bucket = scratch.setdefault('authorized_uuids', set())
    if not isinstance(bucket, set):
        bucket = set(bucket)
        scratch['authorized_uuids'] = bucket
    for value in uuids:
        if value:
            bucket.add(str(value))


def _lookup_result_json(
    *,
    started: float,
    summary: str,
    payload: dict[str, Any],
    tool_name: str,
) -> str:
    """Wrap a lookup result in the SpecialistResult shape.

    Lookups don't emit artifacts — the supervisor consumes the payload
    directly. Putting them under SpecialistResult keeps the
    custom_output_extractor's "match by tool name" contract intact and
    makes the audit log uniform.
    """
    leaked = contains_credential_fields(payload)
    if leaked is not None:
        authoring_logger.warning(
            'lookup egress filter blocked tool=%s field=%s', tool_name, leaked,
        )
        return _error_result(
            reason_code='CREDENTIAL_LEAK_BLOCKED',
            message=f'Lookup result contained forbidden field: {leaked}',
            started=started,
        )
    meta: dict[str, Any] = {
        'confidence': 1.0,
        'latency_ms': int((time.monotonic() - started) * 1000),
        'source_pack_id': PACK_ID,
        'tool': tool_name,
    }
    return json.dumps({
        'kind': 'data',
        'status': 'ok',
        'summary': summary,
        'evidence': [],
        'artifacts': [],
        'meta': meta,
        'payload': payload,
    }, default=str)


async def _assert_builder_workflow_still_owned(
    *,
    builder_context: Any,
    auth: Any,
) -> str:
    """Re-read workflow ownership at tool time and return its app_id."""
    from app.database import async_session
    from app.services.orchestration_authoring.tenant_guard import assert_workflow_owned

    async with async_session() as db:
        workflow = await assert_workflow_owned(
            db,
            workflow_id=builder_context.workflow_id,
            auth=auth,
        )
    return str(workflow.app_id)


async def _check_layered_auth(
    sherlock_ctx: Any,
    *,
    started: float,
    audit: dict[str, Any],
) -> tuple[Any, Any] | str:
    """Re-run R3 checks. Returns (auth, builder_context) or an error JSON.

    `audit` is mutated in place: on failure paths, `audit['reason_code']`
    is stamped before the error JSON is returned so the caller's
    `try/finally` audit emit picks up the right validation_result.
    """
    builder_context = getattr(sherlock_ctx, 'builder_context', None)
    auth = getattr(sherlock_ctx, 'auth', None)
    if builder_context is None:
        audit['reason_code'] = 'NO_BUILDER_CONTEXT'
        return _error_result(
            reason_code='NO_BUILDER_CONTEXT',
            message='Authoring tools require an active builder context.',
            started=started,
        )
    if getattr(builder_context, 'view_mode', None) != 'edit':
        audit['reason_code'] = 'PERMISSION_DENIED'
        return _error_result(
            reason_code='PERMISSION_DENIED',
            message='Builder is read-only. Switch to edit mode before changing the canvas.',
            started=started,
        )
    # Owner role bypass via canonical helper (matches `_lookup_handler`
    # block above; see comment there).
    from app.auth.permissions import missing_permissions as _missing_perms_apply
    if auth is None or _missing_perms_apply(auth, 'orchestration:manage'):
        audit['reason_code'] = 'PERMISSION_DENIED'
        return _error_result(
            reason_code='PERMISSION_DENIED',
            message='Missing orchestration:manage permission.',
            started=started,
        )
    if builder_context.app_id not in getattr(auth, 'app_access', frozenset()):
        audit['reason_code'] = 'APP_FORBIDDEN'
        return _error_result(
            reason_code='APP_FORBIDDEN',
            message=f'No access to app {builder_context.app_id}.',
            started=started,
        )
    from fastapi import HTTPException

    try:
        workflow_app_id = await _assert_builder_workflow_still_owned(
            builder_context=builder_context,
            auth=auth,
        )
    except HTTPException as exc:
        if exc.status_code == 404:
            audit['reason_code'] = 'WORKFLOW_NOT_FOUND'
            return _error_result(
                reason_code='WORKFLOW_NOT_FOUND',
                message='Workflow not found.',
                started=started,
            )
        raise
    if workflow_app_id != builder_context.app_id:
        audit['reason_code'] = 'APP_FORBIDDEN'
        return _error_result(
            reason_code='APP_FORBIDDEN',
            message=f'Workflow does not belong to app {builder_context.app_id}.',
            started=started,
        )
    return auth, builder_context


def _mark_leak_in_result(audit: dict[str, Any], result: str) -> str:
    """Mirror a CREDENTIAL_LEAK_BLOCKED reason_code from the lookup
    result JSON into the audit dict, so the caller's `finally` emit
    records the right validation_result. Returns the original result
    untouched so callers can pass it straight back to the SDK."""
    try:
        decoded = json.loads(result)
        meta = decoded.get('meta') if isinstance(decoded, dict) else None
        if isinstance(meta, dict) and meta.get('reason_code') == 'CREDENTIAL_LEAK_BLOCKED':
            audit['reason_code'] = 'CREDENTIAL_LEAK_BLOCKED'
    except (ValueError, AttributeError):
        pass
    return result


async def _list_node_types_handler(ctx: Any, args: str) -> str:
    started = time.monotonic()
    sherlock_ctx = getattr(ctx, 'context', ctx)
    audit: dict[str, Any] = {'reason_code': None}
    builder_context = getattr(sherlock_ctx, 'builder_context', None)
    auth = getattr(sherlock_ctx, 'auth', None)
    try:
        check = await _check_layered_auth(sherlock_ctx, started=started, audit=audit)
        if isinstance(check, str):
            return check
        parsed = json.loads(args) if args.strip() else {}
        category_filter = (parsed.get('category') or '').strip() or None

        items: list[NodeTypeRef] = []
        seen: dict[str, NodeTypeRef] = {}
        for (workflow_type, node_type), handler in NODE_REGISTRY.items():
            if node_type.startswith('test.'):
                continue
            if category_filter and getattr(handler, 'category', '') != category_filter:
                continue
            ref = seen.get(node_type)
            if ref is None:
                ref = NodeTypeRef(
                    node_type=node_type,
                    category=str(getattr(handler, 'category', '')),
                    workflow_types=[workflow_type],
                    output_edges=list(getattr(handler, 'output_edges', []) or []),
                )
                seen[node_type] = ref
                items.append(ref)
            else:
                if workflow_type not in ref.workflow_types:
                    ref.workflow_types.append(workflow_type)

        payload = NodeTypesList(items=items).model_dump(mode='json')
        return _mark_leak_in_result(audit, _lookup_result_json(
            started=started,
            summary=f'{len(items)} node type(s) available.',
            payload=payload,
            tool_name='list_node_types',
        ))
    finally:
        _emit_authoring_audit(
            tool='list_node_types',
            builder_context=builder_context,
            auth=auth,
            started=started,
            reason_code=audit.get('reason_code'),
            patch_op_count=0,
        )


async def _list_upstream_variables_handler(ctx: Any, args: str) -> str:
    """Wrap `resolve_upstream_variables` for the CURRENT builder canvas.

    Surfaces the SAME {fields, events, outcome_enums, unresolved} the
    builder's input pane gets, so the agent wires a downstream conditional /
    wait against real provider outcome + event vocabulary instead of magic
    strings. Read-only; vocabulary is resolver-owned and never re-derived
    here. UUIDs are NOT allowlisted — this tool returns no patchable ids.
    """
    started = time.monotonic()
    sherlock_ctx = getattr(ctx, 'context', ctx)
    audit: dict[str, Any] = {'reason_code': None}
    builder_context = getattr(sherlock_ctx, 'builder_context', None)
    auth_outer = getattr(sherlock_ctx, 'auth', None)
    try:
        check = await _check_layered_auth(sherlock_ctx, started=started, audit=audit)
        if isinstance(check, str):
            return check
        auth, builder_context = check

        parsed = json.loads(args) if args.strip() else {}
        target_node_id = parsed.get('target_node_id')
        if not isinstance(target_node_id, str) or not target_node_id:
            audit['reason_code'] = 'NODE_CONFIG_INVALID'
            return _error_result(
                reason_code='NODE_CONFIG_INVALID',
                message='target_node_id is required',
                started=started,
            )

        definition = builder_context.definition or {}
        nodes = [
            WorkflowDefinitionNode.model_validate(n)
            for n in definition.get('nodes', [])
        ]
        edges = [
            WorkflowDefinitionEdge.model_validate(e)
            for e in definition.get('edges', [])
        ]

        from app.database import async_session

        try:
            async with async_session() as db:
                resolved = await resolve_upstream_variables(
                    db,
                    tenant_id=auth.tenant_id,
                    app_id=builder_context.app_id,
                    workflow_type=builder_context.workflow_type,
                    nodes=nodes,
                    edges=edges,
                    target_node_id=target_node_id,
                )
        except UpstreamSourceNotFound as exc:
            audit['reason_code'] = 'GRAPH_INVALID'
            return _error_result(
                reason_code='GRAPH_INVALID',
                message=str(exc),
                started=started,
            )

        dumped = resolved.model_dump(mode='json', by_alias=True)
        payload = UpstreamVariables(
            fields=dumped.get('fields', []),
            events=dumped.get('events', []),
            outcome_enums=dumped.get('outcomeEnums', []),
            unresolved=dumped.get('unresolved', []),
        ).model_dump(mode='json', by_alias=True)

        event_count = len(payload['events'])
        outcome_count = len(payload['outcomeEnums'])
        return _mark_leak_in_result(audit, _lookup_result_json(
            started=started,
            summary=(
                f'{outcome_count} outcome enum(s), {event_count} event(s) '
                f'upstream of {target_node_id}.'
            ),
            payload=payload,
            tool_name='list_upstream_variables',
        ))
    finally:
        _emit_authoring_audit(
            tool='list_upstream_variables',
            builder_context=builder_context,
            auth=auth_outer,
            started=started,
            reason_code=audit.get('reason_code'),
            patch_op_count=0,
        )


async def _list_provider_connections_handler(ctx: Any, args: str) -> str:
    started = time.monotonic()
    sherlock_ctx = getattr(ctx, 'context', ctx)
    audit: dict[str, Any] = {'reason_code': None}
    builder_context = getattr(sherlock_ctx, 'builder_context', None)
    auth_outer = getattr(sherlock_ctx, 'auth', None)
    try:
        check = await _check_layered_auth(sherlock_ctx, started=started, audit=audit)
        if isinstance(check, str):
            return check
        auth, builder_context = check

        parsed = json.loads(args) if args.strip() else {}
        provider = parsed.get('provider')
        if not isinstance(provider, str) or not provider:
            audit['reason_code'] = 'NODE_CONFIG_INVALID'
            return _error_result(
                reason_code='NODE_CONFIG_INVALID',
                message='provider is required',
                started=started,
            )

        from sqlalchemy import select

        from app.database import async_session
        from app.models.provider_connection import ProviderConnection

        async with async_session() as db:
            rows = (
                await db.execute(
                    select(ProviderConnection).where(
                        ProviderConnection.tenant_id == auth.tenant_id,
                        ProviderConnection.app_id == builder_context.app_id,
                        ProviderConnection.provider == provider,
                        ProviderConnection.active.is_(True),
                    )
                )
            ).scalars().all()

        items = [
            ProviderConnectionRef(
                id=str(row.id),
                name=row.name,
                provider=row.provider,
            )
            for row in rows
        ]
        _record_authorized_uuids(
            sherlock_ctx.scratch if hasattr(sherlock_ctx, 'scratch') else {},
            [item.id for item in items],
        )

        payload = ProviderConnectionsList(items=items).model_dump(mode='json')
        return _mark_leak_in_result(audit, _lookup_result_json(
            started=started,
            summary=f'{len(items)} {provider} connection(s).',
            payload=payload,
            tool_name='list_provider_connections',
        ))
    finally:
        _emit_authoring_audit(
            tool='list_provider_connections',
            builder_context=builder_context,
            auth=auth_outer,
            started=started,
            reason_code=audit.get('reason_code'),
            patch_op_count=0,
        )


async def _list_action_templates_handler(ctx: Any, args: str) -> str:
    started = time.monotonic()
    sherlock_ctx = getattr(ctx, 'context', ctx)
    audit: dict[str, Any] = {'reason_code': None}
    builder_context = getattr(sherlock_ctx, 'builder_context', None)
    auth_outer = getattr(sherlock_ctx, 'auth', None)
    try:
        check = await _check_layered_auth(sherlock_ctx, started=started, audit=audit)
        if isinstance(check, str):
            return check
        auth, builder_context = check

        parsed = json.loads(args) if args.strip() else {}
        channel = parsed.get('channel')
        if not isinstance(channel, str) or not channel:
            audit['reason_code'] = 'NODE_CONFIG_INVALID'
            return _error_result(
                reason_code='NODE_CONFIG_INVALID',
                message='channel is required',
                started=started,
            )

        from sqlalchemy import or_, select

        from app.database import async_session
        from app.models.orchestration import WorkflowActionTemplate

        async with async_session() as db:
            rows = (
                await db.execute(
                    select(WorkflowActionTemplate).where(
                        or_(
                            WorkflowActionTemplate.tenant_id == auth.tenant_id,
                            WorkflowActionTemplate.tenant_id.is_(None),
                        ),
                        or_(
                            WorkflowActionTemplate.app_id == builder_context.app_id,
                            WorkflowActionTemplate.app_id.is_(None),
                        ),
                        WorkflowActionTemplate.channel == channel,
                        WorkflowActionTemplate.active.is_(True),
                    )
                )
            ).scalars().all()

        items = [
            ActionTemplateRef(
                id=str(row.id),
                slug=row.slug,
                name=row.name,
                channel=row.channel,
            )
            for row in rows
        ]
        _record_authorized_uuids(
            sherlock_ctx.scratch if hasattr(sherlock_ctx, 'scratch') else {},
            [item.id for item in items],
        )

        payload = ActionTemplatesList(items=items).model_dump(mode='json')
        return _mark_leak_in_result(audit, _lookup_result_json(
            started=started,
            summary=f'{len(items)} action template(s) for channel {channel}.',
            payload=payload,
            tool_name='list_action_templates',
        ))
    finally:
        _emit_authoring_audit(
            tool='list_action_templates',
            builder_context=builder_context,
            auth=auth_outer,
            started=started,
            reason_code=audit.get('reason_code'),
            patch_op_count=0,
        )


async def _list_cohort_datasets_handler(ctx: Any, args: str) -> str:
    started = time.monotonic()
    sherlock_ctx = getattr(ctx, 'context', ctx)
    audit: dict[str, Any] = {'reason_code': None}
    builder_context = getattr(sherlock_ctx, 'builder_context', None)
    auth_outer = getattr(sherlock_ctx, 'auth', None)
    try:
        check = await _check_layered_auth(sherlock_ctx, started=started, audit=audit)
        if isinstance(check, str):
            return check
        auth, builder_context = check
        del args  # no parameters

        from sqlalchemy import desc, select

        from app.database import async_session
        from app.models.orchestration import CohortDataset, CohortDatasetVersion

        items: list[CohortDatasetRef] = []
        async with async_session() as db:
            rows = (
                await db.execute(
                    select(CohortDataset).where(
                        CohortDataset.tenant_id == auth.tenant_id,
                        CohortDataset.app_id == builder_context.app_id,
                    )
                )
            ).scalars().all()
            for row in rows:
                latest_version = await db.scalar(
                    select(CohortDatasetVersion)
                    .where(CohortDatasetVersion.dataset_id == row.id)
                    .order_by(desc(CohortDatasetVersion.version_number))
                    .limit(1)
                )
                items.append(CohortDatasetRef(
                    id=str(row.id),
                    name=row.name,
                    latest_version_id=(
                        str(latest_version.id) if latest_version is not None else None
                    ),
                ))

        _record_authorized_uuids(
            sherlock_ctx.scratch if hasattr(sherlock_ctx, 'scratch') else {},
            [item.id for item in items if item.id]
            + [item.latest_version_id for item in items if item.latest_version_id],
        )

        payload = CohortDatasetsList(items=items).model_dump(mode='json')
        return _mark_leak_in_result(audit, _lookup_result_json(
            started=started,
            summary=f'{len(items)} cohort dataset(s).',
            payload=payload,
            tool_name='list_cohort_datasets',
        ))
    finally:
        _emit_authoring_audit(
            tool='list_cohort_datasets',
            builder_context=builder_context,
            auth=auth_outer,
            started=started,
            reason_code=audit.get('reason_code'),
            patch_op_count=0,
        )


async def _list_cohort_fields_handler(ctx: Any, args: str) -> str:
    """Cat-B field discovery for a cohort source (read-only).

    Thinly wraps ``field_discovery.list_cohort_fields`` — the heavy logic
    (source resolution, shared live introspection, manifest PII flag) lives
    there. Returns no patchable UUIDs, so nothing is allowlisted.
    """
    started = time.monotonic()
    sherlock_ctx = getattr(ctx, 'context', ctx)
    audit: dict[str, Any] = {'reason_code': None}
    builder_context = getattr(sherlock_ctx, 'builder_context', None)
    auth_outer = getattr(sherlock_ctx, 'auth', None)
    try:
        check = await _check_layered_auth(sherlock_ctx, started=started, audit=audit)
        if isinstance(check, str):
            return check
        auth, builder_context = check

        parsed = json.loads(args) if args.strip() else {}
        source_ref = parsed.get('source_ref')
        if not isinstance(source_ref, str) or not source_ref:
            audit['reason_code'] = 'NODE_CONFIG_INVALID'
            return _error_result(
                reason_code='NODE_CONFIG_INVALID',
                message='source_ref is required',
                started=started,
            )

        from app.database import async_session
        from app.services.orchestration.source_catalog import SourceCatalogError
        from app.services.orchestration_authoring.field_discovery import (
            list_cohort_fields,
        )

        try:
            async with async_session() as db:
                fields = await list_cohort_fields(
                    db=db,
                    app_id=builder_context.app_id,
                    source_ref=source_ref,
                    tenant_id=auth.tenant_id,
                )
        except SourceCatalogError:
            audit['reason_code'] = 'NODE_CONFIG_INVALID'
            return _error_result(
                reason_code='NODE_CONFIG_INVALID',
                message=f'Unknown cohort source {source_ref!r}.',
                started=started,
            )

        payload = {'fields': [f.model_dump(mode='json') for f in fields]}
        return _mark_leak_in_result(audit, _lookup_result_json(
            started=started,
            summary=f'{len(fields)} field(s) on {source_ref}.',
            payload=payload,
            tool_name='list_cohort_fields',
        ))
    finally:
        _emit_authoring_audit(
            tool='list_cohort_fields',
            builder_context=builder_context,
            auth=auth_outer,
            started=started,
            reason_code=audit.get('reason_code'),
            patch_op_count=0,
        )


async def _map_template_variables_handler(ctx: Any, args: str) -> str:
    """Match template placeholders to a cohort source's fields (read-only).

    Reuses ``field_discovery.list_cohort_fields`` for the field names, then
    the pure ``variable_mapper.map_variables`` for the matching. Returns no
    patchable UUIDs, so nothing is allowlisted.
    """
    started = time.monotonic()
    sherlock_ctx = getattr(ctx, 'context', ctx)
    audit: dict[str, Any] = {'reason_code': None}
    builder_context = getattr(sherlock_ctx, 'builder_context', None)
    auth_outer = getattr(sherlock_ctx, 'auth', None)
    try:
        check = await _check_layered_auth(sherlock_ctx, started=started, audit=audit)
        if isinstance(check, str):
            return check
        auth, builder_context = check

        parsed = json.loads(args) if args.strip() else {}
        source_ref = parsed.get('source_ref')
        placeholders = parsed.get('placeholders')
        if not isinstance(source_ref, str) or not source_ref:
            audit['reason_code'] = 'NODE_CONFIG_INVALID'
            return _error_result(
                reason_code='NODE_CONFIG_INVALID',
                message='source_ref is required',
                started=started,
            )
        if not isinstance(placeholders, list) or not all(
            isinstance(p, str) for p in placeholders
        ):
            audit['reason_code'] = 'NODE_CONFIG_INVALID'
            return _error_result(
                reason_code='NODE_CONFIG_INVALID',
                message='placeholders must be a list of strings',
                started=started,
            )

        from app.database import async_session
        from app.services.orchestration.source_catalog import SourceCatalogError
        from app.services.orchestration_authoring.field_discovery import (
            list_cohort_fields,
        )
        from app.services.orchestration_authoring.variable_mapper import (
            map_variables,
        )

        try:
            async with async_session() as db:
                fields = await list_cohort_fields(
                    db=db,
                    app_id=builder_context.app_id,
                    source_ref=source_ref,
                    tenant_id=auth.tenant_id,
                )
        except SourceCatalogError:
            audit['reason_code'] = 'NODE_CONFIG_INVALID'
            return _error_result(
                reason_code='NODE_CONFIG_INVALID',
                message=f'Unknown cohort source {source_ref!r}.',
                started=started,
            )

        result = map_variables(
            placeholders=placeholders,
            fields=[f.name for f in fields],
        )
        return _mark_leak_in_result(audit, _lookup_result_json(
            started=started,
            summary=(
                f'{len(result["mappings"])} matched, '
                f'{len(result["unmatched"])} unmatched on {source_ref}.'
            ),
            payload=result,
            tool_name='map_template_variables',
        ))
    finally:
        _emit_authoring_audit(
            tool='map_template_variables',
            builder_context=builder_context,
            auth=auth_outer,
            started=started,
            reason_code=audit.get('reason_code'),
            patch_op_count=0,
        )


async def _resolve_connection_handler(ctx: Any, args: str) -> str:
    started = time.monotonic()
    sherlock_ctx = getattr(ctx, 'context', ctx)
    audit: dict[str, Any] = {'reason_code': None}
    builder_context = getattr(sherlock_ctx, 'builder_context', None)
    auth_outer = getattr(sherlock_ctx, 'auth', None)
    try:
        check = await _check_layered_auth(sherlock_ctx, started=started, audit=audit)
        if isinstance(check, str):
            return check
        auth, builder_context = check

        parsed = json.loads(args) if args.strip() else {}
        channel_arg = parsed.get('channel')
        if not isinstance(channel_arg, str) or not channel_arg:
            audit['reason_code'] = 'NODE_CONFIG_INVALID'
            return _error_result(
                reason_code='NODE_CONFIG_INVALID',
                message='channel is required',
                started=started,
            )
        hint = parsed.get('hint')
        hint = hint if isinstance(hint, str) and hint.strip() else None

        from app.services.orchestration import channel_taxonomy

        canonical = channel_taxonomy.resolve_channel(channel_arg)
        if canonical is None:
            audit['reason_code'] = 'NODE_CONFIG_INVALID'
            return _error_result(
                reason_code='NODE_CONFIG_INVALID',
                message=f'Unknown channel {channel_arg!r}.',
                started=started,
            )
        providers = set(channel_taxonomy.channel_provider_map().get(canonical, []))

        from sqlalchemy import select

        from app.database import async_session
        from app.models.channel_default_connection import ChannelDefaultConnection
        from app.models.provider_connection import ProviderConnection

        async with async_session() as db:
            rows = (
                await db.execute(
                    select(ProviderConnection).where(
                        ProviderConnection.tenant_id == auth.tenant_id,
                        ProviderConnection.app_id == builder_context.app_id,
                        ProviderConnection.provider.in_(providers),
                        ProviderConnection.active.is_(True),
                    )
                )
            ).scalars().all()
            default_row = await db.scalar(
                select(ChannelDefaultConnection).where(
                    ChannelDefaultConnection.tenant_id == auth.tenant_id,
                    ChannelDefaultConnection.app_id == builder_context.app_id,
                    ChannelDefaultConnection.channel == canonical,
                )
            )

        candidates = [
            ConnRef(id=str(row.id), name=row.name, provider=row.provider)
            for row in rows
        ]
        candidate_ids = {c.id for c in candidates}
        default_id = (
            str(default_row.connection_id)
            if default_row is not None
            and str(default_row.connection_id) in candidate_ids
            else None
        )

        resolution = resolve_connection_ladder(
            candidates=candidates, default_id=default_id, hint=hint,
        )

        if resolution.status == 'resolved' and resolution.connection is not None:
            conn = resolution.connection
            _record_authorized_uuids(
                sherlock_ctx.scratch if hasattr(sherlock_ctx, 'scratch') else {},
                [conn.id],
            )
            payload = {
                'status': 'resolved',
                'connection': {
                    'id': conn.id, 'name': conn.name, 'provider': conn.provider,
                },
            }
            summary = f'Resolved {canonical} connection {conn.name!r}.'
        elif resolution.status == 'pick':
            picks = resolution.candidates or []
            payload = {
                'status': 'pick',
                'candidates': [
                    {'id': c.id, 'name': c.name, 'provider': c.provider}
                    for c in picks
                ],
            }
            summary = f'{len(picks)} {canonical} connection(s) to choose from.'
        else:
            payload = {'status': 'none', 'candidates': []}
            summary = f'No {canonical} connection configured for this app.'

        return _mark_leak_in_result(audit, _lookup_result_json(
            started=started,
            summary=summary,
            payload=payload,
            tool_name='resolve_connection',
        ))
    finally:
        _emit_authoring_audit(
            tool='resolve_connection',
            builder_context=builder_context,
            auth=auth_outer,
            started=started,
            reason_code=audit.get('reason_code'),
            patch_op_count=0,
        )


async def _resolve_template_handler(ctx: Any, args: str) -> str:
    """Cat-A resolution for a wati_template_picker field.

    Enforces chain order (connection_id MUST be in the per-turn allowlist),
    fetches via the SAME path the FE picker uses
    (`list_connection_wati_templates` — D1), and matches the intent with
    `match_template`. Never passes an unmatched intent through as a template
    name: an unknown intent returns not_found so the agent asks.
    """
    started = time.monotonic()
    sherlock_ctx = getattr(ctx, 'context', ctx)
    audit: dict[str, Any] = {'reason_code': None}
    builder_context = getattr(sherlock_ctx, 'builder_context', None)
    auth_outer = getattr(sherlock_ctx, 'auth', None)
    try:
        check = await _check_layered_auth(sherlock_ctx, started=started, audit=audit)
        if isinstance(check, str):
            return check
        auth, builder_context = check

        parsed = json.loads(args) if args.strip() else {}
        connection_id = parsed.get('connection_id')
        if not isinstance(connection_id, str) or not connection_id:
            audit['reason_code'] = 'NODE_CONFIG_INVALID'
            return _error_result(
                reason_code='NODE_CONFIG_INVALID',
                message='connection_id is required',
                started=started,
            )
        intent = parsed.get('intent')
        if not isinstance(intent, str) or not intent.strip():
            audit['reason_code'] = 'NODE_CONFIG_INVALID'
            return _error_result(
                reason_code='NODE_CONFIG_INVALID',
                message='intent is required',
                started=started,
            )

        # Chain order: the connection must have been resolved/listed this turn.
        scratch = getattr(sherlock_ctx, 'scratch', {}) or {}
        authorized = scratch.get('authorized_uuids')
        if not isinstance(authorized, set):
            authorized = set(authorized or [])
        if connection_id not in authorized:
            audit['reason_code'] = 'UUID_NOT_AUTHORIZED'
            return _error_result(
                reason_code='UUID_NOT_AUTHORIZED',
                message=(
                    f'connection_id {connection_id} was not resolved this turn. '
                    'Call resolve_connection (or list_provider_connections) for '
                    'the WhatsApp channel first.'
                ),
                started=started,
            )

        import uuid as _uuid

        from app.database import async_session

        async with async_session() as db:
            fetched = await list_connection_wati_templates(
                db,
                tenant_id=auth.tenant_id,
                app_id=builder_context.app_id,
                connection_id=_uuid.UUID(connection_id),
                refresh=False,
            )

        items = fetched.get('items') or []
        result = match_template(templates=items, intent=intent)

        if result.status == 'resolved':
            payload: dict[str, Any] = {
                'status': 'resolved',
                'name': result.name,
                'placeholders': result.placeholders,
            }
            summary = f'Resolved WhatsApp template {result.name!r}.'
        elif result.status == 'pick':
            payload = {'status': 'pick', 'candidates': result.candidates}
            summary = f'{len(result.candidates)} WhatsApp templates match {intent!r}.'
        else:
            payload = {'status': 'not_found', 'name': None, 'candidates': []}
            summary = (
                f'No WhatsApp template matches {intent!r}; ask the user which '
                'template to use.'
            )

        return _mark_leak_in_result(audit, _lookup_result_json(
            started=started,
            summary=summary,
            payload=payload,
            tool_name='resolve_template',
        ))
    finally:
        _emit_authoring_audit(
            tool='resolve_template',
            builder_context=builder_context,
            auth=auth_outer,
            started=started,
            reason_code=audit.get('reason_code'),
            patch_op_count=0,
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
            {
                'name': 'list_node_types',
                'description': (
                    'Enumerate the node types available in this builder. '
                    'Optional `category` filter; safe to call multiple times.'
                ),
                'params_json_schema': _LIST_NODE_TYPES_SCHEMA,
            },
            {
                'name': 'list_upstream_variables',
                'description': (
                    'Resolve the payload variables, provider outcome enums, '
                    'and resumable event names available upstream of a node on '
                    'the current canvas. Pass `target_node_id`. Use this before '
                    'wiring a conditional or wait so you branch on real provider '
                    'outcomes/events — never invented strings.'
                ),
                'params_json_schema': _LIST_UPSTREAM_VARIABLES_SCHEMA,
            },
            {
                'name': 'list_provider_connections',
                'description': (
                    'List provider_connections in this app for a given '
                    'provider. Returns (id, name, provider) only — no '
                    'credentials. UUIDs returned here are added to the '
                    'per-turn allowlist used by apply_patch.'
                ),
                'params_json_schema': _LIST_PROVIDER_CONNECTIONS_SCHEMA,
            },
            {
                'name': 'list_action_templates',
                'description': (
                    'List INTERNAL action templates for the named channel in '
                    'this tenant + app. Returns (id, slug, name, channel). This '
                    'is NOT the WhatsApp/WATI template source — for a '
                    'wati_template_picker field use resolve_template instead.'
                ),
                'params_json_schema': _LIST_ACTION_TEMPLATES_SCHEMA,
            },
            {
                'name': 'resolve_template',
                'description': (
                    'Resolve a WhatsApp (WATI) message template for a '
                    'wati_template_picker field. Pass `connection_id` (resolved '
                    'this turn) and a free-text `intent`; returns one resolved '
                    'template with its placeholders, a pick list, or not_found '
                    '(ask the user) — never an invented template name.'
                ),
                'params_json_schema': _RESOLVE_TEMPLATE_SCHEMA,
            },
            {
                'name': 'list_cohort_datasets',
                'description': (
                    'List cohort_datasets in this app. Returns (id, name, '
                    'latest_version_id). Both IDs are added to the '
                    'per-turn allowlist.'
                ),
                'params_json_schema': _LIST_COHORT_DATASETS_SCHEMA,
            },
            {
                'name': 'list_cohort_fields',
                'description': (
                    'Discover the fields on a cohort source. Pass `source_ref` '
                    "(e.g. 'crm.lead_record'); returns each field's name, type, "
                    'allowed values, whether it is filterable, and a PII flag. '
                    'Use before wiring payload fields or cohort filters.'
                ),
                'params_json_schema': _LIST_COHORT_FIELDS_SCHEMA,
            },
            {
                'name': 'resolve_connection',
                'description': (
                    'Resolve the provider connection to use for a channel. '
                    'Pass `channel` and an optional `hint`; returns a single '
                    'resolved connection (added to the per-turn allowlist), a '
                    'pick list to disambiguate, or none if unconfigured.'
                ),
                'params_json_schema': _RESOLVE_CONNECTION_SCHEMA,
            },
            {
                'name': 'map_template_variables',
                'description': (
                    'Match template placeholders to a cohort source\'s fields. '
                    'Pass `placeholders` and `source_ref`; returns payload '
                    'mappings, payload_fields_to_add, and unmatched. You MUST '
                    'add payload_fields_to_add to the upstream '
                    'source.cohort.payload_fields in the SAME apply_patch, and '
                    'ASK about any unmatched placeholder — never bind a guess.'
                ),
                'params_json_schema': _MAP_TEMPLATE_VARIABLES_SCHEMA,
            },
        )

    def tool_handlers(self) -> Mapping[str, Any]:
        return {
            'apply_patch': _apply_patch_handler,
            'list_node_types': _list_node_types_handler,
            'list_upstream_variables': _list_upstream_variables_handler,
            'list_provider_connections': _list_provider_connections_handler,
            'list_action_templates': _list_action_templates_handler,
            'resolve_template': _resolve_template_handler,
            'list_cohort_datasets': _list_cohort_datasets_handler,
            'list_cohort_fields': _list_cohort_fields_handler,
            'resolve_connection': _resolve_connection_handler,
            'map_template_variables': _map_template_variables_handler,
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
            'list_node_types': (
                'List node types available for this builder, optionally '
                'filtered by category. Wire edges only from a node\'s declared '
                'output_edges; never invent a handle (e.g. \'passed\'/\'success\').'
            ),
            'list_upstream_variables': (
                'Resolve upstream fields, provider outcome enums, and event '
                'names for a node — read before wiring conditionals or waits.'
            ),
            'list_provider_connections': (
                'List provider connections (id, name, provider). UUIDs are '
                'added to the per-turn allowlist for apply_patch.'
            ),
            'list_action_templates': (
                'List INTERNAL action templates by channel. NOT the '
                'WhatsApp/WATI template source — use resolve_template for a '
                'wati_template_picker field.'
            ),
            'resolve_template': (
                'Resolve a WhatsApp template for a wati_template_picker field '
                'from a free-text intent; returns one template + placeholders, '
                'a pick list, or not_found.'
            ),
            'list_cohort_datasets': (
                'List cohort datasets in this app and their latest version IDs.'
            ),
            'list_cohort_fields': (
                'Discover a cohort source\'s fields (name, type, allowed '
                'values, PII flag, filterable) before wiring payload or filters.'
            ),
            'resolve_connection': (
                'Resolve the connection for a channel (with an optional hint); '
                'returns one connection, a pick list, or none.'
            ),
            'map_template_variables': (
                'Match template placeholders to a cohort source\'s fields. '
                'Add the returned payload_fields_to_add to the upstream '
                'source.cohort.payload_fields in the SAME apply_patch; ASK '
                'about unmatched placeholders rather than binding a guess.'
            ),
        }

    def build_outcome(self, tool_name: str, raw_result: Any) -> Outcome:
        """v2 chat-engine egress hook — credential filter via the
        canonical recursive walker (Decision §R5; Phase 3 Step 4).

        v3 routes the SpecialistResult JSON through the supervisor's
        custom_output_extractor and never calls this; the inline filters
        in `_apply_patch_handler` / `_lookup_result_json` are the
        load-bearing egress points today. We still wire the filter here
        so that any future harness path that goes through
        `CapabilityPack.build_outcome` cannot regress R5.

        On `CredentialLeakError`: log one R10 audit row with
        `validation_result='credential_leak_blocked'` (the offending
        field name and tool name land in the audit log only — never in
        the user-facing payload) and return an empty error envelope.
        """
        from app.services.orchestration_authoring.credential_field_filter import (
            CredentialLeakError,
            assert_no_credentials,
        )

        started = time.monotonic()
        payload = dict(raw_result) if isinstance(raw_result, dict) else {}
        try:
            assert_no_credentials(payload)
        except CredentialLeakError as exc:
            authoring_logger.warning(
                'build_outcome egress filter blocked tool=%s field=%s path=%s',
                tool_name, exc.field_name,
                '.'.join(str(p) for p in exc.path),
            )
            emit_authoring_event({
                'tool': tool_name,
                'app_id': '',
                'tenant_id': '',
                'user_id': '',
                'workflow_id': '',
                'patch_op_count': 0,
                'validation_result': 'credential_leak_blocked',
                'permission_denied': False,
                'duration_ms': int((time.monotonic() - started) * 1000),
            })
            envelope = build_envelope(
                status='error',
                summary=f'{tool_name}: credential field blocked',
                kind='error',
                capability=PACK_ID,
                reason_code='CREDENTIAL_LEAK_BLOCKED',
                payload={},
            )
            return envelope.outcome.model_dump()  # type: ignore[return-value]
        envelope = build_envelope(
            status='ok',
            summary=f'{tool_name} ok',
            kind='artifact',
            capability=PACK_ID,
            payload=payload,
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

"""Sherlock v3 authoring_specialist — orchestration-builder sub-agent.

Mirrors `data_specialist.py` in shape: a single-purpose Agent that the
supervisor invokes via `as_tool(...)` only when the route handler has
attached a `BuilderSnapshot` AND the caller holds `orchestration:manage`.

One source of truth: this module imports `tool_specs()` and
`tool_handlers()` from `orchestration_authoring_pack` to construct its
`FunctionTool(strict_json_schema=True)` list. The pack owns the contract;
the specialist owns the SDK wiring. When the v3 harness eventually
auto-wires packs (per `docs/plans/sherlock-future-plan.md`), this
specialist's manual import becomes a one-line refactor.

Per [[Decisions/2026-05-10-agents-sdk-conformance-review|conformance review]]:
- §A: `as_tool()` takes no parameters JSON Schema; the supervisor sends
  free-text briefs and structured validation lives on this sub-agent's
  tools.
- §C: `apply_patch` config travels as JSON-encoded strings to satisfy
  strict_json_schema.
- §E: Canvas snapshot is baked into the system prompt at agent build
  time; no `describe_workflow` tool.
- §F: `extract_authoring_specialist_output` matches strictly on
  `apply_patch` — no "if only one tool, assume it" fallback because this
  specialist has multiple tools (apply_patch + 5 lookups).
- §I: ModelSettings(parallel_tool_calls=False, reasoning=effort='medium').
"""
from __future__ import annotations

import json
import logging
from typing import Any

import openai
from agents import Agent, FunctionTool

from app.auth.context import AuthContext
from app.services.orchestration.node_registry import NODE_REGISTRY
from app.services.orchestration_authoring.builder_snapshot import BuilderSnapshot
from app.services.orchestration_authoring.orchestration_authoring_pack import (
    OrchestrationAuthoringPack,
    node_type_enum,
)
from app.services.sherlock_v3.contracts import SpecialistResult
from app.services.sherlock_v3.specialist_factory import make_specialist_agent
from app.services.sherlock_v3.tool_output import (
    build_call_name_index,
    is_tool_output_for,
)

logger = logging.getLogger(__name__)


_AUTHORING_TOOL_TERMINAL = 'apply_patch'

_AUTHORING_REFUSAL_SUMMARY = (
    'The authoring specialist could not produce a canvas edit for this request.'
)


def _authoring_refusal_json() -> str:
    """Deterministic refusal SpecialistResult JSON when no usable output exists.

    Mirrors query_synthesis_specialist._refusal_brief: a non-empty human
    reason instead of a silent empty string, so the supervisor never
    projects a blank error/empty card.
    """
    return SpecialistResult(
        kind='error',
        status='error',
        summary=_AUTHORING_REFUSAL_SUMMARY,
    ).model_dump_json()


# Phase 3 — hard cap on nodes inlined into the specialist's system
# prompt. Above this, the prompt blows the token budget and the agent
# can't reason cleanly. Revisit when the `describe_workflow` tool ships
# in v2 (lets the LLM page through the canvas instead of consuming all
# of it as system-prompt tokens). Per Decision §"risks still open":
# "token-budget cliff at ~150–200 nodes."
CANVAS_NODE_LIMIT = 150
CANVAS_TOO_LARGE_SUMMARY = (
    'This workflow has too many nodes for me to inline. Open the '
    'inspector for any node you want to edit and try again.'
)


class CanvasTooLargeError(Exception):
    """Raised by `build_authoring_specialist` when a snapshot's node
    count exceeds `CANVAS_NODE_LIMIT`. The supervisor catches this and
    skips authoring tool inclusion for the turn — no LLM round-trip is
    made for the specialist.

    Carries a `reason_code` and `summary` matching the
    `orchestration.authoring` reason-code surface so callers can render
    a uniform error envelope to the user.
    """

    def __init__(self, *, reason_code: str, summary: str, node_count: int) -> None:
        self.reason_code = reason_code
        self.summary = summary
        self.node_count = node_count
        super().__init__(f'{reason_code}: {node_count} nodes (cap {CANVAS_NODE_LIMIT})')


def _compact_annotation(info: Any) -> str:
    """Render a Pydantic FieldInfo's annotation as a tight string.

    Strips `typing.` / module-path prefixes that bloat the prompt
    without adding signal. For nested BaseModel fields we still emit
    the bare class name; the recursive walker emits its body separately.
    """
    try:
        annotation = repr(info.annotation)
    except Exception:
        return '?'
    annotation = annotation.replace('typing.', '').replace("<class '", '').replace("'>", '')
    # Strip the module path on user-defined classes ("foo.bar.baz._Branch" → "_Branch").
    import re as _re
    annotation = _re.sub(r"[\w.]+\.([A-Z_][A-Za-z0-9_]*)", r"\1", annotation)
    return annotation


def _collect_nested_models(schema: type, seen: set[type]) -> list[type]:
    """Walk a BaseModel's annotations, return every nested BaseModel class
    (including those inside list[...] / Optional[...] / etc.). Stable order."""
    from pydantic import BaseModel as _BM
    from typing import get_args, get_origin
    out: list[type] = []
    for info in schema.model_fields.values():
        anno = info.annotation
        stack = [anno]
        while stack:
            t = stack.pop()
            if t is None:
                continue
            origin = get_origin(t)
            if origin is not None:
                stack.extend(get_args(t))
                continue
            if isinstance(t, type) and issubclass(t, _BM) and t not in seen:
                seen.add(t)
                out.append(t)
                # Recurse into the nested model.
                out.extend(_collect_nested_models(t, seen))
    return out


def _render_model_block(label: str, model_cls: type, *, is_node: bool, header_extras: str = '') -> str:
    """Render one BaseModel as a `## <label>` block with field list."""
    lines = [f'## {label}{header_extras}'] if is_node else [f'### {label}']
    for field_name, info in model_cls.model_fields.items():
        annotation = _compact_annotation(info)
        required = info.is_required()
        default_str = ''
        if not required:
            try:
                default_str = f' — default: {info.get_default(call_default_factory=True)!r}'
            except Exception:
                default_str = ''
        req_marker = ', required' if required else ''
        lines.append(f'  - {field_name} ({annotation}{req_marker}){default_str}')
    return '\n'.join(lines)


def _node_schemas_for_prompt(workflow_type: str) -> str:
    """Render every node type's config schema (with nested models expanded)
    as compact text. The LLM gets the full contract — no guessing."""
    blocks: list[str] = []
    seen_nodes: set[str] = set()
    for (wf_type, node_type), handler in sorted(NODE_REGISTRY.items()):
        # Wildcard handlers shown everywhere; per-workflow handlers only
        # under their declared workflow_type.
        if wf_type not in ('*', workflow_type):
            continue
        if node_type in seen_nodes:
            continue
        seen_nodes.add(node_type)
        schema = getattr(handler, 'config_schema', None)
        outputs = ','.join(getattr(handler, 'output_edges', []) or []) or '(none)'
        category = getattr(handler, 'category', '?')
        header_extras = f'  [category={category}, outputs={outputs}]'
        if schema is None:
            blocks.append(f'## {node_type}{header_extras}\n  (no config schema)')
            continue

        # Top-level node schema.
        block = _render_model_block(node_type, schema, is_node=True, header_extras=header_extras)
        # Nested models referenced by this node — render once each.
        nested_seen: set[type] = set()
        nested = _collect_nested_models(schema, nested_seen)
        for nested_cls in nested:
            block += '\n' + _render_model_block(nested_cls.__name__, nested_cls, is_node=False)
        blocks.append(block)
    return '\n\n'.join(blocks)


def _build_system_prompt(
    *,
    app_id: str,
    builder_context: BuilderSnapshot,
) -> str:
    """Render the per-turn system prompt with the canvas snapshot baked in.

    The frontend keeps `definition.canvas` (cosmetics) and other heavy
    fields out of the prompt by passing only the persistence-shaped
    definition; we still strip `canvas` here as defense in depth.
    """
    definition = dict(builder_context.definition or {})
    definition.pop('canvas', None)
    snapshot = json.dumps({
        'workflow_id': str(builder_context.workflow_id),
        'workflow_type': builder_context.workflow_type,
        'app_id': builder_context.app_id,
        'view_mode': builder_context.view_mode,
        'selected_node_id': builder_context.selected_node_id,
        'data_hash': builder_context.data_hash,
        'definition': definition,
    }, default=str, indent=2)
    enum_list = ', '.join(node_type_enum())
    node_schemas = _node_schemas_for_prompt(builder_context.workflow_type)

    return f"""\
Role: Sherlock — orchestration authoring specialist.

# Goal
Translate the user's authoring intent into a single CanvasPatch that the
frontend applier will animate onto the live canvas. You read the canvas
state below; you propose edits via `apply_patch`. The user reviews and
saves manually.

# App
{app_id}

# Canvas snapshot (this turn — frozen)
{snapshot}

# Available node types (from NODE_REGISTRY at boot)
{enum_list}

# Node config schemas — THIS IS THE CONTRACT
You MUST only use field names listed below. Unknown fields are rejected
with NODE_CONFIG_INVALID; you get one corrective retry then the user sees
an error. Required fields can be omitted at draft time (publish-validator
catches missing required) but you MUST NOT invent new field names. If a
concept you want is not on the schema, leave the node empty and let the
user fill it in via the inspector.

{node_schemas}

# Placeholder node
- `sink.complete` ends a branch with no side effect. **Use `sink.complete`
  as the placeholder when the user says "leave the action node empty"**;
  NEVER use `core.webhook_out` as a placeholder — it dispatches HTTP and
  has real side effects.

# Tools
Lookups (`list_node_types`, `list_upstream_variables`, `list_provider_connections`,
`list_action_templates`, `list_cohort_datasets`) read tenant + app scoped facts;
`apply_patch(ops_json, rationale)` is TERMINAL and emits one CanvasPatch. Each
tool's own description is the source of truth for its arguments.

# Operating rules
1. Lookups first, patch last. UUIDs you reference in `apply_patch`
   (connection_id / dataset_version_id / action_template_id) MUST come
   from a `list_*` call you made THIS TURN. Inventing UUIDs will be
   rejected with reason_code=UUID_NOT_AUTHORIZED.
2. Before authoring a `logic.conditional` predicate `value` or a
   `logic.wait` `event_name` / `event_or_timeout`, call
   `list_upstream_variables(target_node_id)` and pick a CANONICAL outcome
   from `outcomeEnums` or an event from `events`. Store the canonical
   value — the provider label is display-only. Never invent an
   outcome/event string; an unresolved one is rejected with
   reason_code=UNKNOWN_OUTCOME / UNKNOWN_EVENT.
3. `ops_json` is a JSON-encoded array of ops. Each op is
   `{{op, node_id, payload}}`:
   - `add_node`: payload is `{{node_type, position?, config}}`. `config` is
     a JSON OBJECT (not a nested string).
   - `update_node_config`: payload is `{{config_patch}}` — a shallow merge.
   - `connect`: payload is `{{source_node_id, output_id, target_node_id, edge_id}}`.
   - `remove_node`: payload `{{}}` (cascades edges).
4. Do NOT claim work is "saved", "live", or "published". You only
   propose patches; the user clicks Save / Publish.
5. If the user asks for live execution, refuse politely in one line.

# Stop rules
Stop after one successful `apply_patch`. On `status=error`, regenerate
once and try again. After two failures, surface the error to the user.
"""


def _count_nodes(builder_context: BuilderSnapshot) -> int:
    """Count nodes in the snapshot's definition. Robust to None/missing."""
    definition = builder_context.definition
    if not isinstance(definition, dict):
        return 0
    nodes = definition.get('nodes')
    return len(nodes) if isinstance(nodes, list) else 0


def build_authoring_specialist(
    client: openai.AsyncOpenAI,
    app_id: str,
    *,
    model: str,
    builder_context: BuilderSnapshot,
    auth: AuthContext,
) -> Agent:
    """Construct the authoring_specialist Agent for one turn.

    `builder_context` and `auth` are required — the supervisor never
    builds this agent without them. They're not used directly here
    (handlers read them off `ctx.context`), but threading them through
    documents the binding and lets the system prompt close over the
    snapshot.

    Raises `CanvasTooLargeError` when the snapshot exceeds
    `CANVAS_NODE_LIMIT` — the supervisor catches and skips inclusion
    of the authoring tool for the turn. No LLM call is made.
    """
    del auth  # consumed by the per-tool re-checks via ctx.context.auth

    node_count = _count_nodes(builder_context)
    if node_count > CANVAS_NODE_LIMIT:
        logger.info(
            'authoring_specialist: canvas too large (%d nodes > cap %d) — refusing without LLM call',
            node_count, CANVAS_NODE_LIMIT,
        )
        raise CanvasTooLargeError(
            reason_code='CANVAS_TOO_LARGE',
            summary=CANVAS_TOO_LARGE_SUMMARY,
            node_count=node_count,
        )

    pack = OrchestrationAuthoringPack()
    handlers = pack.tool_handlers()

    # Typed as `list[Any]` because `Agent(tools=...)` annotates the
    # parameter as `list[Tool]` (invariant) — `FunctionTool` is one of
    # several concrete `Tool` types and a plain `list[FunctionTool]`
    # is not assignable.
    function_tools: list[Any] = []
    for spec in pack.tool_specs():
        name = spec['name']
        description = pack.describe_tools(app_id).get(
            name, spec.get('description', '')
        )
        function_tools.append(
            FunctionTool(
                name=name,
                description=description,
                params_json_schema=spec['params_json_schema'],
                on_invoke_tool=handlers[name],
                strict_json_schema=True,
            )
        )

    system_prompt = _build_system_prompt(
        app_id=app_id, builder_context=builder_context,
    )

    return make_specialist_agent(
        role='authoring',
        app_id=app_id,
        client=client,
        model=model,
        instructions=system_prompt,
        reasoning_effort='medium',
        tools=function_tools,
    )


# ─────────────────────── as_tool output extractor ───────────────────────


async def extract_authoring_specialist_output(run_result: Any) -> str:
    """Return the most recent `apply_patch` tool output JSON, by call_id.

    Agents-SDK reality: `tool_call_output_item.raw_item` carries `call_id`,
    NOT `name`. The tool name lives on the preceding `tool_call_item`.
    Build a `call_id -> tool_name` index from the run's tool_call_items
    first, then match outputs against `apply_patch` via that index.

    Strict on `apply_patch` (no defaulting to "the only tool" — this
    specialist has six). Falls back to the agent's final_output text only
    when no apply_patch output exists, preserving the SDK default for
    clarifying-question turns.
    """
    new_items = list(getattr(run_result, 'new_items', []) or [])
    call_name_index = build_call_name_index(new_items)
    for item in reversed(new_items):
        if not is_tool_output_for(
            item, _AUTHORING_TOOL_TERMINAL, call_name_index=call_name_index,
        ):
            continue
        output = getattr(item, 'output', None)
        if isinstance(output, str) and output.strip():
            return output
        if isinstance(output, dict):
            return json.dumps(output, default=str)
    final_output = getattr(run_result, 'final_output', None)
    if isinstance(final_output, str) and final_output.strip():
        return final_output
    # No apply_patch output and no usable text — emit a refusal
    # SpecialistResult so the supervisor never projects a blank card.
    return _authoring_refusal_json()


__all__ = [
    'CANVAS_NODE_LIMIT',
    'CANVAS_TOO_LARGE_SUMMARY',
    'CanvasTooLargeError',
    'build_authoring_specialist',
    'extract_authoring_specialist_output',
]

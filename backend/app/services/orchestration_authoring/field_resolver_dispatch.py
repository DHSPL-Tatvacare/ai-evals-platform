"""Route a node-config picker x-type to the authoring resolver tool that fills it.

Internal wiring only — it points at the EXISTING pack tools (resolve_connection /
resolve_template / list_cohort_fields / map_template_variables), it is not a pack
tool itself. The exhaustiveness guard test asserts every x-type declared in a node
config schema appears in ``XTYPE_RESOLVER`` so a new picker can never be silently
unhandled.

Chain order: channel -> connection -> sub-resource. A sub-resource resolver
(resolve_template) refuses until its connection is resolved first; resolve_template
enforces connection-before-template at runtime via the per-turn UUID allowlist.
"""
from __future__ import annotations

# Explicit sentinel for x-types we deliberately do not resolve yet. Mapped
# (never absent) so the guard test proves nothing is forgotten.
UNSUPPORTED = 'UNSUPPORTED'


# Each picker x-type → the resolver TOOL the agent should call to fill it.
XTYPE_RESOLVER: dict[str, str] = {
    'connection_picker': 'resolve_connection',
    'wati_template_picker': 'resolve_template',
    'recipient_field_picker': 'list_cohort_fields',
    'variable_mapping_list': 'map_template_variables',
    'bolna_agent_picker': UNSUPPORTED,
    'phone_number_picker': UNSUPPORTED,
    'wati_channel_picker': UNSUPPORTED,
    'structured_request_body': UNSUPPORTED,
    'attempt_policy': UNSUPPORTED,
}


def resolver_for(x_type: str) -> str:
    """Resolver tool name for a picker x-type, or ``UNSUPPORTED``.

    An unmapped x-type returns ``UNSUPPORTED`` rather than raising so a stray
    picker degrades to "no auto-resolver" instead of crashing the turn; the
    guard test keeps the declared set covered at boot.
    """
    return XTYPE_RESOLVER.get(x_type, UNSUPPORTED)


def declared_xtypes() -> set[str]:
    """Every ``x-type`` declared across registered node config schemas.

    Derived by scanning NODE_REGISTRY so the guard test cannot drift; a new
    picker field added to any node surfaces here automatically.
    """
    import app.services.orchestration.nodes  # noqa: F401  (registry side-effect)
    from app.services.orchestration.node_registry import NODE_REGISTRY

    found: set[str] = set()

    def _walk(obj: object) -> None:
        if isinstance(obj, dict):
            x_type = obj.get('x-type')
            if isinstance(x_type, str):
                found.add(x_type)
            for value in obj.values():
                _walk(value)
        elif isinstance(obj, list):
            for value in obj:
                _walk(value)

    for (_workflow_type, node_type), handler in NODE_REGISTRY.items():
        if node_type.startswith('test.'):
            continue
        _walk(handler.config_schema.model_json_schema())
    return found

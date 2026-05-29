"""Phase 11 — canonical node descriptor and contract metadata.

This module is the source of truth for:
  - the **rich** node descriptor surfaced to the builder,
  - the per-node payload IO contract (required inputs, emitted outputs),
  - the per-node output-edge metadata (id, label, cardinality, dynamic),
  - the per-node graph rules (does the node need an outgoing edge? terminal?
    can a single output_id fan out to multiple targets?),
  - and the per-node runtime contract (execution kind, attempt policy,
    suspend / resume support).

Handlers (registered in ``node_registry``) keep declaring ``output_edges`` as
a flat ``list[str]`` of stable ids for runtime dispatch — this is the routing
key the executor matches against ``WorkflowDefinitionEdge.output_id``. The
descriptor adds **labels and metadata** on top so the builder can render
edges with human text without making routing dependent on those labels.

The descriptor is consumed by:
  - ``api/node_types.py``        — palette feed for the frontend
  - ``definition_validator.py``  — publish-time graph validation
  - ``definition_normalizer.py`` — legacy → canonical migration

Adding a new active node type requires registering it here. Node types not
registered here fall back to a permissive descriptor that exposes only the
flat ``output_edges`` list — that fallback exists so dispatch / mutation
nodes (whose contract finalization lives in a later commit) keep working
during the contract-foundation rollout.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from app.config import settings
from app.services.orchestration.node_registry import NODE_REGISTRY


# Eight neutral, functional categories (Phase 11 §4). These are surfaced as
# palette groupings — never as routing or domain identifiers. Internal node
# type strings (e.g. ``logic.split``) remain stable and need not match the
# display category (``Routing``).
DisplayCategory = Literal[
    "ingress",
    "qualification",
    "routing",
    "suspension",
    "synchronization",
    "dispatch",
    "mutation",
    "ai",
    "termination",
]

AuthoringStatus = Literal["active", "hidden", "experimental", "deprecated"]

ExecutionKind = Literal[
    "entry_sql",
    "entry_event",
    "qualification",
    "routing",
    "suspension",
    "synchronization",
    "dispatch",
    "mutation",
    "termination",
]

OutputCardinality = Literal["one", "many"]


class OutputEdgeDescriptor(BaseModel):
    """One outgoing edge slot on a node.

    ``id`` is the stable routing key (matches ``WorkflowDefinitionEdge.output_id``).
    ``label`` is the human-readable display string used by the canvas — never
    used for routing. ``dynamic`` means additional output_ids may be appended
    at config time (e.g. ``logic.split`` branches). ``cardinality`` says
    whether one ``(node_id, output_id)`` pair may fan out to multiple
    outgoing edges in the persisted definition.
    """
    id: str
    label: str
    cardinality: OutputCardinality = "one"
    dynamic: bool = False


class GraphRules(BaseModel):
    """How the validator should treat a node when checking the published graph."""
    requires_incoming_edges: bool = True
    requires_outgoing_edges: bool = True
    required_output_ids: list[str] = Field(default_factory=list)
    allows_multiple_outgoing_per_output: bool = False
    terminal: bool = False


class RuntimeContract(BaseModel):
    """How the runtime sees the node — informs scheduler / resume / retry handling."""
    execution_kind: ExecutionKind
    supports_attempt_policy: bool = False
    supports_suspend_resume: bool = False


class EditorHints(BaseModel):
    """Builder hints for picking an editor and laying out the form."""
    preferred_editor: Optional[str] = None
    hidden_fields: list[str] = Field(default_factory=list)
    read_only_fields: list[str] = Field(default_factory=list)
    field_order: list[str] = Field(default_factory=list)
    empty_state_message: Optional[str] = None


class NodeDescriptor(BaseModel):
    """Phase 11 canonical descriptor — superset of the legacy ``NodeTypeDescriptor``.

    ``config_schema`` is the JSON Schema produced by the handler's Pydantic
    config model. ``output_edges`` is the rich metadata shape; the legacy
    flat ``output_edges`` list still exists on the handler for runtime
    dispatch but the descriptor surfaces the rich shape for builders and
    validators.
    """
    node_type: str
    workflow_type: str  # '*' for shared
    display_label: str
    display_category: DisplayCategory
    description: str
    authoring_status: AuthoringStatus = "active"

    config_schema: dict[str, Any]
    editor_hints: EditorHints = Field(default_factory=EditorHints)

    required_payload_fields: list[str] = Field(default_factory=list)
    emitted_payload_fields: list[str] = Field(default_factory=list)

    output_edges: list[OutputEdgeDescriptor] = Field(default_factory=list)

    graph_rules: GraphRules = Field(default_factory=GraphRules)
    runtime_contract: RuntimeContract


# ─────────────────────────────────────────────────────────────────────────────
# Per-node-type contract metadata.
# Only the eight node types finalized in Commit 1 declare a full contract.
# Other node types fall back to ``_legacy_descriptor`` until their own
# contract finalization commits land.
# ─────────────────────────────────────────────────────────────────────────────

_ContractMeta = dict[str, Any]

# Standard graph rules for retry-capable dispatch nodes:
#   - inbound and outbound edges required;
#   - workflow-visible outputs are 'success' / 'exhausted' (per-attempt retry
#     stays inside the node — see ``attempt_policy.run_with_attempt_policy``);
#   - 'exhausted' is the configured ``attempt_policy.on_exhausted_output_id``;
#     descriptors expose the contract slot named ``exhausted`` and validators
#     do not care whether a tenant later reroutes to a different id.
_DISPATCH_OUTPUT_EDGES: list[dict[str, Any]] = [
    {"id": "success", "label": "Success", "cardinality": "one", "dynamic": False},
    {"id": "exhausted", "label": "Exhausted", "cardinality": "one", "dynamic": False},
]

_DISPATCH_GRAPH_RULES: dict[str, Any] = {
    "requires_incoming_edges": True,
    "requires_outgoing_edges": True,
    "required_output_ids": [],  # at least one of success/exhausted must be wired
    "allows_multiple_outgoing_per_output": False,
    "terminal": False,
}


_CONTRACT_META: dict[str, _ContractMeta] = {
    # ─── Ingress ────────────────────────────────────────────────────────────
    "source.cohort": {
        "display_label": "Cohort",
        "display_category": "ingress",
        "description": "Pull contacts from a source — build inline, or reuse a saved cohort.",
        "authoring_status": "active",
        "editor_hints": {"preferred_editor": "SourceCohortPicker"},
        "required_payload_fields": [],
        "emitted_payload_fields": [],
        "output_edges": [{"id": "default", "label": "Cohort", "cardinality": "one", "dynamic": False}],
        "graph_rules": {
            "requires_incoming_edges": False,
            "requires_outgoing_edges": True,
            "required_output_ids": ["default"],
            "allows_multiple_outgoing_per_output": False,
            "terminal": False,
        },
        "runtime_contract": {"execution_kind": "entry_sql"},
    },
    "source.dataset": {
        "display_label": "Dataset",
        "display_category": "ingress",
        "description": "Run against a specific uploaded list. Same contacts every run.",
        "authoring_status": "active",
        "editor_hints": {"preferred_editor": "DatasetPicker"},
        "required_payload_fields": [],
        "emitted_payload_fields": [],
        "output_edges": [{"id": "default", "label": "Cohort", "cardinality": "one", "dynamic": False}],
        "graph_rules": {
            "requires_incoming_edges": False,
            "requires_outgoing_edges": True,
            "required_output_ids": ["default"],
            "allows_multiple_outgoing_per_output": False,
            "terminal": False,
        },
        "runtime_contract": {"execution_kind": "entry_sql"},
    },
    "source.event_trigger": {
        "display_label": "Event Trigger",
        "display_category": "ingress",
        "description": "Trigger a workflow run when an external event fires (e.g. a new CRM lead).",
        "authoring_status": "active",
        "editor_hints": {
            "preferred_editor": "EventTriggerInspector",
            "empty_state_message": "Event payload is supplied by the trigger / webhook.",
        },
        "required_payload_fields": [],
        "emitted_payload_fields": [],
        "output_edges": [{"id": "default", "label": "Cohort", "cardinality": "one", "dynamic": False}],
        "graph_rules": {
            "requires_incoming_edges": False,
            "requires_outgoing_edges": True,
            "required_output_ids": ["default"],
            "allows_multiple_outgoing_per_output": False,
            "terminal": False,
        },
        "runtime_contract": {"execution_kind": "entry_event"},
    },

    # ─── Qualification ──────────────────────────────────────────────────────
    "filter.eligibility": {
        "display_label": "Eligibility Filter",
        "display_category": "qualification",
        "description": "Continue only with contacts that match your eligibility rule.",
        "authoring_status": "active",
        "editor_hints": {"preferred_editor": "PredicateBuilder"},
        "required_payload_fields": [],  # config-derived from predicate field references
        "emitted_payload_fields": [],
        "output_edges": [
            {"id": "passed", "label": "Passed", "cardinality": "one", "dynamic": False},
            {"id": "skipped", "label": "Skipped", "cardinality": "one", "dynamic": False},
        ],
        "graph_rules": {
            "requires_incoming_edges": True,
            "requires_outgoing_edges": True,
            "required_output_ids": [],  # at least one of the two must be wired
            "allows_multiple_outgoing_per_output": False,
            "terminal": False,
        },
        "runtime_contract": {"execution_kind": "qualification"},
    },
    "filter.consent_gate": {
        "display_label": "Consent Gate",
        "display_category": "qualification",
        "description": "Continue only with contacts that have valid consent on record.",
        "authoring_status": "hidden",
        "editor_hints": {
            "empty_state_message": (
                "Consent gating is hidden from the palette until consent ingestion lands. "
                "Existing definitions still execute."
            ),
        },
        "required_payload_fields": [],
        "emitted_payload_fields": [],
        "output_edges": [
            {"id": "allowed", "label": "Allowed", "cardinality": "one", "dynamic": False},
            {"id": "blocked", "label": "Blocked", "cardinality": "one", "dynamic": False},
        ],
        "graph_rules": {
            "requires_incoming_edges": True,
            "requires_outgoing_edges": True,
            "required_output_ids": [],
            "allows_multiple_outgoing_per_output": False,
            "terminal": False,
        },
        "runtime_contract": {"execution_kind": "qualification"},
    },

    # ─── Routing ────────────────────────────────────────────────────────────
    "logic.conditional": {
        "display_label": "Conditional Branch",
        "display_category": "routing",
        "description": "Route each contact to the first matching criteria branch, or a default.",
        "authoring_status": "active",
        "editor_hints": {"preferred_editor": "ConditionalBranchesEditor"},
        "required_payload_fields": [],
        "emitted_payload_fields": [],
        # Branches are dynamic — output_ids derived per-config (branch ids +
        # implicit 'default'). Validator reads config to know the valid set.
        "output_edges": [],
        "graph_rules": {
            "requires_incoming_edges": True,
            "requires_outgoing_edges": True,
            "required_output_ids": [],
            "allows_multiple_outgoing_per_output": False,
            "terminal": False,
        },
        "runtime_contract": {"execution_kind": "routing"},
    },
    "logic.split": {
        "display_label": "Segment Split",
        "display_category": "routing",
        "description": "Route contacts into multiple branches by rule or weighted percentage.",
        "authoring_status": "active",
        "editor_hints": {"preferred_editor": "SplitBranchEditor"},
        "required_payload_fields": [],
        "emitted_payload_fields": [],
        # Branches are dynamic — additional output_ids derived per-config.
        "output_edges": [],
        "graph_rules": {
            "requires_incoming_edges": True,
            "requires_outgoing_edges": True,
            "required_output_ids": [],
            "allows_multiple_outgoing_per_output": False,
            "terminal": False,
        },
        "runtime_contract": {"execution_kind": "routing"},
    },

    # ─── Suspension ─────────────────────────────────────────────────────────
    "logic.wait": {
        "display_label": "Wait Condition",
        "display_category": "suspension",
        "description": "Pause execution until a delay elapses or an awaited event arrives.",
        "authoring_status": "active",
        "editor_hints": {"preferred_editor": "WaitConditionEditor"},
        "required_payload_fields": [],
        "emitted_payload_fields": [],
        # Output set depends on mode; validator reads config to pick which
        # subset of these is required.
        "output_edges": [
            {"id": "wakeup", "label": "Wake-up", "cardinality": "one", "dynamic": False},
            {"id": "event", "label": "Event", "cardinality": "one", "dynamic": False},
            {"id": "timeout", "label": "Timeout", "cardinality": "one", "dynamic": False},
        ],
        "graph_rules": {
            "requires_incoming_edges": True,
            "requires_outgoing_edges": True,
            "required_output_ids": [],
            "allows_multiple_outgoing_per_output": False,
            "terminal": False,
        },
        "runtime_contract": {"execution_kind": "suspension", "supports_suspend_resume": True},
    },

    # ─── Synchronization ────────────────────────────────────────────────────
    "logic.merge": {
        "display_label": "Path Merge",
        "display_category": "synchronization",
        "description": "Reconverge multiple inbound branches into a single downstream path.",
        "authoring_status": "active",
        "editor_hints": {"preferred_editor": "MergePolicyEditor"},
        "required_payload_fields": [],
        "emitted_payload_fields": [],
        "output_edges": [
            {"id": "default", "label": "Continue", "cardinality": "one", "dynamic": False},
        ],
        "graph_rules": {
            "requires_incoming_edges": True,
            "requires_outgoing_edges": True,
            "required_output_ids": ["default"],
            "allows_multiple_outgoing_per_output": False,
            "terminal": False,
        },
        "runtime_contract": {"execution_kind": "synchronization"},
    },

    # ─── Dispatch (retry-capable, success/exhausted) ────────────────────────
    "core.webhook_out": {
        "display_label": "Webhook Dispatch",
        "display_category": "dispatch",
        "description": "Call an external API with a JSON body assembled from contact attributes.",
        "authoring_status": "active",
        "editor_hints": {"preferred_editor": "StructuredRequestBodyEditor"},
        "required_payload_fields": [],  # derived from body field references
        "emitted_payload_fields": [],
        "output_edges": _DISPATCH_OUTPUT_EDGES,
        "graph_rules": _DISPATCH_GRAPH_RULES,
        "runtime_contract": {"execution_kind": "dispatch", "supports_attempt_policy": True},
    },
    "messaging.send_whatsapp_template": {
        "display_label": "Send WhatsApp template",
        "display_category": "dispatch",
        "description": "Send a templated WhatsApp message to a contact via your connected WhatsApp provider.",
        "authoring_status": "active",
        "editor_hints": {},
        "required_payload_fields": [],
        "emitted_payload_fields": [],
        "output_edges": [
            {"id": "success", "label": "Sent", "cardinality": "one", "dynamic": False},
            {"id": "failed",  "label": "Failed", "cardinality": "one", "dynamic": False},
        ],
        "graph_rules": {
            "requires_incoming_edges": True,
            "requires_outgoing_edges": True,
            "required_output_ids": [],
            "allows_multiple_outgoing_per_output": False,
            "terminal": False,
        },
        "runtime_contract": {"execution_kind": "dispatch"},
    },
    "voice.place_call": {
        "display_label": "Place voice call",
        "display_category": "dispatch",
        "description": "Place an AI voice call to a contact via your connected voice provider.",
        "authoring_status": "active",
        "editor_hints": {},
        "required_payload_fields": [],
        "emitted_payload_fields": [],
        "output_edges": [
            {"id": "success", "label": "Placed", "cardinality": "one", "dynamic": False},
            {"id": "failed",  "label": "Failed", "cardinality": "one", "dynamic": False},
        ],
        "graph_rules": {
            "requires_incoming_edges": True,
            "requires_outgoing_edges": True,
            "required_output_ids": [],
            "allows_multiple_outgoing_per_output": False,
            "terminal": False,
        },
        "runtime_contract": {"execution_kind": "dispatch"},
    },
    # ─── Mutation ───────────────────────────────────────────────────────────
    "llm.extract": {
        "display_label": "AI Agent",
        "display_category": "ai",
        "description": "Run a prompt over each contact and save structured fields back to their record for later steps.",
        "authoring_status": "active",
        "editor_hints": {"preferred_editor": "LlmExtractInspector"},
        "required_payload_fields": [],
        "emitted_payload_fields": [],
        "output_edges": [
            {"id": "success", "label": "Success", "cardinality": "one", "dynamic": False},
            {"id": "error", "label": "Error", "cardinality": "one", "dynamic": False},
        ],
        "graph_rules": {
            "requires_incoming_edges": True,
            "requires_outgoing_edges": True,
            "required_output_ids": [],
            "allows_multiple_outgoing_per_output": False,
            "terminal": False,
        },
        "runtime_contract": {"execution_kind": "mutation"},
    },

    # ─── Termination ────────────────────────────────────────────────────────
    "sink.complete": {
        "display_label": "Workflow Complete",
        "display_category": "termination",
        "description": "End the workflow run for the contact.",
        "authoring_status": "active",
        "editor_hints": {},
        "required_payload_fields": [],
        "emitted_payload_fields": [],
        "output_edges": [],
        "graph_rules": {
            "requires_incoming_edges": True,
            "requires_outgoing_edges": False,
            "required_output_ids": [],
            "allows_multiple_outgoing_per_output": False,
            "terminal": True,
        },
        "runtime_contract": {"execution_kind": "termination"},
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Producer vocabulary — the resumable EVENT names and canonical↔provider OUTCOME
# enums a dispatch node contributes to downstream wait / conditional pickers.
#
# Derivation dispatches on the RESOLVED adapter and reads that adapter's own
# canonical<->raw mapping — it never imports one vendor's table and stamps it on
# a different vendor. Each capability builder is given the resolved adapter
# instance; per-vendor truth (outcome action_types, canonical mapping, resume
# events) is read from that instance / its defining module.
# ─────────────────────────────────────────────────────────────────────────────


class OutcomeEnum(BaseModel):
    """One canonical outcome and the producing provider's raw label for it."""
    canonical: str
    provider_label: str


class ProducerVocabulary(BaseModel):
    """The event names + outcome enums one producer node contributes downstream.

    ``outcome_field`` is the bag key the producer's canonical outcome lands on
    (``steps.<node_id>.<outcome_field>``), declared once by the capability adapter
    so the resolver can offer the field AND tag each outcome with its bag path."""
    event_names: list[str] = Field(default_factory=list)
    outcomes: list[OutcomeEnum] = Field(default_factory=list)
    outcome_field: str = ""


# Node type → capability, so the resolver can pick the right adapter family.
_PRODUCER_CAPABILITY: dict[str, str] = {
    "voice.place_call": "voice",
    "messaging.send_whatsapp_template": "messaging",
}


def _adapter_supports_inbound(adapter: Any) -> bool:
    """A producer surfaces outcomes/events only if it can ingest provider inbound.

    Adapter-local probe — an adapter whose ``normalize_webhook`` is a not-yet-
    implemented stub (e.g. AiSensy) raises ``NotImplementedError`` and therefore
    produces NONE of the capability's outcomes/events at runtime; it must not
    surface a fabricated vocabulary to the downstream picker."""
    try:
        # Pragmatic probe: an empty payload exercises only the stub-vs-implemented branch.
        adapter.normalize_webhook({})
    except NotImplementedError:
        return False
    except Exception:  # noqa: BLE001 — a parse error on {} still means inbound is handled
        return True
    return True


def _voice_vocabulary(vendor: str) -> ProducerVocabulary:
    import importlib

    from app.services.orchestration.adapters import resolve_adapter

    adapter = resolve_adapter(capability="voice", vendor=vendor)
    if not _adapter_supports_inbound(adapter):
        return ProducerVocabulary()
    # Read canonical mapping + resume events from the RESOLVED adapter's own
    # module, never a fixed vendor import — derivation stays adapter-local.
    module = importlib.import_module(type(adapter).__module__)
    canonical_outcome = module._canonical_outcome
    resume_event_names = module.voice_resume_event_names

    outcomes: list[OutcomeEnum] = []
    events: set[str] = set()
    for action_type in adapter.ACTION_OUTCOME_MAP:
        canonical = canonical_outcome(action_type)
        outcomes.append(OutcomeEnum(canonical=canonical, provider_label=action_type))
        events.update(resume_event_names(canonical))
    return ProducerVocabulary(
        event_names=sorted(events), outcomes=outcomes,
        outcome_field=module.OUTCOME_BAG_FIELD,
    )


def _messaging_vocabulary(vendor: str) -> ProducerVocabulary:
    import importlib

    from app.services.orchestration.adapters import resolve_adapter
    from app.services.orchestration.adapters.canonical import messaging_resume_event_names

    adapter = resolve_adapter(capability="messaging", vendor=vendor)
    if not _adapter_supports_inbound(adapter):
        return ProducerVocabulary()
    # Read the canonical<-raw outcome mapping from the RESOLVED adapter's own
    # module, never a fixed vendor import — mirrors the voice path's reuse of
    # bolna's _canonical_outcome. The adapter owns the pairs; we don't restate them.
    module = importlib.import_module(type(adapter).__module__)
    canonical_by_raw = module.canonical_outcome_by_action_type()

    outcomes: list[OutcomeEnum] = []
    for action_type in sorted(adapter.ACTION_OUTCOME_MAP):
        canonical = canonical_by_raw.get(action_type, action_type)
        outcomes.append(OutcomeEnum(canonical=canonical, provider_label=action_type))
    events = sorted(messaging_resume_event_names())
    return ProducerVocabulary(
        event_names=events, outcomes=outcomes,
        outcome_field=module.OUTCOME_BAG_FIELD,
    )


_VOCABULARY_BY_CAPABILITY: dict[str, Any] = {
    "voice": _voice_vocabulary,
    "messaging": _messaging_vocabulary,
}


def producer_capability(node_type: str) -> Optional[str]:
    """Capability a dispatch producer node belongs to, or None for non-producers."""
    return _PRODUCER_CAPABILITY.get(node_type)


def producer_vocabulary(*, node_type: str, vendor: str) -> Optional[ProducerVocabulary]:
    """Event names + outcome enums a producer node contributes, resolved per vendor."""
    capability = _PRODUCER_CAPABILITY.get(node_type)
    if capability is None:
        return None
    builder = _VOCABULARY_BY_CAPABILITY.get(capability)
    if builder is None:
        return None
    return builder(vendor)


def produced_event_names_for_capability(capability: str) -> set[str]:
    """Resumable event names a capability's producers can fire, across its
    registered vendors. The canonical event names are capability-truth and do
    not vary by vendor, so this needs no DB lookup — the publish-time wait
    validator scopes the allow-set to the capabilities of the wait's actual
    upstream producer nodes."""
    from app.services.orchestration.adapters import registered_adapters

    builder = _VOCABULARY_BY_CAPABILITY.get(capability)
    if builder is None:
        return set()
    names: set[str] = set()
    for cap, vendor in registered_adapters():
        if cap != capability:
            continue
        try:
            names.update(builder(vendor).event_names)
        except Exception:  # noqa: BLE001 — a misconfigured vendor must not crash validation
            continue
    return names


def _legacy_descriptor(*, node_type: str, workflow_type: str, handler: Any) -> NodeDescriptor:
    """Permissive descriptor for node types not registered in ``_CONTRACT_META``.

    Every Phase 11 (Commit 2) shipped node now has a finalized entry above, so
    this fallback is reserved for *unknown* third-party node types loaded from
    saved definitions. It picks a sensible display category from the type
    prefix and surfaces the handler's flat ``output_edges`` list as
    descriptor edges.
    """
    category = _category_from_prefix(node_type)
    edges = [
        OutputEdgeDescriptor(id=eid, label=eid.replace("_", " ").title(), cardinality="one", dynamic=False)
        for eid in (handler.output_edges or [])
    ]
    is_terminal = not edges
    return NodeDescriptor(
        node_type=node_type,
        workflow_type=workflow_type,
        display_label=node_type,
        display_category=category,
        description="",
        authoring_status="active",
        config_schema=_strip_dev_only_fields(
            handler.config_schema.model_json_schema(), is_dev=settings.is_dev,
        ),
        editor_hints=EditorHints(),
        required_payload_fields=[],
        emitted_payload_fields=[],
        output_edges=edges,
        graph_rules=GraphRules(
            requires_incoming_edges=not node_type.startswith("source."),
            requires_outgoing_edges=not is_terminal,
            terminal=is_terminal,
        ),
        runtime_contract=RuntimeContract(execution_kind=_runtime_kind_from_category(category)),
    )


def _category_from_prefix(node_type: str) -> DisplayCategory:
    if node_type.startswith("source."):
        return "ingress"
    if node_type.startswith("filter."):
        return "qualification"
    if node_type.startswith("logic."):
        return "routing"
    if node_type.startswith("sink."):
        return "termination"
    if node_type.startswith("core."):
        return "dispatch"
    return "routing"


def _runtime_kind_from_category(category: DisplayCategory) -> ExecutionKind:
    if category == "ingress":
        return "entry_event"
    if category == "qualification":
        return "qualification"
    if category == "routing":
        return "routing"
    if category == "suspension":
        return "suspension"
    if category == "synchronization":
        return "synchronization"
    if category == "dispatch":
        return "dispatch"
    if category == "mutation":
        return "mutation"
    if category == "ai":
        return "mutation"
    return "termination"


def _strip_dev_only_fields(config_schema: dict[str, Any], *, is_dev: bool) -> dict[str, Any]:
    """Drop properties flagged ``x-dev-only`` from a rendered JSON Schema in non-dev builds.

    Generic — keys off the ``x-dev-only`` marker so any node can opt a field
    out of the production UI. In dev the schema is returned untouched.
    """
    if is_dev:
        return config_schema
    props = config_schema.get("properties")
    if not isinstance(props, dict):
        return config_schema
    dev_only = [
        name for name, spec in props.items()
        if isinstance(spec, dict) and spec.get("x-dev-only")
    ]
    for name in dev_only:
        props.pop(name, None)
    required = config_schema.get("required")
    if isinstance(required, list) and dev_only:
        config_schema["required"] = [r for r in required if r not in dev_only]
    return config_schema


def build_descriptor(*, node_type: str, workflow_type: str) -> NodeDescriptor:
    """Resolve a handler from the registry and wrap it in a NodeDescriptor.

    Falls back to ``_legacy_descriptor`` for node types whose Phase 11
    contract has not yet been declared in ``_CONTRACT_META``.
    """
    handler = NODE_REGISTRY.get((workflow_type, node_type))
    if handler is None:
        handler = NODE_REGISTRY.get(("*", node_type))
    if handler is None:
        raise KeyError(f"no handler registered for ({workflow_type!r}, {node_type!r})")
    meta = _CONTRACT_META.get(node_type)
    if meta is None:
        return _legacy_descriptor(node_type=node_type, workflow_type=workflow_type, handler=handler)
    edges = [OutputEdgeDescriptor(**e) for e in meta["output_edges"]]
    return NodeDescriptor(
        node_type=node_type,
        workflow_type=workflow_type,
        display_label=meta["display_label"],
        display_category=meta["display_category"],
        description=meta["description"],
        authoring_status=meta.get("authoring_status", "active"),
        config_schema=_strip_dev_only_fields(
            handler.config_schema.model_json_schema(), is_dev=settings.is_dev,
        ),
        editor_hints=EditorHints(**meta.get("editor_hints", {})),
        required_payload_fields=list(meta.get("required_payload_fields", [])),
        emitted_payload_fields=list(meta.get("emitted_payload_fields", [])),
        output_edges=edges,
        graph_rules=GraphRules(**meta.get("graph_rules", {})),
        runtime_contract=RuntimeContract(**meta["runtime_contract"]),
    )


def has_finalized_contract(node_type: str) -> bool:
    """True iff the node type has a Phase 11 contract entry (not just legacy fallback)."""
    return node_type in _CONTRACT_META


def all_finalized_node_types() -> list[str]:
    return sorted(_CONTRACT_META.keys())


__all__ = [
    "DisplayCategory",
    "AuthoringStatus",
    "ExecutionKind",
    "OutputCardinality",
    "OutputEdgeDescriptor",
    "GraphRules",
    "RuntimeContract",
    "EditorHints",
    "NodeDescriptor",
    "OutcomeEnum",
    "ProducerVocabulary",
    "build_descriptor",
    "has_finalized_contract",
    "all_finalized_node_types",
    "producer_capability",
    "producer_vocabulary",
    "produced_event_names_for_capability",
]

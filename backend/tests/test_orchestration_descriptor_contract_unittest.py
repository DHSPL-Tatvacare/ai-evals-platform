"""Node descriptor contract tests — every shipped node has a finalized _CONTRACT_META entry."""
from __future__ import annotations

import pytest

import app.services.orchestration.nodes  # noqa: F401 — register handlers
from app.services.orchestration.node_descriptors import (
    all_finalized_node_types,
    build_descriptor,
    has_finalized_contract,
)


_FINALIZED_NODE_TYPES = {
    "source.cohort",
    "source.dataset",
    "source.event_trigger",
    "filter.eligibility",
    "filter.consent_gate",
    "logic.conditional",
    "logic.split",
    "logic.wait",
    "logic.merge",
    "core.webhook_out",
    "sink.complete",
}

_SUPPORTED_PREFERRED_EDITORS = {
    None,
    "SourceCohortPicker",
    "DatasetPicker",
    "PredicateBuilder",
    "ConditionalBranchesEditor",
    "SplitBranchEditor",
    "WaitConditionEditor",
    "MergePolicyEditor",
    "StructuredRequestBodyEditor",
}


def test_all_finalized_node_types_listed():
    listed = set(all_finalized_node_types())
    missing = _FINALIZED_NODE_TYPES - listed
    assert not missing, f"finalized contract metadata missing for: {sorted(missing)}"


@pytest.mark.parametrize("node_type", sorted(_FINALIZED_NODE_TYPES))
def test_finalized_node_descriptor(node_type):
    assert has_finalized_contract(node_type), node_type
    d = build_descriptor(node_type=node_type, workflow_type="*")
    assert d.node_type == node_type
    assert d.display_label, f"empty display_label for {node_type}"
    assert d.display_category in {
        "ingress", "qualification", "routing", "suspension",
        "synchronization", "dispatch", "mutation", "termination",
    }, d.display_category
    assert d.runtime_contract.execution_kind, f"no execution_kind for {node_type}"
    assert isinstance(d.config_schema, dict)
    assert "properties" in d.config_schema or d.config_schema.get("type") in {"object", None}
    assert d.editor_hints.preferred_editor in _SUPPORTED_PREFERRED_EDITORS


def test_source_cohort_uses_source_cohort_picker():
    d = build_descriptor(node_type="source.cohort", workflow_type="*")
    assert d.editor_hints.preferred_editor == "SourceCohortPicker"
    assert d.display_label == "Cohort"


def test_consent_gate_is_hidden():
    d = build_descriptor(node_type="filter.consent_gate", workflow_type="*")
    assert d.authoring_status == "hidden"


def test_source_nodes_have_only_default_output():
    for nt in ("source.cohort", "source.dataset", "source.event_trigger"):
        d = build_descriptor(node_type=nt, workflow_type="*")
        ids = [oe.id for oe in d.output_edges]
        assert ids == ["default"], (nt, ids)
        assert d.graph_rules.required_output_ids == ["default"]
        assert d.graph_rules.requires_incoming_edges is False
        assert d.graph_rules.requires_outgoing_edges is True


def test_split_outputs_are_dynamic_per_config():
    d = build_descriptor(node_type="logic.split", workflow_type="*")
    assert d.output_edges == []


def test_conditional_outputs_are_dynamic_per_config():
    d = build_descriptor(node_type="logic.conditional", workflow_type="*")
    assert d.output_edges == []
    assert d.editor_hints.preferred_editor == "ConditionalBranchesEditor"


def test_wait_descriptor_lists_all_three_outputs_for_validator():
    d = build_descriptor(node_type="logic.wait", workflow_type="*")
    ids = sorted(oe.id for oe in d.output_edges)
    assert ids == ["event", "timeout", "wakeup"]


def test_core_webhook_has_attempt_policy_runtime_flag():
    d = build_descriptor(node_type="core.webhook_out", workflow_type="*")
    assert d.runtime_contract.supports_attempt_policy is True
    ids = [oe.id for oe in d.output_edges]
    assert ids == ["success", "exhausted"]


def test_webhook_descriptor_exposes_connection_picker():
    d = build_descriptor(node_type="core.webhook_out", workflow_type="*")
    connection_id = d.config_schema["properties"]["connection_id"]
    assert connection_id["x-type"] == "connection_picker"
    assert connection_id["x-provider"] == "webhook"


# ─── dev-only field strip (generic, keyed off x-dev-only) ────────────────────


def test_strip_dev_only_removes_field_in_prod():
    from app.services.orchestration import node_descriptors as nd

    schema = {
        "type": "object",
        "properties": {
            "keep": {"type": "string"},
            "secret_toggle": {"type": "boolean", "x-dev-only": True},
        },
        "required": ["keep", "secret_toggle"],
    }
    out = nd._strip_dev_only_fields(schema, is_dev=False)
    assert "secret_toggle" not in out["properties"]
    assert "secret_toggle" not in out["required"]
    assert "keep" in out["properties"]


def test_strip_dev_only_keeps_field_in_dev():
    from app.services.orchestration import node_descriptors as nd

    schema = {
        "type": "object",
        "properties": {
            "keep": {"type": "string"},
            "secret_toggle": {"type": "boolean", "x-dev-only": True},
        },
        "required": ["keep", "secret_toggle"],
    }
    out = nd._strip_dev_only_fields(schema, is_dev=True)
    assert "secret_toggle" in out["properties"]
    assert "secret_toggle" in out["required"]


def test_build_descriptor_strips_dev_only_field_in_prod(monkeypatch):
    from app.services.orchestration import node_descriptors as nd

    monkeypatch.setattr(nd.settings, "APP_ENVIRONMENT", "production")
    d = build_descriptor(node_type="voice.place_call", workflow_type="*")
    assert "bypass_call_guardrails" not in d.config_schema["properties"]


def test_build_descriptor_keeps_dev_only_field_in_dev(monkeypatch):
    from app.services.orchestration import node_descriptors as nd

    monkeypatch.setattr(nd.settings, "APP_ENVIRONMENT", "local")
    d = build_descriptor(node_type="voice.place_call", workflow_type="*")
    assert "bypass_call_guardrails" in d.config_schema["properties"]

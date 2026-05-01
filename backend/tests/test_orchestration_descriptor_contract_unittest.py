"""Phase 11 — node descriptor contract tests.

Asserts every node type registered in NODE_REGISTRY is exposed through a
`NodeDescriptor` with the canonical shape:
  - non-empty display_label
  - valid display_category
  - declared output_edges (or 'dynamic' coverage for split)
  - graph_rules / runtime_contract populated

The test catalog (the eight nodes finalized in Commit 1) must use the rich
`_CONTRACT_META` entry — not the legacy fallback.
"""
from __future__ import annotations

import pytest

import app.services.orchestration.nodes  # noqa: F401 — register handlers
from app.services.orchestration.node_descriptors import (
    all_finalized_node_types,
    build_descriptor,
    has_finalized_contract,
)
from app.services.orchestration.node_registry import NODE_REGISTRY


_FINALIZED_IN_COMMIT_1 = {
    "source.cohort_query",
    "source.event_trigger",
    "filter.eligibility",
    "filter.consent_gate",
    "logic.conditional",
    "logic.split",
    "logic.wait",
    "logic.merge",
}


def test_all_finalized_node_types_listed():
    """Sanity — every Commit-1 node must register a Phase 11 contract."""
    listed = set(all_finalized_node_types())
    missing = _FINALIZED_IN_COMMIT_1 - listed
    assert not missing, f"finalized contract metadata missing for: {sorted(missing)}"


@pytest.mark.parametrize("node_type", sorted(_FINALIZED_IN_COMMIT_1))
def test_finalized_node_descriptor(node_type):
    assert has_finalized_contract(node_type), node_type
    d = build_descriptor(node_type=node_type, workflow_type="*")
    # Core fields
    assert d.node_type == node_type
    assert d.display_label, f"empty display_label for {node_type}"
    assert d.display_category in {
        "ingress", "qualification", "routing", "suspension",
        "synchronization", "dispatch", "mutation", "termination",
    }, d.display_category
    assert d.runtime_contract.execution_kind, f"no execution_kind for {node_type}"
    # Config schema is JSON-Schema-shaped.
    assert isinstance(d.config_schema, dict)
    assert "properties" in d.config_schema or d.config_schema.get("type") in {"object", None}


def test_consent_gate_is_hidden():
    d = build_descriptor(node_type="filter.consent_gate", workflow_type="*")
    assert d.authoring_status == "hidden"


def test_source_nodes_have_only_default_output():
    for nt in ("source.cohort_query", "source.event_trigger"):
        d = build_descriptor(node_type=nt, workflow_type="*")
        ids = [oe.id for oe in d.output_edges]
        assert ids == ["default"], (nt, ids)
        assert d.graph_rules.required_output_ids == ["default"]
        assert d.graph_rules.requires_incoming_edges is False
        assert d.graph_rules.requires_outgoing_edges is True


def test_split_outputs_are_dynamic_per_config():
    d = build_descriptor(node_type="logic.split", workflow_type="*")
    # Static descriptor surface is empty — branches arrive via config.
    assert d.output_edges == []


def test_wait_descriptor_lists_all_three_outputs_for_validator():
    d = build_descriptor(node_type="logic.wait", workflow_type="*")
    ids = sorted(oe.id for oe in d.output_edges)
    assert ids == ["event", "timeout", "wakeup"]


def test_legacy_node_types_get_fallback_descriptor_with_correct_category():
    # Dispatch / mutation contracts are not finalized in Commit 1 — they
    # should still surface a sensible descriptor via the legacy fallback.
    if ("crm", "crm.send_wati") in NODE_REGISTRY or ("*", "crm.send_wati") in NODE_REGISTRY:
        d = build_descriptor(node_type="crm.send_wati", workflow_type="crm")
        assert d.display_category == "dispatch"
        assert d.authoring_status == "active"
        assert not has_finalized_contract("crm.send_wati")

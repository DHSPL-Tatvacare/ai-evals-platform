"""Pure-function tests for variable mapping precedence + fallback."""
from __future__ import annotations

import pytest

from app.services.orchestration.connections.variable_mapping import (
    VariableMappingConfigError,
    apply_variable_mappings_dict,
    apply_variable_mappings_list,
)


def test_dict_payload_source_resolves_field():
    out = apply_variable_mappings_dict(
        [{"agent_variable": "first_name", "source_kind": "payload", "payload_field": "fn"}],
        {"fn": "Aarti"},
        template_fallback=[],
    )
    assert out == {"first_name": "Aarti"}


def test_dict_static_source_passes_literal():
    out = apply_variable_mappings_dict(
        [{"agent_variable": "campaign", "source_kind": "static", "static_value": "fall-2026"}],
        {"fn": "Aarti"},
        template_fallback=[],
    )
    assert out == {"campaign": "fall-2026"}


def test_dict_missing_payload_field_yields_empty_string():
    out = apply_variable_mappings_dict(
        [{"agent_variable": "city", "source_kind": "payload", "payload_field": "missing"}],
        {"fn": "Aarti"},
        template_fallback=[],
    )
    assert out == {"city": ""}


def test_dict_node_mappings_override_template_fallback():
    out = apply_variable_mappings_dict(
        [{"agent_variable": "first_name", "source_kind": "static", "static_value": "OVERRIDE"}],
        {"fn": "Aarti"},
        template_fallback=[{"name": "first_name", "source": "fn"}],
    )
    assert out == {"first_name": "OVERRIDE"}


def test_dict_template_fallback_used_when_node_mappings_empty():
    out = apply_variable_mappings_dict(
        [],
        {"fn": "Aarti", "city": "Mumbai"},
        template_fallback=[
            {"name": "first_name", "source": "fn"},
            {"name": "city", "source": "city"},
        ],
    )
    assert out == {"first_name": "Aarti", "city": "Mumbai"}


def test_dict_template_fallback_missing_payload_yields_empty():
    out = apply_variable_mappings_dict(
        [],
        {},
        template_fallback=[{"name": "first_name", "source": "fn"}],
    )
    assert out == {"first_name": ""}


def test_dict_unknown_source_kind_raises():
    with pytest.raises(VariableMappingConfigError, match="source_kind"):
        apply_variable_mappings_dict(
            [{"agent_variable": "x", "source_kind": "external", "payload_field": "fn"}],
            {"fn": "Aarti"},
        )


def test_dict_missing_agent_variable_raises():
    with pytest.raises(VariableMappingConfigError, match="agent_variable"):
        apply_variable_mappings_dict(
            [{"source_kind": "payload", "payload_field": "fn"}],
            {"fn": "Aarti"},
        )


def test_list_preserves_order_and_shape():
    out = apply_variable_mappings_list(
        [
            {"agent_variable": "a", "source_kind": "payload", "payload_field": "x"},
            {"agent_variable": "b", "source_kind": "static", "static_value": "lit"},
        ],
        {"x": "1"},
        template_fallback=[],
    )
    assert out == [{"name": "a", "value": "1"}, {"name": "b", "value": "lit"}]


def test_list_template_fallback_when_mappings_empty():
    out = apply_variable_mappings_list(
        [],
        {"fn": "Aarti"},
        template_fallback=[{"name": "patient_name", "source": "fn"}],
    )
    assert out == [{"name": "patient_name", "value": "Aarti"}]


def test_list_node_mappings_override_template_fallback():
    out = apply_variable_mappings_list(
        [{"agent_variable": "patient_name", "source_kind": "static", "static_value": "X"}],
        {"fn": "Aarti"},
        template_fallback=[{"name": "patient_name", "source": "fn"}],
    )
    assert out == [{"name": "patient_name", "value": "X"}]


def test_list_unknown_source_kind_raises():
    with pytest.raises(VariableMappingConfigError):
        apply_variable_mappings_list(
            [{"agent_variable": "x", "source_kind": "weird"}],
            {},
        )

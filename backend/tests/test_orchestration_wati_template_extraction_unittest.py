"""WATI variable extraction (extract_variables → VariableSurface).

Variables come solely from ``customParams`` (WATI's source of truth). No body
scan, no fallbacks: a template without customParams simply has no variables.
Pure-function tests over verbatim WATI candidate shapes. No live WATI.
"""
from __future__ import annotations

from app.services.orchestration.adapters.wati import extract_variables


def test_custom_params_yields_ordered_names():
    # Verbatim shape from a correctly-authored template (document_approved_latest).
    candidate = {
        "customParams": [
            {"paramName": "name", "paramValue": "John"},
            {"paramName": "documentType", "paramValue": "Prescription"},
        ],
        "body": "Hi *{{1}}*,\nyour *{{2}}* has been approved.",
    }
    surface = extract_variables(candidate)
    assert surface.variables == ["name", "documentType"]
    assert surface.body == "Hi *{{1}}*,\nyour *{{2}}* has been approved."


def test_empty_custom_params_yields_no_variables():
    # Verbatim shape from an un-parameterised template (wc_gf_aiagent): the
    # {patient name} text is literal, customParams is empty → no variables.
    candidate = {
        "customParams": [],
        "body": "Hi {patient name}\nProgram Details:{add program details}",
    }
    surface = extract_variables(candidate)
    assert surface.variables == []
    assert surface.body == "Hi {patient name}\nProgram Details:{add program details}"


def test_missing_custom_params_key_yields_no_variables():
    assert extract_variables({"body": "Hi {{1}}"}).variables == []

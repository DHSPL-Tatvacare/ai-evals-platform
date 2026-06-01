"""Edge output-handle discipline: an edge may only wire from a node's
declared output_edges; an invented handle is rejected by validate_definition."""
from __future__ import annotations

import pytest

import app.services.orchestration.nodes  # noqa: F401 — register handlers
from app.services.orchestration.definition_validator import (
    DefinitionValidationError,
    validate_definition,
)


def _wf(nodes, edges):
    return {"nodes": nodes, "edges": edges, "canvas": {}}


_SOURCE = {
    "id": "src",
    "type": "source.event_trigger",
    "position": {"x": 0, "y": 0},
    "data": {},
    "config": {},
}
_GATE = {
    "id": "gate",
    "type": "filter.eligibility",
    "position": {"x": 0, "y": 100},
    "data": {},
    "config": {},
}
_SINK = {
    "id": "done",
    "type": "sink.complete",
    "position": {"x": 0, "y": 200},
    "data": {},
    "config": {},
}


def test_invented_output_handle_rejected_in_draft():
    # filter.eligibility declares only 'passed'/'skipped'; 'success' is invented.
    defn = _wf(
        [_SOURCE, _GATE, _SINK],
        [
            {"id": "e1", "source": "src", "target": "gate", "output_id": "default"},
            {"id": "e2", "source": "gate", "target": "done", "output_id": "success"},
        ],
    )
    with pytest.raises(DefinitionValidationError) as exc_info:
        validate_definition(defn, workflow_type="crm", mode="draft")
    assert any(
        "success" in (it["message"] or "") and (it.get("field") or "").startswith("edges")
        for it in exc_info.value.errors
    )


def test_declared_output_handle_passes_in_draft():
    defn = _wf(
        [_SOURCE, _GATE, _SINK],
        [
            {"id": "e1", "source": "src", "target": "gate", "output_id": "default"},
            {"id": "e2", "source": "gate", "target": "done", "output_id": "passed"},
        ],
    )
    validate_definition(defn, workflow_type="crm", mode="draft")

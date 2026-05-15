"""Strict node config behaviour — unconditional `extra='forbid'`.

The flag-gated rollout was removed. `strict_node_config_dict()` always
returns `ConfigDict(extra='forbid')`. These tests pin that contract:

  1. The helper returns the strict shape, no env reads, no toggles.
  2. Models built from the helper reject unknown keys at validation time.
  3. Legacy `model_validator(mode='before')` coercions on the real node
     configs still fire before strict-mode kicks in (regression guard
     against accidentally moving strictness ahead of legacy lift).
  4. `contract_audit.audit_definition` produces one finding per offending
     node and handles unknown node types without crashing.
"""
from __future__ import annotations

from typing import Optional

import pytest
from pydantic import BaseModel, ValidationError

from app.services.orchestration import _config_strictness
from app.services.orchestration import contract_audit


def test_helper_always_returns_extra_forbid():
    assert _config_strictness.strict_node_config_dict() == {"extra": "forbid"}


def test_strict_dict_built_model_rejects_extra_keys():
    """The helper's contract: any model that consumes
    `strict_node_config_dict()` rejects unknown keys, period."""
    cfg_dict = _config_strictness.strict_node_config_dict()

    class _Sink(BaseModel):
        model_config = cfg_dict
        reason: Optional[str] = None

    instance = _Sink(reason="ok")
    assert instance.reason == "ok"

    with pytest.raises(ValidationError) as exc:
        _Sink(reason="ok", surprise="oops")
    err = str(exc.value).lower()
    assert "extra" in err or "surprise" in err


def test_legacy_consent_gate_dialect_still_loads():
    """Regression guard: legacy ``require_explicit_optin`` shape must keep
    loading on the real config — its ``model_validator(mode='before')``
    runs first, before strict-extras kicks in."""
    from app.services.orchestration.nodes import filter_consent_gate

    cfg = filter_consent_gate._Config(
        channel="wa",
        require_explicit_optin=True,
    )
    assert cfg.consent_policy == "explicit_optin"


def test_legacy_split_default_branch_alias_still_loads():
    """Regression guard: the ``default_branch`` (label) → ``default_branch_id``
    (id) coercion is still applied on the real config."""
    from app.services.orchestration.nodes import logic_split

    cfg = logic_split._Config(
        mode="by_field",
        field="plan",
        branches=[
            {"id": "gold", "label": "Gold", "match": "gold"},
            {"id": "silver", "label": "Silver", "match": "silver"},
        ],
        default_branch="silver",
    )
    assert cfg.default_branch_id == "silver"


def test_audit_clean_workflow_yields_zero_findings():
    findings = contract_audit.audit_definition(
        workflow_id="wf-clean",
        version_id="v-1",
        version_status="published",
        app_id="inside-sales",
        workflow_type="crm",
        definition={
            "nodes": [
                {"id": "n1", "type": "sink.complete", "config": {"reason": "ok"}},
            ],
            "edges": [],
        },
    )
    assert findings == []


def test_audit_handles_unknown_node_type():
    findings = contract_audit.audit_definition(
        workflow_id="wf-unknown-type",
        version_id="v-1",
        version_status="draft",
        app_id="inside-sales",
        workflow_type="crm",
        definition={
            "nodes": [
                {"id": "n1", "type": "not.a.real.type", "config": {}},
            ],
            "edges": [],
        },
    )
    assert len(findings) == 1
    assert "unknown node type" in findings[0].issue.lower()
    assert findings[0].node_id == "n1"


def test_audit_emits_csv_writeable_dataclass():
    """The CSV writer must serialise findings without raising — protects
    against accidentally adding an unhashable field to ``AuditFinding``."""
    import io
    findings = [
        contract_audit.AuditFinding(
            workflow_id="wf-1",
            version_id="v-1",
            version_status="draft",
            app_id="a",
            workflow_type="crm",
            node_id="n1",
            node_type="not.real",
            issue="x",
        ),
    ]
    buf = io.StringIO()
    contract_audit.write_csv(findings, buf)
    assert "wf-1" in buf.getvalue()
    assert "node_id" in buf.getvalue().splitlines()[0]

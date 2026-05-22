"""The action table speaks ONE generic correlation contract — no vendor columns."""
from __future__ import annotations

from app.models.orchestration import WorkflowRunRecipientAction


def test_vendor_named_correlation_columns_are_gone():
    cols = set(WorkflowRunRecipientAction.__table__.columns.keys())
    assert "bolna_execution_id" not in cols
    assert "bolna_batch_id" not in cols


def test_generic_correlation_contract_columns_exist():
    cols = set(WorkflowRunRecipientAction.__table__.columns.keys())
    # send-time id (status/outcome) + reply-quote id (inbound replies)
    assert "provider_correlation_id" in cols
    assert "provider_reply_ref" in cols

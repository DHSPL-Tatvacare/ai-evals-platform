from app.models.orchestration import WorkflowRunRecipientAction


def test_action_has_outcome_bucket_column():
    cols = WorkflowRunRecipientAction.__table__.c
    assert "outcome_bucket" in cols
    assert cols["outcome_bucket"].nullable is True

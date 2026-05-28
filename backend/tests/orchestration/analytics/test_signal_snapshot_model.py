"""Shape assertions for the orchestration signal-snapshot ORM model."""

from app.models.orchestration_signal import OrchestrationSignalSnapshot


def test_tablename_and_schema():
    assert OrchestrationSignalSnapshot.__tablename__ == "orchestration_signal_snapshot"
    assert OrchestrationSignalSnapshot.__table__.schema == "analytics"


def test_columns_present():
    cols = set(OrchestrationSignalSnapshot.__table__.columns.keys())
    assert {"tenant_id", "app_id", "generated_at", "signals"}.issubset(cols)


def test_recent_index_on_tenant_app_generated():
    index_names = {ix.name for ix in OrchestrationSignalSnapshot.__table__.indexes}
    assert "ix_orchestration_signal_snapshot_recent" in index_names

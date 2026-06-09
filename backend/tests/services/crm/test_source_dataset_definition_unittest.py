"""SourceDatasetDefinition ORM — per-dataset ingestion definition; pure metadata, no live DB."""
from __future__ import annotations

from app.models.crm import SourceDatasetDefinition


def test_tablename_and_schema():
    assert SourceDatasetDefinition.__tablename__ == "source_dataset_definition"
    assert SourceDatasetDefinition.__table__.schema == "platform"


def test_columns_present_with_nullability():
    cols = SourceDatasetDefinition.__table__.columns
    expected = {
        "id": False,
        "tenant_id": False,
        "app_id": False,
        "connection_id": False,
        "record_type": False,
        "filter_predicate": True,
        "status": False,
        "version": False,
        "schedule_id": True,
        "created_at": False,
        "updated_at": False,
    }
    assert set(cols.keys()) == set(expected)
    for name, nullable in expected.items():
        assert cols[name].nullable is nullable, name


def test_server_defaults():
    cols = SourceDatasetDefinition.__table__.columns
    assert cols["status"].server_default.arg == "draft"
    assert cols["version"].server_default.arg == "0"


def test_unique_constraint_on_scoping_tuple():
    from sqlalchemy import UniqueConstraint

    uniques = [c for c in SourceDatasetDefinition.__table__.constraints if isinstance(c, UniqueConstraint)]
    tuples = {tuple(col.name for col in u.columns) for u in uniques}
    assert ("tenant_id", "app_id", "connection_id", "record_type") in tuples


def test_tenant_fk_cascade():
    fk = next(iter(SourceDatasetDefinition.__table__.columns["tenant_id"].foreign_keys))
    assert fk.column.table.fullname == "platform.tenants"
    assert fk.ondelete == "CASCADE"

"""ChannelDefaultConnection ORM shape — the D2 default-per-channel table.

Locks the table/columns/constraint so a migration drift is caught on the host
before the docker migrate + boot gate. No DB connection; pure metadata.
"""
import uuid

from app.models.channel_default_connection import ChannelDefaultConnection


def test_table_identity():
    assert ChannelDefaultConnection.__tablename__ == "channel_default_connections"
    assert ChannelDefaultConnection.__table__.schema == "orchestration"


def test_columns_present():
    cols = ChannelDefaultConnection.__table__.columns
    for name in ("id", "tenant_id", "app_id", "channel", "connection_id",
                 "created_at", "updated_at"):
        assert name in cols, f"missing column {name}"
    assert cols["app_id"].type.length == 64
    assert cols["channel"].type.length == 32
    assert cols["tenant_id"].nullable is False
    assert cols["channel"].nullable is False
    assert cols["connection_id"].nullable is False


def test_unique_per_tenant_app_channel():
    uniques = [
        tuple(c.name for c in con.columns)
        for con in ChannelDefaultConnection.__table__.constraints
        if con.__class__.__name__ == "UniqueConstraint"
    ]
    assert ("tenant_id", "app_id", "channel") in uniques


def test_connection_id_fks_provider_connections():
    fk = next(iter(ChannelDefaultConnection.__table__.c.connection_id.foreign_keys))
    assert fk.column.table.name == "provider_connections"
    assert fk.column.table.schema == "orchestration"


def test_instantiable():
    row = ChannelDefaultConnection(
        tenant_id=uuid.uuid4(), app_id="inside-sales",
        channel="whatsapp", connection_id=uuid.uuid4(),
    )
    assert row.channel == "whatsapp"

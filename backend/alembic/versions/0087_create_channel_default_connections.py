"""channel_default_connections — default provider connection per channel.

Rung 2 of the authoring resolve_connection ladder: when a request names a
channel (whatsapp/voice) but not a connection, this table picks the default.
Channel is explicit (provider_connections is provider-keyed). Additive; no
backfill.

Revision ID: 0087
Revises: 0086
Create Date: 2026-06-02
"""
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0087"
down_revision: Union[str, None] = "0086"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "channel_default_connections",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("app_id", sa.String(length=64), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["platform.tenants.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["orchestration.provider_connections.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "tenant_id", "app_id", "channel",
            name="uq_channel_default_connections_scope_channel",
        ),
        schema="orchestration",
    )


def downgrade() -> None:
    op.drop_table("channel_default_connections", schema="orchestration")

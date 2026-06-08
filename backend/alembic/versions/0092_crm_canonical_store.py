"""crm canonical store — landing + core + typed slots + per-connection field map.

Additive: six platform tables for the generic CRM ingestion layer (Leg 3, Phase 1).
``connection_id`` is an indexed UUID, NOT a cross-schema FK to
``orchestration.provider_connections`` (links go orchestration→platform; app code
scopes on tenant+app+connection). Nothing reads these yet — zero blast radius.

Revision ID: 0092
Revises: 0091
Create Date: 2026-06-08
"""
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0092"
down_revision: Union[str, None] = "0091"
branch_labels = None
depends_on = None


def _slot_cols(*, txt: int, numint: int, bools: int) -> list[sa.Column]:
    cols: list[sa.Column] = []
    for i in range(1, txt + 1):
        cols.append(sa.Column(f"txt_{i:02d}", sa.Text(), nullable=True))
    for i in range(1, numint + 1):
        cols.append(sa.Column(f"num_{i:02d}", sa.Numeric(), nullable=True))
        cols.append(sa.Column(f"int_{i:02d}", sa.BigInteger(), nullable=True))
        cols.append(sa.Column(f"dt_{i:02d}", sa.DateTime(timezone=True), nullable=True))
    for i in range(1, bools + 1):
        cols.append(sa.Column(f"bool_{i:02d}", sa.Boolean(), nullable=True))
    cols.append(sa.Column("json_01", postgresql.JSONB(), nullable=True))
    return cols


def upgrade() -> None:
    op.create_table(
        "crm_source_record",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("app_id", sa.String(64), nullable=False),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_object", sa.String(128), nullable=False),
        sa.Column("record_type", sa.String(16), nullable=False),
        sa.Column("source_record_id", sa.String(256), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=False),
        sa.Column("source_record_hash", sa.String(64), nullable=True),
        sa.Column("first_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_in_source_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "tenant_id", "app_id", "connection_id", "source_object", "source_record_id",
            name="uq_crm_source_record_natural_key",
        ),
        schema="platform",
    )
    op.create_index(
        "ix_crm_source_record_scope", "crm_source_record",
        ["tenant_id", "app_id", "connection_id"], schema="platform",
    )

    op.create_table(
        "crm_lead",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("app_id", sa.String(64), nullable=False),
        sa.Column("lead_id", sa.String(128), nullable=False),
        sa.Column("first_name", sa.String(256), nullable=True),
        sa.Column("last_name", sa.String(256), nullable=True),
        sa.Column("full_name", sa.String(512), nullable=True),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("phone_number", sa.String(64), nullable=True),
        sa.Column("phone_number_norm", sa.String(32), nullable=True),
        sa.Column("source", sa.String(128), nullable=True),
        sa.Column("sub_source", sa.String(128), nullable=True),
        sa.Column("lead_stage", sa.String(128), nullable=True),
        sa.Column("lead_substage", sa.String(128), nullable=True),
        sa.Column("status", sa.String(128), nullable=True),
        sa.Column("lost_reason", sa.String(256), nullable=True),
        sa.Column("owner_id", sa.String(128), nullable=True),
        sa.Column("owner_name", sa.String(256), nullable=True),
        sa.Column("converted", sa.Boolean(), nullable=True),
        sa.Column("converted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "app_id", "lead_id", name="uq_crm_lead_business_key"),
        schema="platform",
    )
    op.create_index("ix_crm_lead_scope", "crm_lead", ["tenant_id", "app_id"], schema="platform")
    op.create_index(
        "ix_crm_lead_stage", "crm_lead", ["tenant_id", "app_id", "lead_stage"], schema="platform",
    )
    op.create_index(
        "ix_crm_lead_phone_norm", "crm_lead",
        ["tenant_id", "app_id", "phone_number_norm"], schema="platform",
    )

    op.create_table(
        "crm_lead_ext",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("crm_lead_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("app_id", sa.String(64), nullable=False),
        *_slot_cols(txt=30, numint=20, bools=10),
        sa.ForeignKeyConstraint(
            ["crm_lead_id"], ["platform.crm_lead.id"], ondelete="CASCADE",
        ),
        sa.UniqueConstraint("crm_lead_id", name="uq_crm_lead_ext_one_to_one"),
        schema="platform",
    )
    op.create_index(
        "ix_crm_lead_ext_scope", "crm_lead_ext", ["tenant_id", "app_id"], schema="platform",
    )

    op.create_table(
        "crm_activity",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("app_id", sa.String(64), nullable=False),
        sa.Column("lead_id", sa.String(128), nullable=False),
        sa.Column("source_activity_id", sa.String(256), nullable=False),
        sa.Column("direction", sa.String(32), nullable=True),
        sa.Column("status", sa.String(128), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "tenant_id", "app_id", "source_activity_id", name="uq_crm_activity_natural_key",
        ),
        schema="platform",
    )
    op.create_index(
        "ix_crm_activity_lead", "crm_activity", ["tenant_id", "app_id", "lead_id"], schema="platform",
    )

    op.create_table(
        "crm_activity_ext",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("crm_activity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("app_id", sa.String(64), nullable=False),
        *_slot_cols(txt=10, numint=5, bools=5),
        sa.ForeignKeyConstraint(
            ["crm_activity_id"], ["platform.crm_activity.id"], ondelete="CASCADE",
        ),
        sa.UniqueConstraint("crm_activity_id", name="uq_crm_activity_ext_one_to_one"),
        schema="platform",
    )
    op.create_index(
        "ix_crm_activity_ext_scope", "crm_activity_ext", ["tenant_id", "app_id"], schema="platform",
    )

    op.create_table(
        "crm_field_map",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("app_id", sa.String(64), nullable=False),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("record_type", sa.String(16), nullable=False),
        sa.Column("slot", sa.String(32), nullable=False),
        sa.Column("semantic_key", sa.String(128), nullable=False),
        sa.Column("source_field", sa.String(256), nullable=False),
        sa.Column("data_type", sa.String(32), nullable=False),
        sa.Column("value_map", postgresql.JSONB(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.UniqueConstraint(
            "tenant_id", "app_id", "connection_id", "record_type", "slot",
            name="uq_crm_field_map_slot",
        ),
        sa.UniqueConstraint(
            "tenant_id", "app_id", "connection_id", "record_type", "semantic_key",
            name="uq_crm_field_map_semantic_key",
        ),
        schema="platform",
    )
    op.create_index(
        "ix_crm_field_map_scope", "crm_field_map",
        ["tenant_id", "app_id", "connection_id"], schema="platform",
    )


def downgrade() -> None:
    op.drop_table("crm_field_map", schema="platform")
    op.drop_table("crm_activity_ext", schema="platform")
    op.drop_table("crm_activity", schema="platform")
    op.drop_table("crm_lead_ext", schema="platform")
    op.drop_table("crm_lead", schema="platform")
    op.drop_table("crm_source_record", schema="platform")

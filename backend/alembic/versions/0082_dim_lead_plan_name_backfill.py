"""Backfill dim_lead.attributes.plan_name from the mirror raw_payload.

The leads sync now writes the mutable ``attributes`` bag, but existing rows
predate that wiring (and incremental sync only revisits modified leads).
Lift ``plan_name`` from ``crm_lead_record.raw_payload`` into
``dim_lead.attributes`` so the CRM Leads column/filter/suggestions populate.
Mirrors the source/source_campaign lift in revision 0042.
"""

from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "0082"
down_revision: Union[str, None] = "0081"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text(
        """
        UPDATE analytics.dim_lead dl
        SET attributes = jsonb_strip_nulls(
            coalesce(dl.attributes, '{}'::jsonb)
            || jsonb_build_object('plan_name', clr.raw_payload->>'plan_name')
        )
        FROM analytics.crm_lead_record clr
        WHERE dl.tenant_id = clr.tenant_id
          AND dl.app_id = clr.app_id
          AND dl.lead_id = clr.lead_id
          AND nullif(clr.raw_payload->>'plan_name', '') IS NOT NULL
        """
    ))


def downgrade() -> None:
    # Data backfill — intentionally not reversed (mirrors revision 0042).
    # A rollback would also strip plan_name values the live sync writes,
    # which is not the intent of reverting this one-time lift.
    pass

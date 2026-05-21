"""analytics_dashboards.is_platform — flag system/platform dashboards

Revision ID: 0072
Revises: 0071
Create Date: 2026-05-21
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0072"
down_revision: Union[str, None] = "0071"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analytics_dashboards",
        sa.Column(
            "is_platform",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        schema="platform",
    )


def downgrade() -> None:
    op.drop_column("analytics_dashboards", "is_platform", schema="platform")

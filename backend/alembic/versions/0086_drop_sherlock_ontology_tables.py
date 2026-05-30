"""Drop the dead Sherlock ontology tables.

Removes ``platform.sherlock_ontology_classes``,
``platform.sherlock_ontology_entity_types`` and
``platform.sherlock_entity_resolvers``. These had zero live readers — the only
consumers were the deleted ``app/services/sherlock/`` grounding package and the
``seed_sherlock_ontology`` seeder, both removed in the same change. Child tables
are dropped before the parent ``sherlock_ontology_classes``.

Revision ID: 0086
Revises: 0085
Create Date: 2026-05-30
"""
from alembic import op

revision = "0086"
down_revision = "0085"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS platform.sherlock_entity_resolvers")
    op.execute("DROP TABLE IF EXISTS platform.sherlock_ontology_entity_types")
    op.execute("DROP TABLE IF EXISTS platform.sherlock_ontology_classes")


def downgrade() -> None:
    raise NotImplementedError(
        "0086 drops dead Sherlock ontology tables; no live reader. "
        "Recover from the 0001 baseline snapshot if a rollback is ever needed."
    )

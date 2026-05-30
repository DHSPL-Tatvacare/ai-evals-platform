"""S0.2 — structural guard for Alembic 0086 (drop dead ontology tables).

Asserts the revision exists, chains off 0085, and that ``upgrade()`` drops
all three schema-qualified ``platform.sherlock_*`` ontology tables. We assert
on the revision SOURCE, never live DDL — the acceptance gate runs the real
``alembic upgrade head`` in docker-compose.
"""
from pathlib import Path


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "0086_drop_sherlock_ontology_tables.py"
)


def test_migration_file_exists():
    assert MIGRATION_PATH.exists(), f"missing migration: {MIGRATION_PATH}"


def test_revision_chains_off_0085():
    source = MIGRATION_PATH.read_text()
    assert 'revision = "0086"' in source
    assert 'down_revision = "0085"' in source, "down_revision must chain off 0085"
    assert "def upgrade()" in source
    assert "def downgrade()" in source


def test_upgrade_drops_all_three_ontology_tables():
    source = MIGRATION_PATH.read_text()
    for table in (
        "platform.sherlock_entity_resolvers",
        "platform.sherlock_ontology_entity_types",
        "platform.sherlock_ontology_classes",
    ):
        assert f"DROP TABLE IF EXISTS {table}" in source, (
            f"upgrade() must drop {table}"
        )


def test_child_tables_dropped_before_parent():
    source = MIGRATION_PATH.read_text()
    upgrade_body = source[source.index("def upgrade()"):source.index("def downgrade()")]
    parent_pos = upgrade_body.index("platform.sherlock_ontology_classes")
    for child in (
        "platform.sherlock_entity_resolvers",
        "platform.sherlock_ontology_entity_types",
    ):
        assert upgrade_body.index(child) < parent_pos, (
            f"{child} must be dropped before platform.sherlock_ontology_classes"
        )

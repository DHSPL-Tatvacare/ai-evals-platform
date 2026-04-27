"""baseline prod schema snapshot

Captures prod schema as of 2026-04-27 from prod_schema_snapshot.sql.
On prod and any environment that already has the schema, this migration
is skipped via ``alembic stamp head``. It runs end-to-end only on fresh
dev/test/CI databases.

See:
- backend/alembic/baseline/prod_schema_snapshot.sql — the raw dump
- backend/alembic/baseline/drift_report.md — bucket A reconciliation
- backend/alembic/baseline/drift_accepted.md — accepted drift
- backend/alembic/baseline/follow_up_migrations.md — bucket B / D plan

Revision ID: 0001_baseline_prod
Revises:
Create Date: 2026-04-27
"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence, Union

from alembic import op


revision: str = "0001_baseline_prod"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _load_baseline_statements() -> list[str]:
    """Load the prod dump and split it into single statements.

    asyncpg's prepared-statement path rejects multi-statement scripts, so
    we feed alembic's op.execute one statement at a time.

    The snapshot contains only DDL (no PL/pgSQL function bodies, no DO
    blocks, no dollar-quoted strings — verified at write time). A naive
    split on ``;`` at end-of-line is therefore safe. If a future re-baseline
    introduces dollar-quoted bodies, this splitter must be replaced with
    a real lexer.
    """
    raw = (
        Path(__file__).resolve().parent.parent
        / "baseline"
        / "prod_schema_snapshot.sql"
    ).read_text()

    # Drop:
    # - psql client directives (\restrict / \unrestrict) — not SQL.
    # - pure-comment lines — noise.
    # - the pg_dump search_path reset (`SELECT pg_catalog.set_config('search_path', '', false)`).
    #   It's emitted by pg_dump so its own qualified statements parse correctly,
    #   but it leaves the connection with no search_path, which breaks alembic's
    #   final unqualified `INSERT INTO alembic_version`.
    cleaned_lines = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if line.startswith("\\"):
            continue
        if line.lstrip().startswith("--"):
            continue
        if "set_config('search_path'" in line:
            continue
        cleaned_lines.append(line)
    cleaned = "\n".join(cleaned_lines)

    statements: list[str] = []
    buffer: list[str] = []
    for line in cleaned.splitlines():
        buffer.append(line)
        if line.rstrip().endswith(";"):
            stmt = "\n".join(buffer).strip()
            if stmt:
                statements.append(stmt)
            buffer = []
    # Trailing buffer without terminating semicolon (shouldn't happen for pg_dump).
    tail = "\n".join(buffer).strip()
    if tail:
        statements.append(tail)
    return statements


def upgrade() -> None:
    for stmt in _load_baseline_statements():
        op.execute(stmt)


def downgrade() -> None:
    raise NotImplementedError(
        "Cannot downgrade past the baseline. Drop the database and run "
        "`alembic upgrade head` to recreate, or recover from PITR."
    )

"""Apply manifest-driven COMMENT ON COLUMN statements to the live database.

Sherlock's SQL agent reads ``pg_description`` rows for column semantics
(role, data_type, semantic_type, synonyms, etc.). Those rows are generated
from the per-app manifests under
``backend/app/services/chat_engine/manifests/``, not from
``Base.metadata``, so they need a separate sync pass after schema DDL is
in place. Alembic does not own them; this script does.

Called once per boot from ``app.main`` lifespan after Alembic-applied
migrations and (for now, until Phase 6 ships) after the legacy
``bootstrap_database_schema`` run. Also runnable standalone for
out-of-band re-syncs:

    PYTHONPATH=backend python -m scripts.sync_column_comments

The whole batch runs inside a single transaction. If any statement fails
(e.g., manifest references a column that doesn't exist), the whole batch
rolls back and boot fails loudly — preferred over silent drift.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.services.chat_engine.comment_emitter import emit_column_comments

_log = logging.getLogger(__name__)


async def sync_column_comments(connection: AsyncConnection) -> int:
    """Apply every manifest-emitted COMMENT ON COLUMN to ``connection``.

    Returns the number of statements applied. Does not commit; the caller
    owns the transaction boundary.
    """
    statements = emit_column_comments()
    for stmt in statements:
        await connection.execute(text(stmt))
    _log.info("sync_column_comments: applied %d COMMENT statements", len(statements))
    return len(statements)


async def _main() -> None:
    """Standalone entry: open a connection via app.database.engine and sync."""
    from app.database import engine
    async with engine.begin() as conn:
        await sync_column_comments(conn)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(_main())

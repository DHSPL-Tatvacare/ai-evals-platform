"""Per-tool-call audit writer for ``analytics.log_sherlock_tool_call``.

The Sherlock admin Logs page (``/admin/sherlock/tool-calls/...``) reads
from this table to show the SQL, arguments, routing, and per-call
metrics for every specialist tool invocation. The table, the read API
(``app/services/sherlock/api/tool_calls.py``), and the admin UI all
existed; the writer was missing. This module is the writer.

One row per tool invocation. Written in a fresh session so the
specialist's main pipeline (which closed its own session after
``execute_query``) is not affected by audit-write latency or failures.
Failures degrade to a log line — audit must never break a successful
tool call.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from app.database import async_session
from app.models.analytics_log import LogSherlockToolCall

logger = logging.getLogger(__name__)


async def record_tool_call(
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    app_id: str,
    chat_session_id: uuid.UUID,
    call_id: str | None,
    tool_name: str,
    arguments: dict[str, Any] | None,
    generated_sql: str | None,
    validated_sql: str | None,
    execution_ms: float | None,
    row_count: int | None,
    status: str,
    error_message: str | None,
    llm_model: str | None,
) -> None:
    try:
        async with async_session() as db:
            db.add(LogSherlockToolCall(
                tenant_id=tenant_id,
                user_id=user_id,
                db_session_id=chat_session_id,
                session_id=str(chat_session_id),
                call_id=call_id,
                app_id=app_id,
                tool_name=tool_name,
                arguments=arguments or {},
                generated_sql=generated_sql,
                validated_sql=validated_sql,
                execution_ms=execution_ms,
                row_count=row_count,
                status=status,
                error_message=error_message,
                llm_model=llm_model,
            ))
            await db.commit()
    except Exception as exc:  # noqa: BLE001 — audit must not break the turn
        logger.warning(
            'log_sherlock_tool_call write failed for chat_session=%s tool=%s: %s',
            chat_session_id, tool_name, exc,
        )


__all__ = ['record_tool_call']

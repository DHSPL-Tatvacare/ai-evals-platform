"""
Provider-agnostic multi-turn tool loop.
Delegates all message format concerns to the adapter.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Awaitable

from app.services.chat_engine.types import ChatAdapter

logger = logging.getLogger(__name__)

DispatchFn = Callable[[str, dict[str, Any]], Awaitable[str]]


async def run_tool_loop(
    *,
    adapter: ChatAdapter,
    messages: list[Any],
    tools: list[dict[str, Any]],
    system: str,
    temperature: float,
    dispatch_fn: DispatchFn,
    max_rounds: int = 5,
) -> tuple[str | None, list[Any]]:
    """
    Run the multi-turn tool calling loop.

    Returns (final_text, messages).
    final_text is None if max_rounds exceeded.
    """
    for _round in range(max_rounds):
        response = await adapter.send(messages, tools, system, temperature)
        response_msg = adapter.extract_response_message(response)
        messages.append(response_msg)

        tool_calls = adapter.extract_tool_calls(response)
        if not tool_calls:
            return adapter.extract_text(response), messages

        for tc in tool_calls:
            logger.info("Tool call: %s(%s)", tc.name, list(tc.arguments.keys()))
            result = await dispatch_fn(tc.name, tc.arguments)
            messages.append(adapter.build_tool_result(tc, result))

    return None, messages

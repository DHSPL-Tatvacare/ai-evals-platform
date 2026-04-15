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
    max_rounds: int = 15,
    max_seconds: float = 150.0,
    first_round_tool_choice: str = 'auto',
    on_text_delta: Callable[[str], Awaitable[None]] | None = None,
) -> tuple[str | None, list[Any]]:
    """
    Run the multi-turn tool calling loop.

    Returns (final_text, messages).
    final_text is None if max_rounds or time limit exceeded.
    """
    import time
    deadline = time.monotonic() + max_seconds

    for _round in range(max_rounds):
        if time.monotonic() >= deadline:
            logger.warning('Tool loop hit %ss time limit after %d rounds', max_seconds, _round)
            break
        tool_choice = first_round_tool_choice if _round == 0 else 'auto'
        response = None
        async for event in adapter.send_stream(messages, tools, system, temperature, tool_choice=tool_choice):
            if event["type"] == "text_delta":
                if on_text_delta is not None and event.get("delta"):
                    await on_text_delta(event["delta"])
                continue
            if event["type"] == "response":
                response = event["response"]
                break

        if response is None:
            response = await adapter.send(messages, tools, system, temperature, tool_choice=tool_choice)
        response_msg = adapter.extract_response_message(response)
        if isinstance(response_msg, list):
            messages.extend(response_msg)
        else:
            messages.append(response_msg)

        tool_calls = adapter.extract_tool_calls(response)
        if not tool_calls:
            return adapter.extract_text(response), messages

        tool_results: list[str] = []
        for tc in tool_calls:
            logger.info("Tool call: %s(%s)", tc.name, list(tc.arguments.keys()))
            result = await dispatch_fn(tc.name, tc.arguments)
            tool_results.append(result)
        messages.extend(adapter.build_tool_results(tool_calls, tool_results))

    return None, messages

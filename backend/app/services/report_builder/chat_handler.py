"""
Report builder chat surface.
Wires report-specific tools and system prompt into the shared chat engine.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.chat_engine import create_adapter, run_tool_loop
from app.services.report_builder.tool_definitions import TOOLS
from app.services.report_builder.tool_handlers import dispatch_tool_call

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a report builder assistant. Users describe what they want to see in an \
evaluation report using natural language. Your job is to translate their intent \
into a structured report configuration by selecting and arranging the right \
section types.

WORKFLOW:
1. When the user describes what they want, call list_section_types to see available \
   building blocks.
2. Match the user's intent to section types based on descriptions and use_when hints.
3. If you need more detail about a section type, call get_section_detail.
4. Call list_app_sections to see what the user's app already supports.
5. Use compose_report to propose a configuration. The frontend will show a live preview.
6. Iterate with the user — add, remove, reorder sections based on their feedback.
7. Only call save_template when the user explicitly says to save.

RULES:
- Never ask the user to name section types. Map their natural language to types yourself.
- Be concise. Show what you're building, don't explain the system.
- When proposing sections, briefly explain WHY each maps to their request.
- If the user's request doesn't map to any section type, say so honestly.
"""

MAX_TOOL_ROUNDS = 5


def _summarize_tool_result(name: str, result_str: str) -> str:
    """Extract a short label from a tool result for the UI badge."""
    try:
        data = json.loads(result_str)
    except (json.JSONDecodeError, TypeError):
        return "done"

    if name == "list_section_types":
        sections = data.get("sections", [])
        return f"{len(sections)} types"
    if name == "list_app_sections":
        app_id = data.get("app_id", "")
        sections = data.get("sections", [])
        return f"{app_id} · {len(sections)} sections" if app_id else f"{len(sections)} sections"
    if name == "get_section_detail":
        return data.get("key", data.get("label", "done"))
    if name == "compose_report":
        sections = data.get("sections", [])
        return f"{len(sections)} sections"
    if name == "save_template":
        return data.get("report_name", "saved")
    return "done"


async def run_chat_turn(
    session: dict[str, Any],
    user_message: str,
    *,
    provider: str,
    model: str,
    db: AsyncSession,
) -> dict[str, Any]:
    """
    Process one user message through the LLM with tool calling.
    Returns the final assistant response + any composed report config.
    """
    adapter = await create_adapter(
        provider=provider,
        model=model,
        tenant_id=session["tenant_id"],
        user_id=session["user_id"],
    )

    session["messages"].append(adapter.build_user_message(user_message))

    composed_report: dict | None = None
    tool_call_log: list[dict[str, str]] = []

    async def dispatch(name: str, arguments: dict) -> str:
        nonlocal composed_report

        result_str = await dispatch_tool_call(
            name, arguments,
            db=db,
            tenant_id=session["tenant_id"],
            user_id=session["user_id"],
            app_id=session["app_id"],
        )

        if name == "compose_report":
            parsed = json.loads(result_str)
            if parsed.get("status") == "ok":
                composed_report = parsed

        if name == "save_template":
            await db.commit()

        summary = _summarize_tool_result(name, result_str)
        tool_call_log.append({"name": name, "summary": summary})

        return result_str

    text, session["messages"] = await run_tool_loop(
        adapter=adapter,
        messages=session["messages"],
        tools=TOOLS,
        system=SYSTEM_PROMPT,
        temperature=0.3,
        dispatch_fn=dispatch,
        max_rounds=MAX_TOOL_ROUNDS,
    )

    if text is None:
        text = "I've reached the maximum number of tool calls for this turn. Please try a simpler request."

    return {
        "role": "assistant",
        "content": text,
        "tool_calls": tool_call_log,
        "composed_report": composed_report,
    }

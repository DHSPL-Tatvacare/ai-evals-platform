"""
Report builder chat surface.
Wires report-specific tools and system prompt into the shared chat engine.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.chat_engine import create_adapter, run_tool_loop
from app.services.report_builder.tool_definitions import TOOLS
from app.services.report_builder.tool_handlers import dispatch_tool_call

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are an AI assistant for an evaluation analytics platform. You help users \
build reports AND explore their evaluation data using natural language.

CAPABILITIES:
1. REPORT BUILDER — Compose custom report configurations from available section types.
2. DATA EXPLORER — Query evaluation runs, compare runs, drill into threads, and surface insights.

REPORT BUILDER WORKFLOW:
1. Call list_section_types to see available building blocks.
2. Match user intent to section types based on descriptions and use_when hints.
3. If you need detail about a section type, call get_section_detail.
4. Call list_app_sections to see what the app already supports.
5. Use compose_report to propose a configuration. The frontend shows a live preview.
6. Iterate based on feedback. Only call save_template when the user explicitly says save.

DATA EXPLORER WORKFLOW:
1. Use query_eval_runs to list recent runs with summary stats.
2. Use get_run_summary for detailed stats on a specific run.
3. Use compare_runs to diff two runs and surface what changed.
4. Use query_threads to drill into individual thread results (filter by verdict).
5. Use get_app_stats for aggregate statistics across all runs.

RULES:
- Be concise. Show data, don't explain the system.
- Format numbers clearly: percentages, counts, dates.
- When showing runs, use short IDs (first 8 chars).
- When comparing, highlight what got better and what got worse.
- Never ask the user to name section types. Map natural language to types yourself.
- If a request doesn't map to available tools, say so honestly.
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
    if name == "query_eval_runs":
        count = data.get("count", 0)
        return f"{count} runs"
    if name == "get_run_summary":
        return data.get("name", "") or str(data.get("id", ""))[:8]
    if name == "compare_runs":
        ra = data.get("run_a", {}).get("id", "?")
        rb = data.get("run_b", {}).get("id", "?")
        return f"{ra} vs {rb}"
    if name == "query_threads":
        count = data.get("count", 0)
        return f"{count} threads"
    if name == "get_app_stats":
        return f"{data.get('total_runs', 0)} runs"
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


async def run_chat_turn_streaming(
    session: dict[str, Any],
    user_message: str,
    *,
    provider: str,
    model: str,
    db: AsyncSession,
) -> AsyncGenerator[dict[str, Any], None]:
    """
    Generator version of run_chat_turn that yields SSE-style event dicts.
    Each yielded dict has {"event": str, "data": dict}.
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
    event_queue: list[dict[str, Any]] = []

    async def dispatch(name: str, arguments: dict) -> str:
        nonlocal composed_report

        event_queue.append({"event": "tool_call_start", "data": {"name": name}})

        result_str = await dispatch_tool_call(
            name, arguments,
            db=db,
            tenant_id=session["tenant_id"],
            user_id=session["user_id"],
            app_id=session["app_id"],
        )

        summary = _summarize_tool_result(name, result_str)
        tool_call_log.append({"name": name, "summary": summary})
        event_queue.append({"event": "tool_call_end", "data": {"name": name, "summary": summary}})

        if name == "compose_report":
            parsed = json.loads(result_str)
            if parsed.get("status") == "ok":
                composed_report = parsed

        if name == "save_template":
            await db.commit()

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

    # Yield all queued tool call events
    for event in event_queue:
        yield event

    # Yield content
    yield {"event": "content_delta", "data": {"delta": text}}

    # Yield done
    composed_out = None
    if composed_report:
        composed_out = {
            "reportName": composed_report.get("report_name"),
            "sections": composed_report.get("sections", []),
        }

    yield {
        "event": "done",
        "data": {
            "toolCalls": tool_call_log,
            "composedReport": composed_out,
        },
    }

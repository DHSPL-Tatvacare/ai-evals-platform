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
from app.services.report_builder.tool_definitions import resolve_tools
from app.services.report_builder.tool_handlers import dispatch_tool_call

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are Sherlock, an AI analytics assistant for an evaluation platform. \
You answer data questions and help build custom reports.

TOOLS:

1. analyze(question) — YOUR PRIMARY TOOL for ALL data questions.
   Accepts a natural language question, generates a database query, and returns results.
   Use for: pass rates, rule compliance, trends, comparisons, thread details, friction \
   patterns, adversarial results, aggregations — ANY analytical question.
   Be specific in your question: include the app name, time scope, and what you want to know.
   Examples:
   - "Which rules have the lowest compliance rate across all completed runs?"
   - "Show pass rate by run for the last 10 completed runs, ordered by date"
   - "What are the most common friction causes across all threads?"
   - "List threads with CRITICAL or HARD FAIL verdicts from the most recent run"

2. Report builder tools — use ONLY when user explicitly wants to compose a report layout:
   - list_section_types, get_section_detail, list_app_sections, compose_report, save_template

ROUTING:
- Data questions → analyze. Always.
- "Build me a report" / "compose" / "save template" → report builder tools.
- If unsure → analyze. Users want answers, not report configs.

RESPONSE FORMAT:
- Lead with the answer. No preamble.
- Markdown tables for tabular data.
- Bold key numbers: **78% pass rate**, **12 failures**.
- ▲/▼ arrows for comparisons: **▲ +5%**, **▼ -3 threads**.
- Short IDs (first 8 chars).
- Never dump raw JSON or SQL. Format for humans.
- Never explain what tools you're calling. Just call them and present results.
"""

MAX_TOOL_ROUNDS = 5


def _summarize_tool_result(name: str, result_str: str) -> str:
    """Extract a short label from a tool result for the UI badge."""
    try:
        data = json.loads(result_str)
    except (json.JSONDecodeError, TypeError):
        return "done"

    if name == "analyze":
        row_count = data.get("row_count", 0)
        status = data.get("status", "")
        if status == "error":
            return "query failed"
        return f"{row_count} rows"
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
    if name == "get_report_section":
        return data.get("section_type", data.get("title", "done"))
    if name == "get_thread_detail":
        return data.get("thread_id", "done")
    if name == "get_rule_compliance":
        rules = data.get("rules", [])
        return f"{len(rules)} rules"
    if name == "get_cross_run_rule_compliance":
        rules = data.get("rules", [])
        runs = data.get("total_runs_analyzed", 0)
        return f"{len(rules)} rules across {runs} runs"
    if name == "query_adversarial":
        return f"{data.get('total', 0)} cases"
    return "done"


async def _resolve_tools_for_app(app_id: str, db: AsyncSession) -> list[dict[str, Any]]:
    """Resolve tools from App.config.chat.capabilities. Falls back to all tools."""
    from sqlalchemy import select
    from app.models.app import App

    result = await db.execute(
        select(App.config).where(App.slug == app_id, App.is_active.is_(True))
    )
    config = result.scalar_one_or_none()
    capabilities = None
    if config:
        chat_config = (config or {}).get("chat", {})
        capabilities = chat_config.get("capabilities")
    return resolve_tools(capabilities)


async def run_chat_turn(
    session: dict[str, Any],
    user_message: str,
    *,
    provider: str,
    model: str,
    db: AsyncSession,
    auth: "Any",
) -> dict[str, Any]:
    """
    Process one user message through the LLM with tool calling.
    Returns the final assistant response + any composed report config.
    """
    tools = await _resolve_tools_for_app(session["app_id"], db)

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
            auth=auth,
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
        tools=tools,
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
    auth: "Any",
) -> AsyncGenerator[dict[str, Any], None]:
    """
    Generator version of run_chat_turn that yields SSE-style event dicts.
    Each yielded dict has {"event": str, "data": dict}.
    """
    tools = await _resolve_tools_for_app(session["app_id"], db)

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
            auth=auth,
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
        tools=tools,
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

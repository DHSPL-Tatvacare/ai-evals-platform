"""
Tool schemas for LLM function-calling in the report builder.
Each tool is a dict matching the provider-agnostic tool format
used by llm_base.py. The handler maps tool names to callables.
"""
from __future__ import annotations

from typing import Any

TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_section_types",
        "description": (
            "Returns all available report section types with a short description "
            "and when to use each one. Call this first to understand what building "
            "blocks are available."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_section_detail",
        "description": (
            "Returns full detail for a single section type — data shape, known variants, "
            "and rendering hints. Call when you need to understand a specific section."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "section_type": {
                    "type": "string",
                    "description": "The section type key (e.g. 'compliance_table', 'exemplars').",
                },
            },
            "required": ["section_type"],
        },
    },
    {
        "name": "list_app_sections",
        "description": (
            "Returns which section types the given app currently supports, "
            "with the section IDs and variants configured in its analytics profile."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "app_id": {
                    "type": "string",
                    "description": "The application identifier (e.g. 'kaira-bot', 'inside-sales').",
                },
            },
            "required": ["app_id"],
        },
    },
    {
        "name": "compose_report",
        "description": (
            "Validates a proposed report configuration and returns a preview-ready "
            "payload. The sections array defines which components appear and in what order. "
            "Call this when you have a draft report to show the user."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "report_name": {
                    "type": "string",
                    "description": "Human-readable name for this report template.",
                },
                "sections": {
                    "type": "array",
                    "description": "Ordered list of sections to include in the report.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {
                                "type": "string",
                                "description": "Unique section identifier (e.g. 'custom-compliance').",
                            },
                            "type": {
                                "type": "string",
                                "description": "Section type key from the catalog.",
                            },
                            "title": {
                                "type": "string",
                                "description": "Display title for this section.",
                            },
                            "variant": {
                                "type": "string",
                                "description": "Variant hint for data selection (optional).",
                            },
                        },
                        "required": ["id", "type", "title"],
                    },
                },
            },
            "required": ["report_name", "sections"],
        },
    },
    {
        "name": "save_template",
        "description": (
            "Persists the current report configuration as a reusable template. "
            "Once saved, it appears in the report generation dropdown. "
            "Only call this when the user explicitly confirms they want to save."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "report_name": {
                    "type": "string",
                    "description": "Human-readable name for the saved template.",
                },
                "sections": {
                    "type": "array",
                    "description": "Finalized ordered list of sections.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "type": {"type": "string"},
                            "title": {"type": "string"},
                            "variant": {"type": "string"},
                        },
                        "required": ["id", "type", "title"],
                    },
                },
            },
            "required": ["report_name", "sections"],
        },
    },
    {
        "name": "query_eval_runs",
        "description": (
            "List recent evaluation runs for the current app. Returns run ID, "
            "type, status, pass rate, thread count, and date. Use this when the "
            "user asks about recent runs, trends, or wants to find a specific run."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Number of runs to return (default 10, max 50).",
                },
                "eval_type": {
                    "type": "string",
                    "description": "Filter by eval type: 'custom', 'full_evaluation', 'batch_thread', 'batch_adversarial'. Omit for all types.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_run_summary",
        "description": (
            "Get detailed summary statistics for a single evaluation run. "
            "Returns verdict distributions, pass rates, thread counts, and key metrics. "
            "Use when the user asks about a specific run's results."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "run_id": {
                    "type": "string",
                    "description": "The evaluation run ID (UUID or short prefix).",
                },
            },
            "required": ["run_id"],
        },
    },
    {
        "name": "compare_runs",
        "description": (
            "Compare two evaluation runs side by side. Shows differences in "
            "pass rates, verdict distributions, and key metrics. Use when the "
            "user wants to understand what changed between runs."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "run_id_a": {
                    "type": "string",
                    "description": "First run ID to compare.",
                },
                "run_id_b": {
                    "type": "string",
                    "description": "Second run ID to compare.",
                },
            },
            "required": ["run_id_a", "run_id_b"],
        },
    },
    {
        "name": "query_threads",
        "description": (
            "List evaluation threads from a specific run. Can filter by verdict "
            "to find failing or passing threads. Returns thread ID, correctness "
            "verdict, efficiency verdict, and intent accuracy."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "run_id": {
                    "type": "string",
                    "description": "The evaluation run ID.",
                },
                "verdict": {
                    "type": "string",
                    "description": "Filter by worst_correctness verdict: 'PASS', 'SOFT FAIL', 'HARD FAIL', 'CRITICAL'. Omit for all.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of threads to return (default 10, max 50).",
                },
            },
            "required": ["run_id"],
        },
    },
    {
        "name": "get_app_stats",
        "description": (
            "Get aggregate statistics across all runs for the current app. "
            "Returns total runs, total threads evaluated, correctness and "
            "efficiency distributions, and average intent accuracy."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]

TOOL_NAMES = {tool["name"] for tool in TOOLS}

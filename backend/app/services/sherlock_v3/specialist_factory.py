"""The ONE shared specialist-construction seam for sherlock_v3.

Two module-level functions (no class hierarchy): `make_specialist_agent`
centralizes OpenAIResponsesModel + ModelSettings construction so every
supervisor/specialist inherits the same defaults by construction —
`parallel_tool_calls=False`, reasoning effort, and the uniform
`prompt_cache_key`. `as_specialist_tool` wraps `Agent.as_tool` so every
specialist-as-tool gets a failure function and `max_turns` uniformly.

Prefix-stability contract for the cache key: `prompt_cache_key` groups
requests whose prompt PREFIX is static. The static system prompt must come
first and per-turn content rides in the input, not the instructions, or the
cache key buys nothing.
"""
from __future__ import annotations

import dataclasses
import json
from typing import Any, Awaitable, Callable

import openai
from agents import Agent, Tool
from agents.model_settings import ModelSettings
from agents.models.openai_responses import OpenAIResponsesModel
from agents.tool import FunctionTool, default_tool_error_function
from agents.tool_context import ToolContext
from openai.types.shared import Reasoning

from app.services.sherlock_v3.contracts.brief import SpecialistBrief

InputBuilder = Callable[[ToolContext, str], str]


def make_specialist_agent(
    *,
    role: str,
    app_id: str,
    client: openai.AsyncOpenAI,
    model: str,
    instructions: str,
    tools: list[Any],
    reasoning_effort: str,
    max_turns: int | None = None,
    tool_use_behavior: Any = 'run_llm_again',
    output_type: Any = None,
    tool_choice: Any = None,
) -> Agent:
    """Construct one supervisor/specialist agent through the shared seam.

    `prompt_cache_key` is threaded via `ModelSettings.extra_args` (the SDK
    forwards extra_args into `responses.create`); it is NOT a ModelSettings
    field nor an OpenAIResponsesModel ctor param. `max_turns` is carried for
    the as-tool wrapper, not the Agent ctor.
    """
    settings_kwargs: dict[str, Any] = dict(
        parallel_tool_calls=False,
        reasoning=Reasoning(effort=reasoning_effort),
        extra_args={'prompt_cache_key': f'{app_id}:{role}'},
    )
    if tool_choice is not None:
        settings_kwargs['tool_choice'] = tool_choice

    return Agent(
        name=f'sherlock-{role}-{app_id}',
        instructions=instructions,
        model=OpenAIResponsesModel(model, client),
        model_settings=ModelSettings(**settings_kwargs),
        tools=tools,
        output_type=output_type,
        tool_use_behavior=tool_use_behavior,
    )


def build_specialist_input(ctx: ToolContext, args: str) -> str:
    """Fold runtime scope into the LLM-authored brief, yielding the brief JSON the specialist parses.

    The supervisor authors question/prior_attempts/retry_hint; scope is injected
    from the turn context here so it is never LLM-authored and cannot be spoofed.
    """
    payload = json.loads(args) if args else {}
    # Backstop: tolerate a legacy {"input": "<brief json>"} wrapper so a stray
    # wrap from the model still validates instead of hard-failing the turn.
    if isinstance(payload, dict) and 'question' not in payload and 'input' in payload:
        inner = payload['input']
        if isinstance(inner, str):
            try:
                payload = json.loads(inner)
            except json.JSONDecodeError:
                payload = {'question': inner}
        elif isinstance(inner, dict):
            payload = inner
    run_ctx = ctx.context
    payload['scope'] = {
        'tenant_id': str(run_ctx.tenant_id),
        'app_id': run_ctx.app_id,
        'user_id': str(run_ctx.user_id),
    }
    return SpecialistBrief.model_validate(payload).model_dump_json()


def as_specialist_tool(
    agent: Agent,
    *,
    tool_name: str,
    tool_description: str,
    custom_output_extractor: Any | None = None,
    max_turns: int | None = None,
    failure_error_function: Any | None = None,
    parameters: type | None = None,
    input_builder: InputBuilder | None = None,
) -> Tool:
    """Wrap `agent.as_tool` so every specialist-as-tool is uniform.

    Always sets a `failure_error_function` (the SDK default when None) so a
    specialist crash surfaces as a tool error rather than a silent drop, and
    forwards `max_turns` to bound internal turns. When `parameters` is provided,
    the tool exposes that model's JSON schema at the seam (so the supervisor must
    author the brief shape) and `input_builder` rewrites the structured args into
    the bare brief-string the nested specialist already parses — one contract, no
    second model, no specialist-side change.
    """
    if failure_error_function is None:
        failure_error_function = default_tool_error_function
    tool = agent.as_tool(
        tool_name=tool_name,
        tool_description=tool_description,
        custom_output_extractor=custom_output_extractor,
        max_turns=max_turns,
        failure_error_function=failure_error_function,
    )
    if parameters is None:
        return tool
    if not isinstance(tool, FunctionTool):
        return tool

    inner_invoke = tool.on_invoke_tool
    build = input_builder or build_specialist_input

    async def on_invoke_tool(context: ToolContext, args: str) -> Any:
        return await inner_invoke(context, build(context, args))

    # Wrap as_tool's tool rather than pass parameters= natively: the SDK-native
    # path runs ensure_strict_json_schema, which rejects this brief (its nested
    # bouncer Verdict/Diagnostic dicts set additionalProperties). strict_json_schema
    # off here; real enforcement is the input_builder's model_validate.
    return dataclasses.replace(
        tool,
        params_json_schema=parameters.model_json_schema(),
        on_invoke_tool=on_invoke_tool,
        strict_json_schema=False,
    )


__all__ = ['make_specialist_agent', 'as_specialist_tool', 'build_specialist_input']

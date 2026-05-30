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

from typing import Any

import openai
from agents import Agent, Tool
from agents.model_settings import ModelSettings
from agents.models.openai_responses import OpenAIResponsesModel
from agents.tool import default_tool_error_function
from openai.types.shared import Reasoning


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


def as_specialist_tool(
    agent: Agent,
    *,
    tool_name: str,
    tool_description: str,
    custom_output_extractor: Any | None = None,
    max_turns: int | None = None,
    failure_error_function: Any | None = None,
) -> Tool:
    """Wrap `agent.as_tool` so every specialist-as-tool is uniform.

    Always sets a `failure_error_function` (the SDK default when None) so a
    specialist crash surfaces as a tool error rather than a silent drop, and
    forwards `max_turns` to bound internal turns.
    """
    if failure_error_function is None:
        failure_error_function = default_tool_error_function
    return agent.as_tool(
        tool_name=tool_name,
        tool_description=tool_description,
        custom_output_extractor=custom_output_extractor,
        max_turns=max_turns,
        failure_error_function=failure_error_function,
    )


__all__ = ['make_specialist_agent', 'as_specialist_tool']

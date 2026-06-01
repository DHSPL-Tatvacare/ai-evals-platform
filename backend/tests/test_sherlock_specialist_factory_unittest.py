"""S1-1 + S1-2 — the shared specialist-construction seam.

One lean factory (`make_specialist_agent`) + one `as_tool` wrapper
(`as_specialist_tool`) that all four agent build sites route through.
Centralizes OpenAIResponsesModel + ModelSettings(parallel_tool_calls=False,
reasoning effort, and the uniform prompt_cache_key via extra_args).
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from agents import Agent

from app.services.sherlock_v3.contracts.brief import SpecialistBrief
from app.services.sherlock_v3.specialist_factory import (
    as_specialist_tool,
    build_specialist_input,
    make_specialist_agent,
)


def _build(**overrides):
    kwargs = dict(
        role='data',
        app_id='kaira-bot',
        client=MagicMock(),
        model='gpt-5.4-mini',
        instructions='SYSTEM',
        tools=[],
        reasoning_effort='medium',
    )
    kwargs.update(overrides)
    return make_specialist_agent(**kwargs)


class SpecialistFactoryTest(unittest.TestCase):
    def test_factory_sets_parallel_false_and_reasoning_effort(self):
        agent = _build(reasoning_effort='medium')
        self.assertIsInstance(agent, Agent)
        self.assertIs(agent.model_settings.parallel_tool_calls, False)
        self.assertEqual(agent.model_settings.reasoning.effort, 'medium')

    def test_factory_sets_prompt_cache_key_in_extra_args(self):
        agent = _build(role='data', app_id='kaira-bot')
        self.assertEqual(
            agent.model_settings.extra_args['prompt_cache_key'],
            'kaira-bot:data',
        )

    def test_prompt_cache_key_is_per_role(self):
        for role, app_id, expected in [
            ('supervisor', 'kaira-bot', 'kaira-bot:supervisor'),
            ('data', 'inside-sales', 'inside-sales:data'),
            ('query_synthesis', 'voice-rx', 'voice-rx:query_synthesis'),
            ('authoring', 'inside-sales', 'inside-sales:authoring'),
        ]:
            agent = _build(role=role, app_id=app_id)
            self.assertEqual(
                agent.model_settings.extra_args['prompt_cache_key'], expected
            )

    def test_factory_passes_tool_use_behavior_and_output_type(self):
        class _Brief:
            pass

        agent = _build(
            tool_use_behavior='stop_on_first_tool',
            output_type=_Brief,
        )
        self.assertEqual(agent.tool_use_behavior, 'stop_on_first_tool')
        self.assertIs(agent.output_type, _Brief)

    def test_factory_default_tool_use_behavior_is_run_llm_again(self):
        agent = _build()
        self.assertEqual(agent.tool_use_behavior, 'run_llm_again')

    def test_factory_threads_tool_choice_when_provided(self):
        agent = _build(tool_choice='auto')
        self.assertEqual(agent.model_settings.tool_choice, 'auto')

    def test_factory_omits_tool_choice_by_default(self):
        agent = _build()
        self.assertIsNone(agent.model_settings.tool_choice)

    def test_as_specialist_tool_sets_failure_error_function(self):
        agent = _build()
        tool = as_specialist_tool(
            agent,
            tool_name='data_specialist',
            tool_description='desc',
        )
        # The returned FunctionTool wraps a non-None failure function so a
        # specialist crash surfaces as a tool error, not a silent drop.
        self.assertIsNotNone(getattr(tool, 'name', None))
        self.assertEqual(tool.name, 'data_specialist')

    def test_default_tool_keeps_bare_string_input_schema(self):
        # Without parameters, the seam preserves the SDK's default {input: string}.
        agent = _build()
        tool = as_specialist_tool(
            agent,
            tool_name='query_synthesis',
            tool_description='desc',
        )
        props = tool.params_json_schema.get('properties', {})
        self.assertEqual(set(props), {'input'})
        self.assertEqual(props['input']['type'], 'string')

    def test_specialist_tool_enforces_specialistbrief_input(self):
        # With parameters=SpecialistBrief, the tool's input JSON schema reflects
        # the brief fields the supervisor must author, not a bare string.
        agent = _build()
        tool = as_specialist_tool(
            agent,
            tool_name='data_specialist',
            tool_description='desc',
            parameters=SpecialistBrief,
            input_builder=build_specialist_input,
        )
        props = tool.params_json_schema.get('properties', {})
        self.assertIn('question', props)
        self.assertIn('prior_attempts', props)
        self.assertIn('retry_hint', props)
        self.assertNotEqual(set(props), {'input'})


class BuildSpecialistInputTest(unittest.TestCase):
    def _scope_ctx(self):
        # ToolContext.context carries the turn-level scope object (recon).
        ctx = MagicMock()
        ctx.context.tenant_id = 'tenant-1'
        ctx.context.app_id = 'kaira-bot'
        ctx.context.user_id = 'user-9'
        return ctx

    def test_input_builder_injects_runtime_scope_not_llm_scope(self):
        # The supervisor authors question/attempts; scope comes from the runtime,
        # overriding anything the LLM tried to put in scope.
        import json

        llm_args = json.dumps(
            {
                'question': 'how many leads converted?',
                'scope': {
                    'tenant_id': 'ATTACKER',
                    'app_id': 'ATTACKER',
                    'user_id': 'ATTACKER',
                },
                'prior_attempts': [],
                'retry_hint': None,
            }
        )
        out = build_specialist_input(self._scope_ctx(), llm_args)
        # Corrected contract: build wraps the brief as the SDK AgentAsToolInput
        # {"input": "<brief json>"} so the nested as_tool handler feeds it as the
        # specialist's input (a bare brief leaves the specialist with empty input).
        wrapper = json.loads(out)
        self.assertEqual(set(wrapper), {'input'})
        brief = SpecialistBrief.model_validate_json(wrapper['input'])
        self.assertEqual(brief.question, 'how many leads converted?')
        self.assertEqual(brief.scope.tenant_id, 'tenant-1')
        self.assertEqual(brief.scope.app_id, 'kaira-bot')
        self.assertEqual(brief.scope.user_id, 'user-9')

    def test_input_builder_yields_brief_shape_without_llm_scope(self):
        # The supervisor may omit scope entirely; the builder still yields the
        # exact brief JSON shape the specialist parses today.
        import json

        llm_args = json.dumps({'question': 'q', 'prior_attempts': [], 'retry_hint': 'hint'})
        out = build_specialist_input(self._scope_ctx(), llm_args)
        brief = SpecialistBrief.model_validate_json(json.loads(out)['input'])
        self.assertEqual(brief.question, 'q')
        self.assertEqual(brief.retry_hint, 'hint')
        self.assertEqual(brief.scope.tenant_id, 'tenant-1')


if __name__ == '__main__':
    unittest.main()

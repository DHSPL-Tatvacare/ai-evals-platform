"""Phase 3 — supervisor toolbelt gating + single-Runner-streamed path.

These tests build the supervisor agent for several permission/context
combinations and inspect:

  * the tools the supervisor was given (names + ordering);
  * the prompt's AVAILABLE_TOOLS block;
  * the synthesis specialist's available_targets seen by its extractor.

Authoring is permission/context gated and must remain so. Synthesis is
always available. The supervisor runs inside ONE Runner.run_streamed
call from runtime.run_turn — we assert no parallel runners by source
inspection of runtime.py.
"""
from __future__ import annotations

import inspect
import unittest
import uuid
from unittest.mock import MagicMock, patch

from app.auth.context import AuthContext
from app.services.orchestration_authoring.builder_snapshot import BuilderSnapshot
from app.services.sherlock_v3 import runtime as runtime_mod
from app.services.sherlock_v3.contracts import SpecialistBrief
from app.services.sherlock_v3.supervisor import build_supervisor


def _supervisor(*args, **kwargs):
    kwargs.setdefault('supervisor_model', 'gpt-4o')
    kwargs.setdefault('specialist_model', 'gpt-4o-mini')
    return build_supervisor(*args, **kwargs)


def _auth(*, owner: bool = False, perms: frozenset[str] = frozenset()) -> AuthContext:
    return AuthContext(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email='test@example.com',
        role_id=uuid.uuid4(),
        is_owner=owner,
        permissions=perms,
        app_access=frozenset({'inside-sales'}),
    )


def _builder_snapshot(view_mode: str = 'edit') -> BuilderSnapshot:
    return BuilderSnapshot(
        workflow_id=uuid.uuid4(),
        version_id=None,
        workflow_type='crm',
        app_id='inside-sales',
        definition={'nodes': [], 'edges': []},
        data_hash='abc',
        view_mode=view_mode,  # type: ignore[arg-type]
    )


def _tool_names(agent: object) -> list[str]:
    tools = getattr(agent, 'tools', []) or []
    out: list[str] = []
    for t in tools:
        name = getattr(t, 'name', None) or getattr(t, '__name__', None)
        if isinstance(name, str):
            out.append(name)
    return out


class SupervisorToolbeltGatingTests(unittest.TestCase):
    """The authoring tool is permission/context gated; synthesis is always on."""

    def test_no_builder_no_authoring_tool(self) -> None:
        client = MagicMock()
        agent = _supervisor(
            'inside-sales', client,
            builder_context=None,
            auth=_auth(perms=frozenset({'orchestration:manage'})),
        )
        names = _tool_names(agent)
        self.assertIn('query_synthesis_specialist', names)
        self.assertIn('data_specialist', names)
        self.assertNotIn('authoring_specialist', names)

    def test_view_mode_does_not_unlock_authoring(self) -> None:
        # Builder context in view mode (read-only). Authoring stays off.
        client = MagicMock()
        agent = _supervisor(
            'inside-sales', client,
            builder_context=_builder_snapshot(view_mode='view'),
            auth=_auth(perms=frozenset({'orchestration:manage'})),
        )
        names = _tool_names(agent)
        self.assertNotIn('authoring_specialist', names)

    def test_missing_permission_no_authoring(self) -> None:
        client = MagicMock()
        agent = _supervisor(
            'inside-sales', client,
            builder_context=_builder_snapshot(view_mode='edit'),
            auth=_auth(perms=frozenset()),  # no orchestration:manage
        )
        names = _tool_names(agent)
        self.assertNotIn('authoring_specialist', names)

    def test_owner_bypass_unlocks_authoring_without_perms(self) -> None:
        client = MagicMock()
        agent = _supervisor(
            'inside-sales', client,
            builder_context=_builder_snapshot(view_mode='edit'),
            auth=_auth(owner=True, perms=frozenset()),
        )
        names = _tool_names(agent)
        self.assertIn('authoring_specialist', names)
        self.assertIn('query_synthesis_specialist', names)

    def test_edit_mode_with_perm_unlocks_authoring(self) -> None:
        client = MagicMock()
        agent = _supervisor(
            'inside-sales', client,
            builder_context=_builder_snapshot(view_mode='edit'),
            auth=_auth(perms=frozenset({'orchestration:manage'})),
        )
        names = _tool_names(agent)
        self.assertIn('authoring_specialist', names)


class SupervisorBriefGroundingTests(unittest.TestCase):
    """Step 1 — planner grounded with vocabulary; Step 3 — brief shape at the data/authoring seams."""

    def test_supervisor_passes_vocabulary_to_planner(self) -> None:
        # The supervisor loads the catalog and passes catalog_vocabulary to the
        # planner builder; for an app WITH a catalog the list is non-empty.
        client = MagicMock()
        with patch(
            'app.services.sherlock_v3.supervisor.build_query_synthesis_specialist',
            wraps=__import__(
                'app.services.sherlock_v3.supervisor', fromlist=['build_query_synthesis_specialist']
            ).build_query_synthesis_specialist,
        ) as spy:
            _supervisor('inside-sales', client, auth=_auth())
        self.assertEqual(spy.call_count, 1)
        vocab = spy.call_args.kwargs.get('vocabulary')
        self.assertIsInstance(vocab, list)
        assert vocab is not None
        self.assertGreater(len(vocab), 0)
        # Reuse of catalog_vocabulary — entries carry the planner-facing shape.
        self.assertIn('name', vocab[0])
        self.assertIn('description', vocab[0])

    def test_data_and_authoring_tools_enforce_specialistbrief(self) -> None:
        client = MagicMock()
        agent = _supervisor(
            'inside-sales', client,
            builder_context=_builder_snapshot(view_mode='edit'),
            auth=_auth(owner=True, perms=frozenset()),
        )
        brief_schema = SpecialistBrief.model_json_schema()
        by_name = {getattr(t, 'name', None): t for t in (agent.tools or [])}
        for tool_name in ('data_specialist', 'authoring_specialist'):
            tool = by_name.get(tool_name)
            self.assertIsNotNone(tool, f'{tool_name} missing from toolbelt')
            self.assertEqual(
                getattr(tool, 'params_json_schema', None),
                brief_schema,
                f'{tool_name} must expose the SpecialistBrief input schema',
            )
        # Synthesis takes the bare user message, NOT a SpecialistBrief envelope.
        synth = by_name.get('query_synthesis_specialist')
        self.assertIsNotNone(synth)
        self.assertNotEqual(getattr(synth, 'params_json_schema', None), brief_schema)


class SupervisorPromptTests(unittest.TestCase):
    def test_prompt_lists_only_available_tools(self) -> None:
        client = MagicMock()
        agent = _supervisor(
            'inside-sales', client,
            builder_context=None,
            auth=_auth(),
        )
        prompt = agent.instructions
        assert isinstance(prompt, str)
        self.assertIn('query_synthesis_specialist', prompt)
        self.assertIn('data_specialist', prompt)
        # Authoring not wired this turn — must not appear in AVAILABLE_TOOLS.
        # Note: it may still appear in tool-persistence rules text.
        # The AVAILABLE_TOOLS block is the authoritative list.
        avail_block_idx = prompt.find('# AVAILABLE_TOOLS this turn')
        end_idx = prompt.find('\n\n# Output', avail_block_idx)
        avail_block = prompt[avail_block_idx:end_idx]
        self.assertNotIn('authoring_specialist', avail_block)

    def test_prompt_requires_synthesis_first(self) -> None:
        client = MagicMock()
        agent = _supervisor('inside-sales', client, auth=_auth())
        prompt = agent.instructions
        assert isinstance(prompt, str)
        # The "synthesis first" mandate must be in the prompt.
        self.assertIn('query_synthesis_specialist', prompt)
        self.assertIn('first', prompt.lower())

    def test_prompt_refusal_branches_for_non_answerable(self) -> None:
        client = MagicMock()
        agent = _supervisor('inside-sales', client, auth=_auth())
        prompt = agent.instructions
        assert isinstance(prompt, str)
        for token in ('ambiguous', 'non_data', 'non_sql_data', 'answerable'):
            self.assertIn(token, prompt)


class SingleRunnerStreamedPathTests(unittest.TestCase):
    """The whole turn runs inside ONE Runner.run_streamed call."""

    def test_runtime_uses_one_runner_run_streamed_call(self) -> None:
        src = inspect.getsource(runtime_mod)
        # The single call lives in _stream_once.
        self.assertEqual(src.count('Runner.run_streamed('), 1)

    def test_no_pre_python_orchestration_in_runtime(self) -> None:
        src = inspect.getsource(runtime_mod)
        # Legacy classifier/projection modules are dead.
        self.assertNotIn('intent_' + 'classifier', src)
        self.assertNotIn('manifest_' + 'projection', src)
        self.assertNotIn('project_for_intent', src)
        self.assertNotIn('classify_intent', src)


class SupervisorSchemaExportsTests(unittest.TestCase):
    def test_synthesis_brief_json_schema_exported(self) -> None:
        from app.services.sherlock_v3.supervisor import SYNTHESIS_BRIEF_JSON_SCHEMA
        self.assertIsInstance(SYNTHESIS_BRIEF_JSON_SCHEMA, dict)
        self.assertIn('properties', SYNTHESIS_BRIEF_JSON_SCHEMA)


if __name__ == '__main__':
    unittest.main()

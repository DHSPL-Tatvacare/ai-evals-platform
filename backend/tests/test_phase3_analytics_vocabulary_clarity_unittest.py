"""Phase 3 — analytics pack vocabulary clarity surface.

Covers:
- ``ToolVocabulary.canonical_field_names`` exposes every canonical name.
- ``ToolVocabulary.ambiguous_synonyms`` surfaces synonyms that resolve to
  more than one target.
- ``ToolVocabulary.needs_clarification`` encapsulates the pack's own
  "discover or clarify before use" policy without leaking into harness-core.
- The relocated ``report_builder.analytics.question_hints`` module still
  produces the same shape consumed by the chat handler (``context`` +
  ``needs_discovery``).
"""
from __future__ import annotations

import pytest

from app.services.chat_engine.manifest import (
    _clear_manifest_cache_for_tests,
    load_all_manifests,
)
from app.services.chat_engine.sql_agent import load_semantic_model
from app.services.report_builder.analytics.question_hints import (
    compute_question_hints,
)
from app.services.report_builder.analytics.vocabulary import (
    build_tool_vocabulary,
)


@pytest.fixture(autouse=True)
def _load_manifests():
    _clear_manifest_cache_for_tests()
    load_all_manifests()


def _vocab(app_id: str = 'kaira-bot'):
    return build_tool_vocabulary(app_id, load_semantic_model(app_id))


# ── Clarity surface on ToolVocabulary ───────────────────────────────


def test_canonical_field_names_include_dimension_and_column_identifiers():
    vocab = _vocab()
    names = vocab.canonical_field_names()

    # A canonical dimension name (criterion_label is exposed as a
    # semantic dimension on kaira-bot).
    assert any('criterion' in name for name in names)
    # A canonical table.column form exists for at least one declared column.
    qualified = {name for name in names if '.' in name}
    assert qualified, 'canonical_field_names should include table.column entries'


def test_ambiguous_synonyms_reports_multi_target_aliases_only():
    vocab = _vocab()
    ambiguous = vocab.ambiguous_synonyms()

    # Every returned entry must be genuinely ambiguous (>1 target). Empty is
    # acceptable when a manifest has no cross-table synonym collisions.
    for term, targets in ambiguous.items():
        assert len(targets) > 1, f'{term} should have >1 target to be ambiguous'

    # Canonical single-target synonyms must NOT appear here; pick any
    # column_alias_index entry with one target and verify.
    single_target_aliases = [
        term for term, targets in vocab.column_alias_index.items()
        if len(targets) == 1
    ]
    assert single_target_aliases, 'precondition: manifest declares unambiguous synonyms'
    for term in single_target_aliases:
        assert term not in ambiguous


def test_needs_clarification_flags_unknown_id_status_suffixed_terms():
    """Pack policy: a bare ``_id`` / ``_status`` term that isn't declared
    anywhere still forces the outer agent to discover/clarify, because
    these are the common footguns projected by multiple tables."""
    vocab = _vocab()

    assert vocab.needs_clarification('run_status') is True
    assert vocab.needs_clarification('mystery_id') is True


def test_needs_clarification_respects_canonical_and_ambiguous_matches():
    vocab = _vocab()

    # A known canonical dimension should NOT require clarification.
    assert any(vocab.dimensions), 'precondition: vocab has canonical dimensions'
    canonical_term = next(iter(vocab.dimensions))
    assert vocab.needs_clarification(canonical_term) is False

    # An empty term is not meaningful — never forces clarification.
    assert vocab.needs_clarification('') is False
    assert vocab.needs_clarification('   ') is False


# ── Relocated question-hints helper ─────────────────────────────────


def test_compute_question_hints_maps_synonym_to_canonical_name():
    hints = compute_question_hints(
        question='Show pass rate grouped by rule_id.',
        app_id='kaira-bot',
        semantic_model=load_semantic_model('kaira-bot'),
        tool_vocabulary=lambda app_id, model: build_tool_vocabulary(app_id, dict(model)),
    )

    assert hints['needs_discovery'] is False
    assert 'criterion_id' in hints['context']


def test_compute_question_hints_forces_discovery_for_unknown_schema_term():
    hints = compute_question_hints(
        question='Break results down by run_status.',
        app_id='kaira-bot',
        semantic_model=load_semantic_model('kaira-bot'),
        tool_vocabulary=lambda app_id, model: build_tool_vocabulary(app_id, dict(model)),
    )

    assert hints['needs_discovery'] is True
    assert 'run_status' in hints['context']


def test_compute_question_hints_returns_empty_bundle_for_blank_question():
    hints = compute_question_hints(
        question='   ',
        app_id='kaira-bot',
        semantic_model=load_semantic_model('kaira-bot'),
        tool_vocabulary=lambda app_id, model: build_tool_vocabulary(app_id, dict(model)),
    )

    assert hints == {'context': '', 'needs_discovery': False}


def test_compute_question_hints_swallows_vocabulary_build_errors():
    """If the pack's vocabulary fails to build (e.g. missing manifest in a
    test fixture), the helper must return the empty bundle rather than
    raising through harness-core."""

    def _boom(_app_id, _model):
        raise RuntimeError('vocabulary build failed')

    hints = compute_question_hints(
        question='Show pass rate grouped by rule_id.',
        app_id='kaira-bot',
        semantic_model={},
        tool_vocabulary=_boom,
    )

    assert hints == {'context': '', 'needs_discovery': False}

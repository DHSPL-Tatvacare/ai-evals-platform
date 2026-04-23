"""Pack-local semantic source for the contract-stub pack.

Kept deliberately tiny. Exists only to prove a pack can own its own
vocabulary, deterministic validators, tool-description substitutions,
and artifact semantics without reusing analytics manifests.
"""
from __future__ import annotations

from typing import Literal


TemplateVariant = Literal['plain', 'warning', 'success']

TEMPLATE_VARIANTS: tuple[TemplateVariant, ...] = ('plain', 'warning', 'success')

MAX_TEXT_LENGTH: int = 120

TITLE_PREFIXES: dict[TemplateVariant, str] = {
    'plain': 'Stub note',
    'warning': 'Stub warning',
    'success': 'Stub success',
}

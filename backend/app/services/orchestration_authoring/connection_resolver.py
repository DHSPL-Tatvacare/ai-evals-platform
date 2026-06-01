"""Pure resolve_connection ladder for the cat-A connection_picker.

No DB. The pack handler fetches candidates + default thinly and calls
``resolve_connection_ladder``; this module owns the resolution logic only.
Fuzzy matching uses stdlib ``difflib`` — no new fuzzy dependency.
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Literal, Optional

# A clearly-best hint match must clear this similarity; ties within this
# band of the top score are treated as ambiguous and surfaced as a pick.
_HINT_CUTOFF = 0.6
_TIE_BAND = 0.1


@dataclass(frozen=True)
class ConnRef:
    """Minimal connection reference the ladder reasons over."""

    id: str
    name: str
    provider: str


@dataclass
class Resolution:
    """Ladder outcome: a single resolved connection, a pick set, or none."""

    status: Literal['resolved', 'pick', 'none']
    connection: Optional[ConnRef] = None
    candidates: Optional[list[ConnRef]] = field(default=None)


def _score(hint: str, candidate: ConnRef) -> float:
    """Best similarity of the hint against the candidate's provider or name."""
    hint_l = hint.strip().lower()
    provider_score = difflib.SequenceMatcher(
        None, hint_l, candidate.provider.lower()
    ).ratio()
    name_score = difflib.SequenceMatcher(
        None, hint_l, candidate.name.lower()
    ).ratio()
    return max(provider_score, name_score)


def _hint_resolution(
    candidates: list[ConnRef], hint: str
) -> Optional[Resolution]:
    """Rung 1: fuzzy-match the hint; resolve on one clear best, pick on ties."""
    scored = [(c, _score(hint, c)) for c in candidates]
    above = [(c, s) for c, s in scored if s >= _HINT_CUTOFF]
    if not above:
        return None
    above.sort(key=lambda pair: pair[1], reverse=True)
    top_score = above[0][1]
    leaders = [c for c, s in above if top_score - s <= _TIE_BAND]
    if len(leaders) == 1:
        return Resolution(status='resolved', connection=leaders[0])
    return Resolution(status='pick', candidates=leaders)


def resolve_connection_ladder(
    *,
    candidates: list[ConnRef],
    default_id: Optional[str],
    hint: Optional[str],
) -> Resolution:
    """Resolve a connection from candidates via the four-rung ladder."""
    if not candidates:
        return Resolution(status='none')

    if hint and hint.strip():
        hinted = _hint_resolution(candidates, hint)
        if hinted is not None:
            return hinted

    if default_id:
        for c in candidates:
            if c.id == default_id:
                return Resolution(status='resolved', connection=c)

    if len(candidates) == 1:
        return Resolution(status='resolved', connection=candidates[0])

    return Resolution(status='pick', candidates=list(candidates))


__all__ = ['ConnRef', 'Resolution', 'resolve_connection_ladder']

"""Project a specialist's as_tool return into the uniform SubtaskResult."""
from __future__ import annotations

import json
import logging

from app.services.sherlock_v3.contracts.brief import Attempt
from app.services.sherlock_v3.contracts.parts import SubtaskResult
from app.services.sherlock_v3.contracts.result import SpecialistResult

logger = logging.getLogger(__name__)

DATA_SPECIALIST = 'data_specialist'

# Invariant (S1-3): no SubtaskResult with status in {error, empty} carries
# an empty summary — the FE error card must always show a human reason.
_UNPARSEABLE_DATA_SUMMARY = 'The data specialist did not return a readable result.'
_EMPTY_TEXT_SUMMARY = 'The specialist returned no content.'
# On status='ok' the supervisor reads the specialist's text directly, so the
# consultation row carries no summary — the invariant binds error|empty only.
_OK_NO_SUMMARY = ''


def _parse_specialist_result(output: str) -> SpecialistResult | None:
    if not output or not output.strip():
        return None
    try:
        return SpecialistResult.model_validate(json.loads(output))
    except Exception:  # noqa: BLE001 — tolerant boundary; degrade to error projection
        return None


def _resolved_attempt(attempts: list[Attempt]) -> Attempt | None:
    """The attempt whose result the answer rests on — last successful, else last."""
    if not attempts:
        return None
    for attempt in reversed(attempts):
        if attempt.status in ('ok', 'empty'):
            return attempt
    return attempts[-1]


def project_specialist_output(specialist: str, output: str) -> tuple[SubtaskResult, bool]:
    """Return (SubtaskResult, is_error). data parses the SpecialistResult JSON for
    sql/row_count; other specialists carry only status (their text is the answer)."""
    if specialist == DATA_SPECIALIST:
        parsed = _parse_specialist_result(output)
        if parsed is None:
            return SubtaskResult(status='error', summary=_UNPARSEABLE_DATA_SUMMARY), True
        resolved = _resolved_attempt(parsed.attempts)
        is_error = parsed.status == 'error' or parsed.kind == 'error'
        return (
            SubtaskResult(
                status=parsed.status,
                summary=parsed.summary,
                sql=resolved.sql if (resolved and resolved.sql) else None,
                row_count=resolved.row_count if resolved else None,
            ),
            is_error,
        )

    # query_synthesis / authoring return text used by the supervisor; the
    # consultation row needs only that the specialist ran, not the raw text.
    # On empty the invariant binds: carry a human reason. On ok the
    # supervisor reads the text directly, so an empty summary is fine.
    text = (output or '').strip()
    if not text:
        return SubtaskResult(status='empty', summary=_EMPTY_TEXT_SUMMARY), False
    return SubtaskResult(status='ok', summary=_OK_NO_SUMMARY), False

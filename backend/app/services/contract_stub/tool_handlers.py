"""Deterministic, read-only handlers for the contract-stub pack.

No DB writes. No jobs. No hidden state. Handlers return a §6.2
``ToolEnvelopeModel`` via ``build_envelope`` / ``error_envelope`` so the
generic egress path in the harness dispatcher carries them verbatim.
"""
from __future__ import annotations

from typing import Any

from app.services.chat_engine.artifact import (
    ToolEnvelopeModel,
    build_envelope,
    error_envelope,
)
from app.services.contract_stub import reason_codes as stub_reason_codes
from app.services.contract_stub.catalog import (
    MAX_TEXT_LENGTH,
    TEMPLATE_VARIANTS,
    TITLE_PREFIXES,
    TemplateVariant,
)
from app.services.contract_stub.schemas import StubNoteExtras, StubNotePayload


PACK_CAPABILITY = 'contract_stub'
ARTIFACT_CONTRACT_ID = 'contract_stub.note.v1'
ARTIFACT_TYPE = 'note_card'


async def handle_stub_capabilities(**_kwargs: Any) -> ToolEnvelopeModel:
    """Return pack-declared limits and variants (read-only, no artifact)."""

    variants = list(TEMPLATE_VARIANTS)
    return build_envelope(
        status='ok',
        summary=f'{len(variants)} stub variants',
        kind='read',
        capability=PACK_CAPABILITY,
        counts={'rows': 0, 'records': len(variants), 'affected': 0},
        payload={
            'variants': variants,
            'maxTextLength': MAX_TEXT_LENGTH,
        },
    )


async def handle_stub_make_note(
    *,
    text: str,
    variant: str,
    **_kwargs: Any,
) -> ToolEnvelopeModel:
    """Deterministically convert (text, variant) into a note-card artifact.

    Validation order matches the reason-code registry: empty text first,
    then unknown variant, then length. All errors emit the pack's own
    stable reason codes — no prose substitutions.
    """

    if not isinstance(text, str) or not text.strip():
        return error_envelope(
            capability=PACK_CAPABILITY,
            reason_code=stub_reason_codes.CONTRACT_STUB_EMPTY_TEXT,
            summary='Stub note text is empty',
            warnings=['text must be a non-empty string'],
            payload={},
        )
    if variant not in TEMPLATE_VARIANTS:
        return error_envelope(
            capability=PACK_CAPABILITY,
            reason_code=stub_reason_codes.CONTRACT_STUB_UNKNOWN_VARIANT,
            summary=f'Unknown stub variant {variant!r}',
            warnings=[f'variant must be one of {list(TEMPLATE_VARIANTS)}'],
            payload={'allowed_variants': list(TEMPLATE_VARIANTS)},
        )
    if len(text) > MAX_TEXT_LENGTH * 4:
        return error_envelope(
            capability=PACK_CAPABILITY,
            reason_code=stub_reason_codes.CONTRACT_STUB_TEXT_TOO_LONG,
            summary='Stub note text too long',
            warnings=[f'text length exceeds hard cap of {MAX_TEXT_LENGTH * 4} characters'],
            payload={'maxTextLength': MAX_TEXT_LENGTH},
        )

    typed_variant: TemplateVariant = variant  # type: ignore[assignment]
    truncated = len(text) > MAX_TEXT_LENGTH
    body = text[:MAX_TEXT_LENGTH]
    title = TITLE_PREFIXES[typed_variant]

    payload_model = StubNotePayload(
        title=title,
        body=body,
        variant=typed_variant,
        source_text=text,
    )
    extras_model = StubNoteExtras(
        rendered_variant=typed_variant,
        truncated=truncated,
    )

    return build_envelope(
        status='ok',
        summary='Stub note created',
        kind='artifact',
        capability=PACK_CAPABILITY,
        counts={'rows': 0, 'records': 1, 'affected': 0},
        artifact={
            'type': ARTIFACT_TYPE,
            'contract': ARTIFACT_CONTRACT_ID,
            'extras': extras_model.model_dump(mode='json'),
        },
        payload={'note': payload_model.model_dump(mode='json')},
    )

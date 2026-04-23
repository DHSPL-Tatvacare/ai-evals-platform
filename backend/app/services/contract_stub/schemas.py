"""Strict Pydantic request / response / artifact models for the stub pack."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.services.contract_stub.catalog import (
    TEMPLATE_VARIANTS,
    TemplateVariant,
)


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


class StubCapabilitiesInput(BaseModel):
    model_config = ConfigDict(extra='forbid')


class StubMakeNoteInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    text: str = Field(..., description='Free-form source text for the note.')
    variant: TemplateVariant = Field(
        ..., description=f'One of {list(TEMPLATE_VARIANTS)}.'
    )


# ---------------------------------------------------------------------------
# Outputs (tool result payload contracts — for {{output_schema}})
# ---------------------------------------------------------------------------


class StubCapabilitiesOutput(BaseModel):
    """Payload of the ``stub_capabilities`` read envelope."""

    variants: list[Literal['plain', 'warning', 'success']]
    maxTextLength: int


class StubMakeNoteOutput(BaseModel):
    """Payload of the ``stub_make_note`` artifact envelope."""

    note: 'StubNotePayload'


# ---------------------------------------------------------------------------
# Artifact payload + extras contracts
# ---------------------------------------------------------------------------


class StubNotePayload(BaseModel):
    """Renderable artifact payload — ``contract_stub.note.v1``."""

    model_config = ConfigDict(extra='forbid')

    title: str
    body: str
    variant: TemplateVariant
    source_text: str


class StubNoteExtras(BaseModel):
    """Outcome-shaped metadata about the emitted note artifact."""

    model_config = ConfigDict(extra='forbid')

    rendered_variant: TemplateVariant
    truncated: bool


StubMakeNoteOutput.model_rebuild()

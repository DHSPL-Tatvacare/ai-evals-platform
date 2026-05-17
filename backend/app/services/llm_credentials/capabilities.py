"""Compute capability tags from a catalog row.

Reads only ``analytics.ref_llm_models_catalog`` columns — no hardcoded provider
allowlists. Phase 1's migration 0050 adds ``supports_structured_output``;
``models_dev_refresh`` populates it from the models.dev ``structured_output``
field. Anthropic models often express structured output via tool-call schemas
rather than a dedicated flag, so the helper trusts catalog truth instead of
applying a blanket provider rule.
"""
from __future__ import annotations

from app.models.cost import RefLlmModelsCatalog


def compute_capabilities(catalog_row: RefLlmModelsCatalog) -> frozenset[str]:
    """Return the capability tag set for one catalog row.

    Tag list mirrors ``CAPABILITY_VOCABULARY`` in
    ``app.services.llm_credentials.call_sites``. Any new tag must be added in
    both places (and the call-site spec validators will fail loudly if not).
    """
    tags: set[str] = set()
    inputs = set(catalog_row.modalities_input or [])
    outputs = set(catalog_row.modalities_output or [])

    if "text" in inputs:
        tags.add("text_input")
    if "text" in outputs:
        tags.add("text_output")
    if "image" in inputs:
        tags.add("image_input")
    if "audio" in inputs:
        tags.add("audio_input")
    if "audio" in outputs:
        tags.add("audio_output")
    if "video" in inputs:
        tags.add("video_input")
    if "pdf" in inputs:
        tags.add("pdf_input")

    if bool(catalog_row.supports_reasoning):
        tags.add("reasoning")
    if bool(catalog_row.supports_tool_call):
        tags.add("tool_call")
    if bool(catalog_row.supports_attachment):
        tags.add("attachment")
    if bool(catalog_row.supports_structured_output):
        tags.add("structured_output")

    return frozenset(tags)

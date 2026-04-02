"""Shared prompt builders for canonical run and cross-run narratives."""

from __future__ import annotations

import json
from typing import Any

from app.services.reports.contracts.cross_run_report import PlatformCrossRunMetadata
from app.services.reports.contracts.report_sections import PlatformReportSection
from app.services.reports.contracts.run_report import PlatformReportMetadata


def _section_snapshot(section: PlatformReportSection) -> dict[str, Any]:
    return section.model_dump(by_alias=True)


def build_run_narrative_prompt(
    *,
    metadata: PlatformReportMetadata,
    sections: list[PlatformReportSection],
    prompt_references: dict[str, str | None],
) -> str:
    payload = {
        'metadata': metadata.model_dump(by_alias=True),
        'sections': [_section_snapshot(section) for section in sections],
        'promptReferences': prompt_references,
    }
    return (
        'You are generating a canonical single-run report narrative. '
        'Use only the supplied metadata, canonical sections, and prompt references. '
        'Return valid JSON matching the requested schema.\n\n'
        f'```json\n{json.dumps(payload, indent=2, default=str)}\n```'
    )


def build_cross_run_narrative_prompt(
    *,
    metadata: PlatformCrossRunMetadata,
    sections: list[PlatformReportSection],
) -> str:
    payload = {
        'metadata': metadata.model_dump(by_alias=True),
        'sections': [_section_snapshot(section) for section in sections],
    }
    return (
        'You are generating a canonical cross-run analytics narrative. '
        'Synthesize the recurring patterns and strategic recommendations from the canonical sections below. '
        'Return valid JSON matching the requested schema.\n\n'
        f'```json\n{json.dumps(payload, indent=2, default=str)}\n```'
    )

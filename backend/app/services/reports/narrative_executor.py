"""Generic reportId-driven narrative execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.services.reports.contracts.cross_run_narrative import (
    PlatformCrossRunNarrative,
)
from app.services.reports.contracts.report_sections import PlatformReportSection
from app.services.reports.contracts.run_narrative import PlatformRunNarrative
from app.services.reports.narrative_prompt_builders import (
    build_cross_run_narrative_prompt,
    build_run_narrative_prompt,
)


def _select_sections(
    sections: list[PlatformReportSection],
    section_ids: list[str],
) -> list[PlatformReportSection]:
    if not section_ids:
        return sections
    allowed = set(section_ids)
    return [section for section in sections if section.id in allowed]


def _issues_recommendations_from_run_narrative(payload: PlatformRunNarrative) -> dict[str, Any]:
    return {
        'issues': [
            {
                'title': item.title,
                'area': item.area,
                'priority': item.severity,
                'summary': item.summary,
            }
            for item in payload.issues
        ],
        'recommendations': [
            {
                'priority': item.priority,
                'title': item.area,
                'action': item.action,
                'expectedImpact': item.rationale,
            }
            for item in payload.recommendations
        ],
    }


def _issues_recommendations_from_cross_run_narrative(payload: PlatformCrossRunNarrative) -> dict[str, Any]:
    return {
        'issues': [
            {
                'title': item.title,
                'area': item.title,
                'priority': 'P1',
                'summary': item.summary,
            }
            for item in payload.critical_patterns
        ],
        'recommendations': [
            {
                'priority': item.priority,
                'title': item.priority,
                'action': item.action,
                'expectedImpact': item.expected_impact,
            }
            for item in payload.strategic_recommendations
        ],
    }


def _prompt_gaps_from_run_narrative(payload: PlatformRunNarrative) -> list[dict[str, Any]]:
    return [
        {
            'gapType': item.gap_type,
            'promptSection': item.prompt_section,
            'evaluationRule': item.evaluation_rule,
            'summary': item.suggested_fix,
            'suggestedFix': item.suggested_fix,
        }
        for item in payload.prompt_gaps
    ]


def _derived_run_narrative_payloads(payload: PlatformRunNarrative) -> dict[str, Any]:
    return {
        'prompt_gaps': _prompt_gaps_from_run_narrative(payload),
        'issues': _issues_recommendations_from_run_narrative(payload),
        'overview': {
            'message': payload.executive_summary,
            'tone': 'info',
        },
    }


def _derived_cross_run_narrative_payloads(payload: PlatformCrossRunNarrative) -> dict[str, Any]:
    return {
        'prompt_gaps': [],
        'issues': _issues_recommendations_from_cross_run_narrative(payload),
        'overview': {
            'message': payload.executive_summary,
            'tone': 'info',
        },
    }


@dataclass(frozen=True)
class NarrativeKind:
    """Declarative record for one narrative scope.

    Encodes everything that differs between the single-run and cross-run paths:
    the canonical contract (used both for the JSON schema handed to the LLM and
    for alias-aware ``model_validate`` parsing), the prompt builder, whether that
    builder takes the ``prompt_references`` argument, and the scope-specific
    projections (prompt gaps / issues / overview) derived from the parsed payload.
    """

    contract: type[PlatformRunNarrative] | type[PlatformCrossRunNarrative]
    prompt_builder: Callable[..., str]
    uses_prompt_references: bool
    derived_payloads: Callable[[Any], dict[str, Any]]


NARRATIVE_KINDS: dict[str, NarrativeKind] = {
    'single_run': NarrativeKind(
        contract=PlatformRunNarrative,
        prompt_builder=build_run_narrative_prompt,
        uses_prompt_references=True,
        derived_payloads=_derived_run_narrative_payloads,
    ),
    'cross_run': NarrativeKind(
        contract=PlatformCrossRunNarrative,
        prompt_builder=build_cross_run_narrative_prompt,
        uses_prompt_references=False,
        derived_payloads=_derived_cross_run_narrative_payloads,
    ),
}


async def execute_narrative_generation(
    *,
    llm,
    report_id: str,
    report_kind: str,
    metadata,
    sections: list[PlatformReportSection],
    narrative_config: dict[str, Any],
) -> dict[str, Any]:
    del report_id

    if not narrative_config.get('enabled'):
        return {}

    selected_sections = _select_sections(
        sections,
        list((narrative_config.get('inputSelection') or {}).get('sectionIds') or []),
    )
    resolved_assets = narrative_config.get('resolvedAssets') or {}
    prompt_references = resolved_assets.get('promptReferences') or {}
    system_prompt = resolved_assets.get('systemPrompt')
    output_insertion_points = list(narrative_config.get('outputInsertionPoints') or [])

    kind = NARRATIVE_KINDS[report_kind]

    prompt_builder_kwargs: dict[str, Any] = {
        'metadata': metadata,
        'sections': selected_sections,
    }
    if kind.uses_prompt_references:
        prompt_builder_kwargs['prompt_references'] = prompt_references

    prompt = kind.prompt_builder(**prompt_builder_kwargs)
    result = await llm.generate_json(
        prompt=prompt,
        system_prompt=system_prompt,
        json_schema=kind.contract.model_json_schema(),
    )
    # ``model_validate`` is the single alias-aware parse boundary for both scopes:
    # CamelModel sets ``populate_by_name=True`` so the camelCase keys the LLM
    # returns (matching ``model_json_schema()``) are accepted, and so are
    # snake_case field names. This replaces the divergent snake_case ``.get()``
    # cross-run mapper that silently produced empty narratives.
    payload = kind.contract.model_validate(result)
    derived = kind.derived_payloads(payload)
    prompt_gaps_payload = derived['prompt_gaps']
    issues_payload = derived['issues']
    overview_payload = derived['overview']

    inserted_payloads: dict[str, Any] = {}
    payload_data = payload.model_dump(by_alias=True)
    for section_id in output_insertion_points:
        lowered = section_id.lower()
        if 'narrative' in lowered:
            inserted_payloads[section_id] = payload_data
        elif 'prompt-gap' in lowered or 'prompt_gaps' in lowered:
            inserted_payloads[section_id] = prompt_gaps_payload
        elif 'issue' in lowered or 'recommendation' in lowered:
            inserted_payloads[section_id] = issues_payload
        elif 'overview' in lowered or 'callout' in lowered:
            inserted_payloads[section_id] = overview_payload

    return inserted_payloads

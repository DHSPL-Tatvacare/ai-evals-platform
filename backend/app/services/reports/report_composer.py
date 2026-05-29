"""Shared canonical report composition helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

from app.schemas.app_analytics_config import AnalyticsSectionConfig
from app.services.reports.config_models import PresentationSectionConfig
from app.services.reports.contracts.cross_run_report import (
    PlatformCrossRunMetadata,
    PlatformCrossRunPayload,
)
from app.services.reports.contracts.print_document import PlatformReportDocument
from app.services.reports.contracts.report_sections import (
    CalloutSection,
    ComplianceTableSection,
    DistributionChartSection,
    EntitySlicesSection,
    ExemplarsSection,
    FlagsSection,
    FrictionAnalysisSection,
    HeatmapSection,
    InsightPanelsSection,
    IssuesRecommendationsSection,
    MetricBreakdownSection,
    NarrativeSection,
    PlatformReportSection,
    PromptGapAnalysisSection,
    SummaryCardsSection,
    TrendChartSection,
)
from app.services.reports.contracts.run_report import (
    PlatformReportMetadata,
    PlatformReportPresentation,
    PlatformRunReportPayload,
)


_SECTION_MODEL_BY_TYPE = {
    'summary_cards': SummaryCardsSection,
    'narrative': NarrativeSection,
    'metric_breakdown': MetricBreakdownSection,
    'distribution_chart': DistributionChartSection,
    'compliance_table': ComplianceTableSection,
    'friction_analysis': FrictionAnalysisSection,
    'heatmap': HeatmapSection,
    'entity_slices': EntitySlicesSection,
    'flags': FlagsSection,
    'issues_recommendations': IssuesRecommendationsSection,
    'exemplars': ExemplarsSection,
    'prompt_gap_analysis': PromptGapAnalysisSection,
    'callout': CalloutSection,
    'trend_chart': TrendChartSection,
    'insight_panels': InsightPanelsSection,
}


def build_section(
    config: AnalyticsSectionConfig | PresentationSectionConfig,
    data: Any,
) -> PlatformReportSection:
    component_id = getattr(config, 'component_id', None) or getattr(config, 'type')
    section_id = getattr(config, 'section_id', None) or getattr(config, 'id')
    model_cls = _SECTION_MODEL_BY_TYPE[component_id]
    title = config.title or section_id.replace('-', ' ').replace('_', ' ').title()
    if isinstance(data, dict) and 'data' in data:
        extra = {k: v for k, v in data.items() if k != 'data'}
        return model_cls(
            id=section_id,
            title=title,
            description=config.description,
            variant=config.variant,
            data=data['data'],
            **extra,
        )
    return model_cls(
        id=section_id,
        title=title,
        description=config.description,
        variant=config.variant,
        data=data,
    )


def compose_sections(
    section_configs: Sequence[AnalyticsSectionConfig | PresentationSectionConfig],
    section_payloads: Mapping[str, Any],
) -> list[PlatformReportSection]:
    """Compose sections, resolving payloads by section_id first, then falling
    back to the section's component type. The fallback is what makes
    user-authored blueprints (Sherlock ``summary-cards``/``narrative``/... ids)
    render against app payloads whose canonical ids are namespaced (e.g.
    ``voice-rx-summary``). ``_serialize_section_payloads`` mirrors the data
    into both id- and type-keyed entries for this lookup.
    """
    sections: list[PlatformReportSection] = []
    for config in section_configs:
        section_id = getattr(config, 'section_id', None) or getattr(config, 'id')
        payload = section_payloads.get(section_id)
        if payload is None:
            component_id = getattr(config, 'component_id', None) or getattr(config, 'type', None)
            if component_id:
                payload = section_payloads.get(component_id)
        if payload is None:
            continue
        sections.append(build_section(config, payload))
    return sections


def index_sections(
    sections: list[PlatformReportSection],
) -> dict[str, PlatformReportSection]:
    return {section.id: section for section in sections}


def compose_report(
    scope: str,
    metadata: PlatformReportMetadata | PlatformCrossRunMetadata,
    section_configs: Sequence[AnalyticsSectionConfig | PresentationSectionConfig],
    section_payloads: Mapping[str, Any],
    export_document: PlatformReportDocument | None = None,
    presentation: PlatformReportPresentation | None = None,
) -> PlatformRunReportPayload | PlatformCrossRunPayload:
    """Unified composer for both report scopes.

    Binds ``scope`` to its canonical payload model and assembles it from the
    composed sections. The thin ``compose_run_report`` / ``compose_cross_run_report``
    wrappers below delegate here so existing callers keep working.
    """
    sections = compose_sections(section_configs, section_payloads)
    presentation = presentation or PlatformReportPresentation()
    if scope == 'cross_run':
        return PlatformCrossRunPayload(
            metadata=cast(PlatformCrossRunMetadata, metadata),
            presentation=presentation,
            sections=sections,
            export_document=export_document,
        )
    return PlatformRunReportPayload(
        metadata=cast(PlatformReportMetadata, metadata),
        presentation=presentation,
        sections=sections,
        export_document=cast(PlatformReportDocument, export_document),
    )


def compose_run_report(
    metadata: PlatformReportMetadata,
    section_configs: Sequence[AnalyticsSectionConfig | PresentationSectionConfig],
    section_payloads: Mapping[str, Any],
    export_document: PlatformReportDocument,
    presentation: PlatformReportPresentation | None = None,
) -> PlatformRunReportPayload:
    return cast(
        PlatformRunReportPayload,
        compose_report(
            'single_run',
            metadata=metadata,
            section_configs=section_configs,
            section_payloads=section_payloads,
            export_document=export_document,
            presentation=presentation,
        ),
    )


def compose_cross_run_report(
    metadata: PlatformCrossRunMetadata,
    section_configs: Sequence[AnalyticsSectionConfig | PresentationSectionConfig],
    section_payloads: Mapping[str, Any],
    export_document: PlatformReportDocument | None = None,
    presentation: PlatformReportPresentation | None = None,
) -> PlatformCrossRunPayload:
    return cast(
        PlatformCrossRunPayload,
        compose_report(
            'cross_run',
            metadata=metadata,
            section_configs=section_configs,
            section_payloads=section_payloads,
            export_document=export_document,
            presentation=presentation,
        ),
    )

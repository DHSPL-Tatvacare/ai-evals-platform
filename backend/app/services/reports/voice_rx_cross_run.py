"""Canonical cross-run aggregation for Voice Rx canonical single-run payloads."""

from __future__ import annotations

from app.schemas.app_analytics_config import AppAnalyticsConfig
from app.services.reports.contracts.cross_run_report import PlatformCrossRunMetadata, PlatformCrossRunPayload
from app.services.reports.contracts.run_report import PlatformRunReportPayload
from app.services.reports.report_composer import compose_cross_run_report


def _parse_numeric(value: str) -> float:
    try:
        return float(value.replace('%', '').strip())
    except ValueError:
        return 0.0


def build_voice_rx_cross_run_payload(
    runs_data: list[tuple[dict, dict]],
    analytics_config: AppAnalyticsConfig,
    *,
    app_id: str,
    total_runs_available: int,
) -> PlatformCrossRunPayload:
    payloads = [
        (meta, PlatformRunReportPayload.model_validate(data))
        for meta, data in runs_data
    ]
    payloads.sort(key=lambda item: item[0].get('created_at', ''))

    run_labels: list[str] = []
    overall_accuracies: list[float] = []
    critical_errors = 0
    total_items = 0
    severity_rows: dict[str, list[float | None]] = {}
    issue_counts: dict[str, int] = {}

    for meta, payload in payloads:
        sections = {section.id: section for section in payload.sections}
        run_labels.append(payload.metadata.run_name or meta.get('id', '')[:8])

        summary = sections.get('voice-rx-summary')
        if summary:
            cards = {card.key: card for card in summary.data}
            overall_accuracies.append(_parse_numeric(cards.get('overall-accuracy').value if cards.get('overall-accuracy') else '0'))
            critical_errors += int(_parse_numeric(cards.get('critical-errors').value if cards.get('critical-errors') else '0'))
            total_items += int(_parse_numeric(cards.get('total-items').value if cards.get('total-items') else '0'))

        severity = sections.get('voice-rx-severity')
        if severity and severity.data:
            series = severity.data[0]
            for idx, category in enumerate(series.categories):
                severity_rows.setdefault(category, [None] * len(payloads))
                severity_rows[category][len(run_labels) - 1] = float(series.values[idx]) if idx < len(series.values) else None

        issues = sections.get('voice-rx-issues')
        if issues:
            for issue in issues.data.issues:
                issue_counts[issue.title] = issue_counts.get(issue.title, 0) + 1

    avg_accuracy = sum(overall_accuracies) / len(overall_accuracies) if overall_accuracies else 0
    section_payloads = {
        'voice-rx-cross-summary': [
            {
                'key': 'avg-overall-accuracy',
                'label': 'Average Overall Accuracy',
                'value': f'{avg_accuracy:.1f}%',
                'tone': 'positive' if avg_accuracy >= 90 else 'warning' if avg_accuracy >= 75 else 'negative',
            },
            {
                'key': 'runs',
                'label': 'Runs Analyzed',
                'value': str(len(payloads)),
                'tone': 'neutral',
            },
            {
                'key': 'items',
                'label': 'Items Evaluated',
                'value': str(total_items),
                'tone': 'neutral',
            },
            {
                'key': 'critical-errors',
                'label': 'Critical Errors',
                'value': str(critical_errors),
                'tone': 'negative' if critical_errors else 'positive',
            },
        ],
        'voice-rx-cross-metrics': [
            {
                'key': 'avg-overall-accuracy',
                'label': 'Average Overall Accuracy',
                'value': avg_accuracy,
                'maxValue': 100,
                'tone': 'positive' if avg_accuracy >= 90 else 'warning' if avg_accuracy >= 75 else 'negative',
            }
        ],
        'voice-rx-cross-severity': {
            'columns': run_labels,
            'rows': [
                {
                    'label': category,
                    'cells': [
                        {
                            'label': category,
                            'value': value,
                            'tone': 'negative' if category == 'CRITICAL' and (value or 0) > 0 else 'warning' if (value or 0) > 0 else 'positive',
                        }
                        for value in values
                    ],
                }
                for category, values in severity_rows.items()
            ],
        },
        'voice-rx-cross-issues': {
            'issues': [
                {
                    'title': title,
                    'area': 'Accuracy',
                    'priority': 'P0' if title == 'Critical error volume' else 'P1',
                    'summary': f'Observed in {count} runs.',
                }
                for title, count in issue_counts.items()
            ],
            'recommendations': [
                {
                    'priority': 'P0' if avg_accuracy < 85 else 'P1',
                    'title': 'Focus transcription QA on repeated discrepancy types',
                    'action': 'Use the run-level discrepancy examples to tighten prompts and reviewer checks for the recurring error classes.',
                }
            ],
        },
    }

    metadata = PlatformCrossRunMetadata(
        app_id=app_id,
        computed_at=payloads[-1][1].metadata.computed_at if payloads else '',
        source_run_count=len(payloads),
        total_runs_available=total_runs_available,
        cache_key=f'{app_id}:cross_run',
    )
    return compose_cross_run_report(
        metadata=metadata,
        section_configs=analytics_config.cross_run.sections,
        section_payloads=section_payloads,
        export_document=None,
    )

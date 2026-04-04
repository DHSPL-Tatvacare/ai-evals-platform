import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.reports.contracts.report_sections import (
    ExemplarsSection,
    SummaryCardsSection,
)
from app.services.reports.contracts.run_report import PlatformReportMetadata
from app.services.reports.narrative_executor import execute_narrative_generation


class _FakeLLM:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def generate_json(self, *, prompt, system_prompt=None, json_schema=None, **kwargs):
        self.calls.append(
            {
                'prompt': prompt,
                'system_prompt': system_prompt,
                'json_schema': json_schema,
                'kwargs': kwargs,
            },
        )
        return self.response


class ReportNarrativeExecutorTests(unittest.IsolatedAsyncioTestCase):
    async def test_execute_narrative_generation_uses_report_config_assets_and_output_points(self):
        metadata = PlatformReportMetadata(
            app_id='kaira-bot',
            run_id='run-123',
            run_name='Nightly Run',
            eval_type='batch_thread',
            created_at='2026-04-04T10:00:00+00:00',
            computed_at='2026-04-04T10:05:00+00:00',
        )
        sections = [
            SummaryCardsSection(
                id='kaira-summary',
                title='Executive Summary',
                variant='overview',
                data=[],
            ),
            ExemplarsSection(
                id='kaira-exemplars',
                title='Exemplars',
                variant='examples',
                data=[],
            ),
        ]
        llm = _FakeLLM(
            {
                'executive_summary': 'Quality is stable.',
                'top_issues': [
                    {
                        'title': 'Intent slips',
                        'area': 'Intent',
                        'severity': 'high',
                        'summary': 'Pricing questions still miss.',
                    },
                ],
                'recommendations': [
                    {
                        'priority': 'P1',
                        'area': 'Intent',
                        'action': 'Tighten routing examples',
                        'rationale': 'Reduce fallback errors',
                    },
                ],
                'exemplars': [],
                'prompt_gaps': [
                    {
                        'gap_type': 'UNDERSPEC',
                        'prompt_section': 'Escalation',
                        'evaluation_rule': 'rule-1',
                        'suggested_fix': 'Add escalation thresholds',
                    },
                ],
            },
        )

        inserted_payloads = await execute_narrative_generation(
            llm=llm,
            report_id='quality-review',
            report_kind='single_run',
            metadata=metadata,
            sections=sections,
            narrative_config={
                'enabled': True,
                'assetKeys': {
                    'systemPromptKey': 'quality-review-system',
                },
                'resolvedAssets': {
                    'systemPrompt': 'Use the quality-review prompt.',
                },
                'inputSelection': {'sectionIds': ['kaira-summary', 'kaira-exemplars']},
                'outputInsertionPoints': ['kaira-narrative', 'kaira-prompt-gaps', 'kaira-recommendations'],
            },
        )

        self.assertEqual(llm.calls[0]['system_prompt'], 'Use the quality-review prompt.')
        self.assertIn('kaira-narrative', inserted_payloads)
        self.assertIn('kaira-prompt-gaps', inserted_payloads)
        self.assertIn('kaira-recommendations', inserted_payloads)
        self.assertEqual(inserted_payloads['kaira-narrative']['executiveSummary'], 'Quality is stable.')
        self.assertEqual(inserted_payloads['kaira-recommendations']['recommendations'][0]['action'], 'Tighten routing examples')

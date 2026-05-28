// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { PlatformReportView } from '@/features/analytics/components/PlatformReportRenderer';
import type { EvaluatorReportView, PlatformReportSection, PlatformRunReportPayload } from '@/types/platformReports';

function summaryCards(score: string): PlatformReportSection[] {
  return [
    {
      id: 'cards-1',
      type: 'summary_cards',
      title: 'Summary',
      description: null,
      variant: 'default',
      data: [{ key: 'score', label: 'Score', value: score, subtitle: 'A', tone: 'positive' }],
    },
  ];
}

function makeReport(evaluatorViews?: EvaluatorReportView[]): PlatformRunReportPayload {
  return {
    schemaVersion: 'v1',
    metadata: {
      appId: 'kaira-bot',
      reportKind: 'single_run',
      runId: 'run-1',
      runName: 'Run One',
      evalType: 'custom',
      createdAt: '2026-05-01T00:00:00Z',
      computedAt: '2026-05-01T00:00:00Z',
      sourceRunCount: 1,
      llmProvider: null,
      llmModel: null,
      narrativeModel: null,
      cacheKey: null,
    },
    presentation: {
      sections: [
        { sectionId: 'cards-1', componentId: 'summary_cards', title: 'Summary', description: null, variant: 'default', printable: true },
      ],
      rendererId: 'run-v1',
      layoutGroups: [{ id: 'g', tab: 'detailed', layout: 'stack', sectionIds: ['cards-1'] }],
      density: 'comfortable',
      designTokens: {},
      themeTokens: {},
    },
    sections: summaryCards('70'),
    exportDocument: { blocks: [] } as unknown as PlatformRunReportPayload['exportDocument'],
    ...(evaluatorViews ? { evaluatorViews } : {}),
  };
}

describe('PlatformReportView evaluator switcher', () => {
  it('shows the switcher and swaps sections when more than one evaluator view exists', () => {
    const report = makeReport([
      { evaluatorId: 'e1', evaluatorName: 'Tone', sections: summaryCards('85') },
      { evaluatorId: 'e2', evaluatorName: 'Compliance', sections: summaryCards('42') },
    ]);
    render(<PlatformReportView report={report} actions={null} />);

    expect(screen.getByRole('button', { name: 'Tone' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Compliance' })).toBeInTheDocument();
    // Defaults to the first view's sections.
    expect(screen.getAllByText('85').length).toBeGreaterThan(0);
    expect(screen.queryByText('42')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Compliance' }));
    expect(screen.getAllByText('42').length).toBeGreaterThan(0);
    expect(screen.queryByText('85')).not.toBeInTheDocument();
  });

  it('renders flat top-level sections with no switcher when evaluatorViews is absent', () => {
    render(<PlatformReportView report={makeReport()} actions={null} />);
    expect(screen.getAllByText('70').length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: 'Tone' })).not.toBeInTheDocument();
  });

  it('renders flat sections with no switcher when only one evaluator view exists', () => {
    const report = makeReport([{ evaluatorId: 'e1', evaluatorName: 'Tone', sections: summaryCards('85') }]);
    render(<PlatformReportView report={report} actions={null} />);
    // Single view is not surfaced as a switcher; the flat top-level sections render.
    expect(screen.getAllByText('70').length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: 'Tone' })).not.toBeInTheDocument();
  });
});

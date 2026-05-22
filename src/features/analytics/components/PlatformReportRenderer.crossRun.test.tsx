// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { PlatformReportView } from '@/features/analytics/components/PlatformReportRenderer';
import type { PlatformCrossRunPayload } from '@/types/platformReports';

function makeCrossRunReport(): PlatformCrossRunPayload {
  return {
    schemaVersion: 'v1',
    metadata: {
      appId: 'kaira-bot',
      reportKind: 'cross_run',
      computedAt: '2026-05-01T00:00:00Z',
      sourceRunCount: 3,
      totalRunsAvailable: 3,
      cacheKey: null,
    },
    presentation: {
      sections: [
        {
          sectionId: 'cards-1',
          componentId: 'summary_cards',
          title: 'Summary',
          description: null,
          variant: 'default',
          printable: true,
        },
      ],
      rendererId: 'cross-run-v1',
      layoutGroups: [
        { id: 'detailed-default', tab: 'detailed', layout: 'stack', sectionIds: ['cards-1'] },
      ],
      density: 'comfortable',
      designTokens: {},
      themeTokens: {},
    },
    sections: [
      {
        id: 'cards-1',
        type: 'summary_cards',
        title: 'Summary',
        description: null,
        variant: 'default',
        data: [
          { key: 'score', label: 'Score', value: '85', subtitle: 'A', tone: 'positive' },
        ],
      },
    ],
  };
}

describe('PlatformReportView cross-run payload', () => {
  it('renders without crashing when given a cross-run payload', () => {
    expect(() => render(<PlatformReportView report={makeCrossRunReport()} actions={null} />)).not.toThrow();
  });

  it('shows the Summary tab', () => {
    render(<PlatformReportView report={makeCrossRunReport()} actions={null} />);
    expect(screen.getByRole('button', { name: 'Summary' })).toBeInTheDocument();
  });

  it('shows the Detailed Analysis tab', () => {
    render(<PlatformReportView report={makeCrossRunReport()} actions={null} />);
    expect(screen.getByRole('button', { name: 'Detailed Analysis' })).toBeInTheDocument();
  });

  it('renders a fallback title when metadata has no runName', () => {
    render(<PlatformReportView report={makeCrossRunReport()} actions={null} />);
    // Cross-run metadata has no runName — renderer should show a generic title
    expect(screen.getByText('Evaluation Report')).toBeInTheDocument();
  });
});

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

function makeNarrativeCrossRunReport(): PlatformCrossRunPayload {
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
          sectionId: 'narr',
          componentId: 'narrative',
          title: 'AI Narrative',
          description: null,
          variant: 'default',
          printable: true,
        },
      ],
      rendererId: 'cross-run-v1',
      layoutGroups: [
        { id: 'summary-default', tab: 'summary', layout: 'stack', sectionIds: ['narr'] },
        { id: 'detailed-default', tab: 'detailed', layout: 'stack', sectionIds: ['narr'] },
      ],
      density: 'comfortable',
      designTokens: {},
      themeTokens: {},
    },
    sections: [
      {
        id: 'narr',
        type: 'narrative',
        title: 'AI Narrative',
        description: null,
        variant: 'default',
        data: {
          schemaVersion: 'v1',
          schemaKey: 'platform_cross_run_narrative_v1',
          schemaOwner: 'backend',
          executiveSummary: 'Overall summary text.',
          trendAnalysis: 'Trend text.',
          criticalPatterns: [{ title: 'Pattern Alpha', summary: 'pattern detail', affectedRuns: 2 }],
          strategicRecommendations: [{ priority: 'P0', action: 'Do the thing', expectedImpact: 'big impact' }],
        },
      },
    ],
  };
}

describe('PlatformReportView cross-run payload', () => {
  it('renders without crashing when given a cross-run payload', () => {
    expect(() => render(<PlatformReportView report={makeCrossRunReport()} actions={null} />)).not.toThrow();
  });

  it('renders the full cross-run narrative (patterns + recommendations) in the Summary tab', () => {
    // Summary is the default tab. "Full narrative" means the patterns and the
    // strategic recommendations show — not just the executive-summary headline.
    render(<PlatformReportView report={makeNarrativeCrossRunReport()} actions={null} />);
    // Rendered in BOTH the Summary and Detailed panels (Tabs mounts both) — the
    // Summary tab now shows the full narrative, not a single executive-summary block.
    expect(screen.getAllByText('Pattern Alpha').length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText('Do the thing').length).toBeGreaterThanOrEqual(2);
    // …and it reuses the single-run Summary shape (top-issues table + Recommendations),
    // not bespoke stacked boxes.
    expect(screen.getAllByText('Recurring failure patterns').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Recommendations').length).toBeGreaterThanOrEqual(1);
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

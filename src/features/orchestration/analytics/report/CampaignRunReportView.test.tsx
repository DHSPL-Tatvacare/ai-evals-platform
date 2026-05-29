import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { CampaignRunReportView } from './CampaignRunReportView';
import type { RunReportResponse } from '../types';

function baseReport(overrides: Partial<RunReportResponse> = {}): RunReportResponse {
  return {
    runId: 'run-1',
    workflowId: 'wf-1',
    workflowName: 'Onboarding outreach',
    appId: 'inside-sales',
    status: 'completed',
    triggeredBy: 'scheduler',
    startedAt: '2026-05-29T09:00:00Z',
    completedAt: '2026-05-29T09:12:00Z',
    durationSeconds: 720,
    recipientsTotal: 50,
    spend: 4.2,
    buckets: { positive: 18, reached: 30, noResponse: 12, failed: 5, inFlight: 3 },
    channels: [
      {
        capability: 'voice',
        vendor: 'bolna',
        connectionLabel: 'Bolna',
        stages: [
          { key: 'dialed', label: 'Dialed', count: 50 },
          { key: 'connected', label: 'Connected', count: 40 },
          { key: 'answered', label: 'Answered', count: 35 },
          { key: 'positive', label: 'Positive', count: 18 },
        ],
        metrics: { avgDurationSec: 95, totalDurationSec: 3325 },
      },
      {
        capability: 'messaging',
        vendor: 'wati',
        connectionLabel: 'WhatsApp',
        stages: [
          { key: 'sent', label: 'Sent', count: 35 },
          { key: 'delivered', label: 'Delivered', count: 33 },
          { key: 'read', label: 'Read', count: 25 },
          { key: 'replied', label: 'Replied', count: 12 },
        ],
        metrics: {},
      },
    ],
    recipients: [
      {
        recipientId: 'rec-1',
        displayName: 'Asha P',
        contactLast4: '4821',
        attributes: { city: 'Pune' },
        channels: [
          {
            capability: 'voice',
            outcomeBucket: 'positive',
            stageReached: 'answered',
            summary: 'Patient agreed to a follow-up consult.',
            metrics: { durationSec: 110 },
          },
          {
            capability: 'messaging',
            outcomeBucket: 'reached',
            stageReached: 'read',
            summary: null,
            metrics: {},
          },
        ],
      },
    ],
    recipientsTotalCount: 50,
    ...overrides,
  };
}

describe('CampaignRunReportView', () => {
  it('renders one channel strip per capability present', () => {
    render(<CampaignRunReportView report={baseReport()} />);
    expect(screen.getAllByText('Voice · Bolna').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Messaging · WhatsApp').length).toBeGreaterThanOrEqual(1);
  });

  it('renders the locked section titles and outcome donut title', () => {
    render(<CampaignRunReportView report={baseReport()} />);
    expect(screen.getByText('Engagement funnel')).toBeInTheDocument();
    expect(screen.getByText('Outcome mix')).toBeInTheDocument();
    expect(screen.getByText('Closed-loop routing')).toBeInTheDocument();
  });

  it('renders the data-driven subtitle from distinct capabilities', () => {
    render(<CampaignRunReportView report={baseReport()} />);
    expect(
      screen.getByText('50 contacts across Voice and WhatsApp'),
    ).toBeInTheDocument();
  });

  it('shows recipient outcome, S·D·R stage signal and transcript snippet', () => {
    render(<CampaignRunReportView report={baseReport()} />);
    expect(screen.getByText('Asha P')).toBeInTheDocument();
    expect(
      screen.getByText('Patient agreed to a follow-up consult.'),
    ).toBeInTheDocument();
    const caption = screen.getByText(/contacts · per-channel outcome and engagement/);
    expect(caption).toHaveTextContent('Top 1 of 50 contacts');
  });

  it('renders a third channel with no reshape (generic channel iteration)', () => {
    const report = baseReport();
    report.channels.push({
      capability: 'email',
      vendor: null,
      connectionLabel: 'Resend',
      stages: [
        { key: 'sent', label: 'Sent', count: 20 },
        { key: 'opened', label: 'Opened', count: 8 },
      ],
      metrics: {},
    });
    render(<CampaignRunReportView report={report} />);
    expect(screen.getAllByText('Email · Resend').length).toBeGreaterThanOrEqual(1);
    expect(
      screen.getByText('50 contacts across Voice, WhatsApp and Email'),
    ).toBeInTheDocument();
  });

  it('degrades when a channel is absent and connection label is null', () => {
    const report = baseReport({
      channels: [
        {
          capability: 'voice',
          vendor: null,
          connectionLabel: null,
          stages: [{ key: 'dialed', label: 'Dialed', count: 10 }],
          metrics: {},
        },
      ],
      recipients: [
        {
          recipientId: 'rec-2',
          displayName: null,
          contactLast4: null,
          attributes: {},
          channels: [
            {
              capability: 'voice',
              outcomeBucket: null,
              stageReached: null,
              summary: null,
              metrics: {},
            },
          ],
        },
      ],
      recipientsTotalCount: 10,
    });
    const { container } = render(<CampaignRunReportView report={report} />);
    expect(screen.getAllByText('Voice').length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText('Messaging · WhatsApp')).not.toBeInTheDocument();
    expect(within(container).getByText('Outcome mix')).toBeInTheDocument();
  });
});

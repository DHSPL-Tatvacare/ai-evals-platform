// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { EngagementFunnel } from './EngagementFunnel';
import type { RunReportChannel } from '../types';

const voice: RunReportChannel = {
  capability: 'voice',
  vendor: 'bolna',
  connectionLabel: 'Bolna - GoodFlip',
  stages: [
    { key: 'dialed', label: 'Dialed', count: 27 },
    { key: 'connected', label: 'Connected', count: 25 },
    { key: 'answered', label: 'Answered', count: 12 },
    { key: 'positive', label: 'Positive', count: 12 },
  ],
  metrics: {},
};

const messaging: RunReportChannel = {
  capability: 'messaging',
  vendor: 'wati',
  connectionLabel: 'WATI - GoodFlip',
  stages: [
    { key: 'sent', label: 'Sent', count: 19 },
    { key: 'delivered', label: 'Delivered', count: 19 },
    { key: 'read', label: 'Read', count: 19 },
    { key: 'replied', label: 'Replied', count: 0 },
  ],
  metrics: {},
};

describe('EngagementFunnel', () => {
  it('renders one funnel per channel, each headed independently (no clubbing)', () => {
    render(<EngagementFunnel channels={[voice, messaging]} />);
    // One header per channel.
    expect(screen.getByText('Voice · Bolna - GoodFlip')).toBeInTheDocument();
    expect(screen.getByText('Messaging · WATI - GoodFlip')).toBeInTheDocument();
    // Each channel funnel has exactly one root stage (no drop-off marker).
    // voice: 4 stages -> 3 dropoffs; messaging: 4 stages -> 3 dropoffs.
    expect(screen.getAllByTestId('funnel-dropoff')).toHaveLength(6);
    // Stage labels from data only.
    expect(screen.getByText('Dialed')).toBeInTheDocument();
    expect(screen.getByText('Sent')).toBeInTheDocument();
  });

  it('does not concatenate channels into one bar list', () => {
    const { container } = render(<EngagementFunnel channels={[voice, messaging]} />);
    // 8 stages total across 2 channels.
    expect(container.querySelectorAll('[data-funnel-stage]')).toHaveLength(8);
  });

  it('renders a synthetic third channel with no code change (generic)', () => {
    const email: RunReportChannel = {
      capability: 'email',
      vendor: null,
      connectionLabel: 'Resend',
      stages: [
        { key: 'sent', label: 'Sent', count: 20 },
        { key: 'opened', label: 'Opened', count: 8 },
      ],
      metrics: {},
    };
    render(<EngagementFunnel channels={[voice, messaging, email]} />);
    expect(screen.getByText('Email · Resend')).toBeInTheDocument();
    expect(screen.getByText('Opened')).toBeInTheDocument();
    // email funnel: 2 stages -> 1 drop-off. Total dropoffs = 3 + 3 + 1 = 7.
    expect(screen.getAllByTestId('funnel-dropoff')).toHaveLength(7);
  });

  it('omits the provider logo when the channel has no vendor but still labels it', () => {
    const email: RunReportChannel = {
      capability: 'email',
      vendor: null,
      connectionLabel: null,
      stages: [{ key: 'sent', label: 'Sent', count: 5 }],
      metrics: {},
    };
    const { container } = render(<EngagementFunnel channels={[email]} />);
    expect(screen.getByText('Email')).toBeInTheDocument();
    // no provider logo img for a vendor-less channel
    expect(within(container).queryByRole('img')).toBeNull();
  });
});

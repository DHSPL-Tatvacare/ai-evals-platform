import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/features/analytics/components/ChartRenderer', () => ({
  ChartRenderer: () => <div data-testid="chart" />,
}));

import { TrendCard } from './TrendCard';

describe('TrendCard', () => {
  it('renders the title and the chart when data is present', () => {
    render(
      <TrendCard
        title="Outcomes over time"
        data={[{ day: '2026-05-01', positive: 3 }]}
        xKey="day"
        seriesKeys={['positive']}
      />,
    );
    expect(screen.getByText('Outcomes over time')).toBeInTheDocument();
    expect(screen.getByTestId('chart')).toBeInTheDocument();
  });

  it('renders an empty hint when there is no data', () => {
    render(<TrendCard title="Outcomes over time" data={[]} xKey="day" seriesKeys={['positive']} />);
    expect(screen.getByText(/no trend data/i)).toBeInTheDocument();
  });
});

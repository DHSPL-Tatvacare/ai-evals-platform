import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { MetricBreakdownCard, type MetricBreakdownColumn } from './MetricBreakdownCard';

interface Row {
  key: string;
  label: string;
  recipients: number;
  cost: number;
}

const ROWS: Row[] = [
  { key: 'a', label: 'Campaign A', recipients: 100, cost: 1.5 },
  { key: 'b', label: 'Campaign B', recipients: 40, cost: 0.5 },
];

const COLUMNS: MetricBreakdownColumn<Row>[] = [
  { key: 'recipients', header: 'Recipients', render: (r) => r.recipients },
  { key: 'cost', header: 'Cost', render: (r) => `$${r.cost.toFixed(2)}` },
];

describe('MetricBreakdownCard', () => {
  it('renders the name header, metric columns and row values', () => {
    render(
      <MetricBreakdownCard
        title="Breakdown"
        nameHeader="By campaign"
        rows={ROWS}
        columns={COLUMNS}
        keyExtractor={(r) => r.key}
        renderName={(r) => r.label}
      />,
    );
    expect(screen.getByText('By campaign')).toBeInTheDocument();
    expect(screen.getByText('Recipients')).toBeInTheDocument();
    expect(screen.getByText('Cost')).toBeInTheDocument();
    expect(screen.getByText('Campaign A')).toBeInTheDocument();
    expect(screen.getByText('$1.50')).toBeInTheDocument();
  });
});

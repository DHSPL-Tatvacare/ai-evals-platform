import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { FunnelCard } from './FunnelCard';

const STAGES = [
  { key: 'dialed', label: 'Dialed', value: 100 },
  { key: 'connected', label: 'Connected', value: 60 },
  { key: 'positive', label: 'Positive', value: 20 },
];

describe('FunnelCard', () => {
  it('renders each stage label and value', () => {
    render(<FunnelCard title="Conversion" stages={STAGES} />);
    for (const stage of STAGES) {
      expect(screen.getByText(stage.label)).toBeInTheDocument();
      expect(screen.getByText(String(stage.value))).toBeInTheDocument();
    }
  });

  it('renders an empty hint when there are no stages', () => {
    render(<FunnelCard title="Conversion" stages={[]} />);
    expect(screen.getByText(/no funnel data/i)).toBeInTheDocument();
  });
});

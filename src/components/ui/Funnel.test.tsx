// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Funnel } from './Funnel';

describe('Funnel', () => {
  it('renders nothing meaningful for empty stages without throwing', () => {
    const { container } = render(<Funnel stages={[]} />);
    expect(container).toBeTruthy();
    // No stage rows.
    expect(container.querySelectorAll('[data-funnel-stage]')).toHaveLength(0);
  });

  it('renders each stage with label, count, %-of-root and step drop-off vs previous', () => {
    render(
      <Funnel
        stages={[
          { key: 'dialed', label: 'Dialed', count: 27 },
          { key: 'connected', label: 'Connected', count: 25 },
          { key: 'answered', label: 'Answered', count: 12 },
          { key: 'positive', label: 'Positive', count: 12 },
        ]}
      />,
    );
    expect(screen.getByText('Dialed')).toBeInTheDocument();
    expect(screen.getByText('Connected')).toBeInTheDocument();
    expect(screen.getByText('Answered')).toBeInTheDocument();
    expect(screen.getByText('Positive')).toBeInTheDocument();

    // counts
    expect(screen.getByText('27')).toBeInTheDocument();
    expect(screen.getByText('25')).toBeInTheDocument();
    expect(screen.getAllByText('12').length).toBeGreaterThanOrEqual(1);

    // % of root: root=100%, 25/27=93%, 12/27=44%
    expect(screen.getByText('100%')).toBeInTheDocument();
    expect(screen.getByText('93%')).toBeInTheDocument();
    expect(screen.getAllByText('44%').length).toBeGreaterThanOrEqual(1);
  });

  it('first stage has no drop-off; later stages show drop-off vs the previous stage', () => {
    render(
      <Funnel
        stages={[
          { key: 'dialed', label: 'Dialed', count: 27 },
          { key: 'connected', label: 'Connected', count: 25 },
          { key: 'answered', label: 'Answered', count: 12 },
          { key: 'positive', label: 'Positive', count: 12 },
        ]}
      />,
    );
    const rows = screen.getAllByTestId('funnel-dropoff');
    // one drop-off marker per non-first stage
    expect(rows).toHaveLength(3);
    // 25 from 27 -> -7%
    expect(rows[0]).toHaveTextContent('7%');
    // 12 from 25 -> -52%
    expect(rows[1]).toHaveTextContent('52%');
    // 12 from 12 -> 0%
    expect(rows[2]).toHaveTextContent('0%');
  });

  it('single stage renders full width and no connector / no drop-off', () => {
    render(<Funnel stages={[{ key: 'only', label: 'Only', count: 10 }]} />);
    expect(screen.getByText('Only')).toBeInTheDocument();
    expect(screen.getByText('100%')).toBeInTheDocument();
    expect(screen.queryAllByTestId('funnel-dropoff')).toHaveLength(0);
    const band = screen.getByTestId('funnel-band-only');
    expect(band).toHaveStyle({ width: '100%' });
  });

  it('root count of 0 yields all 0% widths with no division by zero', () => {
    render(
      <Funnel
        stages={[
          { key: 'a', label: 'A', count: 0 },
          { key: 'b', label: 'B', count: 0 },
        ]}
      />,
    );
    expect(screen.getAllByText('0%').length).toBeGreaterThanOrEqual(2);
    const bandA = screen.getByTestId('funnel-band-a');
    const bandB = screen.getByTestId('funnel-band-b');
    expect(bandA).toHaveStyle({ width: '0%' });
    expect(bandB).toHaveStyle({ width: '0%' });
  });

  it('a 0-count later stage renders a zero-width band but keeps its label and 0', () => {
    render(
      <Funnel
        stages={[
          { key: 'sent', label: 'Sent', count: 19 },
          { key: 'replied', label: 'Replied', count: 0 },
        ]}
      />,
    );
    expect(screen.getByText('Replied')).toBeInTheDocument();
    expect(screen.getByText('0')).toBeInTheDocument();
    expect(screen.getByTestId('funnel-band-replied')).toHaveStyle({ width: '0%' });
  });

  it('equal counts yield equal band widths', () => {
    render(
      <Funnel
        stages={[
          { key: 'a', label: 'A', count: 10 },
          { key: 'b', label: 'B', count: 10 },
        ]}
      />,
    );
    expect(screen.getByTestId('funnel-band-a')).toHaveStyle({ width: '100%' });
    expect(screen.getByTestId('funnel-band-b')).toHaveStyle({ width: '100%' });
  });
});

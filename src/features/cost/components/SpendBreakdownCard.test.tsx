import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { SpendBreakdownCard } from './SpendBreakdownCard';
import type { GroupedSpend } from '../types';

const TWO_ROWS: GroupedSpend[] = [
  { key: 'gpt-4o', costUsd: 3.0, tokens: 10000, calls: 6 },
  { key: 'gemini-pro', costUsd: 1.0, tokens: 4000, calls: 0 },
];

const ZERO_CALLS_ROW: GroupedSpend[] = [
  { key: 'model-x', costUsd: 2.5, tokens: 8000, calls: 0 },
];

const NORMAL_ROW: GroupedSpend[] = [
  { key: 'model-y', costUsd: 4.0, tokens: 12000, calls: 8 },
];

function renderCard(rows: GroupedSpend[]) {
  return render(
    <SpendBreakdownCard
      title="By Model"
      subtitle="test subtitle"
      rows={rows}
      nameHeader="Model"
      renderName={(row) => <span>{row.key}</span>}
      searchPlaceholder="Search models"
    />,
  );
}

describe('SpendBreakdownCard', () => {
  it('renders "—" in the Avg/req column when calls is 0 (divide-by-zero guard)', () => {
    renderCard(ZERO_CALLS_ROW);
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
  });

  it('renders a formatted avg/req for a normal row', () => {
    renderCard(NORMAL_ROW);
    // 4.0 / 8 = $0.500 — formatUsd(0.5) → '$0.500'
    expect(screen.getByText('$0.500')).toBeInTheDocument();
  });

  it('does NOT render "—" for the avg/req of a row with non-zero calls', () => {
    renderCard(NORMAL_ROW);
    // There should be no em-dash cell for a row that has calls.
    expect(screen.queryByText('—')).toBeNull();
  });

  it('share % equals cost/total*100 to one decimal for a known two-row fixture', () => {
    // Row 1: 3.0 / 4.0 = 75.0%, Row 2: 1.0 / 4.0 = 25.0%
    renderCard(TWO_ROWS);
    expect(screen.getByText('75.0%')).toBeInTheDocument();
    expect(screen.getByText('25.0%')).toBeInTheDocument();
  });

  it('renders all row keys and the card title', () => {
    renderCard(TWO_ROWS);
    expect(screen.getByText('By Model')).toBeInTheDocument();
    expect(screen.getByText('gpt-4o')).toBeInTheDocument();
    expect(screen.getByText('gemini-pro')).toBeInTheDocument();
  });

  it('renders "—" for the zero-calls row even when another row has calls', () => {
    // TWO_ROWS has gpt-4o (calls=6) and gemini-pro (calls=0).
    renderCard(TWO_ROWS);
    // gemini-pro avg/req → '—'
    expect(screen.getByText('—')).toBeInTheDocument();
    // gpt-4o avg/req → 3.0/6 = $0.500
    expect(screen.getByText('$0.500')).toBeInTheDocument();
  });
});

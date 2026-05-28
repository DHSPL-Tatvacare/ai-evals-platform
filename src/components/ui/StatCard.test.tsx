import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Coins } from 'lucide-react';

import { StatCard } from './StatCard';

describe('StatCard', () => {
  it('renders label and value', () => {
    render(<StatCard icon={Coins} label="Spend" value="$1.23" />);
    expect(screen.getByText('Spend')).toBeInTheDocument();
    expect(screen.getByText('$1.23')).toBeInTheDocument();
  });

  it('applies the danger tone class to the value', () => {
    render(<StatCard icon={Coins} label="Failed %" value="12%" tone="danger" />);
    const value = screen.getByText('12%');
    expect(value.className).toContain('var(--color-error)');
  });
});

import { useState } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { EvaluatorPills } from './EvaluatorPills';

const ITEMS = [
  { id: 'e1', name: 'Empathy' },
  { id: 'e2', name: 'Compliance' },
];

describe('EvaluatorPills', () => {
  it('renders a pill per item', () => {
    render(<EvaluatorPills items={ITEMS} activeId="e1" onSelect={() => {}} />);
    expect(screen.getByText('Empathy')).toBeInTheDocument();
    expect(screen.getByText('Compliance')).toBeInTheDocument();
  });

  it('marks the active item with the active styling', () => {
    render(<EvaluatorPills items={ITEMS} activeId="e2" onSelect={() => {}} />);
    expect(screen.getByText('Compliance').className).toContain('var(--border-brand)');
    expect(screen.getByText('Empathy').className).toContain('var(--border-subtle)');
  });

  it('fires onSelect with the clicked item id', () => {
    const onSelect = vi.fn();
    render(<EvaluatorPills items={ITEMS} activeId="e1" onSelect={onSelect} />);
    fireEvent.click(screen.getByText('Compliance'));
    expect(onSelect).toHaveBeenCalledWith('e2');
  });

  it('drives selection when wired to local state', () => {
    function Harness() {
      const [active, setActive] = useState('e1');
      return <EvaluatorPills items={ITEMS} activeId={active} onSelect={setActive} />;
    }
    render(<Harness />);
    fireEvent.click(screen.getByText('Compliance'));
    expect(screen.getByText('Compliance').className).toContain('var(--border-brand)');
  });
});

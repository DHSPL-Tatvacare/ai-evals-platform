import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

import { ConditionalBranchesEditor } from '@/features/orchestration/components/editors/ConditionalBranchesEditor';
import type { ConditionalBranch } from '@/features/orchestration/types';

const BRANCHES: ConditionalBranch[] = [
  { id: 'vip', label: 'VIP', predicate: { field: 'tier', op: 'eq', value: 'vip' } },
  { id: 'warm', label: 'Warm', predicate: { field: 'score', op: 'gte', value: '50' } },
];

describe('ConditionalBranchesEditor', () => {
  it('lists each branch with its editable name and shown output-edge id', () => {
    const onChange = vi.fn();
    render(
      <ConditionalBranchesEditor value={{ branches: BRANCHES }} onChange={onChange} />,
    );
    const labelInputs = screen.getAllByPlaceholderText('Branch name');
    expect(labelInputs).toHaveLength(2);
    expect((labelInputs[0] as HTMLInputElement).value).toBe('VIP');
    // Each branch surfaces its routing-key (output-edge id).
    expect(screen.getByText('vip')).toBeInTheDocument();
    expect(screen.getByText('warm')).toBeInTheDocument();
  });

  it('always shows the implicit default branch', () => {
    const onChange = vi.fn();
    render(
      <ConditionalBranchesEditor value={{ branches: BRANCHES }} onChange={onChange} />,
    );
    expect(screen.getByText('default')).toBeInTheDocument();
    expect(screen.getByText(/Unmatched contacts continue on/i)).toBeInTheDocument();
  });

  it('adds a branch with a stable id the operator never types', () => {
    const onChange = vi.fn();
    render(
      <ConditionalBranchesEditor value={{ branches: BRANCHES }} onChange={onChange} />,
    );
    fireEvent.click(screen.getByText('Add branch'));
    const next = onChange.mock.calls[0][0] as { branches: ConditionalBranch[] };
    expect(next.branches).toHaveLength(3);
    expect(typeof next.branches[2].id).toBe('string');
    expect(next.branches[2].id.length).toBeGreaterThan(0);
    expect(next.branches[2].predicate).toBeDefined();
  });

  it('removes a branch', () => {
    const onChange = vi.fn();
    render(
      <ConditionalBranchesEditor value={{ branches: BRANCHES }} onChange={onChange} />,
    );
    const removeButtons = screen.getAllByRole('button', { name: /Remove branch/i });
    fireEvent.click(removeButtons[0]);
    const next = onChange.mock.calls[0][0] as { branches: ConditionalBranch[] };
    expect(next.branches).toHaveLength(1);
    expect(next.branches[0].id).toBe('warm');
  });

  it('renders an empty-state and an Add branch action when there are no branches', () => {
    const onChange = vi.fn();
    render(<ConditionalBranchesEditor value={{ branches: [] }} onChange={onChange} />);
    expect(screen.getByText('Add branch')).toBeInTheDocument();
  });
});

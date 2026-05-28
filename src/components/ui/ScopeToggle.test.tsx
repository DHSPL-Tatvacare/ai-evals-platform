import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ScopeToggle } from './ScopeToggle';

describe('ScopeToggle', () => {
  it('hides the tenant option when canSeeTenant is false', () => {
    render(<ScopeToggle value="mine" onChange={vi.fn()} canSeeTenant={false} />);
    expect(screen.getByRole('tab', { name: /my campaigns/i })).toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: /all campaigns/i })).toBeNull();
  });

  it('shows the tenant option when canSeeTenant is true', () => {
    render(<ScopeToggle value="tenant" onChange={vi.fn()} canSeeTenant />);
    expect(screen.getByRole('tab', { name: /all campaigns/i })).toBeInTheDocument();
  });

  it('calls onChange with the selected scope', () => {
    const onChange = vi.fn();
    render(<ScopeToggle value="tenant" onChange={onChange} canSeeTenant />);
    fireEvent.click(screen.getByRole('tab', { name: /my campaigns/i }));
    expect(onChange).toHaveBeenCalledWith('mine');
  });
});

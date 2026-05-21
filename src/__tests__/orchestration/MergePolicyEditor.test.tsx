import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import { MergePolicyEditor } from '@/features/orchestration/components/editors/MergePolicyEditor';

describe('MergePolicyEditor — option values match backend literals', () => {
  it('renders both policy fields', () => {
    const onChange = vi.fn();
    render(<MergePolicyEditor value={{}} onChange={onChange} />);
    expect(screen.getByText('Recipient merge policy')).toBeInTheDocument();
    expect(screen.getByText('Payload merge policy')).toBeInTheDocument();
  });

  it('default merge_policy help text matches dedupe copy', () => {
    const onChange = vi.fn();
    render(<MergePolicyEditor value={{}} onChange={onChange} />);
    // Default merge_policy is 'dedupe'
    expect(
      screen.getByText(/If the same recipient arrives from multiple branches/),
    ).toBeInTheDocument();
  });

  it('default payload_policy help text matches last_wins copy', () => {
    const onChange = vi.fn();
    render(<MergePolicyEditor value={{}} onChange={onChange} />);
    // Default payload_policy is 'last_wins'
    expect(
      screen.getByText(/The payload from the last branch to arrive replaces/),
    ).toBeInTheDocument();
  });

  it('shallow_merge help text is visible when selected', () => {
    const onChange = vi.fn();
    render(
      <MergePolicyEditor
        value={{ merge_policy: 'dedupe', payload_policy: 'shallow_merge' }}
        onChange={onChange}
      />,
    );
    expect(
      screen.getByText(/Later arrivals override colliding keys field-by-field/),
    ).toBeInTheDocument();
  });

  it('first_wins payload help text is visible when selected', () => {
    const onChange = vi.fn();
    render(
      <MergePolicyEditor
        value={{ merge_policy: 'first_wins', payload_policy: 'first_wins' }}
        onChange={onChange}
      />,
    );
    expect(
      screen.getByText(/The payload from the first branch to arrive is preserved/),
    ).toBeInTheDocument();
  });
});

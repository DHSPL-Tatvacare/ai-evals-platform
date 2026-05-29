import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

import { RuleSetBuilder } from '@/features/orchestration/components/editors/RuleSetBuilder';
import type { LeafPredicate, PredicateAst } from '@/features/orchestration/types';

describe('RuleSetBuilder', () => {
  it('renders a single starter rule for an empty value', () => {
    const onChange = vi.fn();
    render(<RuleSetBuilder value={undefined} onChange={onChange} />);
    // Field / Op / Value are each stacked on their own labelled row.
    expect(screen.getByText('Field')).toBeInTheDocument();
    expect(screen.getByText('Operator')).toBeInTheDocument();
    expect(screen.getByText('Value')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('payload field')).toBeInTheDocument();
  });

  it('exposes a Match ALL / ANY selector and maps ALL to and, ANY to or', () => {
    const onChange = vi.fn();
    const value: PredicateAst = {
      and: [
        { field: 'a', op: 'eq', value: '1' },
        { field: 'b', op: 'eq', value: '2' },
      ],
    };
    render(<RuleSetBuilder value={value} onChange={onChange} />);
    // Two rules render.
    expect(screen.getAllByPlaceholderText('payload field')).toHaveLength(2);
    // Add a rule keeps the AND wrapper.
    fireEvent.click(screen.getByText('Add rule'));
    const next = onChange.mock.calls[0][0] as { and: PredicateAst[] };
    expect(next.and).toHaveLength(3);
  });

  it('switches a multi-rule set from ALL to ANY (and -> or)', () => {
    const onChange = vi.fn();
    const value: PredicateAst = {
      and: [
        { field: 'a', op: 'eq', value: '1' },
        { field: 'b', op: 'eq', value: '2' },
      ],
    };
    render(<RuleSetBuilder value={value} onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: /ALL/i }));
    fireEvent.click(screen.getByText(/ANY/i));
    const next = onChange.mock.calls.at(-1)?.[0] as { or?: PredicateAst[] };
    expect(next.or).toBeDefined();
    expect(next.or).toHaveLength(2);
  });

  it('renders a Combobox driven by fieldOptions when provided', () => {
    const onChange = vi.fn();
    const value: LeafPredicate = { field: '', op: 'eq', value: '' };
    render(
      <RuleSetBuilder
        value={value}
        onChange={onChange}
        fieldOptions={['phone', 'steps.wa.wa_button_id']}
      />,
    );
    // Combobox renders the placeholder as the trigger label; clicking it
    // opens the upstream-field options.
    fireEvent.click(screen.getByText('payload field'));
    expect(screen.getByText('steps.wa.wa_button_id')).toBeInTheDocument();
  });

  it('renders the leaf VALUE as an outcome dropdown (no free-text) when outcomeOptions are provided', () => {
    const onChange = vi.fn();
    const value: LeafPredicate = { field: 'outcome', op: 'eq', value: '' };
    render(
      <RuleSetBuilder
        value={value}
        onChange={onChange}
        outcomeOptions={[
          { canonical: 'answered', providerLabel: 'bolna_answered', sourceNodeId: 'v1', provider: 'bolna' },
          { canonical: 'no-answer', providerLabel: 'bolna_rnr', sourceNodeId: 'v1', provider: 'bolna' },
        ]}
      />,
    );
    // The free-text value input is gone in favour of the outcome dropdown.
    expect(screen.queryByPlaceholderText('value')).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('Select an outcome'));
    // Options show "<canonical> · <providerLabel>".
    expect(screen.getByText('answered · bolna_answered')).toBeInTheDocument();
    expect(screen.getByText('no-answer · bolna_rnr')).toBeInTheDocument();
  });

  it('stores the canonical outcome value (not the provider label) when selected', () => {
    const onChange = vi.fn();
    const value: LeafPredicate = { field: 'outcome', op: 'eq', value: '' };
    render(
      <RuleSetBuilder
        value={value}
        onChange={onChange}
        outcomeOptions={[
          { canonical: 'answered', providerLabel: 'bolna_answered', sourceNodeId: 'v1', provider: 'bolna' },
        ]}
      />,
    );
    fireEvent.click(screen.getByText('Select an outcome'));
    fireEvent.click(screen.getByText('answered · bolna_answered'));
    const next = onChange.mock.calls.at(-1)?.[0] as LeafPredicate;
    expect(next.value).toBe('answered');
  });
});

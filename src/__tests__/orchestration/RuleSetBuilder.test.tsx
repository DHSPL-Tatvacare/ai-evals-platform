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
    const value: LeafPredicate = { field: 'steps.v1.voice_outcome', op: 'eq', value: '' };
    render(
      <RuleSetBuilder
        value={value}
        onChange={onChange}
        fieldOptions={['steps.v1.voice_outcome']}
        outcomeOptions={[
          { canonical: 'answered', providerLabel: 'bolna_answered', sourceNodeId: 'v1', provider: 'bolna', field: 'steps.v1.voice_outcome' },
          { canonical: 'no_answer', providerLabel: 'bolna_rnr', sourceNodeId: 'v1', provider: 'bolna', field: 'steps.v1.voice_outcome' },
        ]}
      />,
    );
    // The free-text value input is gone in favour of the outcome dropdown.
    expect(screen.queryByPlaceholderText('value')).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('Select an outcome'));
    // Canonical is the clear label; the provider raw label is muted right-aligned meta.
    expect(screen.getByText('answered')).toBeInTheDocument();
    expect(screen.getByText('bolna_answered')).toBeInTheDocument();
    expect(screen.getByText('no_answer')).toBeInTheDocument();
    expect(screen.getByText('bolna_rnr')).toBeInTheDocument();
  });

  it('keeps a free-text value input for a non-outcome leaf field even when outcomeOptions are present', () => {
    const onChange = vi.fn();
    // A non-outcome field (wa_button_id) compared while an upstream voice
    // outcome exists must stay authorable as free text, not be forced into the
    // outcome dropdown.
    const value: LeafPredicate = {
      field: 'steps.wa.wa_button_id',
      op: 'eq',
      value: '',
    };
    render(
      <RuleSetBuilder
        value={value}
        onChange={onChange}
        fieldOptions={['steps.v1.voice_outcome', 'steps.wa.wa_button_id']}
        outcomeOptions={[
          { canonical: 'answered', providerLabel: 'bolna_answered', sourceNodeId: 'v1', provider: 'bolna', field: 'steps.v1.voice_outcome' },
        ]}
      />,
    );
    expect(screen.getByPlaceholderText('value')).toBeInTheDocument();
    expect(screen.queryByText('Select an outcome')).not.toBeInTheDocument();
  });

  it('shows the outcome dropdown only for the matching producer outcome field', () => {
    const onChange = vi.fn();
    // The leaf field targets the voice producer's outcome path
    // (steps.<sourceNodeId>.voice_outcome) so the dropdown should appear.
    const value: LeafPredicate = {
      field: 'steps.v1.voice_outcome',
      op: 'eq',
      value: '',
    };
    render(
      <RuleSetBuilder
        value={value}
        onChange={onChange}
        fieldOptions={['steps.v1.voice_outcome']}
        outcomeOptions={[
          { canonical: 'answered', providerLabel: 'bolna_answered', sourceNodeId: 'v1', provider: 'bolna', field: 'steps.v1.voice_outcome' },
        ]}
      />,
    );
    expect(screen.queryByPlaceholderText('value')).not.toBeInTheDocument();
    expect(screen.getByText('Select an outcome')).toBeInTheDocument();
  });

  it('makes a messaging producer outcome pickable at its own declared field (wa_status)', () => {
    const onChange = vi.fn();
    // Messaging declares its outcome bag field (wa_status), exactly like voice
    // declares voice_outcome. A leaf targeting that contract path must surface
    // the same canonical-outcome dropdown — provider-agnostic by contract.
    const value: LeafPredicate = { field: 'steps.wa1.wa_status', op: 'eq', value: '' };
    render(
      <RuleSetBuilder
        value={value}
        onChange={onChange}
        fieldOptions={['steps.wa1.wa_status']}
        outcomeOptions={[
          { canonical: 'delivered', providerLabel: 'wa_delivered', sourceNodeId: 'wa1', provider: 'wati', field: 'steps.wa1.wa_status' },
          { canonical: 'replied', providerLabel: 'wa_replied', sourceNodeId: 'wa1', provider: 'wati', field: 'steps.wa1.wa_status' },
        ]}
      />,
    );
    expect(screen.queryByPlaceholderText('value')).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('Select an outcome'));
    expect(screen.getByText('delivered')).toBeInTheDocument();
    expect(screen.getByText('wa_delivered')).toBeInTheDocument();
    expect(screen.getByText('replied')).toBeInTheDocument();
  });

  it('keeps free text for a leaf targeting a path the producer never declares', () => {
    const onChange = vi.fn();
    // The messaging producer declares its outcome at steps.wa1.wa_status. A leaf
    // targeting a DIFFERENT path (here the voice-shaped steps.wa1.voice_outcome,
    // which this producer never writes) must NOT be forced into the outcome
    // dropdown — eligibility binds to the contract-declared field, not a guess.
    const value: LeafPredicate = {
      field: 'steps.wa1.voice_outcome',
      op: 'eq',
      value: '',
    };
    render(
      <RuleSetBuilder
        value={value}
        onChange={onChange}
        fieldOptions={['steps.wa1.wa_status', 'steps.wa1.wa_button_id']}
        outcomeOptions={[
          { canonical: 'replied', providerLabel: 'wa_replied', sourceNodeId: 'wa1', provider: 'wati', field: 'steps.wa1.wa_status' },
        ]}
      />,
    );
    expect(screen.getByPlaceholderText('value')).toBeInTheDocument();
    expect(screen.queryByText('Select an outcome')).not.toBeInTheDocument();
  });

  it('stores the canonical outcome value (not the provider label) when selected', () => {
    const onChange = vi.fn();
    const value: LeafPredicate = { field: 'steps.v1.voice_outcome', op: 'eq', value: '' };
    render(
      <RuleSetBuilder
        value={value}
        onChange={onChange}
        fieldOptions={['steps.v1.voice_outcome']}
        outcomeOptions={[
          { canonical: 'answered', providerLabel: 'bolna_answered', sourceNodeId: 'v1', provider: 'bolna', field: 'steps.v1.voice_outcome' },
        ]}
      />,
    );
    fireEvent.click(screen.getByText('Select an outcome'));
    fireEvent.click(screen.getByText('answered'));
    const next = onChange.mock.calls.at(-1)?.[0] as LeafPredicate;
    expect(next.value).toBe('answered');
  });
});

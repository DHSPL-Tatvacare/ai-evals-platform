import { useState } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { EvaluatorPickerList } from './EvaluatorPickerList';
import type { EvaluatorDefinition } from '@/types';

function makeEvaluator(over: Partial<EvaluatorDefinition>): EvaluatorDefinition {
  return {
    id: 'e1',
    name: 'Quality',
    prompt: 'Assess the call quality',
    modelId: 'm',
    outputSchema: [],
    appId: 'voice-rx',
    ...over,
  } as EvaluatorDefinition;
}

const EVALUATORS: EvaluatorDefinition[] = [
  makeEvaluator({ id: 'e1', name: 'Empathy', prompt: 'Rate empathy' }),
  makeEvaluator({ id: 'e2', name: 'Compliance', prompt: 'Check disclosures' }),
];

function Harness({ initial = new Set<string>() }: { initial?: Set<string> }) {
  const [selected, setSelected] = useState<Set<string>>(initial);
  return (
    <EvaluatorPickerList
      evaluators={EVALUATORS}
      selectedIds={selected}
      onToggle={(id) =>
        setSelected((prev) => {
          const next = new Set(prev);
          if (next.has(id)) next.delete(id);
          else next.add(id);
          return next;
        })
      }
      onSelectAll={() => setSelected(new Set(EVALUATORS.map((e) => e.id)))}
      onSelectNone={() => setSelected(new Set())}
    />
  );
}

describe('EvaluatorPickerList', () => {
  it('renders a row per evaluator', () => {
    render(<Harness />);
    expect(screen.getByText('Empathy')).toBeInTheDocument();
    expect(screen.getByText('Compliance')).toBeInTheDocument();
  });

  it('filters rows by the search query', () => {
    render(<Harness />);
    fireEvent.change(screen.getByPlaceholderText('Search evaluators...'), {
      target: { value: 'empathy' },
    });
    expect(screen.getByText('Empathy')).toBeInTheDocument();
    expect(screen.queryByText('Compliance')).not.toBeInTheDocument();
  });

  it('All selects every checkbox; None clears them', () => {
    render(<Harness />);
    const boxes = () => screen.getAllByRole('checkbox') as HTMLInputElement[];
    fireEvent.click(screen.getByText('All'));
    expect(boxes().every((b) => b.checked)).toBe(true);
    fireEvent.click(screen.getByText('None'));
    expect(boxes().some((b) => b.checked)).toBe(false);
  });

  it('shows the generic empty-state copy when there are no evaluators', () => {
    render(
      <EvaluatorPickerList
        evaluators={[]}
        selectedIds={new Set()}
        onToggle={() => {}}
        onSelectAll={() => {}}
        onSelectNone={() => {}}
      />,
    );
    expect(screen.getByText('No evaluators found for this app.')).toBeInTheDocument();
  });
});

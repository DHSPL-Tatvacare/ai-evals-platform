import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { SpecialistGroup, type SpecialistPart } from './SpecialistGroup';
import type { SubtaskPart } from '../generated/sherlockContract';

const SHIMMER = '[class*="chat-widget-shimmer"]';

function runningSubtask(id: string, specialist: string): SubtaskPart {
  return {
    id,
    seq: 1,
    type: 'subtask',
    chat_session_id: 'sess',
    created_at: 0,
    specialist,
    call_id: `call-${id}`,
    brief: { question: 'q', scope: { tenant_id: 't', app_id: 'a', user_id: 'u' } },
    state: { status: 'running', started_at: 1 },
  };
}

describe('SpecialistGroup single-shimmer invariant', () => {
  it('shimmers exactly one row when two specialists run concurrently', () => {
    const parts: SpecialistPart[] = [
      runningSubtask('s1', 'query_synthesis_specialist'),
      runningSubtask('s2', 'data_specialist'),
    ];
    const { container } = render(<SpecialistGroup parts={parts} settled={false} />);
    expect(container.querySelectorAll(SHIMMER).length).toBe(1);
  });

  it('renders persona display labels and drops the article for a single specialist', () => {
    const part = runningSubtask('s1', 'query_synthesis_specialist');
    const settledSubtask: SubtaskPart = {
      ...part,
      state: { status: 'completed', started_at: 1, ended_at: 2, result: { status: 'ok', row_count: 0, sql: null } },
    };
    render(<SpecialistGroup parts={[settledSubtask]} settled />);
    expect(screen.getByText('Consulted Titan Metis, the planner')).toBeTruthy();
  });

  it('keeps exactly one shimmer (on the header) when collapsed while running', () => {
    const parts: SpecialistPart[] = [runningSubtask('s1', 'data_specialist')];
    const { container, getByRole } = render(<SpecialistGroup parts={parts} settled={false} />);
    // expanded: one row shimmers
    expect(container.querySelectorAll(SHIMMER).length).toBe(1);
    // collapse — rows hide; the only visible live line (header) must still shimmer
    fireEvent.click(getByRole('button', { expanded: true }));
    expect(container.querySelectorAll(SHIMMER).length).toBe(1);
  });
});

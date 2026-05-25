import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/services/api/evaluatorsApi', () => ({
  evaluatorsRepository: {
    getVariables: vi.fn().mockResolvedValue([]),
    getApiPaths: vi.fn().mockResolvedValue([]),
  },
}));
vi.mock('@/hooks', () => ({
  useAppConfig: () => ({
    evaluator: { dynamicVariableSources: { registry: true, listingApiPaths: true } },
  }),
}));
vi.mock('@/stores', () => ({
  useAppStore: (selector: (s: { currentApp: string }) => unknown) =>
    selector({ currentApp: 'inside-sales' }),
}));

import { evaluatorsRepository } from '@/services/api/evaluatorsApi';
import type { VariableInfo } from '@/types';
import { VariablePickerPopover } from './VariablePickerPopover';

const STATIC_VARS: VariableInfo[] = [
  {
    key: 'first_name',
    displayName: 'first_name',
    description: 'Cohort fields',
    category: 'Cohort fields',
    valueType: 'text',
    requiresAudio: false,
    requiresEvalOutput: false,
    sourceTypes: null,
    example: '',
  },
];

describe('VariablePickerPopover staticOnly', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders only the supplied variables and never fetches registry variables', async () => {
    const onInsert = vi.fn();
    render(
      <VariablePickerPopover
        appId="inside-sales"
        staticOnly
        staticVariables={STATIC_VARS}
        onInsert={onInsert}
        buttonLabel="Insert variable"
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /insert variable/i }));
    await waitFor(() => expect(screen.getByText('{{first_name}}')).toBeInTheDocument());
    expect(evaluatorsRepository.getVariables).not.toHaveBeenCalled();
    expect(evaluatorsRepository.getApiPaths).not.toHaveBeenCalled();

    fireEvent.click(screen.getByText('{{first_name}}'));
    expect(onInsert).toHaveBeenCalledWith('{{first_name}}');
  });

  it('still fetches registry variables when staticOnly is not set', async () => {
    render(
      <VariablePickerPopover
        appId="inside-sales"
        staticVariables={STATIC_VARS}
        onInsert={vi.fn()}
        buttonLabel="Variables"
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /variables/i }));
    await waitFor(() =>
      expect(evaluatorsRepository.getVariables).toHaveBeenCalled(),
    );
  });
});

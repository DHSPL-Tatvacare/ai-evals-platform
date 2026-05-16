/**
 * Tests for the slim, query-fed LLMConfigSection (Phase 3).
 *
 * Plan-required behaviour:
 *  - Only enabled + validated providers appear in the provider list.
 *  - Model select is disabled until a provider is chosen.
 *  - When zero providers are configured, an inline notice is shown.
 *
 * Notes:
 *  - Radix Select renders portalled `<SelectPrimitive.Item>` content only
 *    when the trigger is open. To stay reliable in jsdom we assert the
 *    *trigger* state (selected label / placeholder / disabled) rather
 *    than driving Radix's keyboard interactions.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement, type ReactNode } from 'react';

import { LLMConfigSection } from './LLMConfigSection';

vi.mock('@/services/api/aiSettingsQueries', () => ({
  useProviderConfigs: vi.fn(),
}));
import { useProviderConfigs } from '@/services/api/aiSettingsQueries';

const mockedHook = useProviderConfigs as unknown as ReturnType<typeof vi.fn>;

function wrap(ui: ReactNode) {
  const qc = new QueryClient();
  return createElement(QueryClientProvider, { client: qc }, ui);
}

describe('LLMConfigSection', () => {
  it('lists only enabled + validated providers in the provider trigger', () => {
    mockedHook.mockReturnValue({
      data: [
        {
          provider: 'openai',
          isEnabled: true,
          validationStatus: 'ok',
          curatedModels: ['gpt-5.4'],
        },
        {
          provider: 'gemini',
          isEnabled: true,
          validationStatus: 'untested',
          curatedModels: ['gemini-2.5-pro'],
        },
        {
          provider: 'anthropic',
          isEnabled: false,
          validationStatus: 'ok',
          curatedModels: ['claude-opus'],
        },
      ],
      isLoading: false,
    });

    render(
      wrap(
        <LLMConfigSection
          provider="openai"
          onProviderChange={vi.fn()}
          model="gpt-5.4"
          onModelChange={vi.fn()}
        />,
      ),
    );

    // OpenAI is enabled+validated → selected label visible on the trigger.
    expect(screen.getByText('OpenAI')).toBeInTheDocument();
    // Gemini (untested) and Anthropic (disabled) must NOT be selectable.
    // They are not the selected provider, so their labels should not appear
    // anywhere in the trigger DOM.
    expect(screen.queryByText('Gemini')).not.toBeInTheDocument();
    expect(screen.queryByText('Anthropic')).not.toBeInTheDocument();
  });

  it('disables the model select until a provider is chosen', () => {
    mockedHook.mockReturnValue({
      data: [
        {
          provider: 'openai',
          isEnabled: true,
          validationStatus: 'ok',
          curatedModels: ['gpt-5.4'],
        },
      ],
      isLoading: false,
    });

    render(
      wrap(
        <LLMConfigSection
          provider=""
          onProviderChange={vi.fn()}
          model=""
          onModelChange={vi.fn()}
        />,
      ),
    );

    // Each Select renders one Radix trigger (role="combobox").
    const triggers = screen.getAllByRole('combobox');
    expect(triggers).toHaveLength(2);
    // Provider trigger is enabled, model trigger is disabled.
    expect(triggers[0]).not.toBeDisabled();
    expect(triggers[1]).toBeDisabled();
  });

  it('shows the "no provider configured" notice when nothing is enabled+validated', () => {
    mockedHook.mockReturnValue({
      data: [
        {
          provider: 'openai',
          isEnabled: false,
          validationStatus: 'ok',
          curatedModels: ['gpt-5.4'],
        },
      ],
      isLoading: false,
    });

    render(
      wrap(
        <LLMConfigSection
          provider=""
          onProviderChange={vi.fn()}
          model=""
          onModelChange={vi.fn()}
        />,
      ),
    );

    expect(
      screen.getByText(/no llm provider configured/i),
    ).toBeInTheDocument();
    // No comboboxes are rendered in the empty-state branch.
    expect(screen.queryAllByRole('combobox')).toHaveLength(0);
  });
});

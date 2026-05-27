import { render } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { LLMProviderLogo } from './LLMProviderLogo';
import {
  LLM_PROVIDER_LOGOS,
  LLM_PROVIDER_LOGOS_DARK,
} from '@/constants/llmProviders';

function setTheme(theme: 'light' | 'dark') {
  document.documentElement.setAttribute('data-theme', theme);
}

describe('LLMProviderLogo', () => {
  afterEach(() => {
    document.documentElement.removeAttribute('data-theme');
  });

  it('renders the light logo for sarvam in light mode', () => {
    setTheme('light');
    const { container } = render(<LLMProviderLogo provider="sarvam" />);
    const img = container.querySelector('img');
    expect(img?.getAttribute('src')).toBe(LLM_PROVIDER_LOGOS.sarvam);
    expect(img?.getAttribute('alt')).toMatch(/Sarvam/i);
  });

  it('swaps to the dark logo for sarvam in dark mode', () => {
    setTheme('dark');
    const { container } = render(<LLMProviderLogo provider="sarvam" />);
    const img = container.querySelector('img');
    expect(img?.getAttribute('src')).toBe(LLM_PROVIDER_LOGOS_DARK.sarvam);
  });

  it('uses the same logo in both themes for a provider with no dark variant', () => {
    setTheme('dark');
    const { container } = render(<LLMProviderLogo provider="openai" />);
    const img = container.querySelector('img');
    expect(img?.getAttribute('src')).toBe(LLM_PROVIDER_LOGOS.openai);
  });

  it('honors the size prop', () => {
    const { container } = render(<LLMProviderLogo provider="sarvam" size={28} />);
    const img = container.querySelector('img');
    expect(img?.getAttribute('width')).toBe('28');
    expect(img?.getAttribute('height')).toBe('28');
  });
});

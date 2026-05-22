import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ConnectionProviderLogo } from './ConnectionProviderLogo';
import { CONNECTION_PROVIDER_LOGOS } from '@/constants/connectionProviders';

describe('ConnectionProviderLogo', () => {
  it('renders the brand <img> for a vendor that has a logo', () => {
    const { container } = render(<ConnectionProviderLogo provider="wati" />);
    const img = container.querySelector('img');
    expect(img).not.toBeNull();
    expect(img?.getAttribute('src')).toBe(CONNECTION_PROVIDER_LOGOS.wati);
    expect(img?.getAttribute('alt')).toMatch(/WATI/i);
  });

  it('falls back to a neutral lucide icon for a vendor with no logo', () => {
    const { container } = render(<ConnectionProviderLogo provider="webhook" />);
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('svg')).not.toBeNull();
  });

  it('falls back for an entirely unknown vendor identifier', () => {
    const { container } = render(<ConnectionProviderLogo provider="totally-unknown" />);
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('svg')).not.toBeNull();
  });

  it('honors the size prop on the rendered image', () => {
    const { container } = render(
      <ConnectionProviderLogo provider="bolna" size={28} />,
    );
    const img = container.querySelector('img');
    expect(img?.getAttribute('width')).toBe('28');
    expect(img?.getAttribute('height')).toBe('28');
  });
});

import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { FileText } from 'lucide-react';
import { Illustration } from './Illustration';
import { EmptyState } from './EmptyState';

describe('Illustration', () => {
  it('resolves a key to its asset src', () => {
    const { container } = render(<Illustration name="notFound" />);
    const img = container.querySelector('img');
    expect(img?.getAttribute('src')).toBe('/illustrations/not-found.webp');
    expect(img?.getAttribute('aria-hidden')).toBe('true');
  });
});

describe('EmptyState illustration', () => {
  it('renders the illustration instead of the icon when illustration is set', () => {
    const { container } = render(
      <EmptyState icon={FileText} illustration="empty" title="Nothing here yet" />,
    );
    const img = container.querySelector('img');
    expect(img?.getAttribute('src')).toBe('/illustrations/empty.webp');
    expect(container.querySelector('svg')).toBeNull();
  });

  it('renders the icon when no illustration is set', () => {
    const { container } = render(<EmptyState icon={FileText} title="Nothing here yet" />);
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('svg')).not.toBeNull();
  });

  it('keeps the icon (ignores illustration) in compact mode', () => {
    const { container } = render(
      <EmptyState icon={FileText} illustration="empty" title="x" compact />,
    );
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('svg')).not.toBeNull();
  });
});

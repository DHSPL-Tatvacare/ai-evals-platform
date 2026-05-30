import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const reducedMotionMock = vi.fn<() => boolean>(() => false);

vi.mock('framer-motion', async (importOriginal) => ({
  ...(await importOriginal<typeof import('framer-motion')>()),
  useReducedMotion: () => reducedMotionMock(),
}));

import { FlowingBorder } from './FlowingBorder';

afterEach(() => {
  reducedMotionMock.mockReturnValue(false);
});

function frame() {
  return screen.getByTestId('flowing-border');
}

describe('FlowingBorder', () => {
  it('renders children regardless of active state', () => {
    render(
      <FlowingBorder active={false}>
        <span>inner</span>
      </FlowingBorder>,
    );
    expect(screen.getByText('inner')).toBeInTheDocument();
  });

  it('idle (active=false) renders no animated overlay', () => {
    render(
      <FlowingBorder active={false}>
        <span>inner</span>
      </FlowingBorder>,
    );
    expect(frame().dataset.active).toBe('false');
    expect(screen.queryByTestId('flowing-border-overlay')).not.toBeInTheDocument();
  });

  it('active rendering differs from idle — animated conic overlay appears', () => {
    render(
      <FlowingBorder active>
        <span>inner</span>
      </FlowingBorder>,
    );
    expect(frame().dataset.active).toBe('true');
    const overlay = screen.getByTestId('flowing-border-overlay');
    expect(overlay).toBeInTheDocument();
    expect(overlay.dataset.animated).toBe('true');
  });

  it('reduced-motion active renders a static overlay (no travel animation)', () => {
    reducedMotionMock.mockReturnValue(true);
    render(
      <FlowingBorder active>
        <span>inner</span>
      </FlowingBorder>,
    );
    const overlay = screen.getByTestId('flowing-border-overlay');
    expect(overlay).toBeInTheDocument();
    expect(overlay.dataset.animated).toBe('false');
  });

  it('path variant renders an animated SVG perimeter when active', () => {
    render(
      <FlowingBorder active variant="path">
        <span>inner</span>
      </FlowingBorder>,
    );
    const path = screen.getByTestId('flowing-border-path');
    expect(path).toBeInTheDocument();
    expect(path.dataset.animated).toBe('true');
  });

  it('path variant under reduced-motion renders static perimeter', () => {
    reducedMotionMock.mockReturnValue(true);
    render(
      <FlowingBorder active variant="path">
        <span>inner</span>
      </FlowingBorder>,
    );
    const path = screen.getByTestId('flowing-border-path');
    expect(path.dataset.animated).toBe('false');
  });

  it('contains no hex colour literals — tokens only', () => {
    const source = readFileSync(
      join(process.cwd(), 'src/components/ui/FlowingBorder.tsx'),
      'utf8',
    );
    expect(source).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
  });
});

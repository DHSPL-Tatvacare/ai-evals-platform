import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { NodeCard } from './NodeCard';

describe('NodeCard — AI category gradient fill', () => {
  it('paints the canvas icon square + bar with the AI gradient tokens', () => {
    const { container } = render(
      <NodeCard label="AI Agent" category="ai" variant="canvas" />,
    );
    expect(container.querySelector('[style*="--gradient-node-ai"]')).not.toBeNull();
    expect(container.querySelector('[style*="--surface-node-ai"]')).not.toBeNull();
  });

  it('paints the palette tile with the AI gradient tokens', () => {
    const { container } = render(
      <NodeCard label="AI Agent" category="ai" variant="palette" />,
    );
    expect(container.querySelector('[style*="--gradient-node-ai"]')).not.toBeNull();
    expect(container.querySelector('[style*="--surface-node-ai"]')).not.toBeNull();
  });

  it('keeps solid fills for non-ai categories — no gradient bleed', () => {
    const { container } = render(
      <NodeCard label="Send" category="dispatch" variant="canvas" />,
    );
    expect(container.querySelector('[style*="--gradient-node-ai"]')).toBeNull();
  });

  it('outlines the ai canvas card with a gradient (transparent border)', () => {
    const { container } = render(
      <NodeCard label="AI Agent" category="ai" variant="canvas" />,
    );
    const root = container.firstElementChild as HTMLElement;
    expect(root.style.borderColor).toBe('transparent');
  });

  it('keeps the solid accent border on non-ai canvas cards', () => {
    const { container } = render(
      <NodeCard label="Send" category="dispatch" variant="canvas" />,
    );
    const root = container.firstElementChild as HTMLElement;
    expect(root.style.borderColor).not.toBe('transparent');
  });
});

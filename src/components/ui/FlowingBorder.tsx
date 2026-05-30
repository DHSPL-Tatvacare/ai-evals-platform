import { useReducedMotion } from 'framer-motion';
import type { CSSProperties, ReactNode } from 'react';
import { cn } from '@/utils';

interface FlowingBorderProps {
  active: boolean;
  children: ReactNode;
  speed?: string;
  variant?: 'conic' | 'path';
  className?: string;
}

// Scoped keyframes + reduced-motion guard for the flowing border. globals.css
// owns the colour tokens (--gradient-flow-border, --duration-flow-lap) and the
// registered @property --angle; the motion lives here so the primitive is
// self-contained and not coupled to a global keyframe name.
const STYLE_ID = 'flowing-border-keyframes';
const KEYFRAMES = `
@keyframes flowing-border-lap { to { --angle: 360deg; } }
@keyframes flowing-border-dash { to { stroke-dashoffset: -100; } }
`;

function ensureKeyframes(): void {
  if (typeof document === 'undefined') return;
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement('style');
  style.id = STYLE_ID;
  style.textContent = KEYFRAMES;
  document.head.appendChild(style);
}

type FlowVars = CSSProperties & Record<'--flow-lap', string>;

export function FlowingBorder({
  active,
  children,
  speed,
  variant = 'conic',
  className,
}: FlowingBorderProps) {
  const prefersReducedMotion = useReducedMotion();
  const animated = active && !prefersReducedMotion;

  ensureKeyframes();

  const lap = speed ?? 'var(--duration-flow-lap)';

  return (
    <div
      data-testid="flowing-border"
      data-active={active ? 'true' : 'false'}
      className={cn('relative isolate', className)}
      style={{ '--flow-lap': lap } as FlowVars}
    >
      {active && variant === 'conic' && (
        <span
          aria-hidden="true"
          data-testid="flowing-border-overlay"
          data-animated={animated ? 'true' : 'false'}
          className={cn(
            'pointer-events-none absolute inset-0 z-[var(--z-base)] rounded-[inherit] p-px',
            animated && 'flowing-border-overlay--animated',
          )}
          style={{
            background: 'var(--gradient-flow-border)',
            WebkitMask:
              'linear-gradient(var(--bg-primary) 0 0) content-box, linear-gradient(var(--bg-primary) 0 0)',
            WebkitMaskComposite: 'xor',
            mask: 'linear-gradient(var(--bg-primary) 0 0) content-box, linear-gradient(var(--bg-primary) 0 0)',
            maskComposite: 'exclude',
            animation: animated
              ? `flowing-border-lap var(--flow-lap) linear infinite`
              : undefined,
          }}
        />
      )}
      {active && variant === 'path' && (
        <svg
          aria-hidden="true"
          data-testid="flowing-border-path"
          data-animated={animated ? 'true' : 'false'}
          className="pointer-events-none absolute inset-0 z-[var(--z-base)] h-full w-full"
          preserveAspectRatio="none"
        >
          <rect
            x="0.5"
            y="0.5"
            width="calc(100% - 1px)"
            height="calc(100% - 1px)"
            rx="inherit"
            fill="none"
            stroke="var(--color-flow-2)"
            strokeWidth="1.5"
            pathLength={100}
            strokeDasharray="25 75"
            style={{
              animation: animated
                ? `flowing-border-dash var(--flow-lap) linear infinite`
                : undefined,
            }}
          />
        </svg>
      )}
      {children}
    </div>
  );
}

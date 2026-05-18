import { useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';

/**
 * Streaming-border comet for the chat composer.
 *
 * Single-comet sweep around the composer's rounded-rect outline, one
 * full loop per ``cycleMs``. Strictly one comet, never blinking, never
 * resetting midway.
 *
 * Why ``pathLength={1}``: SVG's ``pathLength`` attribute renormalizes
 * stroke-dash math to [0, 1] in path-length units instead of pixels.
 * That means the dash array (``0.3 0.7`` = 30% visible, 70% gap) and
 * the animation target (``strokeDashoffset: -1`` = one full loop) are
 * CONSTANTS — they never depend on the measured perimeter.
 *
 * Earlier versions stored ``perimeter = rect.getTotalLength()`` in
 * state and animated to ``-perimeter``. Every resize (textarea grow,
 * chip toggle, container reflow) re-measured perimeter, the
 * ``animate`` target shifted, and framer-motion restarted the
 * transition — that's the "comet resets midway" bug. Removing the
 * perimeter measurement removes the bug class entirely.
 */

interface ComposerStreamingBorderProps {
  targetRef: React.RefObject<HTMLElement | null>;
  /** ms per full perimeter loop. Lower = faster. */
  cycleMs?: number;
}

export function ComposerStreamingBorder({
  targetRef,
  cycleMs = 1800,
}: ComposerStreamingBorderProps) {
  const [box, setBox] = useState<{ w: number; h: number; r: number } | null>(null);

  useEffect(() => {
    const el = targetRef.current;
    if (!el) return;
    const sync = () => {
      const cs = window.getComputedStyle(el);
      const radius = parseFloat(cs.borderTopLeftRadius || '0') || 0;
      setBox({ w: el.clientWidth, h: el.clientHeight, r: radius });
    };
    sync();
    const ro = new ResizeObserver(sync);
    ro.observe(el);
    return () => ro.disconnect();
  }, [targetRef]);

  if (box === null) return null;

  return (
    <svg
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 h-full w-full overflow-visible"
      width={box.w}
      height={box.h}
    >
      <defs>
        <linearGradient id="composer-comet" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="var(--color-brand-primary)" stopOpacity="0.35" />
          <stop offset="70%" stopColor="var(--color-brand-primary)" stopOpacity="0.85" />
          <stop offset="100%" stopColor="var(--color-brand-primary)" stopOpacity="1" />
        </linearGradient>
      </defs>

      <RectRef
        box={box}
        cycleMs={cycleMs}
      />
    </svg>
  );
}

interface RectRefProps {
  box: { w: number; h: number; r: number };
  cycleMs: number;
}

/**
 * Inner component so the SVG container can re-render on box changes
 * (width/height/radius mirror the composer) while the animated rect
 * stays mounted with stable animation targets. The ``key`` is the
 * box geometry so React swaps the element only when dimensions
 * genuinely change — but the dash/offset targets stay constant in
 * pathLength units, so even on swap there's no mid-cycle restart of
 * an in-progress animation: the new element starts fresh from 0.
 */
function RectRef({ box, cycleMs }: RectRefProps) {
  // Stable ref to a single motion controller across renders. Avoids
  // framer-motion's "target changed" restart on every parent render.
  const rectKey = useRef('rect-singleton').current;

  return (
    <motion.rect
      key={rectKey}
      x={1.5}
      y={1.5}
      width={Math.max(0, box.w - 3)}
      height={Math.max(0, box.h - 3)}
      rx={box.r}
      ry={box.r}
      fill="none"
      stroke="url(#composer-comet)"
      strokeWidth={3}
      strokeLinecap="round"
      // pathLength normalizes the path: dash + offset are now in [0,1]
      // units, INDEPENDENT of the rect's actual perimeter. The values
      // below never change → framer-motion never restarts.
      pathLength={1}
      strokeDasharray="0.3 0.7"
      initial={{ strokeDashoffset: 0 }}
      animate={{ strokeDashoffset: -1 }}
      transition={{
        duration: cycleMs / 1000,
        repeat: Infinity,
        ease: 'linear',
      }}
    />
  );
}

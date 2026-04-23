import { motion } from 'framer-motion';
import { cn } from '@/utils';

interface LoadingStateProps {
  /** Message under the animation. Defaults to "Loading…". Pass empty string to hide. */
  message?: string;
  /** Fills the parent with min-h-full so content centers vertically. Default true. */
  fill?: boolean;
  className?: string;
}

const FRAME = 48;
const GAP = 3;
const DURATION = 3.7;
const TIMES = [0, 0.27, 0.54, 0.81, 1];

// Three split parameters — vertical, top-row horizontal, bottom-row horizontal.
// Values replicated from motion.dev's "Independent transforms" demo: each cycle
// pushes to an extreme, inverts, settles to neutral, and holds briefly. Top and
// bottom rows move on opposite horizontal phase; vy kicks in after the first
// horizontal beat, so x and y read as independent axes.
const VY  = [0.50, 0.65, 0.35, 0.50, 0.50];
const HXT = [0.50, 0.75, 0.25, 0.50, 0.50];
const HXB = [0.50, 0.10, 0.90, 0.50, 0.50];

const x2 = (xs: number[]) => xs.map((v) => +(2 * v).toFixed(4));
const inv2 = (xs: number[]) => xs.map((v) => +(2 * (1 - v)).toFixed(4));

interface CellDef {
  origin: '0% 0%' | '100% 0%' | '0% 100%' | '100% 100%';
  scaleX: number[];
  scaleY: number[];
}

const CELLS: ReadonlyArray<CellDef> = [
  { origin: '0% 0%',     scaleX: x2(HXT),   scaleY: x2(VY) },
  { origin: '100% 0%',   scaleX: inv2(HXT), scaleY: x2(VY) },
  { origin: '0% 100%',   scaleX: x2(HXB),   scaleY: inv2(VY) },
  { origin: '100% 100%', scaleX: inv2(HXB), scaleY: inv2(VY) },
];

/**
 * Unified loading surface — 4 brand-colored cells in a 2×2 grid. Each cell's
 * transform-origin is pinned to its outer corner and scales inward. Three
 * shared split parameters drive all 4 cells in lockstep, so gutters stay
 * perfectly uniform at every frame while x and y read as independent axes.
 */
export function LoadingState({ message = 'Loading…', fill = true, className }: LoadingStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center gap-3',
        fill && 'min-h-full flex-1 py-12',
        className,
      )}
    >
      <div
        className="grid grid-cols-2 grid-rows-2"
        style={{ width: FRAME, height: FRAME, gap: GAP }}
        aria-label="Loading"
        role="status"
      >
        {CELLS.map((c, idx) => (
          <motion.span
            key={idx}
            className="block rounded-[2px] bg-[var(--color-brand-primary)]"
            style={{ transformOrigin: c.origin }}
            initial={false}
            animate={{ scaleX: c.scaleX, scaleY: c.scaleY }}
            transition={{
              duration: DURATION,
              times: TIMES,
              ease: 'easeInOut',
              repeat: Infinity,
              repeatType: 'loop',
            }}
          />
        ))}
      </div>
      {message && (
        <p className="text-xs text-[var(--text-muted)] tracking-wide">{message}</p>
      )}
    </div>
  );
}

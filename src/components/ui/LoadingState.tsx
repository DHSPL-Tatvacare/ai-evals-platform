import { motion } from 'framer-motion';
import { cn } from '@/utils';

interface LoadingStateProps {
  /** Message under the animation. Defaults to "Loading…". Pass empty string to hide. */
  message?: string;
  /** Fills the parent with min-h-full so content centers vertically. Default true. */
  fill?: boolean;
  className?: string;
}

/**
 * Unified loading surface — centered horizontally + vertically, animated 4
 * shape-shifting blocks, optional message. Canonical screen loader for the
 * platform.
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
        className="relative h-12 w-12"
        aria-label="Loading"
        role="status"
      >
        {QUADRANTS.map((q, i) => (
          <motion.span
            key={i}
            className="absolute block rounded-[3px]"
            style={{
              top: q.anchorTop,
              bottom: q.anchorBottom,
              left: q.anchorLeft,
              right: q.anchorRight,
              background: q.color,
            }}
            animate={{
              width: q.widthKeyframes,
              height: q.heightKeyframes,
            }}
            transition={{
              duration: 2.8,
              repeat: Infinity,
              ease: [0.45, 0, 0.3, 1],
              delay: i * 0.35,
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

// Each block anchors to its corner (so width/height grow/shrink from that
// corner, not from the center) and independently morphs width and height at
// different phases. The overall 48×48 container stays constant — blocks shift
// relative proportions within it without rotating or repositioning.
const QUADRANTS = [
  {
    // top-left
    anchorTop: 0,
    anchorLeft: 0,
    anchorBottom: 'auto' as const,
    anchorRight: 'auto' as const,
    color: 'var(--color-brand-primary)',
    widthKeyframes: ['22px', '18px', '26px', '20px', '22px'],
    heightKeyframes: ['22px', '26px', '18px', '24px', '22px'],
  },
  {
    // top-right
    anchorTop: 0,
    anchorRight: 0,
    anchorBottom: 'auto' as const,
    anchorLeft: 'auto' as const,
    color: 'var(--color-accent-indigo)',
    widthKeyframes: ['20px', '26px', '18px', '24px', '20px'],
    heightKeyframes: ['24px', '20px', '26px', '18px', '24px'],
  },
  {
    // bottom-left
    anchorBottom: 0,
    anchorLeft: 0,
    anchorTop: 'auto' as const,
    anchorRight: 'auto' as const,
    color: 'var(--color-accent-teal)',
    widthKeyframes: ['24px', '18px', '22px', '26px', '24px'],
    heightKeyframes: ['20px', '24px', '20px', '18px', '20px'],
  },
  {
    // bottom-right
    anchorBottom: 0,
    anchorRight: 0,
    anchorTop: 'auto' as const,
    anchorLeft: 'auto' as const,
    color: 'var(--color-accent-amber)',
    widthKeyframes: ['18px', '22px', '26px', '20px', '18px'],
    heightKeyframes: ['22px', '22px', '20px', '26px', '22px'],
  },
];

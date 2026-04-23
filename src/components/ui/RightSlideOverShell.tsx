import { type CSSProperties, type ReactNode, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { cn } from '@/utils';
import { useRightOverlay } from '@/hooks';

// Springs are authored, not configured. This one is tuned to match the
// established wizard-panel feel: the panel arrives with a small overshoot
// that lands softly, communicating "this is a working surface, not a
// transient popover". Matching WizardOverlay keeps every right-edge
// surface feeling like part of the same chassis.
const PANEL_SLIDE_SPRING = { type: 'spring' as const, stiffness: 380, damping: 38, mass: 0.9 };

// Backdrop is a simple fade — the interesting motion belongs to the panel.
// A short cubic ease matches Modal.tsx, so overlay backdrops feel the same
// regardless of which surface is opening.
const BACKDROP_FADE = { duration: 0.2, ease: [0.22, 1, 0.36, 1] as [number, number, number, number] };

interface RightSlideOverShellProps {
  isOpen: boolean;
  /** Invoked on backdrop click (when enabled) and as the default escape handler. */
  onClose: () => void;
  /** Override escape-key handling. Defaults to onClose. Used by surfaces that need a
   *  confirm-before-close flow (e.g. unsaved-changes dialog) to intercept escape. */
  onEscape?: () => void;
  /** DOM id of the element that labels the overlay (heading); wired into aria-labelledby. */
  labelledBy?: string;
  /** Panel width + max-width classes. Defaults to the medium overlay token. */
  widthClassName?: string;
  /** Outer wrapper z-index class. Default is the overlay layer; nested overlays
   *  (opened from inside another overlay) should pass the dropdown layer. */
  zIndexClassName?: string;
  /** Panel background class. Defaults to --bg-elevated; a few surfaces use --bg-primary. */
  panelClassName?: string;
  /** Backdrop class. Defaults to --bg-overlay with a light blur. */
  backdropClassName?: string;
  /** Whether clicking the backdrop fires onClose. Default true. */
  closeOnBackdropClick?: boolean;
  /** Inline style applied to the panel. Use this for pixel-based widths that can't
   *  be expressed as a Tailwind class (e.g. a dynamic prop). */
  panelStyle?: CSSProperties;
  children: ReactNode;
}

/**
 * Chassis for every right-edge slide-over in the app. Owns:
 *  - Portal to document.body (so stacking order can't be clobbered by ancestor CSS)
 *  - Backdrop fade + panel spring via framer-motion (AnimatePresence drives mount/unmount)
 *  - Body scroll lock while open
 *  - useRightOverlay wiring (FAB hide, stacked escape, focus restoration, ARIA)
 *  - useReducedMotion honoured: backdrop + panel collapse to instant when requested
 *
 * Consumers own their own header/body/footer markup. The shell is deliberately
 * unopinionated about layout inside the panel so surfaces keep full design control.
 */
export function RightSlideOverShell({
  isOpen,
  onClose,
  onEscape,
  labelledBy,
  widthClassName = 'w-[var(--overlay-width-md)] max-w-[85vw]',
  zIndexClassName = 'z-[var(--z-overlay)]',
  panelClassName = 'bg-[var(--bg-elevated)]',
  backdropClassName = 'bg-[var(--bg-overlay)] backdrop-blur-sm',
  closeOnBackdropClick = true,
  panelStyle,
  children,
}: RightSlideOverShellProps) {
  const prefersReducedMotion = useReducedMotion();
  const ariaProps = useRightOverlay(isOpen, {
    onClose: onEscape ?? onClose,
    labelledBy,
  });

  useEffect(() => {
    if (!isOpen) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previous;
    };
  }, [isOpen]);

  const backdropTransition = prefersReducedMotion ? { duration: 0 } : BACKDROP_FADE;
  const panelTransition = prefersReducedMotion ? { duration: 0 } : PANEL_SLIDE_SPRING;

  return createPortal(
    <AnimatePresence>
      {isOpen && (
        <div className={cn('fixed inset-0 flex', zIndexClassName)}>
          <motion.div
            className={cn('absolute inset-0', backdropClassName)}
            onClick={closeOnBackdropClick ? onClose : undefined}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={backdropTransition}
          />

          <motion.div
            {...ariaProps}
            style={panelStyle}
            className={cn(
              'ml-auto relative z-10 h-full shadow-2xl overflow-hidden flex flex-col',
              widthClassName,
              panelClassName,
            )}
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={panelTransition}
          >
            {children}
          </motion.div>
        </div>
      )}
    </AnimatePresence>,
    document.body,
  );
}

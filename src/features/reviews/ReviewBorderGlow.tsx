import { AnimatePresence, motion } from 'framer-motion';
import { useReviewModeStore } from '@/stores/reviewModeStore';

export function ReviewBorderGlow() {
  const active = useReviewModeStore((s) => s.active);

  return (
    <AnimatePresence>
      {active && (
        <motion.div
          key="review-border-glow"
          className="review-border-glow"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.4 }}
          style={{
            position: 'fixed',
            inset: 0,
            pointerEvents: 'none',
            zIndex: 'var(--z-overlay)',
          }}
        />
      )}
    </AnimatePresence>
  );
}

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
          initial={{ opacity: 0, scale: 1.04 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.98, filter: 'blur(6px)' }}
          transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
          style={{
            position: 'absolute',
            inset: 0,
            pointerEvents: 'none',
            zIndex: 'var(--z-overlay)',
          }}
        />
      )}
    </AnimatePresence>
  );
}

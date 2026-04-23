import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Search, X } from 'lucide-react';
import { cn } from '@/utils';

interface PageHeaderSearchProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  label?: string;
  className?: string;
  expandedWidth?: number;
}

const SPRING_TRANSITION = {
  type: 'spring',
  stiffness: 420,
  damping: 32,
  mass: 0.8,
} as const;

export function PageHeaderSearch({
  value,
  onChange,
  placeholder = 'Search…',
  label = 'Search',
  className,
  expandedWidth = 220,
}: PageHeaderSearchProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(value.trim().length > 0);
  const expanded = open || value.trim().length > 0;

  useEffect(() => {
    if (expanded) {
      window.requestAnimationFrame(() => {
        inputRef.current?.focus();
      });
    }
  }, [expanded]);

  const collapseIfEmpty = () => {
    if (value.trim().length === 0) {
      setOpen(false);
    }
  };

  const handleDismiss = () => {
    if (value.trim().length > 0) {
      onChange('');
      inputRef.current?.focus();
      return;
    }
    setOpen(false);
  };

  return (
    <motion.div
      initial={false}
      animate={{ width: expanded ? expandedWidth : 28 }}
      transition={SPRING_TRANSITION}
      className={cn('overflow-hidden', className)}
    >
      <div className="flex h-7 items-center rounded-md border border-[var(--border-default)] bg-[var(--bg-secondary)] text-[var(--text-secondary)]">
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md transition-colors hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-accent)]"
          aria-label={label}
          title={label}
        >
          <Search className="h-3.5 w-3.5" />
        </button>

        <AnimatePresence initial={false}>
          {expanded ? (
            <motion.div
              initial={{ opacity: 0, x: 8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 8 }}
              transition={{ duration: 0.14, ease: 'easeOut' }}
              className="flex min-w-0 flex-1 items-center pr-1"
            >
              <input
                ref={inputRef}
                type="text"
                value={value}
                onChange={(event) => onChange(event.target.value)}
                onBlur={collapseIfEmpty}
                onKeyDown={(event) => {
                  if (event.key === 'Escape') {
                    event.preventDefault();
                    handleDismiss();
                  }
                }}
                placeholder={placeholder}
                aria-label={label}
                className="h-7 min-w-0 flex-1 bg-transparent pr-1 text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none"
              />
              <button
                type="button"
                onMouseDown={(event) => event.preventDefault()}
                onClick={handleDismiss}
                className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-[var(--text-muted)] transition-colors hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-accent)]"
                aria-label={value.trim().length > 0 ? `Clear ${label.toLowerCase()}` : `Close ${label.toLowerCase()}`}
                title={value.trim().length > 0 ? 'Clear search' : 'Close search'}
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </motion.div>
          ) : null}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}

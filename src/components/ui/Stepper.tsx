import { Check } from 'lucide-react';

import { cn } from '@/utils/cn';

export type StepState = 'done' | 'current' | 'locked';

export interface StepperStep<T extends string> {
  value: T;
  label: string;
  state: StepState;
}

interface StepperProps<T extends string> {
  steps: StepperStep<T>[];
  onSelect: (value: T) => void;
  className?: string;
  'aria-label'?: string;
}

/** Horizontal gated stepper. Locked steps are muted and not clickable; done shows a check,
 *  current is brand-highlighted. The narrative + navigation for a setup lifecycle. */
export function Stepper<T extends string>({
  steps,
  onSelect,
  className,
  'aria-label': ariaLabel,
}: StepperProps<T>) {
  return (
    <div role="tablist" aria-label={ariaLabel} className={cn('flex items-center gap-2', className)}>
      {steps.map((step, i) => {
        const locked = step.state === 'locked';
        const current = step.state === 'current';
        const done = step.state === 'done';
        return (
          <div key={step.value} className="flex items-center gap-2">
            <button
              type="button"
              role="tab"
              aria-selected={current}
              disabled={locked}
              onClick={() => onSelect(step.value)}
              className={cn(
                'flex items-center gap-2 rounded-md px-3 py-1.5 text-[13px] font-medium transition-colors',
                locked
                  ? 'cursor-not-allowed text-[var(--text-muted)]'
                  : current
                    ? 'bg-[var(--surface-brand-subtle)] text-[var(--text-brand)]'
                    : 'text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)] hover:text-[var(--text-primary)]',
              )}
            >
              <span
                className={cn(
                  'flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold',
                  done
                    ? 'bg-[var(--color-success)] text-[var(--text-inverse)]'
                    : current
                      ? 'bg-[var(--text-brand)] text-[var(--text-inverse)]'
                      : 'border border-[var(--border-default)] text-[var(--text-muted)]',
                )}
              >
                {done ? <Check className="h-3 w-3" /> : i + 1}
              </span>
              <span>{step.label}</span>
            </button>
            {i < steps.length - 1 ? (
              <span className="h-px w-6 bg-[var(--border-default)]" aria-hidden="true" />
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

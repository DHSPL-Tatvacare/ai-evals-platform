import type { ReactNode } from 'react';

import { cn } from '@/utils';

interface WizardStepLayoutProps {
  eyebrow?: string;
  title: string;
  description: string;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
}

interface WizardSectionProps {
  title?: string;
  description?: string;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
  contentClassName?: string;
}

interface WizardFieldRowProps {
  title: string;
  description: string;
  control: ReactNode;
  className?: string;
  controlClassName?: string;
}

interface WizardMetricProps {
  label: string;
  value: string | number;
  className?: string;
}

export function WizardStepLayout({
  children,
  className,
}: WizardStepLayoutProps) {
  return (
    <div
      className={cn(
        'space-y-0 [&>*]:py-4 [&>*:first-child]:pt-0 [&>*:last-child]:pb-0 [&>*+*]:border-t [&>*+*]:border-[var(--border-subtle)]',
        className,
      )}
    >
      {children}
    </div>
  );
}

export function WizardSection({
  title,
  description,
  aside,
  children,
  className,
  contentClassName,
}: WizardSectionProps) {
  return (
    <section className={cn('space-y-3', className)}>
      {(title || description || aside) && (
        <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
          <div className="space-y-1">
            {title && (
              <h4 className="text-[14px] font-semibold text-[var(--text-primary)]">
                {title}
              </h4>
            )}
            {description && (
              <p className="max-w-2xl text-[12px] leading-5 text-[var(--text-muted)]">
                {description}
              </p>
            )}
          </div>
          {aside && <div className="shrink-0">{aside}</div>}
        </div>
      )}

      <div className={cn('space-y-4', contentClassName)}>
        {children}
      </div>
    </section>
  );
}

export function WizardFieldRow({
  title,
  description,
  control,
  className,
  controlClassName,
}: WizardFieldRowProps) {
  return (
    <div
      className={cn(
        'grid items-start gap-2.5 md:grid-cols-[minmax(0,1.35fr)_minmax(260px,1fr)] md:gap-4',
        className,
      )}
    >
      <div className="space-y-1">
        <h5 className="text-[13px] font-medium text-[var(--text-primary)]">{title}</h5>
        <p className="text-[12px] leading-5 text-[var(--text-muted)]">{description}</p>
      </div>
      <div className={cn('w-full md:justify-self-stretch', controlClassName)}>{control}</div>
    </div>
  );
}

export function WizardMetric({ label, value, className }: WizardMetricProps) {
  return (
    <div
      className={cn(
        'rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-primary)]/65 px-3 py-2',
        className,
      )}
    >
      <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--text-muted)]">
        {label}
      </p>
      <p className="mt-1 text-[15px] font-semibold tracking-[-0.02em] text-[var(--text-primary)]">
        {value}
      </p>
    </div>
  );
}

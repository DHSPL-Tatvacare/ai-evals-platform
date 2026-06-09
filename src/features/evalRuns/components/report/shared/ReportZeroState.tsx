import type { CSSProperties, ReactNode } from 'react';
import { Sparkles } from 'lucide-react';

import { Button } from '@/components/ui';
import { cn } from '@/utils';
import type { ReportConfigSummary } from '@/types';

interface ReportVariantTheme {
  accent: string;
  accentMuted: string;
}

// Brand a new documentVariant by adding an entry here; unknown variants fall back to the brand default.
const REPORT_VARIANT_THEMES: Record<string, ReportVariantTheme> = {
  'kaira-run-v1': { accent: 'var(--color-accent-teal)', accentMuted: 'var(--surface-success)' },
  'inside-sales-run-v1': { accent: 'var(--color-accent-purple)', accentMuted: 'var(--surface-brand-subtle)' },
  'voice-rx-run-v1': { accent: 'var(--color-error)', accentMuted: 'var(--surface-error)' },
  'kaira-cross-run-v1': { accent: 'var(--color-accent-teal)', accentMuted: 'var(--surface-success)' },
  'inside-sales-cross-run-v1': { accent: 'var(--color-accent-purple)', accentMuted: 'var(--surface-brand-subtle)' },
  'voice-rx-cross-run-v1': { accent: 'var(--color-error)', accentMuted: 'var(--surface-error)' },
};

function getDocumentVariant(config: ReportConfigSummary | null): string | null {
  const exportConfig = config?.exportConfig;
  if (!exportConfig || typeof exportConfig !== 'object') return null;

  const variant = (exportConfig as Record<string, unknown>).documentVariant;
  return typeof variant === 'string' ? variant : null;
}

function getVariantTheme(config: ReportConfigSummary | null): ReportVariantTheme {
  const variant = getDocumentVariant(config);
  return variant ? REPORT_VARIANT_THEMES[variant] ?? {
    accent: 'var(--color-brand-accent)',
    accentMuted: 'rgba(255,255,255,0.16)',
  } : {
    accent: 'var(--color-brand-accent)',
    accentMuted: 'rgba(255,255,255,0.16)',
  };
}

export interface SectionPreview {
  id: string;
  title: string;
}

// Faded, non-animated mock of a generated report so the empty state previews
// the deliverable instead of leaving a void behind the call-to-action.
function ReportGhostPreview() {
  const block = 'rounded-[var(--radius-default)] bg-[var(--bg-tertiary)]';
  const card = 'rounded-[var(--radius-lg)] border border-[var(--border-subtle)] p-4';
  return (
    <div
      aria-hidden
      className="pointer-events-none absolute inset-0 select-none overflow-hidden p-6 md:p-8"
      style={{
        maskImage: 'linear-gradient(to bottom, black 25%, transparent 92%)',
        WebkitMaskImage: 'linear-gradient(to bottom, black 25%, transparent 92%)',
      }}
    >
      <div className="mx-auto max-w-4xl space-y-5">
        <div className="space-y-2">
          <div className={cn(block, 'h-5 w-48')} />
          <div className={cn(block, 'h-3 w-72')} />
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className={cn(card, 'space-y-2')}>
              <div className={cn(block, 'h-3 w-2/3')} />
              <div className={cn(block, 'h-6 w-1/2')} />
            </div>
          ))}
        </div>
        <div className={cn(card, 'space-y-3')}>
          <div className={cn(block, 'h-3 w-40')} />
          <div className="flex h-32 items-end gap-2">
            {[62, 88, 44, 73, 56, 92, 48].map((h, i) => (
              <div key={i} className={cn(block, 'flex-1')} style={{ height: `${h}%` }} />
            ))}
          </div>
        </div>
        <div className="space-y-2">
          <div className={cn(block, 'h-3 w-full')} />
          <div className={cn(block, 'h-3 w-11/12')} />
          <div className={cn(block, 'h-3 w-3/4')} />
        </div>
      </div>
    </div>
  );
}

export function ReportZeroState({
  config,
  sectionsPreview,
  canGenerate,
  actionLabel,
  onGenerate,
  progressContent,
  errorMessage,
  description,
  tone = 'accent',
}: {
  config: ReportConfigSummary | null;
  sectionsPreview?: SectionPreview[];
  canGenerate: boolean;
  actionLabel: string;
  onGenerate: () => void;
  progressContent?: ReactNode;
  errorMessage?: string | null;
  /** Overrides the default body copy when no error/progress is shown. */
  description?: string;
  /** 'accent' = vivid blueprint-colored hero (single-run default); 'neutral' =
   *  plain surface so the primary CTA stands out against it (cross-run). */
  tone?: 'accent' | 'neutral';
}) {
  const isNeutral = tone === 'neutral';
  const theme = getVariantTheme(config);
  const heroStyle: CSSProperties | undefined = isNeutral
    ? undefined
    : {
        background: `linear-gradient(135deg, ${theme.accent} 0%, color-mix(in srgb, ${theme.accent} 55%, var(--color-neutral-900)) 100%)`,
      };
  const cardClass = isNeutral
    ? 'border border-[var(--border-default)] bg-[var(--bg-secondary)] text-[var(--text-primary)]'
    : 'text-[var(--text-on-color)]';
  const chipClass = isNeutral
    ? 'border border-[var(--border-default)] bg-[var(--bg-tertiary)] text-[var(--text-secondary)]'
    : 'border border-[var(--text-on-color)]/15 bg-[var(--text-on-color)]/10 text-[var(--text-on-color)]/80';
  const bodyTextClass = isNeutral ? 'text-[var(--text-secondary)]' : 'text-[var(--text-on-color)]/85';

  const blueprintLabel = config?.name?.trim() || 'Report';
  const sections = sectionsPreview ?? [];

  return (
    <div className="relative min-h-[70vh] overflow-hidden">
      <ReportGhostPreview />
      <div className="relative flex min-h-[70vh] items-center justify-center px-4 py-12">
        <div
          className={cn('w-full max-w-lg rounded-[var(--radius-lg)] px-8 py-9 text-center shadow-[var(--shadow-lg)]', cardClass)}
          style={heroStyle}
        >
          <span className={cn('inline-block rounded-full px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em]', chipClass)}>
            {blueprintLabel}
          </span>

          {errorMessage ? (
            <p className={cn('mt-4 text-sm leading-6', bodyTextClass)}>{errorMessage}</p>
          ) : !progressContent ? (
            <p className={cn('mt-4 text-sm leading-6', bodyTextClass)}>
              {description ?? 'Generate an AI-written report — narrative, metrics, and recommendations.'}
            </p>
          ) : null}

          <div className="mt-6 flex justify-center">
            {progressContent ? (
              progressContent
            ) : canGenerate ? (
              <Button size="md" onClick={onGenerate}>
                <Sparkles className="h-4 w-4" />
                {actionLabel}
              </Button>
            ) : null}
          </div>

          {sections.length > 0 && !progressContent ? (
            <div className="mt-7 flex flex-wrap justify-center gap-1.5">
              {sections.map((s) => (
                <span
                  key={s.id}
                  className={cn('inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-medium', chipClass)}
                >
                  {s.title}
                </span>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

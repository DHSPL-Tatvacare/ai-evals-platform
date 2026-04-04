import { WizardSection, WizardStepLayout } from './WizardStepLayout';

export interface ReviewBadge {
  label: string;
  value: string;
}

export interface ReviewSummary {
  name: string;
  description?: string;
  badges: ReviewBadge[];
}

export interface ReviewSection {
  label: string;
  items: { key: string; value: string }[];
}

interface ReviewStepProps {
  summary: ReviewSummary;
  sections: ReviewSection[];
}

export function ReviewStep({ summary, sections }: ReviewStepProps) {
  return (
    <WizardStepLayout
      eyebrow="Review"
      title="Final pass before launch"
      description="Sanity-check the configuration so the stress test runs exactly as intended once you start it."
    >
      <WizardSection className="rounded-[12px] border border-[var(--border-subtle)] bg-[var(--bg-secondary)]/40 px-4 py-4">
        <h3 className="text-[18px] font-semibold tracking-[-0.02em] text-[var(--text-primary)]">
          {summary.name}
        </h3>
        {summary.description && (
          <p className="mt-1 text-[13px] leading-6 text-[var(--text-secondary)]">
            {summary.description}
          </p>
        )}
        {summary.badges.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2">
            {summary.badges.map((badge) => (
              <span
                key={badge.label}
                className="inline-flex items-center gap-1 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-primary)]/70 px-3 py-1 text-[11px] text-[var(--text-secondary)]"
              >
                <span className="text-[var(--text-muted)]">{badge.label}:</span>
                <span className="font-medium text-[var(--text-primary)]">{badge.value}</span>
              </span>
            ))}
          </div>
        )}
      </WizardSection>

      <div className="space-y-3">
        {sections.map((section) => (
          <WizardSection
            key={section.label}
            title={section.label}
            className="rounded-[12px] border border-[var(--border-subtle)] bg-[var(--bg-secondary)]/25 px-4 py-4"
            contentClassName="space-y-0"
          >
            {section.items.map((item) => (
              <div
                key={item.key}
                className="flex items-start justify-between gap-4 py-2.5"
              >
                <span className="shrink-0 text-[13px] text-[var(--text-secondary)]">{item.key}</span>
                <span className="min-w-0 break-words text-right text-[13px] font-medium text-[var(--text-primary)]">
                  {item.value}
                </span>
              </div>
            ))}
          </WizardSection>
        ))}
      </div>
    </WizardStepLayout>
  );
}

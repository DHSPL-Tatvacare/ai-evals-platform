import { Copy, Ruler, Save } from 'lucide-react';
import { Button } from '@/components/ui';
import { notificationService } from '@/services/notifications';
import { buildComposedReportOutline } from '../chatWidgetHelpers';
import type { BlueprintPart } from '../types';

interface BlueprintCardProps {
  part: BlueprintPart;
  onSave?: () => void;
}

export function BlueprintCard({ part, onSave }: BlueprintCardProps) {
  const handleCopy = async () => {
    await navigator.clipboard.writeText(buildComposedReportOutline({
      reportName: part.name,
      sections: part.sections,
    }));
    notificationService.success('Blueprint outline copied');
  };

  return (
    <div className="rounded-2xl border border-[color-mix(in_srgb,var(--color-accent-purple)_35%,transparent)] bg-[color-mix(in_srgb,var(--color-accent-purple)_10%,var(--bg-secondary))] p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-sm font-semibold text-[var(--text-primary)]">
            <Ruler className="h-4 w-4 text-[var(--color-accent-purple)]" />
            <span className="truncate">{part.name}</span>
          </div>
          <div className="mt-1 text-xs text-[var(--text-muted)]">
            {`${part.sections.length} section${part.sections.length === 1 ? '' : 's'}`}
          </div>
        </div>
        {part.saved ? (
          <span className="rounded-full bg-[color-mix(in_srgb,var(--color-accent-purple)_18%,transparent)] px-2 py-1 text-[11px] font-semibold text-[var(--color-accent-purple)]">
            Saved
          </span>
        ) : null}
      </div>
      <ol className="mt-4 space-y-2 text-sm text-[var(--text-primary)]">
        {part.sections.map((section, index) => (
          <li key={section.id} className="flex items-start gap-3 rounded-xl bg-[color-mix(in_srgb,var(--bg-primary)_55%,transparent)] px-3 py-2">
            <span className="mt-0.5 text-xs font-semibold text-[var(--color-accent-purple)]">{index + 1}</span>
            <div className="min-w-0">
              <div className="truncate font-medium">{section.title}</div>
              <div className="font-mono text-[11px] text-[var(--text-muted)]">{section.type}</div>
            </div>
          </li>
        ))}
      </ol>
      <div className="mt-4 flex flex-wrap gap-2">
        <Button variant="ghost" size="sm" icon={Copy} onClick={() => void handleCopy()}>
          Copy outline
        </Button>
        <Button variant="primary" size="sm" icon={Save} disabled={part.saved || !onSave} onClick={() => onSave?.()}>
          {part.saved ? 'Saved' : 'Save blueprint'}
        </Button>
      </div>
    </div>
  );
}

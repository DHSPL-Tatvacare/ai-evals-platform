import { Fragment, useMemo } from 'react';

import { useWatiTemplates } from '@/features/orchestration/queries/referenceData';
import type { VariableMapping } from '@/features/orchestration/components/VariableMappingField';

interface Props {
  connectionId?: string;
  templateName?: string;
  variableMappings: VariableMapping[];
}

const PLACEHOLDER_RE = /\{\{(\d+)\}\}/g;

/** Human-readable chip text for the mapping bound to a template parameter. */
function chipLabel(mapping: VariableMapping | undefined): string | null {
  if (!mapping) return null;
  if (mapping.source_kind === 'static') {
    const v = mapping.static_value?.trim();
    return v ? `${v} · static` : null;
  }
  const f = mapping.payload_field?.trim();
  return f ? `${f} · field` : null;
}

function BindingChip({ label }: { label: string }) {
  return (
    <span className="mx-0.5 inline-flex items-center rounded-full border border-[color-mix(in_srgb,var(--interactive-primary)_35%,transparent)] bg-[color-mix(in_srgb,var(--interactive-primary)_14%,var(--bg-primary))] px-1.5 py-0.5 align-baseline font-mono text-[11px] text-[var(--text-primary)]">
      {label}
    </span>
  );
}

function NotSetChip() {
  return (
    <span className="mx-0.5 inline-flex items-center rounded-full border border-dashed border-[var(--border-default)] bg-[var(--bg-tertiary)] px-1.5 py-0.5 align-baseline font-mono text-[11px] italic text-[var(--text-muted)]">
      not set
    </span>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex h-full items-center justify-center p-4 text-center text-xs text-[var(--text-secondary)]">
      {message}
    </div>
  );
}

export function TemplateMessagePreview({ connectionId, templateName, variableMappings }: Props) {
  const { data } = useWatiTemplates(connectionId);

  const template = useMemo(() => {
    if (!templateName) return null;
    return (data?.items ?? []).find((t) => t.name === templateName) ?? null;
  }, [data, templateName]);

  // Chip for a 1-based placeholder index → its parameter name → bound mapping.
  const chipFor = (oneBasedIndex: number) => {
    const paramName = template?.parameters[oneBasedIndex - 1];
    const mapping = paramName
      ? variableMappings.find((m) => m.agent_variable === paramName)
      : undefined;
    const label = chipLabel(mapping);
    return label ? <BindingChip label={label} /> : <NotSetChip />;
  };

  if (!connectionId || !templateName || !template) {
    return <EmptyState message="Select a template to preview the message." />;
  }

  const body = template.body ?? '';
  const hasBody = body.trim().length > 0;

  return (
    <div className="flex h-full flex-col overflow-y-auto p-4">
      <span className="mb-3 text-[10.5px] font-bold uppercase tracking-[0.1em] text-[var(--text-muted)]">
        Message preview
      </span>
      {hasBody ? (
        <div className="rounded-2xl rounded-br-md border border-[color-mix(in_srgb,var(--interactive-primary)_35%,transparent)] bg-[color-mix(in_srgb,var(--interactive-primary)_14%,var(--bg-primary))] px-4 py-3 text-[13px] leading-relaxed text-[var(--text-primary)] whitespace-pre-wrap break-words">
          {renderBody(body, chipFor)}
        </div>
      ) : (
        <div className="flex flex-col gap-1.5">
          {template.parameters.map((param, i) => (
            <div
              key={`${param}-${i}`}
              className="flex items-center gap-2 rounded-[var(--radius-default)] border border-[var(--border-subtle)] px-2.5 py-2 text-sm"
            >
              <span className="font-mono text-[var(--text-primary)]">{param}</span>
              <span className="ml-auto">{chipFor(i + 1)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** Split the body on positional {{n}} placeholders, interleaving text + chips. */
function renderBody(body: string, chipFor: (oneBasedIndex: number) => React.ReactNode) {
  const out: React.ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  PLACEHOLDER_RE.lastIndex = 0;
  let key = 0;
  while ((match = PLACEHOLDER_RE.exec(body)) !== null) {
    if (match.index > lastIndex) {
      out.push(<Fragment key={`t-${key}`}>{body.slice(lastIndex, match.index)}</Fragment>);
    }
    out.push(<Fragment key={`c-${key}`}>{chipFor(Number(match[1]))}</Fragment>);
    lastIndex = match.index + match[0].length;
    key += 1;
  }
  if (lastIndex < body.length) {
    out.push(<Fragment key={`t-${key}`}>{body.slice(lastIndex)}</Fragment>);
  }
  return out;
}

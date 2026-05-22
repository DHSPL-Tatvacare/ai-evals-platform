import { ShieldCheck } from 'lucide-react';

import { Input } from '@/components/ui/Input';
import { LlmModelSelect, type LlmModelSelectValue } from '@/components/ui/LlmModelSelect';
import { SchemaTable } from '@/features/evals/components/SchemaTable';
import type { WorkflowType } from '@/features/orchestration/types';
import type { EvaluatorOutputField } from '@/types';
import { cn } from '@/utils/cn';

const CALL_SITE = 'workflow_llm_extract';

interface LlmExtractConfig {
  prompt?: string;
  output_schema?: EvaluatorOutputField[];
  input_template?: string | null;
  output_namespace?: string;
  provider_override?: string | null;
  model_override?: string | null;
  concurrency?: number;
  inter_call_delay?: number;
}

interface Props {
  value: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
  /** Drives the clinical data-residency constraint at the provider picker. */
  workflowType?: WorkflowType;
}

export function LlmExtractEditor({ value, onChange, workflowType }: Props) {
  const config = value as LlmExtractConfig;
  const isClinical = workflowType === 'clinical';

  const fields = Array.isArray(config.output_schema) ? config.output_schema : [];

  const modelValue: LlmModelSelectValue | null =
    config.provider_override && config.model_override
      ? {
          credentialId: '',
          provider: config.provider_override as LlmModelSelectValue['provider'],
          credentialName: 'default',
          model: config.model_override,
        }
      : null;

  return (
    <div className="flex flex-col gap-4">
      <section className="flex flex-col gap-1">
        <label className="text-xs font-medium text-[var(--text-secondary)]">Prompt</label>
        <p className="text-xs text-[var(--text-muted)]">
          Instructions sent for each contact. Reference fields with{' '}
          <code>{'{{field}}'}</code>.
        </p>
        <textarea
          value={config.prompt ?? ''}
          onChange={(e) => onChange({ prompt: e.target.value })}
          rows={5}
          spellCheck={false}
          placeholder="Classify the sentiment of {{last_message}} as positive, neutral, or negative."
          className={cn(
            'block w-full resize-y rounded-[var(--radius-default)] border border-[var(--border-default)]',
            'bg-[var(--bg-base)] px-2 py-1.5 text-xs text-[var(--text-primary)]',
            'focus:border-[var(--color-brand)] focus:outline-none',
          )}
        />
      </section>

      <section className="flex flex-col gap-1">
        <label className="text-xs font-medium text-[var(--text-secondary)]">
          Output fields
        </label>
        <p className="text-xs text-[var(--text-muted)]">
          The structured fields the model must return. Saved under the output key below.
        </p>
        <SchemaTable
          fields={fields}
          onChange={(next) => onChange({ output_schema: next })}
        />
      </section>

      <section className="flex flex-col gap-1">
        <label className="text-xs font-medium text-[var(--text-secondary)]">
          Context template <span className="text-[var(--text-muted)]">(optional)</span>
        </label>
        <p className="text-xs text-[var(--text-muted)]">
          Per-contact context rendered from <code>{'{{field}}'}</code> placeholders. Leave
          empty to pass the whole record as JSON.
        </p>
        <textarea
          value={config.input_template ?? ''}
          onChange={(e) => onChange({ input_template: e.target.value || null })}
          rows={3}
          spellCheck={false}
          placeholder="{{last_message}}"
          className={cn(
            'block w-full resize-y rounded-[var(--radius-default)] border border-[var(--border-default)]',
            'bg-[var(--bg-base)] px-2 py-1.5 text-xs text-[var(--text-primary)]',
            'focus:border-[var(--color-brand)] focus:outline-none',
          )}
        />
      </section>

      <section className="flex flex-col gap-1">
        <label className="text-xs font-medium text-[var(--text-secondary)]">Output key</label>
        <p className="text-xs text-[var(--text-muted)]">
          The record key the extracted object is saved under. Defaults to this node&apos;s id.
        </p>
        <Input
          value={config.output_namespace ?? ''}
          onChange={(e) => onChange({ output_namespace: e.target.value })}
          placeholder="extracted"
        />
      </section>

      <section className="flex flex-col gap-1">
        <label className="text-xs font-medium text-[var(--text-secondary)]">Model</label>
        {isClinical ? (
          <div
            className={cn(
              'flex items-start gap-2 rounded-[var(--radius-default)] border border-[var(--border-subtle)]',
              'bg-[var(--surface-info)] px-2 py-1.5 text-xs text-[var(--text-secondary)]',
            )}
          >
            <ShieldCheck
              className="mt-0.5 h-3.5 w-3.5 shrink-0"
              style={{ color: 'var(--color-info)' }}
              aria-hidden="true"
            />
            <span>
              Clinical workflow — only approved, in-region models may process patient
              data. Pick from your tenant&apos;s configured in-region deployments.
            </span>
          </div>
        ) : (
          <p className="text-xs text-[var(--text-muted)]">
            Leave unset to use your tenant&apos;s default for this capability.
          </p>
        )}
        <LlmModelSelect
          callSite={CALL_SITE}
          value={modelValue}
          onChange={(next) =>
            onChange({
              provider_override: next?.provider ?? null,
              model_override: next?.model ?? null,
            })
          }
          layout="rows"
        />
      </section>
    </div>
  );
}

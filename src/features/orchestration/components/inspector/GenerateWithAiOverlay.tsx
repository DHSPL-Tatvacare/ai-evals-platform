import { useCallback, useState } from 'react';
import { RefreshCw, Sparkles, X } from 'lucide-react';

import { Button } from '@/components/ui/Button';
import { RightSlideOverShell } from '@/components/ui/RightSlideOverShell';
import { llmAssistApi } from '@/services/api/llmAssistApi';
import type { LLMProvider } from '@/services/api/aiSettingsApi';
import { LLM_PROVIDER_LABELS } from '@/constants/llmProviders';
import type { UpstreamField } from '@/services/api/orchestration';
import type { WorkflowType } from '@/features/orchestration/types';
import { jsonSchemaToOutputFields } from '@/utils';
import type { EvaluatorOutputField } from '@/types';
import {
  decodeApiError,
  summarizeApiErrorBody,
} from '@/features/orchestration/contracts/errorDecoder';
import { cn } from '@/utils/cn';

import {
  buildGeneratePromptBody,
  buildGenerateSchemaBody,
} from './generateContext';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  /** Match the primary inspector width. */
  width: number;
  workflowType?: WorkflowType;
  provider: string | null;
  model: string | null;
  fields: UpstreamField[];
  onInsert: (result: { prompt: string; outputSchema?: EvaluatorOutputField[] }) => void;
}

const sectionLabel = 'flex items-center gap-1.5 text-[13px] font-semibold text-[var(--text-primary)]';

export function GenerateWithAiOverlay({
  isOpen,
  onClose,
  width,
  workflowType,
  provider,
  model,
  fields,
  onInsert,
}: Props) {
  const [userIdea, setUserIdea] = useState('');
  const [excluded, setExcluded] = useState<Set<string>>(new Set());
  const [alsoSchema, setAlsoSchema] = useState(false);
  const [draftPrompt, setDraftPrompt] = useState<string | null>(null);
  const [draftFields, setDraftFields] = useState<EvaluatorOutputField[] | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const hasModel = Boolean(provider && model);

  const toggleVar = useCallback((path: string) => {
    setExcluded((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }, []);

  const handleGenerate = useCallback(async () => {
    if (!provider || !model) {
      setError('Pick a model in the Configure pane first.');
      return;
    }
    if (!userIdea.trim()) {
      setError('Describe what this step should do.');
      return;
    }
    setIsGenerating(true);
    setError(null);
    setDraftPrompt(null);
    setDraftFields(null);
    try {
      const { prompt } = await llmAssistApi.generatePrompt(
        buildGeneratePromptBody({
          provider: provider as LLMProvider,
          model,
          userIdea,
          fields,
          excluded,
        }),
      );
      setDraftPrompt(prompt);
      if (alsoSchema) {
        const { schema } = await llmAssistApi.generateSchema(
          buildGenerateSchemaBody({
            provider: provider as LLMProvider,
            model,
            userIdea,
            fields,
            excluded,
          }),
        );
        const mapped = jsonSchemaToOutputFields(schema);
        if (mapped.ok) setDraftFields(mapped.fields);
        else setError(`Prompt drafted, but the fields could not be parsed: ${mapped.reason}`);
      }
    } catch (err) {
      setError(summarizeApiErrorBody(decodeApiError(err), 'Failed to generate.'));
    } finally {
      setIsGenerating(false);
    }
  }, [provider, model, userIdea, fields, excluded, alsoSchema]);

  const handleInsert = useCallback(() => {
    if (!draftPrompt) return;
    onInsert({ prompt: draftPrompt, outputSchema: draftFields ?? undefined });
    onClose();
  }, [draftPrompt, draftFields, onInsert, onClose]);

  const inputClass = cn(
    'block w-full resize-y rounded-[var(--radius-default)] border border-[var(--border-default)]',
    'bg-[var(--bg-base)] px-2.5 py-2 text-sm text-[var(--text-primary)]',
    'focus:border-[var(--color-brand)] focus:outline-none',
  );

  return (
    <RightSlideOverShell
      isOpen={isOpen}
      onClose={onClose}
      panelStyle={{ width }}
      widthClassName="max-w-[92vw]"
    >
      <div className="flex h-full flex-col bg-[var(--bg-primary)]">
        <div className="flex items-center gap-2.5 border-b border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-4 py-3">
          <span className="flex h-7 w-7 items-center justify-center rounded-[var(--radius-default)] bg-[var(--surface-info)] text-[var(--color-info)]">
            <Sparkles className="h-4 w-4" aria-hidden="true" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-[15px] font-semibold text-[var(--text-primary)]">
              Generate prompt with AI
            </span>
            <span className="block text-[12px] text-[var(--text-muted)]">
              Describe the goal — we draft the prompt for you.
            </span>
          </span>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close generate overlay"
            className="rounded p-1 text-[var(--text-muted)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto p-4">
          <div className="flex flex-col gap-2">
            <span className={sectionLabel}>What should this step do?</span>
            <textarea
              value={userIdea}
              onChange={(e) => setUserIdea(e.target.value)}
              rows={3}
              placeholder="Read each contact's last message and decide if they sound positive, neutral, or negative, with a confidence score."
              className={inputClass}
            />
            <span className="text-[11.5px] text-[var(--text-secondary)]">
              Plain English. No need to mention variables — pick the ones to wire in below.
            </span>
          </div>

          <div className="flex flex-col gap-2">
            <span className={sectionLabel}>Context the model will use</span>
            <div className="flex flex-col gap-2 rounded-[var(--radius-default)] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3">
              <div className="flex items-center justify-between text-[12px]">
                <span className="text-[var(--text-muted)]">Model</span>
                <span className="text-[var(--text-secondary)]">
                  {hasModel
                    ? `${LLM_PROVIDER_LABELS[provider as LLMProvider] ?? provider} · ${model}`
                    : 'Not set — pick one in Configure'}
                </span>
              </div>
              {workflowType === 'clinical' ? (
                <div className="flex items-center justify-between text-[12px]">
                  <span className="text-[var(--text-muted)]">Workflow</span>
                  <span className="text-[var(--color-info)]">Clinical · in-region only</span>
                </div>
              ) : null}
              <div className="flex flex-col gap-1.5">
                <span className="text-[12px] text-[var(--text-muted)]">
                  Available variables — click to include or exclude
                </span>
                {fields.length === 0 ? (
                  <span className="text-[11.5px] text-[var(--text-secondary)]">
                    No upstream variables yet.
                  </span>
                ) : (
                  <div className="flex flex-wrap gap-1.5">
                    {fields.map((f) => {
                      const off = excluded.has(f.path);
                      return (
                        <button
                          key={f.path}
                          type="button"
                          onClick={() => toggleVar(f.path)}
                          className={cn(
                            'rounded-full border px-2 py-0.5 font-mono text-[11px]',
                            off
                              ? 'border-[var(--border-subtle)] text-[var(--text-muted)] line-through'
                              : 'border-[var(--color-brand)] bg-[var(--surface-info)] text-[var(--text-primary)]',
                          )}
                        >
                          {f.path}
                        </button>
                      );
                    })}
                  </div>
                )}
                <span className="mt-0.5 text-[11px] text-[var(--text-secondary)]">
                  Names only — never the actual values. Nothing real is sent to draft the prompt.
                </span>
              </div>
            </div>
            <label className="flex items-center gap-2 text-[12.5px] text-[var(--text-secondary)]">
              <input
                type="checkbox"
                checked={alsoSchema}
                onChange={(e) => setAlsoSchema(e.target.checked)}
              />
              Also draft the fields to extract from this description
            </label>
          </div>

          {error ? (
            <p className="rounded-[var(--radius-default)] border border-[var(--border-warning)] bg-[var(--surface-warning)] p-2 text-[12px] text-[var(--color-warning)]">
              {error}
            </p>
          ) : null}

          {draftPrompt ? (
            <div className="flex flex-col gap-2">
              <span className={sectionLabel}>Draft — review before inserting</span>
              <div className="whitespace-pre-wrap rounded-[var(--radius-default)] border border-[var(--border-default)] bg-[var(--bg-base)] p-2.5 font-mono text-[12px] text-[var(--text-primary)]">
                {draftPrompt}
              </div>
              {draftFields ? (
                <div className="flex flex-wrap gap-1.5">
                  {draftFields.map((f) => (
                    <span
                      key={f.key}
                      className="rounded bg-[var(--bg-tertiary)] px-1.5 py-0.5 font-mono text-[11px] text-[var(--text-secondary)]"
                    >
                      {f.key}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}
        </div>

        <div className="flex items-center gap-2 border-t border-[var(--border-subtle)] px-4 py-3">
          {draftPrompt ? (
            <Button
              type="button"
              size="sm"
              variant="secondary"
              icon={RefreshCw}
              onClick={handleGenerate}
              disabled={isGenerating}
            >
              Regenerate
            </Button>
          ) : null}
          <span className="flex-1" />
          <Button type="button" size="sm" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          {draftPrompt ? (
            <Button type="button" size="sm" variant="primary" onClick={handleInsert}>
              Insert into prompt
            </Button>
          ) : (
            <Button
              type="button"
              size="sm"
              variant="primary"
              icon={Sparkles}
              onClick={handleGenerate}
              isLoading={isGenerating}
              disabled={!hasModel || !userIdea.trim() || isGenerating}
            >
              {isGenerating ? 'Generating…' : 'Generate'}
            </Button>
          )}
        </div>
      </div>
    </RightSlideOverShell>
  );
}

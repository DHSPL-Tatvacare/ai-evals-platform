import { useCallback, useMemo, useRef, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { AlertTriangle, ChevronDown, Play, RefreshCw, ShieldCheck, Sparkles, SquarePen, Wand2, X } from 'lucide-react';

import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { LlmModelSelect, type LlmModelSelectValue } from '@/components/ui/LlmModelSelect';
import { VariablePickerPopover } from '@/components/ui/VariablePickerPopover';
import {
  InspectorEmptyState,
  InspectorField,
  InspectorSection,
} from '@/features/orchestration/components/inspector/InspectorPrimitives';
import {
  lintUnknownVariables,
  parentLockStatus,
  saveAsCollides,
  sourceGroupLabel,
  suggestKnownVariable,
  toVariableInfo,
} from '@/features/orchestration/components/inspector/upstreamVariables';
import { useResolveUpstreamVariables } from '@/features/orchestration/queries/upstreamVariables';
import { EditSchemaOverlay } from '@/features/orchestration/components/inspector/EditSchemaOverlay';
import { GenerateWithAiOverlay } from '@/features/orchestration/components/inspector/GenerateWithAiOverlay';
import { downstreamKeys, resultSignature } from '@/features/orchestration/components/inspector/testPane';
import { useWorkflowBuilderStore } from '@/features/orchestration/store/workflowBuilderStore';
import {
  runLlmExtractTest,
  type LlmExtractDryRunResponse,
  type UpstreamField,
} from '@/services/api/orchestration';
import {
  decodeApiError,
  summarizeApiErrorBody,
} from '@/features/orchestration/contracts/errorDecoder';
import type { WorkflowType } from '@/features/orchestration/types';
import type { EvaluatorOutputField } from '@/types';
import { useCurrentAppId } from '@/hooks';
import { cn } from '@/utils/cn';

const CALL_SITE = 'workflow_llm_extract';
const MIN_WIDTH = 480;
const MAX_WIDTH = 1280;

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
  /** Drives the clinical data-residency note at the model picker. */
  workflowType?: WorkflowType;
  displayLabel: string;
  nodeType: string;
  onClose: () => void;
  readOnly?: boolean;
}

const paneLabelClass =
  'text-[10.5px] font-bold uppercase tracking-[0.1em] text-[var(--text-muted)]';

function PaneHeader({ step, label, action }: { step: number; label: string; action?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2 border-b border-[var(--border-subtle)] px-3 py-2.5">
      <span className="flex items-center gap-1.5">
        <span className="inline-flex h-4 w-4 items-center justify-center rounded-full bg-[var(--color-brand)] text-[10px] font-bold text-[var(--text-on-color)]">
          {step}
        </span>
        <span className={paneLabelClass}>{label}</span>
      </span>
      {action}
    </div>
  );
}

export function LlmExtractInspector({
  value,
  onChange,
  workflowType,
  displayLabel,
  nodeType,
  onClose,
  readOnly = false,
}: Props) {
  const config = value as LlmExtractConfig;
  const isClinical = workflowType === 'clinical';
  const fields = Array.isArray(config.output_schema) ? config.output_schema : [];
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [varFilter, setVarFilter] = useState('');
  const [generateOpen, setGenerateOpen] = useState(false);
  const [schemaOpen, setSchemaOpen] = useState(false);
  const promptRef = useRef<HTMLTextAreaElement>(null);

  const appId = useCurrentAppId();
  const nodes = useWorkflowBuilderStore((s) => s.nodes);
  const edges = useWorkflowBuilderStore((s) => s.edges);
  const targetNodeId = useWorkflowBuilderStore((s) => s.selectedNodeId);
  const { data: upstream } = useResolveUpstreamVariables({
    appId,
    workflowType,
    nodes,
    edges,
    targetNodeId,
  });
  const upstreamFields = useMemo(() => upstream?.fields ?? [], [upstream]);
  const unresolved = useMemo(() => upstream?.unresolved ?? [], [upstream]);
  const lockStatus = parentLockStatus(upstreamFields, unresolved);

  // Group resolved fields by source for the Input pane, honoring the filter.
  const groupedFields = useMemo(() => {
    const q = varFilter.trim().toLowerCase();
    const groups = new Map<string, UpstreamField[]>();
    for (const f of upstreamFields) {
      if (q && !f.path.toLowerCase().includes(q)) continue;
      if (!groups.has(f.source)) groups.set(f.source, []);
      groups.get(f.source)!.push(f);
    }
    return [...groups.entries()];
  }, [upstreamFields, varFilter]);

  const promptText = config.prompt ?? '';
  const unknownVars = lintUnknownVariables(promptText, upstreamFields);
  const saveAsConflict = saveAsCollides(config.output_namespace, upstreamFields);

  // Insert a token at the caret (or append) and restore focus after it.
  const insertToken = useCallback(
    (token: string) => {
      const ta = promptRef.current;
      const current = config.prompt ?? '';
      if (!ta) {
        onChange({ prompt: current + token });
        return;
      }
      const start = ta.selectionStart ?? current.length;
      const end = ta.selectionEnd ?? current.length;
      onChange({ prompt: current.slice(0, start) + token + current.slice(end) });
      requestAnimationFrame(() => {
        ta.focus();
        const pos = start + token.length;
        ta.setSelectionRange(pos, pos);
      });
    },
    [config.prompt, onChange],
  );

  // ── Test pane: editable sample → dry-run → result + downstream keys ──────
  const [sampleText, setSampleText] = useState('');
  const [sampleEdited, setSampleEdited] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [result, setResult] = useState<LlmExtractDryRunResponse | null>(null);
  const [ranSignature, setRanSignature] = useState<string | null>(null);
  const pendingSignature = useRef('');

  const sampleFromResolver = useMemo(
    () => JSON.stringify(upstream?.sample ?? {}, null, 2),
    [upstream],
  );
  // Show the resolver sample until the user edits it — derived, not an effect.
  const sampleValue = sampleEdited ? sampleText : sampleFromResolver;

  const namespace = config.output_namespace || targetNodeId || 'output';
  const downstream = downstreamKeys(namespace, fields);
  const currentSignature = resultSignature({
    provider: config.provider_override,
    model: config.model_override,
    prompt: config.prompt,
    outputSchema: fields,
    sampleText: sampleValue,
  });
  const resultIsStale = result != null && currentSignature !== ranSignature;

  const testMutation = useMutation({
    mutationFn: (sample: Record<string, unknown>) =>
      runLlmExtractTest({ appId, config: value, sample }),
    onSuccess: (data) => {
      setResult(data);
      setRanSignature(pendingSignature.current);
      setRunError(null);
    },
    onError: (err) =>
      setRunError(summarizeApiErrorBody(decodeApiError(err), 'Dry-run failed.')),
  });

  const handleRun = () => {
    let parsed: Record<string, unknown>;
    try {
      parsed = sampleValue.trim() ? (JSON.parse(sampleValue) as Record<string, unknown>) : {};
    } catch {
      setRunError('Sample must be valid JSON.');
      return;
    }
    setRunError(null);
    pendingSignature.current = currentSignature;
    testMutation.mutate(parsed);
  };

  const inspectorWidth = useWorkflowBuilderStore((s) => s.inspectorWidth);
  const setInspectorWidth = useWorkflowBuilderStore((s) => s.setInspectorWidth);
  const dragRef = useRef<{ startX: number; startWidth: number } | null>(null);

  const onResizePointerDown = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      e.preventDefault();
      dragRef.current = { startX: e.clientX, startWidth: inspectorWidth };
      e.currentTarget.setPointerCapture(e.pointerId);
    },
    [inspectorWidth],
  );
  const onResizePointerMove = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      const drag = dragRef.current;
      if (!drag) return;
      // Panel docks on the right: dragging the left edge leftward widens it.
      const next = drag.startWidth + (drag.startX - e.clientX);
      setInspectorWidth(Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, next)));
    },
    [setInspectorWidth],
  );
  const onResizePointerUp = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    dragRef.current = null;
    e.currentTarget.releasePointerCapture(e.pointerId);
  }, []);

  const modelValue: LlmModelSelectValue | null =
    config.provider_override && config.model_override
      ? {
          credentialId: '',
          provider: config.provider_override as LlmModelSelectValue['provider'],
          credentialName: 'default',
          model: config.model_override,
        }
      : null;

  const textAreaClass = cn(
    'block w-full resize-y rounded-[var(--radius-default)] border border-[var(--border-default)]',
    'bg-[var(--bg-base)] px-2.5 py-2 text-sm text-[var(--text-primary)]',
    'focus:border-[var(--color-brand)] focus:outline-none',
  );

  return (
    <div className="flex h-full shrink-0" style={{ width: inspectorWidth }}>
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize inspector"
        onPointerDown={onResizePointerDown}
        onPointerMove={onResizePointerMove}
        onPointerUp={onResizePointerUp}
        className="group relative w-1.5 shrink-0 cursor-col-resize bg-transparent"
      >
        <span className="absolute left-0 top-1/2 h-10 w-0.5 -translate-y-1/2 rounded bg-[var(--border-default)] group-hover:bg-[var(--color-brand)]" />
      </div>

      <div className="flex min-w-0 flex-1 flex-col border-l border-[var(--border-subtle)] bg-[var(--bg-primary)]">
        <div className="flex items-center gap-2.5 border-b border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-4 py-3">
          <span className="flex h-7 w-7 items-center justify-center rounded-[var(--radius-default)] bg-[var(--surface-info)] text-[var(--color-info)]">
            <Sparkles className="h-4 w-4" aria-hidden="true" />
          </span>
          <span className="min-w-0">
            <span className="block truncate text-[15px] font-semibold text-[var(--text-primary)]">
              {displayLabel}
            </span>
            <span className="block truncate font-mono text-[11px] text-[var(--text-muted)]">
              {nodeType}
            </span>
          </span>
          <span className="flex-1" />
          <button
            type="button"
            onClick={onClose}
            aria-label="Close inspector"
            className="rounded p-1 text-[var(--text-muted)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <fieldset
          disabled={readOnly}
          className="grid min-h-0 flex-1 grid-cols-[236px_1fr_244px]"
        >
          {/* INPUT — variables available upstream, click to drop into the prompt. */}
          <section className="flex min-w-0 flex-col overflow-y-auto">
            <PaneHeader step={1} label="Input" />
            <div className="flex flex-col gap-3 p-3">
              {lockStatus === 'no-upstream' ? (
                <InspectorEmptyState>
                  Connect an upstream step — a source, dataset, or an earlier step —
                  to pull its variables into the prompt.
                </InspectorEmptyState>
              ) : null}

              {upstreamFields.length > 0 ? (
                <input
                  value={varFilter}
                  onChange={(e) => setVarFilter(e.target.value)}
                  placeholder="Filter variables…"
                  className={cn(
                    'w-full rounded-[var(--radius-default)] border border-[var(--border-default)]',
                    'bg-[var(--bg-base)] px-2.5 py-1.5 text-xs text-[var(--text-primary)]',
                    'focus:border-[var(--color-brand)] focus:outline-none',
                  )}
                />
              ) : null}

              {groupedFields.map(([source, list]) => (
                <div key={source} className="flex flex-col gap-0.5">
                  <span className={cn(paneLabelClass, 'px-1 pb-0.5')}>
                    {sourceGroupLabel(source)} · {list.length}
                  </span>
                  {list.map((f) => (
                    <button
                      key={f.path}
                      type="button"
                      onClick={() => insertToken(`{{${f.path}}}`)}
                      title={`Insert {{${f.path}}}`}
                      className={cn(
                        'flex items-center gap-2 rounded-[var(--radius-default)] border border-transparent px-2 py-1.5 text-left',
                        'hover:border-[var(--border-default)] hover:bg-[var(--bg-secondary)]',
                      )}
                    >
                      <span className="truncate font-mono text-xs text-[var(--text-primary)]">
                        {f.path}
                      </span>
                      <span className="ml-auto shrink-0 rounded bg-[var(--bg-tertiary)] px-1.5 py-0.5 text-[10px] text-[var(--text-secondary)]">
                        {f.type}
                      </span>
                    </button>
                  ))}
                </div>
              ))}

              {unresolved.map((u) => (
                <div
                  key={u.nodeId}
                  className="rounded-[var(--radius-default)] border border-dashed border-[var(--border-warning)] bg-[var(--surface-warning)] p-2.5"
                >
                  <div className="flex items-center gap-1.5 text-[11.5px] font-semibold text-[var(--color-warning)]">
                    <AlertTriangle className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                    {u.label}
                  </div>
                  <p className="mt-1 text-[11px] text-[var(--text-secondary)]">{u.reason}</p>
                </div>
              ))}
            </div>
          </section>

          {/* CONFIGURE — the editable pane. */}
          <section className="flex min-w-0 flex-col overflow-y-auto border-l border-[var(--border-subtle)]">
            <PaneHeader step={2} label="Configure" />
            <div className="flex flex-col gap-5 p-4">
              <InspectorField
                label="Model"
                description="Which model runs the prompt. Leave unset to use your tenant's default for this capability. The dry-run uses this model too."
              >
                {isClinical ? (
                  <div
                    className={cn(
                      'mb-2 flex items-start gap-2 rounded-[var(--radius-default)] border border-[var(--border-subtle)]',
                      'bg-[var(--surface-info)] px-2 py-1.5 text-xs text-[var(--text-secondary)]',
                    )}
                  >
                    <ShieldCheck
                      className="mt-0.5 h-3.5 w-3.5 shrink-0"
                      style={{ color: 'var(--color-info)' }}
                      aria-hidden="true"
                    />
                    <span>
                      Clinical workflow — only approved, in-region models may process
                      patient data. Pick from your tenant's configured in-region
                      deployments.
                    </span>
                  </div>
                ) : null}
                <LlmModelSelect
                  callSite={CALL_SITE}
                  value={modelValue}
                  onChange={(next) =>
                    onChange({
                      provider_override: next?.provider ?? null,
                      model_override: next?.model ?? null,
                    })
                  }
                  layout="stack"
                  compact
                />
              </InspectorField>

              <InspectorField
                label="Prompt"
                description="Instructions sent to the model for each record. Reference fields with {{field}}."
              >
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <VariablePickerPopover
                    appId={appId}
                    staticOnly
                    staticVariables={upstreamFields.map(toVariableInfo)}
                    onInsert={insertToken}
                    buttonLabel="Insert variable"
                  />
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    icon={Wand2}
                    onClick={() => setGenerateOpen(true)}
                  >
                    Generate with AI
                  </Button>
                </div>
                <textarea
                  ref={promptRef}
                  value={promptText}
                  onChange={(e) => onChange({ prompt: e.target.value })}
                  rows={5}
                  spellCheck={false}
                  placeholder="Classify the sentiment of {{last_message}} as positive, neutral, or negative."
                  className={textAreaClass}
                />
                {unknownVars.length > 0 ? (
                  <div className="mt-2 flex flex-col gap-1">
                    {unknownVars.map((v) => {
                      const suggestion = suggestKnownVariable(v, upstreamFields);
                      return (
                        <div
                          key={v}
                          className="flex items-start gap-1.5 text-[11.5px] text-[var(--color-warning)]"
                        >
                          <AlertTriangle
                            className="mt-0.5 h-3.5 w-3.5 shrink-0"
                            aria-hidden="true"
                          />
                          <span>
                            <span className="font-mono">{`{{${v}}}`}</span> isn't a known
                            variable
                            {suggestion ? (
                              <>
                                {' '}
                                — did you mean{' '}
                                <b className="text-[var(--text-primary)]">{suggestion}</b>?
                              </>
                            ) : null}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                ) : null}
              </InspectorField>

              <InspectorSection
                title="Fields to extract"
                description="The structured fields the model must return, enforced as JSON Schema. Edit them in a roomy schema editor."
                actions={
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    icon={SquarePen}
                    onClick={() => setSchemaOpen(true)}
                  >
                    Edit schema
                  </Button>
                }
              >
                {fields.length === 0 ? (
                  <InspectorEmptyState>
                    No fields yet — open the schema editor to add the fields the model
                    should return.
                  </InspectorEmptyState>
                ) : (
                  <div className="flex flex-col gap-1">
                    {fields.map((f) => (
                      <div
                        key={f.key}
                        className="flex items-center gap-2 rounded-[var(--radius-default)] px-1.5 py-1 text-sm"
                      >
                        <span className="font-mono text-[var(--text-primary)]">{f.key}</span>
                        <span className="rounded bg-[var(--bg-tertiary)] px-1.5 py-0.5 text-[10px] text-[var(--text-secondary)]">
                          {f.type}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </InspectorSection>

              <div className="flex flex-col">
                <button
                  type="button"
                  onClick={() => setAdvancedOpen((v) => !v)}
                  className="flex items-center gap-1.5 border-t border-[var(--border-subtle)] pt-3 text-sm font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                >
                  <ChevronDown
                    className={cn('h-3.5 w-3.5 transition-transform', advancedOpen && 'rotate-180')}
                  />
                  Advanced
                </button>
                {advancedOpen ? (
                  <div className="mt-3 grid grid-cols-2 gap-3">
                    <InspectorField
                      label="Save results as"
                      description="The record key the extracted object is saved under. Defaults to this node's id."
                    >
                      <Input
                        value={config.output_namespace ?? ''}
                        onChange={(e) => onChange({ output_namespace: e.target.value })}
                        placeholder="analysis"
                      />
                      {saveAsConflict ? (
                        <p className="mt-1 flex items-start gap-1.5 text-[11px] text-[var(--color-warning)]">
                          <AlertTriangle
                            className="mt-0.5 h-3 w-3 shrink-0"
                            aria-hidden="true"
                          />
                          <span>
                            An upstream variable is already named “{config.output_namespace}”.
                            Pick another to keep downstream references unambiguous.
                          </span>
                        </p>
                      ) : null}
                    </InspectorField>
                    <InspectorField
                      label="Concurrency"
                      description="How many records to process in parallel (1–20)."
                    >
                      <Input
                        type="number"
                        min={1}
                        max={20}
                        value={config.concurrency ?? 1}
                        onChange={(e) => onChange({ concurrency: Number(e.target.value) })}
                      />
                    </InspectorField>
                    <InspectorField
                      label="Delay (s)"
                      description="Seconds to stagger between starting each record, for rate limiting."
                    >
                      <Input
                        type="number"
                        min={0}
                        step={0.1}
                        value={config.inter_call_delay ?? 0}
                        onChange={(e) => onChange({ inter_call_delay: Number(e.target.value) })}
                      />
                    </InspectorField>
                    <InspectorField
                      label="Context template"
                      description="Per-record context rendered from {{field}} placeholders. Leave empty to pass the whole record as JSON."
                    >
                      <Input
                        value={config.input_template ?? ''}
                        onChange={(e) => onChange({ input_template: e.target.value || null })}
                        placeholder="(optional)"
                      />
                    </InspectorField>
                  </div>
                ) : null}
              </div>
            </div>
          </section>

          {/* TEST — editable sample → dry-run → result + downstream keys. */}
          <section className="flex min-w-0 flex-col overflow-y-auto border-l border-[var(--border-subtle)]">
            <PaneHeader step={3} label="Test" />
            <div className="flex flex-col gap-3 p-3">
              <div className="flex flex-col gap-1">
                <span className={paneLabelClass}>Sample record</span>
                <textarea
                  value={sampleValue}
                  onChange={(e) => {
                    setSampleEdited(true);
                    setSampleText(e.target.value);
                  }}
                  rows={6}
                  spellCheck={false}
                  placeholder="{ }"
                  className={cn(textAreaClass, 'font-mono text-xs')}
                />
              </div>
              <Button
                type="button"
                size="sm"
                variant="primary"
                icon={Play}
                onClick={handleRun}
                isLoading={testMutation.isPending}
                disabled={!config.prompt || testMutation.isPending}
              >
                Run
              </Button>

              {runError ? (
                <p className="flex items-start gap-1.5 rounded-[var(--radius-default)] border border-[var(--border-warning)] bg-[var(--surface-warning)] p-2 text-[11.5px] text-[var(--color-warning)]">
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                  <span>{runError}</span>
                </p>
              ) : null}

              {result ? (
                <div className={cn('flex flex-col gap-2', resultIsStale && 'opacity-50')}>
                  {resultIsStale ? (
                    <span className="flex items-center gap-1.5 text-[11px] text-[var(--text-muted)]">
                      <RefreshCw className="h-3 w-3" aria-hidden="true" />
                      Inputs changed — re-run to refresh.
                    </span>
                  ) : null}
                  <span className={paneLabelClass}>Result</span>
                  <pre className="overflow-x-auto whitespace-pre-wrap rounded-[var(--radius-default)] border border-[var(--border-default)] bg-[var(--bg-base)] p-2.5 font-mono text-[11px] text-[var(--text-primary)]">
                    {JSON.stringify(result.result, null, 2)}
                  </pre>
                  {downstream.length > 0 ? (
                    <div className="flex flex-col gap-1">
                      <span className={paneLabelClass}>Downstream keys</span>
                      <div className="flex flex-wrap gap-1">
                        {downstream.map((k) => (
                          <code
                            key={k}
                            className="rounded bg-[var(--bg-tertiary)] px-1.5 py-0.5 text-[10.5px] text-[var(--color-info)]"
                          >
                            {k}
                          </code>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </div>
              ) : (
                <InspectorEmptyState>
                  Run the prompt over a sample record to preview the extracted fields.
                </InspectorEmptyState>
              )}
            </div>
          </section>
        </fieldset>
      </div>

      <GenerateWithAiOverlay
        isOpen={generateOpen}
        onClose={() => setGenerateOpen(false)}
        width={inspectorWidth}
        workflowType={workflowType}
        provider={config.provider_override ?? null}
        model={config.model_override ?? null}
        fields={upstreamFields}
        onInsert={({ prompt, outputSchema }) =>
          onChange(outputSchema ? { prompt, output_schema: outputSchema } : { prompt })
        }
      />
      <EditSchemaOverlay
        isOpen={schemaOpen}
        onClose={() => setSchemaOpen(false)}
        width={inspectorWidth}
        fields={fields}
        onChange={(next) => onChange({ output_schema: next })}
      />
    </div>
  );
}

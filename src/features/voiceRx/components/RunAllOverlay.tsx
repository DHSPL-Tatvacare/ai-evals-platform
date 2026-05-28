import { useState, useId } from "react";
import { X, PlayCircle } from "lucide-react";
import { Button, LlmModelSelect, RightSlideOverShell, type LlmModelSelectValue } from "@/components/ui";
import { useEvaluatorsStore } from "@/stores";
import type { LLMProvider } from "@/services/api/aiSettingsApi";
import { EvaluatorPickerList } from "@/features/evals/components/EvaluatorPickerList";

export interface RunAllSelection {
  evaluatorIds: string[];
  provider: LLMProvider;
  model: string;
}

interface RunAllOverlayProps {
  open: boolean;
  onClose: () => void;
  onRun: (selection: RunAllSelection) => void;
  initialSelectedIds?: string[];
}

export function RunAllOverlay({ open, onClose, onRun, initialSelectedIds }: RunAllOverlayProps) {
  const titleId = useId();
  const evaluators = useEvaluatorsStore((s) => s.evaluators);
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(initialSelectedIds ?? evaluators.map((e) => e.id)),
  );
  // TODO: split into two pickers (audio_transcription + chat_text) per
  // docs/plans/2026-05-18-llm-call-site-architecture/phase-3-frontend-and-capability-gating.md
  // Task 5; UX shift gated on design review.
  const [llmPick, setLlmPick] = useState<LlmModelSelectValue | null>(null);
  const selectedProvider = (llmPick?.provider ?? '') as LLMProvider | '';
  const selectedModel = llmPick?.model ?? '';

  // Sync selection when overlay opens with new evaluator list
  const evaluatorIds = evaluators.map((e) => e.id).join(",");
  const initialKey = initialSelectedIds?.join(",") ?? "";
  const [lastIds, setLastIds] = useState(evaluatorIds + "|" + initialKey);
  const syncKey = evaluatorIds + "|" + initialKey;
  if (syncKey !== lastIds) {
    setLastIds(syncKey);
    setSelected(new Set(initialSelectedIds ?? evaluators.map((e) => e.id)));
  }

  function handleSubmit() {
    if (selected.size === 0 || !selectedModel || !selectedProvider) return;
    onRun({
      evaluatorIds: Array.from(selected),
      provider: selectedProvider,
      model: selectedModel,
    });
    onClose();
  }

  function toggleEvaluator(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function selectAll() {
    setSelected(new Set(evaluators.map((e) => e.id)));
  }

  function selectNone() {
    setSelected(new Set());
  }

  return (
    <RightSlideOverShell
      isOpen={open}
      onClose={onClose}
      labelledBy={titleId}
      widthClassName="w-[var(--overlay-width-sm)] max-w-[85vw]"
    >
        {/* Header */}
        <div className="shrink-0 flex items-center justify-between px-6 py-4 border-b border-[var(--border-subtle)]">
          <div>
            <h2 id={titleId} className="text-lg font-semibold text-[var(--text-primary)]">
              Run Evaluators
            </h2>
            <p className="text-xs text-[var(--text-muted)] mt-0.5">
              Select evaluators to run on this listing. They will execute in
              parallel.
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded-[6px] p-1 text-[var(--text-muted)] hover:bg-[var(--interactive-secondary)] hover:text-[var(--text-primary)] transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* LLM config */}
        <div className="shrink-0 px-6 py-4 border-b border-[var(--border-subtle)]">
          <LlmModelSelect callSite="chat_text" value={llmPick} onChange={setLlmPick} />
        </div>

        <EvaluatorPickerList
          evaluators={evaluators}
          selectedIds={selected}
          onToggle={toggleEvaluator}
          onSelectAll={selectAll}
          onSelectNone={selectNone}
          emptyText="No evaluators configured for this listing."
        />

        {/* Footer */}
        <div className="shrink-0 px-6 py-4 border-t border-[var(--border-subtle)] flex items-center justify-between">
          <span className="text-xs text-[var(--text-muted)]">
            {selected.size} of {evaluators.length} selected
          </span>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={onClose}>
              Cancel
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={selected.size === 0 || !selectedModel || !selectedProvider}
              icon={PlayCircle}
            >
              Run {selected.size} Evaluator{selected.size !== 1 ? "s" : ""}
            </Button>
          </div>
        </div>
    </RightSlideOverShell>
  );
}

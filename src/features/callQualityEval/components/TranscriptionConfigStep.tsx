import { Info } from 'lucide-react';
import { Select, Switch } from '@/components/ui';
import type { SelectOption } from '@/components/ui';

const LANGUAGE_OPTIONS: SelectOption[] = [
  { value: 'hi', label: 'Hindi' },
  { value: 'en', label: 'English' },
  { value: 'hi-en', label: 'Hindi-English (Mixed)' },
  { value: 'auto', label: 'Auto-detect' },
];

const SCRIPT_OPTIONS: SelectOption[] = [
  { value: 'auto', label: 'Auto-detect' },
  { value: 'devanagari', label: 'Devanagari' },
  { value: 'latin', label: 'Latin (Romanized)' },
];

const TARGET_SCRIPT_OPTIONS: SelectOption[] = [
  { value: 'latin', label: 'Latin (Romanized)' },
  { value: 'devanagari', label: 'Devanagari' },
];

export interface TranscriptionConfig {
  language: string;
  script: string;
  forceRetranscribe: boolean;
  preserveCodeSwitching: boolean;
  speakerDiarization: boolean;
  transliterate: boolean;
  targetScript: string;
}

interface TranscriptionConfigStepProps {
  config: TranscriptionConfig;
  onChange: (updates: Partial<TranscriptionConfig>) => void;
  totalCalls: number;
}

function ToggleRow({
  label,
  description,
  checked,
  onChange,
}: {
  label: string;
  description: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <span className="text-[13px] font-medium text-[var(--text-primary)]">{label}</span>
        <p className="text-[11px] text-[var(--text-muted)]">{description}</p>
      </div>
      <Switch checked={checked} onCheckedChange={onChange} size="sm" className="mt-0.5 shrink-0" />
    </div>
  );
}

export function TranscriptionConfigStep({ config, onChange, totalCalls }: TranscriptionConfigStepProps) {
  return (
    <div className="space-y-4">
      {/* Info callout */}
      <div className="flex items-start gap-2.5 rounded-md border border-blue-500/20 bg-blue-500/5 px-3 py-2.5">
        <Info className="h-4 w-4 text-blue-400 mt-0.5 shrink-0" />
        <p className="text-[12px] text-[var(--text-secondary)]">
          Speech in each recording is converted to text before evaluation. Choose the spoken language and script; calls that already have a transcript are reused unless you force re-transcription.
        </p>
      </div>

      {/* Language */}
      <div>
        <label className="block text-[13px] font-medium text-[var(--text-primary)] mb-1.5">Language</label>
        <Select value={config.language} onChange={(language) => onChange({ language })} options={LANGUAGE_OPTIONS} />
      </div>

      {/* Source script */}
      <div>
        <label className="block text-[13px] font-medium text-[var(--text-primary)] mb-1.5">Source script</label>
        <Select value={config.script} onChange={(script) => onChange({ script })} options={SCRIPT_OPTIONS} />
      </div>

      {/* Toggles */}
      <div className="border-t border-[var(--border-subtle)] pt-3 mt-1 space-y-3">
        <ToggleRow
          label="Speaker diarization"
          description="Label each turn as agent or lead."
          checked={config.speakerDiarization}
          onChange={(v) => onChange({ speakerDiarization: v })}
        />
        <ToggleRow
          label="Preserve code-switching"
          description="Keep Hindi ↔ English mixing exactly as spoken."
          checked={config.preserveCodeSwitching}
          onChange={(v) => onChange({ preserveCodeSwitching: v })}
        />
        <ToggleRow
          label="Force re-transcription"
          description="Re-transcribe even when a transcript already exists."
          checked={config.forceRetranscribe}
          onChange={(v) => onChange({ forceRetranscribe: v })}
        />
        <ToggleRow
          label="Transliterate transcript"
          description="Also produce the transcript in another script (same language) — handy for romanizing Devanagari. Runs on the evaluation model."
          checked={config.transliterate}
          onChange={(v) => onChange({ transliterate: v })}
        />
      </div>

      {/* Target script — only when transliteration is on */}
      {config.transliterate && (
        <div>
          <label className="block text-[13px] font-medium text-[var(--text-primary)] mb-1.5">Target script</label>
          <Select value={config.targetScript} onChange={(targetScript) => onChange({ targetScript })} options={TARGET_SCRIPT_OPTIONS} />
          <p className="mt-1 text-[11px] text-[var(--text-muted)]">Text already in this script is returned unchanged.</p>
        </div>
      )}

      {/* Stats summary — bottom, mirrors Select Calls */}
      <div className="flex gap-4 text-xs">
        <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
          <div className="text-[10px] font-medium text-[var(--text-muted)] uppercase">Total calls</div>
          <div className="text-sm font-semibold text-[var(--text-primary)]">{totalCalls}</div>
        </div>
        <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
          <div className="text-[10px] font-medium text-[var(--text-muted)] uppercase">Need transcription</div>
          <div className="text-sm font-semibold text-[var(--text-primary)]">{totalCalls}</div>
        </div>
      </div>
    </div>
  );
}

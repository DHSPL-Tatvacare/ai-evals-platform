import { Info } from 'lucide-react';
import { Combobox, Switch, Tooltip } from '@/components/ui';
import type { ComboboxOption } from '@/components/ui';
import { LANGUAGES, getLanguageLabel } from '@/constants/languages';
import { SCRIPTS } from '@/constants/scripts';

// Full curated registries (flags + native names), shared with the voice-rx flow.
const LANGUAGE_OPTIONS: ComboboxOption[] = LANGUAGES.map((l) => ({
  value: l.code,
  label: getLanguageLabel(l),
  searchText: `${l.name} ${l.nativeName} ${l.code}`,
}));

const SCRIPT_OPTIONS: ComboboxOption[] = SCRIPTS.map((s) => ({
  value: s.id,
  label: s.name,
}));

const TARGET_SCRIPT_OPTIONS: ComboboxOption[] = SCRIPTS.filter((s) => s.id !== 'auto').map((s) => ({
  value: s.id,
  label: s.name,
}));

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

function LabelWithInfo({ label, info }: { label: string; info: string }) {
  return (
    <div className="flex items-center gap-1.5 mb-1.5">
      <span className="text-[13px] font-medium text-[var(--text-primary)]">{label}</span>
      <Tooltip content={info} position="top" maxWidth={320}>
        <Info
          aria-label={`${label} info`}
          className="h-3.5 w-3.5 text-[var(--text-muted)] hover:text-[var(--text-secondary)] cursor-help"
        />
      </Tooltip>
    </div>
  );
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
      <div className="flex items-start gap-2.5 rounded-md border border-[var(--border-info)] bg-[var(--surface-info)] px-3 py-2.5">
        <Info className="h-4 w-4 text-[var(--color-info)] mt-0.5 shrink-0" />
        <p className="text-[12px] text-[var(--text-secondary)]">
          Speech in each recording is converted to text before evaluation. Choose the spoken language and script; calls that already have a transcript are reused unless you force re-transcription.
        </p>
      </div>

      {/* Language */}
      <div>
        <LabelWithInfo
          label="Language"
          info="The language actually spoken on the calls — e.g. Hindi, Tamil, English. Pick a specific language for best accuracy, or Auto-detect to let the model identify it per call."
        />
        <Combobox
          options={LANGUAGE_OPTIONS}
          value={config.language}
          onChange={(language) => onChange({ language })}
          placeholder="Select language..."
        />
      </div>

      {/* Source script */}
      <div>
        <LabelWithInfo
          label="Source script"
          info="The writing system the transcript comes out in. The same language can be written in different scripts — e.g. Hindi in Devanagari (कैसे हो) or in Latin/Roman letters (kaise ho). Auto-detect lets the model choose based on the audio."
        />
        <Combobox
          options={SCRIPT_OPTIONS}
          value={config.script}
          onChange={(script) => onChange({ script })}
          placeholder="Select source script..."
        />
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
          description="Keep mixed-language speech exactly as spoken."
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
          label="Normalize transcript"
          description="Transliterate the transcript into the target script — same language, different script (e.g. romanize Devanagari). Runs on the evaluation model."
          checked={config.transliterate}
          onChange={(v) => onChange({ transliterate: v })}
        />
      </div>

      {/* Target script — only when transliteration is on */}
      {config.transliterate && (
        <div>
          <label className="block text-[13px] font-medium text-[var(--text-primary)] mb-1.5">Target script</label>
          <Combobox
            options={TARGET_SCRIPT_OPTIONS}
            value={config.targetScript}
            onChange={(targetScript) => onChange({ targetScript })}
            placeholder="Select target script..."
          />
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

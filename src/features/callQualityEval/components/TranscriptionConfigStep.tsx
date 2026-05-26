import { Select, Switch } from '@/components/ui';
import type { SelectOption } from '@/components/ui';
import {
  WizardStepLayout,
  WizardSection,
  WizardFieldRow,
  WizardMetric,
} from '@/features/evalRuns/components/WizardStepLayout';

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

export function TranscriptionConfigStep({ config, onChange, totalCalls }: TranscriptionConfigStepProps) {
  return (
    <WizardStepLayout
      eyebrow="Transcription"
      title="Configure transcription"
      description="Calls without a transcript are transcribed before evaluation."
    >
      <WizardSection
        aside={
          <div className="flex gap-2">
            <WizardMetric label="Total calls" value={totalCalls} />
            <WizardMetric label="Need transcription" value={totalCalls} />
          </div>
        }
      >
        <WizardFieldRow
          title="Language"
          description="Spoken language of the calls. Auto-detect inspects each recording."
          control={<Select value={config.language} onChange={(language) => onChange({ language })} options={LANGUAGE_OPTIONS} size="sm" />}
        />
        <WizardFieldRow
          title="Source script"
          description="Script the call is spoken in. Used when transliterating."
          control={<Select value={config.script} onChange={(script) => onChange({ script })} options={SCRIPT_OPTIONS} size="sm" />}
        />
        <WizardFieldRow
          title="Speaker diarization"
          description="Label each turn as agent or lead."
          control={<Switch checked={config.speakerDiarization} onCheckedChange={(v) => onChange({ speakerDiarization: v })} size="sm" />}
        />
        <WizardFieldRow
          title="Preserve code-switching"
          description="Keep Hindi ↔ English mixing exactly as spoken."
          control={<Switch checked={config.preserveCodeSwitching} onCheckedChange={(v) => onChange({ preserveCodeSwitching: v })} size="sm" />}
        />
        <WizardFieldRow
          title="Force re-transcription"
          description="Re-transcribe even when a transcript already exists."
          control={<Switch checked={config.forceRetranscribe} onCheckedChange={(v) => onChange({ forceRetranscribe: v })} size="sm" />}
        />
      </WizardSection>
    </WizardStepLayout>
  );
}

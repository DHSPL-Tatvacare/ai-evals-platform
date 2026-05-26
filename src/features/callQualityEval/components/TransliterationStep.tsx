import { Select, Switch } from '@/components/ui';
import type { SelectOption } from '@/components/ui';
import {
  WizardStepLayout,
  WizardSection,
  WizardFieldRow,
} from '@/features/evalRuns/components/WizardStepLayout';
import type { TranscriptionConfig } from './TranscriptionConfigStep';

const TARGET_SCRIPT_OPTIONS: SelectOption[] = [
  { value: 'latin', label: 'Latin (Romanized)' },
  { value: 'devanagari', label: 'Devanagari' },
];

interface TransliterationStepProps {
  config: TranscriptionConfig;
  onChange: (updates: Partial<TranscriptionConfig>) => void;
}

export function TransliterationStep({ config, onChange }: TransliterationStepProps) {
  return (
    <WizardStepLayout
      eyebrow="Transliteration"
      title="Transliterate the transcript"
      description="Optionally convert the transcript into another script for easier reading. Same language — only the script changes."
    >
      <WizardSection>
        <WizardFieldRow
          title="Transliterate transcript"
          description="Runs a third model pass to convert the transcript into the target script. The original is always kept; the result view lets you switch between them."
          control={<Switch checked={config.transliterate} onCheckedChange={(v) => onChange({ transliterate: v })} size="sm" />}
        />
        {config.transliterate && (
          <WizardFieldRow
            title="Target script"
            description="Script to transliterate into. Text already in this script is returned unchanged."
            control={<Select value={config.targetScript} onChange={(targetScript) => onChange({ targetScript })} options={TARGET_SCRIPT_OPTIONS} size="sm" />}
          />
        )}
      </WizardSection>
    </WizardStepLayout>
  );
}

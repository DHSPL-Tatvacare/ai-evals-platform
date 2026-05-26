import { LegacyLlmConfigCompat } from '@/components/ui';
import { LLMConfigStep, type LLMConfig } from '@/features/evalRuns/components/LLMConfigStep';
import { WizardSection, WizardStepLayout } from '@/features/evalRuns/components/WizardStepLayout';
import type { LLMProvider } from '@/services/api/aiSettingsApi';

interface ModelsStepProps {
  transcription: LLMConfig;
  evaluation: LLMConfig;
  transliterateEnabled: boolean;
  onTranscriptionChange: (c: LLMConfig) => void;
  onEvaluationChange: (c: LLMConfig) => void;
}

export function ModelsStep({
  transcription,
  evaluation,
  transliterateEnabled,
  onTranscriptionChange,
  onEvaluationChange,
}: ModelsStepProps) {
  return (
    <WizardStepLayout
      eyebrow="Models"
      title="Choose transcription and evaluation models"
      description="Transcription turns the recording into text and needs an audio-capable model. Evaluation scores the transcript and can be any text model."
    >
      <WizardSection title="Transcription model" description="Only audio-capable models are listed. Used to transcribe the call recording.">
        <LegacyLlmConfigCompat
          callSite="audio_transcription"
          provider={(transcription.provider || '') as LLMProvider | ''}
          onProviderChange={(v) => onTranscriptionChange({ ...transcription, provider: v, model: '' })}
          model={transcription.model}
          onModelChange={(model) => onTranscriptionChange({ ...transcription, model })}
          layout="rows"
        />
      </WizardSection>
      {/* Evaluation model reuses LLMConfigStep so temperature + thinking are preserved. */}
      <LLMConfigStep config={evaluation} onChange={onEvaluationChange} />
      {transliterateEnabled && (
        <WizardSection title="Transliteration model" description="The transliteration pass is text-only and reuses the evaluation model above.">
          <p className="text-xs text-[var(--text-muted)]">Transliteration runs on the evaluation model — no separate model needed.</p>
        </WizardSection>
      )}
    </WizardStepLayout>
  );
}

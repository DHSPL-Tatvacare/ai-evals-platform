import { LegacyLlmConfigCompat } from '@/components/ui';
import { LLMConfigStep, type LLMConfig } from '@/features/evalRuns/components/LLMConfigStep';
import { WizardSection, WizardStepLayout } from '@/features/evalRuns/components/WizardStepLayout';
import type { LLMProvider } from '@/services/api/aiSettingsApi';

interface ModelsStepProps {
  transcription: LLMConfig;
  evaluation: LLMConfig;
  onTranscriptionChange: (c: LLMConfig) => void;
  onEvaluationChange: (c: LLMConfig) => void;
}

export function ModelsStep({
  transcription,
  evaluation,
  onTranscriptionChange,
  onEvaluationChange,
}: ModelsStepProps) {
  return (
    <WizardStepLayout
      eyebrow="Models"
      title="Choose transcription and evaluation models"
      description="Transcription turns the recording into text and needs an audio-capable model. Evaluation scores the transcript and can be any text model."
    >
      <WizardSection title="Transcription Model" description="Only audio-capable models are listed. Used to transcribe the call recording.">
        <LegacyLlmConfigCompat
          callSite="audio_transcription"
          provider={(transcription.provider || '') as LLMProvider | ''}
          onProviderChange={(v) => onTranscriptionChange({ ...transcription, provider: v, model: '' })}
          model={transcription.model}
          onModelChange={(model) => onTranscriptionChange({ ...transcription, model })}
          layout="rows"
        />
      </WizardSection>
      <LLMConfigStep
        config={evaluation}
        onChange={onEvaluationChange}
        modelSectionTitle="Evaluation Model (LLM as a Judge)"
        modelSectionDescription="The model that scores each call against your rubrics. It also runs the normalization (transliteration) pass when that option is enabled in the Transcription step."
      />
    </WizardStepLayout>
  );
}

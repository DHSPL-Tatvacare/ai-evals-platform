import type { Run } from '@/types';
import type { KairaBotSettings } from '@/stores/appSettingsStore';

interface GlobalTimeouts {
  textOnly: number;
  withSchema: number;
  withAudio: number;
  withAudioAndSchema: number;
}

export function buildAdversarialRetryParams(args: {
  run: Run;
  kairaSettings: KairaBotSettings;
  timeouts: GlobalTimeouts;
  retryEvalIds: number[];
  sourceRunId: string;
  nameSuffix?: string;
}): Record<string, unknown> {
  const { run, kairaSettings, timeouts, retryEvalIds, sourceRunId, nameSuffix } = args;
  const batchMetadata = run.batch_metadata ?? {};

  return {
    name: `${run.name || 'Adversarial Stress Test'}${nameSuffix ? ` ${nameSuffix}` : ' Retry'}`,
    description: run.description || null,
    user_id: kairaSettings.kairaChatUserId,
    kaira_api_url: kairaSettings.kairaApiUrl,
    kaira_auth_token: kairaSettings.kairaAuthToken || null,
    kaira_timeout: (batchMetadata.kaira_timeout as number | undefined) ?? 120,
    test_count: 0,
    turn_delay: (batchMetadata.turn_delay as number | undefined) ?? 1.5,
    case_delay: (batchMetadata.case_delay as number | undefined) ?? 0,
    llm_provider: run.llm_provider,
    llm_model: run.llm_model,
    temperature: run.eval_temperature ?? 0.1,
    thinking: (batchMetadata.thinking as string | undefined) ?? 'low',
    parallel_cases: (batchMetadata.parallel_cases as boolean | undefined) || undefined,
    case_workers: (batchMetadata.case_workers as number | undefined) || undefined,
    flow_mode: (batchMetadata.flow_mode as string | undefined) || undefined,
    case_mode: 'saved',
    retry_eval_ids: retryEvalIds,
    source_run_id: sourceRunId,
    timeouts: {
      text_only: timeouts.textOnly,
      with_schema: timeouts.withSchema,
      with_audio: timeouts.withAudio,
      with_audio_and_schema: timeouts.withAudioAndSchema,
    },
  };
}

export function canSubmitAdversarialRun(kairaSettings: KairaBotSettings): boolean {
  return Boolean(
    kairaSettings.kairaApiUrl.trim() &&
      kairaSettings.kairaChatUserId.trim(),
  );
}

import type { EvaluatorOutputField } from '@/types';

/** Downstream-reachable keys produced by this node — `{save_as}.{field}`. */
export function downstreamKeys(
  namespace: string,
  fields: readonly EvaluatorOutputField[],
): string[] {
  return fields.filter((f) => f.key).map((f) => `${namespace}.${f.key}`);
}

interface SignatureParts {
  provider?: string | null;
  model?: string | null;
  prompt?: string;
  outputSchema?: readonly EvaluatorOutputField[];
  sampleText: string;
}

/** A stable signature of every input a dry-run depends on. When it changes
 *  after a run, the rendered result is stale and must be re-run. */
export function resultSignature(parts: SignatureParts): string {
  return JSON.stringify({
    provider: parts.provider ?? null,
    model: parts.model ?? null,
    prompt: parts.prompt ?? '',
    schema: (parts.outputSchema ?? []).map((f) => [f.key, f.type]),
    sample: parts.sampleText,
  });
}

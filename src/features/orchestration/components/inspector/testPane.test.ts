import { describe, expect, it } from 'vitest';

import type { EvaluatorOutputField } from '@/types';
import { downstreamKeys, resultSignature } from './testPane';

const field = (key: string, type = 'text'): EvaluatorOutputField =>
  ({ key, type }) as EvaluatorOutputField;

describe('downstreamKeys', () => {
  it('prefixes each field key with the save-as namespace', () => {
    expect(downstreamKeys('analysis', [field('sentiment'), field('confidence')])).toEqual([
      'analysis.sentiment',
      'analysis.confidence',
    ]);
  });

  it('skips fields without a key', () => {
    expect(downstreamKeys('analysis', [field(''), field('summary')])).toEqual([
      'analysis.summary',
    ]);
  });
});

describe('resultSignature', () => {
  const base = {
    provider: 'openai',
    model: 'gpt-4o',
    prompt: 'Classify {{x}}',
    outputSchema: [field('sentiment', 'enum')],
    sampleText: '{"x":1}',
  };

  it('is stable for unchanged inputs', () => {
    expect(resultSignature(base)).toBe(resultSignature({ ...base }));
  });

  it('changes when the prompt, model, schema, or sample changes', () => {
    const sig = resultSignature(base);
    expect(resultSignature({ ...base, prompt: 'New {{x}}' })).not.toBe(sig);
    expect(resultSignature({ ...base, model: 'gpt-4o-mini' })).not.toBe(sig);
    expect(resultSignature({ ...base, outputSchema: [field('sentiment', 'text')] })).not.toBe(sig);
    expect(resultSignature({ ...base, sampleText: '{"x":2}' })).not.toBe(sig);
  });
});

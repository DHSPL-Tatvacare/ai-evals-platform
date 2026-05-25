import { describe, expect, it } from 'vitest';

import type { UpstreamField } from '@/services/api/orchestration';
import {
  buildGeneratePromptBody,
  buildGenerateSchemaBody,
  composeGenerateIdea,
  variableNamesForGenerate,
} from './generateContext';

const FIELDS: UpstreamField[] = [
  { path: 'first_name', type: 'text', source: 'cohort', sourceNodeId: 'n' },
  // dataset fields DO carry a real sample value — it must never leave for a draft.
  { path: 'phone', type: 'text', source: 'dataset', sourceNodeId: 'n', sampleValue: '+91-555-SECRETVALUE' },
];

describe('variableNamesForGenerate', () => {
  it('returns paths only, never sample values', () => {
    expect(variableNamesForGenerate(FIELDS)).toEqual(['first_name', 'phone']);
  });

  it('honors the excluded set', () => {
    expect(variableNamesForGenerate(FIELDS, new Set(['phone']))).toEqual(['first_name']);
  });
});

describe('composeGenerateIdea', () => {
  it('appends the variable names as {{tokens}} to the user idea', () => {
    const idea = composeGenerateIdea('Classify the sentiment', ['first_name', 'last_message']);
    expect(idea).toContain('Classify the sentiment');
    expect(idea).toContain('{{first_name}}');
    expect(idea).toContain('{{last_message}}');
  });

  it('returns the user idea unchanged when there are no variables', () => {
    expect(composeGenerateIdea('Just classify', [])).toBe('Just classify');
  });
});

describe('buildGeneratePromptBody — privacy', () => {
  it('carries variable NAMES in user_idea and NEVER a sample value', () => {
    const body = buildGeneratePromptBody({
      provider: 'openai',
      model: 'gpt-4o',
      userIdea: 'Classify sentiment',
      fields: FIELDS,
    });
    expect(body.promptType).toBe('extraction');
    expect(body.userIdea).toContain('{{first_name}}');
    expect(body.userIdea).toContain('{{phone}}');
    // The dataset sample value must never appear anywhere in the request.
    expect(JSON.stringify(body)).not.toContain('SECRETVALUE');
  });

  it('excludes toggled-off variables from the request', () => {
    const body = buildGeneratePromptBody({
      provider: 'openai',
      model: 'gpt-4o',
      userIdea: 'x',
      fields: FIELDS,
      excluded: new Set(['phone']),
    });
    expect(body.userIdea).toContain('{{first_name}}');
    expect(body.userIdea).not.toContain('{{phone}}');
  });
});

describe('buildGenerateSchemaBody — privacy', () => {
  it('uses extraction prompt type and leaks no sample value', () => {
    const body = buildGenerateSchemaBody({
      provider: 'openai',
      model: 'gpt-4o',
      userIdea: 'Fields for sentiment',
      fields: FIELDS,
    });
    expect(body.promptType).toBe('extraction');
    expect(JSON.stringify(body)).not.toContain('SECRETVALUE');
  });
});

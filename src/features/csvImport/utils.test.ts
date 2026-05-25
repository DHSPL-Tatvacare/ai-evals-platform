import { describe, expect, it } from 'vitest';

import { analyzeDatasetHeaders } from './utils';

describe('analyzeDatasetHeaders', () => {
  it('trims headers and passes clean input', () => {
    const result = analyzeDatasetHeaders(['  phone ', 'name', 'lead_id']);
    expect(result.columns).toEqual(['phone', 'name', 'lead_id']);
    expect(result.interiorBlankPositions).toEqual([]);
    expect(result.duplicates).toEqual([]);
  });

  it('drops trailing blank columns without flagging them', () => {
    const result = analyzeDatasetHeaders(['phone', 'name', '', '  ']);
    expect(result.columns).toEqual(['phone', 'name']);
    expect(result.interiorBlankPositions).toEqual([]);
    expect(result.duplicates).toEqual([]);
  });

  it('flags an interior blank by its 1-based position', () => {
    const result = analyzeDatasetHeaders(['phone', '', 'name']);
    expect(result.columns).toEqual(['phone', '', 'name']);
    expect(result.interiorBlankPositions).toEqual([2]);
  });

  it('flags case-sensitive duplicate column names', () => {
    const result = analyzeDatasetHeaders(['phone', 'name', 'phone']);
    expect(result.duplicates).toEqual(['phone']);
    expect(result.columns).toEqual(['phone', 'name', 'phone']);
  });

  it('treats different cases as distinct names', () => {
    const result = analyzeDatasetHeaders(['Phone', 'phone']);
    expect(result.duplicates).toEqual([]);
  });

  it('returns empty columns for an all-blank header row', () => {
    const result = analyzeDatasetHeaders(['', '  ', '']);
    expect(result.columns).toEqual([]);
    expect(result.interiorBlankPositions).toEqual([]);
    expect(result.duplicates).toEqual([]);
  });
});

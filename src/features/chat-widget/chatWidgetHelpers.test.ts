import { test, expect } from 'vitest';

import {
  appendTextPart,
  buildComposedReportOutline,
  getToolPartIndex,
  isChartPayload,
  partsFromStoredMessage,
  shouldApplyRuntimeSeq,
  upsertToolPart,
} from './chatWidgetHelpers';

test('upsertToolPart appends a new tool part', () => {
  const result = upsertToolPart([], {
    type: 'tool-call',
    toolCallId: 'tc_1',
    toolName: 'data_query',
    state: 'executing',
  });

  expect(result).toEqual([{
    type: 'tool-call',
    toolCallId: 'tc_1',
    toolName: 'data_query',
    state: 'executing',
  }]);
});

test('upsertToolPart updates an existing tool part by toolCallId', () => {
  const result = upsertToolPart(
    [{
      type: 'tool-call',
      toolCallId: 'tc_1',
      toolName: 'data_query',
      state: 'executing',
    }],
    {
      type: 'tool-call',
      toolCallId: 'tc_1',
      toolName: 'data_query',
      state: 'completed',
      summary: '7 rows',
      durationMs: 120,
    },
  );

  expect(result).toEqual([{
    type: 'tool-call',
    toolCallId: 'tc_1',
    toolName: 'data_query',
    state: 'completed',
    summary: '7 rows',
    durationMs: 120,
  }]);
});

test('upsertToolPart keeps repeated tool names separate when toolCallId differs', () => {
  const result = upsertToolPart(
    [{
      type: 'tool-call',
      toolCallId: 'tc_1',
      toolName: 'data_query',
      state: 'completed',
      summary: '7 rows',
    }],
    {
      type: 'tool-call',
      toolCallId: 'tc_2',
      toolName: 'data_query',
      state: 'executing',
    },
  );

  expect(result).toEqual([
    {
      type: 'tool-call',
      toolCallId: 'tc_1',
      toolName: 'data_query',
      state: 'completed',
      summary: '7 rows',
    },
    {
      type: 'tool-call',
      toolCallId: 'tc_2',
      toolName: 'data_query',
      state: 'executing',
    },
  ]);
});

test('getToolPartIndex only matches by toolCallId', () => {
  expect(
    getToolPartIndex(
      [
        { type: 'tool-call', toolCallId: 'tc_1', toolName: 'data_query', state: 'completed' },
        { type: 'tool-call', toolCallId: 'tc_2', toolName: 'data_query', state: 'executing' },
      ],
      'tc_2',
    ),
  ).toBe(1);
});

test('appendTextPart merges consecutive text parts', () => {
  expect(
    appendTextPart(
      [{ type: 'text', content: 'Hello' }],
      ' world',
    ),
  ).toEqual([{ type: 'text', content: 'Hello world' }]);
});

test('shouldApplyRuntimeSeq rejects duplicate or out-of-order events', () => {
  expect(shouldApplyRuntimeSeq(4, 4)).toBe(false);
  expect(shouldApplyRuntimeSeq(4, 3)).toBe(false);
  expect(shouldApplyRuntimeSeq(4, 5)).toBe(true);
});

test('buildComposedReportOutline formats a readable section list', () => {
  expect(
    buildComposedReportOutline({
      reportName: 'Weekly Review',
      sections: [
        { id: 'summary', type: 'summary_cards', title: 'Summary Cards' },
        { id: 'compliance', type: 'compliance_table', title: 'Compliance Table' },
      ],
    }),
  ).toBe('Weekly Review\n- Summary Cards (summary_cards)\n- Compliance Table (compliance_table)');
});

test('partsFromStoredMessage ignores legacy tool calls without toolCallId', () => {
  expect(
    partsFromStoredMessage('Done', {
      toolCalls: [
        {
          name: 'data_query',
          summary: '7 rows',
          detail: { executionMs: 12, rowCount: 7 },
        },
      ],
    }),
  ).toEqual([{ type: 'text', content: 'Done' }]);
});

test('isChartPayload accepts new-shape chart payloads', () => {
  const payload = {
    kind: 'chart',
    spec: { mark: 'bar', encoding: { x: { field: 'x' }, y: { field: 'y' } } },
    data: [{ x: 'a', y: 1 }],
  };
  expect(isChartPayload(payload)).toBe(true);
});

test('isChartPayload rejects legacy pre-contract chart payloads', () => {
  const legacy = {
    spec: {
      type: 'bar',
      title: 'Pass rate',
      xKey: 'evaluator',
      yKey: 'pass_rate',
      seriesKeys: [],
      xLabel: 'Evaluator',
      yLabel: 'Pass Rate',
    },
    data: [{ evaluator: 'E1', pass_rate: 80 }],
    sqlQuery: 'SELECT ...',
    sourceQuestion: 'show pass rate',
  };
  expect(isChartPayload(legacy)).toBe(false);
});

test('partsFromStoredMessage drops unsupported legacy chart metadata', () => {
  expect(
    partsFromStoredMessage('Done', {
      // Phase 1: persisted metadata carries ``artifacts[]``; an unknown-
      // pack or malformed-payload artifact is dropped silently so the
      // message renders as text-only.
      artifacts: [
        {
          pack_id: 'analytics',
          contract_id: 'analytics.chart.v1',
          payload: {
            spec: { type: 'bar', xKey: 'x' },
            data: [{ x: 'a', y: 1 }],
          },
        },
      ] as never,
    }),
  ).toEqual([{ type: 'text', content: 'Done' }]);
});

test('partsFromStoredMessage renders an analytics.chart.v1 artifact as a chart part', () => {
  const parts = partsFromStoredMessage('Done', {
    artifacts: [
      {
        pack_id: 'analytics',
        contract_id: 'analytics.chart.v1',
        payload: {
          kind: 'chart',
          spec: { mark: 'bar', encoding: { x: { field: 'x' }, y: { field: 'y' } } },
          data: [{ x: 'a', y: 1 }],
        },
      },
    ],
  });

  expect(parts).toEqual([
    { type: 'text', content: 'Done' },
    {
      type: 'chart',
      payload: {
        kind: 'chart',
        spec: { mark: 'bar', encoding: { x: { field: 'x' }, y: { field: 'y' } } },
        data: [{ x: 'a', y: 1 }],
      },
    },
  ]);
});

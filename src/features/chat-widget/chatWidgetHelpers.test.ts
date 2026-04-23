import { test, expect } from 'vitest';

import {
  appendTextPart,
  buildComposedReportOutline,
  getToolPartIndex,
  isChartPayload,
  jobBadgeFromOutcome,
  partsFromStoredMessage,
  shouldApplyRuntimeSeq,
  upsertJobBadgePart,
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

// ──────────────────────────────────────────────────────────────────────
// Phase 7 audit fixes (Gaps 4 + 5): JobBadge synthesis + persistence.
// ──────────────────────────────────────────────────────────────────────

test('jobBadgeFromOutcome returns null when outcome has no job slot', () => {
  expect(jobBadgeFromOutcome(undefined, 'data_query', 'ok')).toBeNull();
  expect(jobBadgeFromOutcome({ kind: 'read' }, 'data_query', 'ok')).toBeNull();
  expect(jobBadgeFromOutcome({ job: {} }, 'x', 'y')).toBeNull();
  expect(jobBadgeFromOutcome({ job: { id: 'only-id' } }, 'x', 'y')).toBeNull();
  expect(jobBadgeFromOutcome({ job: { status: 'queued' } }, 'x', 'y')).toBeNull();
});

test('jobBadgeFromOutcome produces a JobBadgePart when envelope carries a job', () => {
  const badge = jobBadgeFromOutcome(
    { job: { id: 'job-abc-123', status: 'queued' } },
    'generate_report',
    'Running slow query',
  );
  expect(badge).toEqual({
    type: 'job-badge',
    jobId: 'job-abc-123',
    jobType: 'generate_report',
    status: 'queued',
    summary: 'Running slow query',
  });
});

test('upsertJobBadgePart updates status on same jobId, preserves existing resultHref', () => {
  const initial = [
    { type: 'job-badge' as const, jobId: 'j1', jobType: 'q', status: 'queued' as const, resultHref: '/jobs/j1' },
  ];
  const next = upsertJobBadgePart(initial, {
    type: 'job-badge',
    jobId: 'j1',
    jobType: 'q',
    status: 'running',
    summary: 'Crunching data',
  });
  expect(next).toEqual([
    {
      type: 'job-badge',
      jobId: 'j1',
      jobType: 'q',
      status: 'running',
      summary: 'Crunching data',
      resultHref: '/jobs/j1',
    },
  ]);
});

test('partsFromStoredMessage rehydrates a JobBadgePart from stored tool outcome', () => {
  const parts = partsFromStoredMessage('Working on it', {
    toolCalls: [
      {
        toolCallId: 'tc_1',
        name: 'generate_report',
        summary: 'Submitting',
        detail: { executionMs: 120 },
        outcome: {
          kind: 'job_submitted',
          capability: 'analytics',
          job: { id: 'job-1', status: 'running' },
        },
      },
    ],
  });
  // Tool part first, then the synthesized badge, then the text.
  expect(parts).toEqual([
    {
      type: 'tool-call',
      toolCallId: 'tc_1',
      toolName: 'generate_report',
      summary: 'Submitting',
      detail: { executionMs: 120 },
      state: 'completed',
      durationMs: 120,
    },
    {
      type: 'job-badge',
      jobId: 'job-1',
      jobType: 'generate_report',
      status: 'running',
      summary: 'Submitting',
    },
    { type: 'text', content: 'Working on it' },
  ]);
});

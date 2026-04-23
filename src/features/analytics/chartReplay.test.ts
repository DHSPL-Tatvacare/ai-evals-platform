import { describe, expect, it } from 'vitest';

import type { VegaLiteSpec } from '@/features/chat-widget/types';

import { validateChartPayload } from '@/features/chat-widget/types';

import { vegaLiteToRecharts } from './vegaLiteToRecharts';
import { toValidatedChartPayload } from './chartReplayValidation';
import type { SavedChart } from './types';

/**
 * Phase 4.6A — saved charts + dashboards replay through the same translator
 * used by live chat. These tests lock down the chat→save→replay round-trip.
 * Phase 6 §743 — replay additionally validates through the generated
 * ``validateChartPayload`` validator; invalid canonicals fall back cleanly.
 */

function savedConfigFor(
  payloadKind: 'chart',
  spec: VegaLiteSpec,
): SavedChart['chartConfig'] {
  return {
    canonical: {
      kind: payloadKind,
      // Stored canonical is the generated ``Spec`` shape (Pydantic
      // ``dict[str, Any]``). ``VegaLiteSpec`` is a structurally-
      // compatible subtype; the cast is a one-way lens for the test.
      spec: spec as unknown as SavedChart['chartConfig']['canonical'] extends { spec: infer S } ? S : never,
    },
    renderer: {
      type: 'bar',
      xKey: 'x',
      yKey: 'y',
      xLabel: 'X',
      yLabel: 'Y',
    },
  };
}

describe('saved-chart replay parity', () => {
  it('replays a simple bar spec to the same shape as live chat', () => {
    const spec: VegaLiteSpec = {
      mark: 'bar',
      encoding: {
        x: { field: 'evaluator', type: 'nominal', axis: { title: 'Evaluator' } },
        y: { field: 'pass_rate', type: 'quantitative', axis: { title: 'Pass Rate (%)' } },
      },
    };
    const data = [
      { evaluator: 'E1', pass_rate: 80 },
      { evaluator: 'E2', pass_rate: 60 },
    ];
    const savedConfig = savedConfigFor('chart', spec);

    const liveProps = vegaLiteToRecharts(spec, data);
    const validated = toValidatedChartPayload(savedConfig.canonical, data);
    expect(validated).not.toBeNull();
    const replayedProps = vegaLiteToRecharts(
      validated!.spec as unknown as VegaLiteSpec,
      validated!.data,
    );

    expect(replayedProps).toEqual(liveProps);
  });

  it('replays a grouped_bar (xOffset+color) spec with wide-row pivot parity', () => {
    const spec: VegaLiteSpec = {
      mark: 'bar',
      encoding: {
        x: { field: 'day', type: 'nominal' },
        y: { field: 'count', type: 'quantitative' },
        xOffset: { field: 'status' },
        color: { field: 'status', type: 'nominal' },
      },
    };
    const data = [
      { day: 'Mon', status: 'PASS', count: 2 },
      { day: 'Mon', status: 'FAIL', count: 1 },
      { day: 'Tue', status: 'PASS', count: 3 },
    ];
    const savedConfig = savedConfigFor('chart', spec);
    const validated = toValidatedChartPayload(savedConfig.canonical, data);
    expect(validated).not.toBeNull();
    const live = vegaLiteToRecharts(spec, data);
    const replayed = vegaLiteToRecharts(
      validated!.spec as unknown as VegaLiteSpec,
      validated!.data,
    );
    expect(replayed.type).toBe('grouped_bar');
    expect(replayed).toEqual(live);
    expect(replayed.seriesKeys).not.toEqual(['status']);
  });

  it('replays a fold-transform multi-line spec without reshaping data', () => {
    const spec: VegaLiteSpec = {
      transform: [{ fold: ['pass_rate', 'fail_rate'], as: ['measure', 'value'] }],
      mark: 'line',
      encoding: {
        x: { field: 'day', type: 'temporal' },
        y: { field: 'value', type: 'quantitative' },
        color: { field: 'measure', type: 'nominal' },
      },
    };
    const data = [
      { day: '2025-01-01', pass_rate: 80, fail_rate: 20 },
      { day: '2025-01-02', pass_rate: 70, fail_rate: 30 },
    ];
    const savedConfig = savedConfigFor('chart', spec);
    const validated = toValidatedChartPayload(savedConfig.canonical, data);
    expect(validated).not.toBeNull();
    const replayed = vegaLiteToRecharts(
      validated!.spec as unknown as VegaLiteSpec,
      validated!.data,
    );
    expect(replayed.type).toBe('line');
    expect(replayed.seriesKeys).toEqual(['pass_rate', 'fail_rate']);
    expect(replayed.data).toBe(data);
  });

  it('does not touch legacy charts that lack kind/spec (backward-compat path)', () => {
    const legacy: SavedChart['chartConfig'] = {
      renderer: {
        type: 'bar',
        xKey: 'evaluator',
        yKey: 'pass_rate',
        xLabel: 'Evaluator',
        yLabel: 'Pass Rate',
      },
    };
    expect(legacy.canonical).toBeUndefined();
    expect(toValidatedChartPayload(legacy.canonical, [])).toBeNull();
  });
});

describe('Phase 6 §743 — replay validator gate', () => {
  it('accepts a valid canonical + data pair', () => {
    const spec: VegaLiteSpec = {
      mark: 'bar',
      encoding: {
        x: { field: 'evaluator', type: 'nominal' },
        y: { field: 'pass_rate', type: 'quantitative' },
      },
    };
    const config = savedConfigFor('chart', spec);
    const data = [{ evaluator: 'E1', pass_rate: 80 }];
    const validated = toValidatedChartPayload(config.canonical, data);
    expect(validated).not.toBeNull();
    expect(validated!.kind).toBe('chart');
    expect(validated!.data).toBe(data);
  });

  it('rejects a missing canonical (legacy / renderer-only charts)', () => {
    expect(toValidatedChartPayload(null, [])).toBeNull();
    expect(toValidatedChartPayload(undefined, [])).toBeNull();
  });

  it('rejects a canonical with an unknown kind', () => {
    // Cast through ``unknown`` — production code cannot pass this shape
    // via types, but the runtime validator must still reject drift from
    // the wire.
    const bogus = { kind: 'pie', spec: { mark: 'arc' } } as unknown as
      SavedChart['chartConfig']['canonical'];
    expect(toValidatedChartPayload(bogus, [])).toBeNull();
  });

  it('rejects an assembled payload carrying extra top-level fields', () => {
    // Phase 6 §743: replay no longer tolerates unknown fields silently.
    // The strict ``additionalProperties: false`` lives on the Pydantic
    // union variants; exercise it directly with the generated validator.
    const extraTopLevel = {
      kind: 'chart',
      spec: { mark: 'bar' },
      data: [{ x: 1 }],
      unexpected_field: 'should fail',
    };
    expect(validateChartPayload(extraTopLevel)).toBe(false);
  });

  it('rejects a canonical whose data is not an array', () => {
    const spec: VegaLiteSpec = { mark: 'bar' };
    const config = savedConfigFor('chart', spec);
    // Assemble a deliberately broken payload by smuggling non-array data
    // into the validator through the public helper signature.
    const notArray = ('oops' as unknown) as Record<string, unknown>[];
    expect(toValidatedChartPayload(config.canonical, notArray)).toBeNull();
  });
});

/**
 * Phase 6 §743 — saved-chart detail and dashboard-tile replay paths
 * validate through the same generated ``ajv`` validator chat/runtime
 * already use. The stored canonical carries ``kind`` + ``spec`` only;
 * rows arrive separately from the data route. This helper assembles a
 * full ``ChartPayloadChart`` from the two halves, runs the generated
 * validator, and returns the validated payload (or ``null`` if the
 * canonical is absent / the assembled payload fails validation).
 *
 * Callers render the validated result through the same
 * ``vegaLiteToRecharts`` translator the live chat path uses, so the
 * saved-chart and dashboard replay paths never trust a shape-check.
 */
import type { ChartPayloadChart } from '@/features/chat-widget/types';
import { validateChartPayload } from '@/features/chat-widget/types';

import type { SavedChartCanonicalConfig } from './types';

export function toValidatedChartPayload(
  canonical: SavedChartCanonicalConfig | null | undefined,
  data: Record<string, unknown>[],
): ChartPayloadChart | null {
  if (!canonical || canonical.kind !== 'chart' || !canonical.spec) {
    return null;
  }
  const assembled = {
    kind: 'chart' as const,
    spec: canonical.spec,
    data,
  };
  if (!validateChartPayload(assembled)) {
    return null;
  }
  // Narrowed by the generated validator's type predicate. The union
  // only has one ``kind: 'chart'`` variant, so this cast is sound.
  return assembled as ChartPayloadChart;
}

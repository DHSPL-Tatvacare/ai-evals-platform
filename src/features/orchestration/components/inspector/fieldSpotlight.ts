import { createContext, useContext, useMemo } from 'react';

/** Minimal shape of an upstream field needed to map a dropdown option back to
 *  the canvas node that produces it. Mirrors `UpstreamField` from the
 *  orchestration API without coupling this module to the full response type. */
export interface FieldNodeRef {
  path: string;
  sourceNodeId: string;
}

/** Build a `path -> sourceNodeId` lookup from resolved upstream fields. The
 *  dropdown options carry only the `path` string, so this index is what lets
 *  a hover resolve to the React Flow node id without parsing the path. */
export function indexFieldNodeIds(
  fields: readonly FieldNodeRef[],
): Map<string, string> {
  const index = new Map<string, string>();
  for (const f of fields) {
    if (f.path && f.sourceNodeId) index.set(f.path, f.sourceNodeId);
  }
  return index;
}

export interface FieldSpotlightValue {
  enter(path: string): void;
  leave(): void;
}

export const NOOP_FIELD_SPOTLIGHT: FieldSpotlightValue = {
  enter: () => {},
  leave: () => {},
};

export const FieldSpotlightContext =
  createContext<FieldSpotlightValue>(NOOP_FIELD_SPOTLIGHT);

/** Returns Combobox-ready hover props. Spread onto any field-picking Combobox
 *  (`<Combobox {...useFieldSpotlight()} />`) to spotlight the source node while
 *  an option is hovered. No-ops outside a `FieldSpotlightProvider`. */
export function useFieldSpotlight(): {
  onOptionHover: (value: string) => void;
  onOptionHoverLeave: () => void;
} {
  const ctx = useContext(FieldSpotlightContext);
  return useMemo(
    () => ({
      onOptionHover: (value: string) => ctx.enter(value),
      onOptionHoverLeave: () => ctx.leave(),
    }),
    [ctx],
  );
}

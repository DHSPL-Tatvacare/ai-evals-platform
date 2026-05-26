import { useCallback, useRef } from 'react';

import { useWorkflowBuilderStore } from '@/features/orchestration/store/workflowBuilderStore';

const MIN_WIDTH = 480;
const MAX_WIDTH = 1280;

/** Pointer-drag resize for the right-docked inspector, persisting width to
 *  `workflowBuilderStore.inspectorWidth`. Mirrors LlmExtractInspector's logic
 *  so any preview-bearing inspector can opt into the same wide, resizable shell. */
export function useResizableInspectorWidth() {
  const inspectorWidth = useWorkflowBuilderStore((s) => s.inspectorWidth);
  const setInspectorWidth = useWorkflowBuilderStore((s) => s.setInspectorWidth);
  const dragRef = useRef<{ startX: number; startWidth: number } | null>(null);

  const onResizePointerDown = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      e.preventDefault();
      dragRef.current = { startX: e.clientX, startWidth: inspectorWidth };
      e.currentTarget.setPointerCapture(e.pointerId);
    },
    [inspectorWidth],
  );

  const onResizePointerMove = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      const drag = dragRef.current;
      if (!drag) return;
      // Panel docks on the right: dragging the left edge leftward widens it.
      const next = drag.startWidth + (drag.startX - e.clientX);
      setInspectorWidth(Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, next)));
    },
    [setInspectorWidth],
  );

  const onResizePointerUp = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    dragRef.current = null;
    e.currentTarget.releasePointerCapture(e.pointerId);
  }, []);

  const width = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, inspectorWidth));

  return { width, onResizePointerDown, onResizePointerMove, onResizePointerUp };
}

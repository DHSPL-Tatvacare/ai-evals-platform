import { useEffect } from 'react';
import { useUIStore } from '@/stores';

/**
 * Registers a right-edge overlay with the UI store so the Sherlock chat FAB
 * (and any other right-anchored surface) can hide while an overlay is open.
 *
 * Use this in every overlay/drawer/sheet that slides in from the right edge.
 * The counter is ref-counted — multiple overlays compose safely.
 */
export function useRightOverlay(open: boolean): void {
  useEffect(() => {
    if (!open) return;
    useUIStore.getState().pushRightOverlay();
    return () => useUIStore.getState().popRightOverlay();
  }, [open]);
}

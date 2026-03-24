/**
 * Guide-compatible useTheme hook — delegates to the main app's theme system.
 * Returns the same { theme, toggle } interface the guide components expect,
 * with `theme` always resolved to 'light' | 'dark' (never 'system').
 */
import { useCallback, useMemo } from 'react';
import { useGlobalSettingsStore } from '@/stores/globalSettingsStore';

type Theme = 'light' | 'dark';

function resolveTheme(mode: string): Theme {
  if (mode === 'light' || mode === 'dark') return mode;
  // 'system' → check media query
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export function useTheme() {
  const storeTheme = useGlobalSettingsStore((s) => s.theme);
  const setTheme = useGlobalSettingsStore((s) => s.setTheme);

  const theme = useMemo(() => resolveTheme(storeTheme), [storeTheme]);

  const toggle = useCallback(() => {
    const current = resolveTheme(useGlobalSettingsStore.getState().theme);
    setTheme(current === 'light' ? 'dark' : 'light');
  }, [setTheme]);

  return { theme, toggle } as const;
}

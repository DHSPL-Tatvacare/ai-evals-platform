import { useEffect, useState } from 'react';

type ResolvedTheme = 'light' | 'dark';

function readTheme(): ResolvedTheme {
  return document.documentElement.getAttribute('data-theme') === 'dark'
    ? 'dark'
    : 'light';
}

/**
 * Resolved 'light' | 'dark' from the `data-theme` attribute ThemeProvider sets,
 * re-reading on change. Mirrors useResolvedColor — use when an element must swap
 * a concrete asset (e.g. an <img> src) rather than a CSS variable.
 */
export function useResolvedTheme(): ResolvedTheme {
  const [theme, setTheme] = useState<ResolvedTheme>(() =>
    typeof document === 'undefined' ? 'light' : readTheme(),
  );

  useEffect(() => {
    const observer = new MutationObserver(() => setTheme(readTheme()));
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    });
    return () => observer.disconnect();
  }, []);

  return theme;
}

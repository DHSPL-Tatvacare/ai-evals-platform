import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';

import { useAuthStore } from '@/stores/authStore';
import { fetchRunReport } from '@/services/api/orchestrationAnalytics';
import { CampaignRunReportView } from './report/CampaignRunReportView';
import type { AnalyticsScope, RunReportResponse } from './types';
import '@/styles/print-mode.css';

declare global {
  interface Window {
    __REPORT_PRINT_TOKEN__?: string;
  }
}

const PRINT_BODY_CLASS = 'report-print-mode';
/** Stop watching for layout settle once the page hasn't grown for this long. */
const HEIGHT_STABLE_WINDOW_MS = 150;
/** Hard cap so a misbehaving section can never wedge the headless renderer. */
const READINESS_TIMEOUT_MS = 8_000;

/**
 * Bridge the headless-Chromium auth token into the SPA before any component
 * mounts or `apiRequest` reads `accessToken`. Backend injects via
 * `add_init_script`; the URL-query fallback is kept for manual debugging only.
 */
function bootstrapPrintToken(): void {
  if (typeof window === 'undefined') return;

  const injectedToken = window.__REPORT_PRINT_TOKEN__;
  if (typeof injectedToken === 'string' && injectedToken.length > 0) {
    useAuthStore.getState().setAccessToken(injectedToken);
    return;
  }

  const params = new URLSearchParams(window.location.search);
  const token = params.get('token');
  if (token) {
    useAuthStore.getState().setAccessToken(token);
  }
}

bootstrapPrintToken();

/**
 * Print-mode renderer for orchestration campaign runs. Backend Playwright
 * navigates here, injects a one-shot auth token before the app boots, the page
 * fetches the run report, then renders the SAME `CampaignRunReportView` the
 * live overlay mounts — only with `printMode` set so it stacks for A4.
 */
export function PrintCampaignRun() {
  const { runId } = useParams<{ runId: string }>();
  const [report, setReport] = useState<RunReportResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    document.body.classList.add(PRINT_BODY_CLASS);

    // Force light theme for the print artifact: headless Chromium can boot
    // either color scheme, and a stale dark rendering would ship a black PDF.
    const html = document.documentElement;
    const prevTheme = html.getAttribute('data-theme');
    const prevInlineBg = html.style.backgroundColor;
    html.setAttribute('data-theme', 'light');
    html.style.backgroundColor = '';

    return () => {
      document.body.classList.remove(PRINT_BODY_CLASS);
      document.body.removeAttribute('data-report-ready');
      document.body.removeAttribute('data-report-error');
      if (prevTheme) html.setAttribute('data-theme', prevTheme);
      else html.removeAttribute('data-theme');
      html.style.backgroundColor = prevInlineBg;
    };
  }, []);

  useEffect(() => {
    if (!runId) {
      setError('Missing runId in URL');
      return;
    }
    const params = new URLSearchParams(window.location.search);
    const appId = params.get('appId') ?? '';
    const scope = (params.get('scope') ?? 'mine') as AnalyticsScope;
    if (!appId) {
      setError('Missing appId in URL');
      return;
    }
    let cancelled = false;
    fetchRunReport(runId, { appId, scope })
      .then((payload) => {
        if (!cancelled) setReport(payload);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to fetch run report');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [runId]);

  // Wait for the payload to render, fonts to load, then the page height to
  // settle so any deferred layout (charts, table wrapping) has committed.
  useEffect(() => {
    if (!report) return;

    let cancelled = false;
    let pollHandle: number | null = null;
    const start = performance.now();

    async function signalWhenStable() {
      try {
        if (typeof document.fonts !== 'undefined') {
          await document.fonts.ready;
        }
      } catch {
        // Font loading failures are non-fatal — proceed to height-stability.
      }
      if (cancelled) return;

      let lastHeight = document.documentElement.scrollHeight;
      let lastChange = performance.now();

      const poll = () => {
        if (cancelled) return;
        const now = performance.now();
        const currentHeight = document.documentElement.scrollHeight;
        if (currentHeight !== lastHeight) {
          lastHeight = currentHeight;
          lastChange = now;
        }
        const stableFor = now - lastChange;
        const elapsed = now - start;
        if (stableFor >= HEIGHT_STABLE_WINDOW_MS || elapsed >= READINESS_TIMEOUT_MS) {
          document.body.setAttribute('data-report-ready', 'true');
          return;
        }
        pollHandle = window.requestAnimationFrame(poll);
      };
      pollHandle = window.requestAnimationFrame(poll);
    }

    void signalWhenStable();

    return () => {
      cancelled = true;
      if (pollHandle !== null) cancelAnimationFrame(pollHandle);
    };
  }, [report]);

  // Surface fetch errors to the headless browser so the PDF endpoint fails
  // fast instead of timing out on the readiness selector.
  useEffect(() => {
    if (!error) return;
    document.body.setAttribute('data-report-error', error);
    document.body.setAttribute('data-report-ready', 'true');
  }, [error]);

  if (error) {
    return (
      <div className="min-h-screen bg-[var(--bg-primary)] p-6">
        <div className="rounded-md border border-[var(--color-error)] bg-[var(--bg-secondary)] p-4 text-sm text-[var(--color-error)]">
          Failed to load run report: {error}
        </div>
      </div>
    );
  }

  if (!report) {
    return (
      <div className="min-h-screen bg-[var(--bg-primary)] p-6">
        <div className="text-sm text-[var(--text-muted)]">Loading run report…</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[var(--bg-primary)] px-6 py-6">
      <CampaignRunReportView report={report} printMode />
    </div>
  );
}

export default PrintCampaignRun;

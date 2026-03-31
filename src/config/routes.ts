/**
 * Centralized route path constants and builder functions.
 * Use these instead of hardcoded string literals.
 */
export const routes = {
  login: '/login',
  signup: '/signup',
  adminUsers: '/admin/users',
  profile: '/profile',
  guide: '/guide',
  voiceRx: {
    home: "/",
    upload: "/upload",
    listing: (id: string) => `/listing/${id}`,
    dashboard: "/dashboard",
    evaluators: '/evaluators',
    runs: "/runs",
    runDetail: (runId: string) => `/runs/${runId}`,
    logs: "/logs",
    settings: "/settings",
  },
  kaira: {
    home: "/kaira",
    chat: "/kaira/chat",
    chatSession: (chatId: string) => `/kaira/chat/${chatId}`,
    dashboard: "/kaira/dashboard",
    evaluators: '/kaira/evaluators',
    runs: "/kaira/runs",
    runDetail: (runId: string) => `/kaira/runs/${runId}`,
    adversarialDetail: (runId: string, evalId: string) =>
      `/kaira/runs/${runId}/adversarial/${evalId}`,
    threadDetail: (threadId: string) => `/kaira/threads/${threadId}`,
    logs: "/kaira/logs",
    settings: "/kaira/settings",
    settingsTags: "/kaira/settings/tags",
  },
  insideSales: {
    home: '/inside-sales',
    listing: '/inside-sales',
    evaluators: '/inside-sales/evaluators',
    evaluatorDetail: (id: string) => `/inside-sales/evaluators/${id}`,
    runs: '/inside-sales/runs',
    runDetail: (runId: string) => `/inside-sales/runs/${runId}`,
    callDetail: (runId: string, callId: string) => `/inside-sales/runs/${runId}/calls/${callId}`,
    callView: (activityId: string) => `/inside-sales/calls/${activityId}`,
    leadDetail: (prospectId: string) => `/inside-sales/leads/${prospectId}`,
    dashboard: '/inside-sales/dashboard',
    logs: '/inside-sales/logs',
    settings: '/inside-sales/settings',
  },
};

/** Resolve the run detail path for a given appId. */
export function runDetailForApp(appId: string, runId: string): string {
  if (appId === "kaira-bot") {
    return routes.kaira.runDetail(runId);
  }
  if (appId === "inside-sales") {
    return routes.insideSales.runDetail(runId);
  }
  return routes.voiceRx.runDetail(runId);
}

/** Resolve the API logs path for a given appId. */
export function apiLogsForApp(appId: string): string {
  if (appId === "kaira-bot") {
    return routes.kaira.logs;
  }
  if (appId === "inside-sales") {
    return routes.insideSales.logs;
  }
  return routes.voiceRx.logs;
}

/** Check if a pathname is a run detail page for a given runId (Kaira or VoiceRx). */
export function isRunDetailPath(pathname: string, runId?: string): boolean {
  if (runId) {
    return pathname === `/kaira/runs/${runId}` || pathname === `/runs/${runId}` || pathname === `/inside-sales/runs/${runId}`;
  }
  return (
    /^\/kaira\/runs\/[^/]+$/.test(pathname) || /^\/runs\/[^/]+$/.test(pathname) || /^\/inside-sales\/runs\/[^/]+$/.test(pathname)
  );
}

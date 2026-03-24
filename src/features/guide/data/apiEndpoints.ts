import { apiRoutes } from './apiRoutes';

export interface ApiEndpoint {
  method: 'GET' | 'POST' | 'PUT' | 'DELETE';
  path: string;
  router: string;
  prefix: string;
  queryParams: string[];
  bodyExample: string;
}

function parseEndpoints(): ApiEndpoint[] {
  const endpoints: ApiEndpoint[] = [];

  for (const route of apiRoutes) {
    const entries = route.keyEndpoints.split(', ');
    for (const entry of entries) {
      const [methodStr, ...rest] = entry.trim().split(' ');
      const method = methodStr as ApiEndpoint['method'];
      const suffix = rest.join(' ');
      // Normalize: avoid trailing slash (FastAPI 307-redirects /path/ → /path)
      const raw = `${route.prefix}${suffix}`;
      const path = raw.length > 1 && raw.endsWith('/') ? raw.slice(0, -1) : raw;

      // Infer query params for common patterns
      const queryParams: string[] = [];
      if (method === 'GET' && (route.prefix === '/api/listings' || route.prefix === '/api/eval-runs' || route.prefix === '/api/prompts' || route.prefix === '/api/schemas' || route.prefix === '/api/evaluators' || route.prefix === '/api/history' || route.prefix === '/api/tags')) {
        queryParams.push('app_id');
      }
      if (method === 'GET' && suffix === '/search') {
        queryParams.push('q');
      }

      // Infer body examples for mutation methods
      let bodyExample = '';
      if (method === 'POST' || method === 'PUT') {
        if (route.prefix === '/api/jobs' && suffix === '/') {
          bodyExample = JSON.stringify({ job_type: 'evaluate-voice-rx', params: { listing_ids: ['uuid'] } }, null, 2);
        } else if (route.prefix === '/api/listings' && suffix === '/') {
          bodyExample = JSON.stringify({ app_id: 'voice-rx', name: 'Example', transcript: {} }, null, 2);
        } else if (route.prefix === '/api/chat' && suffix === '/sessions') {
          bodyExample = JSON.stringify({ app_id: 'kaira-bot', title: 'New Session' }, null, 2);
        } else if (route.prefix === '/api/chat' && suffix === '/messages') {
          bodyExample = JSON.stringify({ session_id: 'uuid', role: 'user', content: 'Hello' }, null, 2);
        } else if (route.prefix === '/api/evaluators' && suffix === '/') {
          bodyExample = JSON.stringify({ app_id: 'voice-rx', name: 'My Evaluator', prompt: '...', output_schema: {} }, null, 2);
        } else if (route.prefix === '/api/prompts' && suffix === '/') {
          bodyExample = JSON.stringify({ app_id: 'voice-rx', name: 'My Prompt', content: '...' }, null, 2);
        } else if (route.prefix === '/api/schemas' && suffix === '/') {
          bodyExample = JSON.stringify({ app_id: 'voice-rx', name: 'My Schema', schema: {} }, null, 2);
        } else if (route.prefix === '/api/settings' && suffix === '/') {
          bodyExample = JSON.stringify({ app_id: '', key: 'setting_key', value: '...' }, null, 2);
        } else if (route.prefix === '/api/tags' && suffix === '/') {
          bodyExample = JSON.stringify({ app_id: 'voice-rx', name: 'tag-name' }, null, 2);
        } else if (route.prefix === '/api/auth' && suffix === '/login') {
          bodyExample = JSON.stringify({ email: 'user@example.com', password: '...' }, null, 2);
        } else if (route.prefix === '/api/auth' && suffix === '/signup') {
          bodyExample = JSON.stringify({ token: 'invite-token', email: 'user@example.com', password: '...', displayName: 'User Name' }, null, 2);
        } else if (route.prefix === '/api/admin' && suffix === '/users') {
          bodyExample = JSON.stringify({ email: 'new@example.com', displayName: 'New User', password: '...', role: 'member' }, null, 2);
        } else if (route.prefix === '/api/admin' && suffix === '/invite-links') {
          bodyExample = JSON.stringify({ label: 'Team invite', defaultRole: 'member', maxUses: 10, expiresInHours: 168 }, null, 2);
        } else if (route.prefix === '/api/admin' && suffix === '/erase') {
          bodyExample = JSON.stringify({ target: 'eval_runs', appId: 'voice-rx' }, null, 2);
        }
      }

      endpoints.push({
        method,
        path,
        router: route.router,
        prefix: route.prefix,
        queryParams,
        bodyExample,
      });
    }
  }

  return endpoints;
}

export const apiEndpoints = parseEndpoints();

export const routers = [...new Set(apiEndpoints.map((e) => e.router))];

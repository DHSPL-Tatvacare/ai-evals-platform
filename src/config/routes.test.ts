import test, { afterEach } from 'node:test';
import assert from 'node:assert/strict';

import {
  firstAccessibleRoute,
  homeRouteForApp,
  inferAppIdFromPath,
  resetAppNavigationRegistry,
  routes,
  runDetailForApp,
  syncAppNavigation,
  threadDetailForApp,
} from './routes';

afterEach(() => {
  resetAppNavigationRegistry();
});

test('homeRouteForApp maps kaira-bot slug to kaira dashboard route', () => {
  assert.equal(homeRouteForApp('kaira-bot'), routes.kaira.home);
});

test('homeRouteForApp maps inside-sales slug to inside sales home route', () => {
  assert.equal(homeRouteForApp('inside-sales'), routes.insideSales.home);
});

test('firstAccessibleRoute returns the first valid app home route', () => {
  assert.equal(firstAccessibleRoute(['kaira-bot']), routes.kaira.home);
});

test('firstAccessibleRoute falls back to voice rx home when there is no app access', () => {
  assert.equal(firstAccessibleRoute([]), routes.voiceRx.home);
});

test('homeRouteForApp respects backend-driven navigation overrides', () => {
  syncAppNavigation('kaira-bot', { homePath: '/assistant' });

  assert.equal(homeRouteForApp('kaira-bot'), '/assistant');
  assert.equal(firstAccessibleRoute(['kaira-bot']), '/assistant');
});

test('inferAppIdFromPath uses configured owned path prefixes instead of hardcoded slugs', () => {
  syncAppNavigation('kaira-bot', {
    homePath: '/assistant',
    ownedPathPrefixes: ['/assistant'],
  });

  assert.equal(inferAppIdFromPath('/assistant/runs/123'), 'kaira-bot');
});

test('runDetailForApp uses configured path templates', () => {
  syncAppNavigation('inside-sales', {
    runDetailPath: '/revenue/runs/:runId',
  });

  assert.equal(runDetailForApp('inside-sales', 'run-42'), '/revenue/runs/run-42');
});

test('threadDetailForApp fills all required template params and returns null when missing', () => {
  assert.equal(
    threadDetailForApp('inside-sales', 'thread-9', 'run-7'),
    '/inside-sales/runs/run-7/calls/thread-9',
  );
  assert.equal(threadDetailForApp('inside-sales', 'thread-9'), null);
});

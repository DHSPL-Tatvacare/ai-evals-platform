import { test, expect } from 'vitest';

import { getNavItems } from './sidebarNav';
import { routes } from './routes';

test('inside-sales nav includes the campaign analytics item when orchestration is enabled', () => {
  const items = getNavItems('inside-sales', { hasOrchestration: true });
  expect(items.some((item) => item.to === routes.insideSales.analyticsOrchestration)).toBe(true);
});

test('inside-sales nav omits the campaign analytics item when orchestration is disabled', () => {
  const items = getNavItems('inside-sales', { hasOrchestration: false });
  expect(items.some((item) => item.to === routes.insideSales.analyticsOrchestration)).toBe(false);
});

import { test, expect } from 'vitest';

import { getAdminNavGroups, getNavItems } from './sidebarNav';
import { routes } from './routes';

test('inside-sales flat nav no longer carries a Campaign analytics item', () => {
  const items = getNavItems('inside-sales');
  expect(items.some((item) => item.to === routes.insideSales.analyticsOrchestration)).toBe(false);
});

test('admin Analytics group surfaces Campaign analytics when orchestration is manageable', () => {
  const groups = getAdminNavGroups({
    canManageUsers: false,
    canViewCost: false,
    canManageOrchestration: true,
  });
  const analytics = groups.find((g) => g.id === 'analytics');
  expect(analytics?.items.some((item) => item.to === routes.adminCampaignAnalytics)).toBe(true);
});

test('admin Analytics group omits Campaign analytics without orchestration access', () => {
  const groups = getAdminNavGroups({
    canManageUsers: false,
    canViewCost: true,
    canManageOrchestration: false,
  });
  const analytics = groups.find((g) => g.id === 'analytics');
  expect(analytics?.items.some((item) => item.to === routes.adminCampaignAnalytics)).toBe(false);
});

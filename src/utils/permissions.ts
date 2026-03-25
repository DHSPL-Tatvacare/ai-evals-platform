import { useAuthStore } from '@/stores/authStore';

/** Check permission from outside React (callbacks, services) */
export function hasPermission(permission: string): boolean {
  const user = useAuthStore.getState().user;
  if (!user) return false;
  if (user.isOwner) return true;
  return user.permissions.includes(permission);
}

/** Check app access from outside React */
export function hasAppAccess(appSlug: string): boolean {
  const user = useAuthStore.getState().user;
  if (!user) return false;
  if (user.isOwner) return true;
  return user.appAccess.includes(appSlug);
}

/** React hook for permission check (reactive) */
export function usePermission(permission: string): boolean {
  const user = useAuthStore((s) => s.user);
  if (!user) return false;
  if (user.isOwner) return true;
  return user.permissions.includes(permission);
}

/** React hook for app access check (reactive) */
export function useAppAccess(appSlug: string): boolean {
  const user = useAuthStore((s) => s.user);
  if (!user) return false;
  if (user.isOwner) return true;
  return user.appAccess.includes(appSlug);
}

/** All grantable permission IDs — keep in sync with backend Permission enum */
export const PERMISSIONS = {
  LISTING_CREATE: 'listing:create',
  LISTING_DELETE: 'listing:delete',
  EVAL_RUN: 'eval:run',
  EVAL_DELETE: 'eval:delete',
  EVAL_EXPORT: 'eval:export',
  RESOURCE_CREATE: 'resource:create',
  RESOURCE_EDIT: 'resource:edit',
  RESOURCE_DELETE: 'resource:delete',
  REPORT_GENERATE: 'report:generate',
  ANALYTICS_VIEW: 'analytics:view',
  SETTINGS_EDIT: 'settings:edit',
  USER_CREATE: 'user:create',
  USER_INVITE: 'user:invite',
  USER_EDIT: 'user:edit',
  USER_DEACTIVATE: 'user:deactivate',
  USER_RESET_PASSWORD: 'user:reset_password',
  ROLE_ASSIGN: 'role:assign',
  TENANT_SETTINGS: 'tenant:settings',
} as const;

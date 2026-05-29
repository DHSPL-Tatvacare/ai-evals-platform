import { useAuthStore } from '@/stores/authStore';
import { USER_MANAGEMENT_PERMISSIONS, userHasAnyPermission, userHasPermission } from '@/utils/permissions';

/** True when the caller may view tenant-wide ("All campaigns") analytics.
 *  Mirrors the admin-area gate used by `adminHomeRoute` / AppSwitcher:
 *  any user-management permission, cost:view, schedule:manage, or Owner.
 *  The server re-validates `scope=tenant`; this only governs the toggle. */
export function useCanSeeTenantAnalytics(): boolean {
  const user = useAuthStore((s) => s.user);
  if (!user) return false;
  if (user.isOwner) return true;
  return (
    userHasAnyPermission(user, USER_MANAGEMENT_PERMISSIONS) ||
    userHasPermission(user, 'cost:view') ||
    userHasPermission(user, 'schedule:manage')
  );
}

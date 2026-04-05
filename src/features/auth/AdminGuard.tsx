import type { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuthStore } from '@/stores/authStore';
import { ADMIN_ACCESS_PERMISSIONS, userHasAnyPermission } from '@/utils/permissions';

export function AdminGuard({ children }: { children: ReactNode }) {
  const user = useAuthStore((s) => s.user);
  if (!user) return <Navigate to="/" replace />;
  const hasAdminAccess = userHasAnyPermission(user, ADMIN_ACCESS_PERMISSIONS);
  if (!hasAdminAccess) return <Navigate to="/" replace />;
  return <>{children}</>;
}

import type { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuthStore } from '@/stores/authStore';

const ADMIN_PERMISSIONS = ['user:create', 'user:edit', 'user:invite', 'user:deactivate', 'user:reset_password'];

export function AdminGuard({ children }: { children: ReactNode }) {
  const user = useAuthStore((s) => s.user);
  if (!user) return <Navigate to="/" replace />;
  if (user.isOwner) return <>{children}</>;
  const hasAdminAccess = ADMIN_PERMISSIONS.some((p) => user.permissions.includes(p));
  if (!hasAdminAccess) return <Navigate to="/" replace />;
  return <>{children}</>;
}

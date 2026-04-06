import type { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuthStore } from '@/stores/authStore';
import { firstAccessibleRoute } from '@/config/routes';

interface PermissionGateProps {
  action: string;
  app?: string;
  fallback?: ReactNode;
  children: ReactNode;
}

/** Renders children only if the user has the required permission. */
export function PermissionGate({ action, app, fallback = null, children }: PermissionGateProps) {
  const user = useAuthStore((s) => s.user);
  if (!user) return null;
  if (user.isOwner) return <>{children}</>;
  if (app && !user.appAccess.includes(app)) return <>{fallback}</>;
  if (!user.permissions.includes(action)) return <>{fallback}</>;
  return <>{children}</>;
}

interface AppAccessGuardProps {
  app: string;
  children: ReactNode;
}

/** Route-level guard — redirects to first accessible app if no access. */
export function AppAccessGuard({ app, children }: AppAccessGuardProps) {
  const user = useAuthStore((s) => s.user);
  if (!user) return null;
  if (user.isOwner || user.appAccess.includes(app)) return <>{children}</>;

  const fallbackRoute = firstAccessibleRoute(user.appAccess);
  return <Navigate to={fallbackRoute} replace />;
}

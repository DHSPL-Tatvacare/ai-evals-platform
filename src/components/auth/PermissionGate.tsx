import type { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuthStore } from '@/stores/authStore';

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

  // Redirect to first accessible app or home
  const firstApp = user.appAccess[0];
  const fallbackRoute = firstApp ? `/${firstApp}` : '/';
  return <Navigate to={fallbackRoute} replace />;
}

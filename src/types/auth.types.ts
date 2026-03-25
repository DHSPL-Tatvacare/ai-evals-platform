export interface User {
  id: string;
  email: string;
  displayName: string;
  tenantId: string;
  tenantName: string;
  roleId: string;
  roleName: string;
  isOwner: boolean;
  permissions: string[];
  appAccess: string[];
}

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface AuthState {
  user: User | null;
  accessToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
}

export interface SignupCredentials {
  token: string;
  email: string;
  password: string;
  displayName: string;
}

export interface ValidateInviteResult {
  valid: boolean;
  tenantName?: string;
  roleId?: string;
  roleName?: string;
  expiresAt?: string;
  allowedDomains?: string[];
}

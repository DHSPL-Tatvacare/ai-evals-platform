export interface User {
  id: string;
  email: string;
  displayName: string;
  role: 'owner' | 'admin' | 'member';
  tenantId: string;
  tenantName: string;
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
  defaultRole?: string;
  expiresAt?: string;
  allowedDomains?: string[];
}

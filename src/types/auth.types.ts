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

import { apiRequest } from './client';
import type { User, LoginCredentials, SignupCredentials, ValidateInviteResult } from '@/types/auth.types';

interface LoginResponse {
  accessToken: string;
  user: User;
}

interface RefreshResponse {
  accessToken: string;
}

export const authApi = {
  login: (credentials: LoginCredentials): Promise<LoginResponse> =>
    apiRequest('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify(credentials),
    }),

  refresh: (): Promise<RefreshResponse> =>
    fetch('/api/auth/refresh', {
      method: 'POST',
      credentials: 'include',
    }).then((r) => {
      if (!r.ok) throw new Error('Refresh failed');
      return r.json();
    }),

  logout: (): Promise<void> =>
    fetch('/api/auth/logout', {
      method: 'POST',
      credentials: 'include',
    }).then(() => {}),

  getMe: (): Promise<User> => apiRequest('/api/auth/me'),

  changePassword: (currentPassword: string, newPassword: string): Promise<void> =>
    apiRequest('/api/auth/me/password', {
      method: 'PUT',
      body: JSON.stringify({ currentPassword, newPassword }),
    }),

  validateInvite: (token: string): Promise<ValidateInviteResult> =>
    fetch(`/api/auth/validate-invite?token=${encodeURIComponent(token)}`)
      .then((r) => r.json()),

  signup: (data: SignupCredentials): Promise<LoginResponse> =>
    fetch('/api/auth/signup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
      credentials: 'include',
    }).then((r) => {
      if (!r.ok) return r.json().then((d: { detail?: string }) => { throw new Error(d.detail || 'Signup failed'); });
      return r.json();
    }),
};

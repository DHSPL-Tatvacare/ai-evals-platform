import { apiRequest } from './client';

export interface AdminUser {
  id: string;
  email: string;
  displayName: string;
  role: 'owner' | 'admin' | 'member';
  isActive: boolean;
  createdAt: string;
}

export interface CreateUserRequest {
  email: string;
  displayName: string;
  password: string;
  role: 'admin' | 'member';
}

export interface UpdateUserRequest {
  displayName?: string;
  role?: 'admin' | 'member';
  isActive?: boolean;
}

export interface TenantInfo {
  id: string;
  name: string;
  slug: string;
  isActive: boolean;
  createdAt: string;
}

export const adminApi = {
  listUsers: (): Promise<AdminUser[]> =>
    apiRequest('/api/admin/users'),

  createUser: (data: CreateUserRequest): Promise<AdminUser> =>
    apiRequest('/api/admin/users', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateUser: (userId: string, data: UpdateUserRequest): Promise<AdminUser> =>
    apiRequest(`/api/admin/users/${userId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  deactivateUser: (userId: string): Promise<void> =>
    apiRequest(`/api/admin/users/${userId}`, {
      method: 'DELETE',
    }),

  getTenant: (): Promise<TenantInfo> =>
    apiRequest('/api/admin/tenant'),

  updateTenant: (data: { name: string }): Promise<TenantInfo> =>
    apiRequest('/api/admin/tenant', {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
};

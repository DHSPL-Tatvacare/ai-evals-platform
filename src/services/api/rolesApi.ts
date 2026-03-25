import { apiRequest } from './client';

export interface RoleResponse {
  id: string;
  name: string;
  description: string | null;
  isSystem: boolean;
  appAccess: string[];
  permissions: string[];
  userCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface AppResponse {
  id: string;
  slug: string;
  displayName: string;
  description: string;
  iconUrl: string;
  isActive: boolean;
}

export interface CreateRoleRequest {
  name: string;
  description?: string;
  appAccess: string[];
  permissions: string[];
}

export interface UpdateRoleRequest {
  name?: string;
  description?: string;
  appAccess?: string[];
  permissions?: string[];
}

export interface AuditLogEntry {
  id: string;
  actorId: string;
  actorEmail: string | null;
  action: string;
  entityType: string;
  entityId: string;
  beforeState: Record<string, unknown> | null;
  afterState: Record<string, unknown> | null;
  ipAddress: string | null;
  createdAt: string;
}

export interface AuditLogResponse {
  items: AuditLogEntry[];
  total: number;
  page: number;
  pageSize: number;
}

export const rolesApi = {
  listApps: () => apiRequest<AppResponse[]>('/api/apps'),
  listRoles: () => apiRequest<RoleResponse[]>('/api/admin/roles'),
  getRole: (id: string) => apiRequest<RoleResponse>(`/api/admin/roles/${id}`),
  createRole: (data: CreateRoleRequest) =>
    apiRequest<RoleResponse>('/api/admin/roles', { method: 'POST', body: JSON.stringify(data) }),
  updateRole: (id: string, data: UpdateRoleRequest) =>
    apiRequest<RoleResponse>(`/api/admin/roles/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteRole: (id: string) =>
    apiRequest<void>(`/api/admin/roles/${id}`, { method: 'DELETE' }),
  getAuditLog: (page = 1, pageSize = 50, action?: string) => {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (action) params.set('action', action);
    return apiRequest<AuditLogResponse>(`/api/admin/audit-log?${params}`);
  },
};

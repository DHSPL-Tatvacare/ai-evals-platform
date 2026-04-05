import { useState, useEffect } from 'react';
import { Modal, Button, Input } from '@/components/ui';
import { rolesApi } from '@/services/api/rolesApi';
import type { RoleResponse, AppResponse, PermissionCatalogGroupResponse } from '@/services/api/rolesApi';
import { notificationService } from '@/services/notifications';
import { cn } from '@/utils';

interface RoleEditorDialogProps {
  isOpen: boolean;
  role: RoleResponse | null;
  onClose: () => void;
  onSaved: () => void;
}

export function RoleEditorDialog({ isOpen, role, onClose, onSaved }: RoleEditorDialogProps) {
  const isEdit = role !== null;

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [selectedApps, setSelectedApps] = useState<Set<string>>(new Set());
  const [selectedPerms, setSelectedPerms] = useState<Set<string>>(new Set());
  const [apps, setApps] = useState<AppResponse[]>([]);
  const [permissionGroups, setPermissionGroups] = useState<PermissionCatalogGroupResponse[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    rolesApi.listApps().then(setApps).catch(() => {});
    rolesApi.listPermissionCatalog().then((catalog) => setPermissionGroups(catalog.groups)).catch(() => {});
  }, []);

  useEffect(() => {
    if (isOpen) {
      if (role) {
        setName(role.name);
        setDescription(role.description ?? '');
        setSelectedApps(new Set(role.appAccess));
        setSelectedPerms(new Set(role.permissions));
      } else {
        setName('');
        setDescription('');
        setSelectedApps(new Set());
        setSelectedPerms(new Set());
      }
      setError('');
    }
  }, [isOpen, role]);

  const toggleApp = (slug: string) => {
    setSelectedApps((prev) => {
      const next = new Set(prev);
      if (next.has(slug)) {
        next.delete(slug);
      } else {
        next.add(slug);
      }
      return next;
    });
  };

  const togglePerm = (id: string) => {
    setSelectedPerms((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setError('Role name is required');
      return;
    }
    setIsSubmitting(true);
    setError('');
    try {
      const payload = {
        name: name.trim(),
        description: description.trim() || undefined,
        appAccess: Array.from(selectedApps),
        permissions: Array.from(selectedPerms),
      };
      if (isEdit && role) {
        await rolesApi.updateRole(role.id, payload);
        notificationService.success('Role updated');
      } else {
        await rolesApi.createRole(payload);
        notificationService.success('Role created');
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save role');
      notificationService.error('Failed to save role');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={isEdit ? 'Edit Role' : 'Create Role'}>
      <form onSubmit={handleSubmit} className="space-y-5">
        {/* Name */}
        <div>
          <label className="mb-1 block text-[13px] font-medium text-[var(--text-secondary)]">
            Role Name
          </label>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Analyst"
            autoFocus
          />
        </div>

        {/* Description */}
        <div>
          <label className="mb-1 block text-[13px] font-medium text-[var(--text-secondary)]">
            Description <span className="text-[var(--text-muted)]">(optional)</span>
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What does this role do?"
            rows={2}
            className="w-full rounded-[6px] border border-[var(--border-default)] bg-[var(--bg-primary)] px-3 py-2 text-[13px] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] transition-colors focus:border-[var(--border-focus)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand-accent)]/50 resize-none"
          />
        </div>

        {/* App Access */}
        {apps.length > 0 && (
          <div>
            <p className="mb-2 text-[13px] font-medium text-[var(--text-secondary)]">App Access</p>
            <div className="flex flex-wrap gap-2">
              {apps.map((app) => {
                const checked = selectedApps.has(app.slug);
                return (
                  <label
                    key={app.slug}
                    className={cn(
                      'flex cursor-pointer items-center gap-2 rounded-md border px-3 py-1.5 text-[12px] transition-colors',
                      checked
                        ? 'border-[var(--color-brand-accent)] bg-[var(--color-brand-accent)]/10 text-[var(--text-brand)]'
                        : 'border-[var(--border-default)] bg-[var(--bg-secondary)] text-[var(--text-secondary)]',
                    )}
                  >
                    <input
                      type="checkbox"
                      className="sr-only"
                      checked={checked}
                      onChange={() => toggleApp(app.slug)}
                    />
                    {app.displayName}
                  </label>
                );
              })}
            </div>
          </div>
        )}

        {/* Permissions */}
        <div>
            <p className="mb-3 text-[13px] font-medium text-[var(--text-secondary)]">Permissions</p>
            <div className="space-y-4">
              {permissionGroups.map((group) => (
                <div key={group.label}>
                  <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
                    {group.label}
                  </p>
                  <div className="grid grid-cols-1 gap-1 sm:grid-cols-2">
                  {group.permissions.map((perm) => {
                    const checked = selectedPerms.has(perm.id);
                    return (
                        <label
                          key={perm.id}
                          className="flex cursor-pointer items-start gap-2 rounded px-2 py-1 text-[13px] text-[var(--text-primary)] hover:bg-[var(--bg-secondary)] transition-colors"
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => togglePerm(perm.id)}
                            className="mt-0.5 h-3.5 w-3.5 rounded border-[var(--border-default)] accent-[var(--color-brand-accent)]"
                          />
                          <span className="flex flex-col">
                            <span>{perm.label}</span>
                            <span className="text-[11px] text-[var(--text-muted)]">{perm.description}</span>
                          </span>
                        </label>
                      );
                    })}
                  </div>
                </div>
              ))}
              {permissionGroups.length === 0 && (
                <p className="text-[12px] text-[var(--text-muted)]">Permission catalog unavailable.</p>
              )}
            </div>
          </div>

        {error && <p className="text-[13px] text-[var(--color-error)]">{error}</p>}

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="secondary" size="md" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" size="md" isLoading={isSubmitting}>
            {isEdit ? 'Save Changes' : 'Create Role'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

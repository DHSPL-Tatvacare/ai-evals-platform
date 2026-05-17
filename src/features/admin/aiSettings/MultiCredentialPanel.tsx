import { useState } from 'react';
import {
  CheckCircle2,
  Plus,
  ShieldAlert,
  ShieldQuestion,
  Trash2,
} from 'lucide-react';

import { Badge, Button, EmptyState, LLMProviderLogo, Switch } from '@/components/ui';
import { LLM_PROVIDER_LABELS } from '@/constants/llmProviders';
import { notificationService } from '@/services/notifications';
import {
  useDeleteCredential,
  useTenantCredentials,
  useUpdateCredential,
  useValidateCredential,
} from '@/services/api/llmCredentialsQueries';
import type {
  LlmProvider,
  TenantCredential,
} from '@/services/api/llmCredentialsApi';

import { AzureDeploymentEditor } from './AzureDeploymentEditor';
import { CredentialFormSlideOver } from './CredentialFormSlideOver';

interface MultiCredentialPanelProps {
  provider: LlmProvider;
}

/**
 * Provider-scoped multi-credential admin view. Replaces the single-credential
 * bridge form. Lists every `tenant_llm_credentials` row for `(tenant, provider)`,
 * supports add/edit/delete/validate/enable-toggle per credential, and for
 * Azure credentials renders the nested deployment editor inline.
 */
export function MultiCredentialPanel({ provider }: MultiCredentialPanelProps) {
  const { data: credentials = [], isLoading } = useTenantCredentials(provider);
  const [formState, setFormState] = useState<
    | { open: false }
    | { open: true; mode: 'create' }
    | { open: true; mode: 'edit'; credential: TenantCredential }
  >({ open: false });

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex shrink-0 items-center justify-between gap-3 border-b border-dashed border-[var(--border-subtle)] pb-3">
        <div className="flex items-center gap-3">
          <LLMProviderLogo provider={provider} size={28} />
          <div className="flex flex-col">
            <h2 className="text-[15px] font-semibold text-[var(--text-primary)]">
              {LLM_PROVIDER_LABELS[provider]}
            </h2>
            <p className="text-[12px] text-[var(--text-secondary)]">
              {credentials.length === 0
                ? 'No credentials configured.'
                : `${credentials.length} credential${credentials.length === 1 ? '' : 's'} configured.`}
            </p>
          </div>
        </div>
        <Button
          variant="primary"
          size="sm"
          icon={Plus}
          onClick={() => setFormState({ open: true, mode: 'create' })}
        >
          Add credential
        </Button>
      </header>

      <div className="mt-4 flex flex-1 min-h-0 flex-col overflow-y-auto">
        {isLoading ? (
          <div className="px-3 py-4 text-[12px] text-[var(--text-muted)]">
            Loading…
          </div>
        ) : credentials.length === 0 ? (
          // Header's "Add credential" button is the single action; no
          // duplicate CTA inside the empty state.
          <EmptyState
            icon={Plus}
            title={`No ${LLM_PROVIDER_LABELS[provider]} credentials yet`}
            description="Use the Add credential button above to register your first key."
            fill
          />
        ) : (
          <div className="space-y-3">
            {credentials.map((c) => (
              <CredentialCard
                key={c.id}
                credential={c}
                provider={provider}
                onEdit={() =>
                  setFormState({ open: true, mode: 'edit', credential: c })
                }
              />
            ))}
          </div>
        )}
      </div>

      {formState.open && (
        <CredentialFormSlideOver
          open
          onClose={() => setFormState({ open: false })}
          provider={provider}
          credential={
            formState.mode === 'edit' ? formState.credential : null
          }
        />
      )}
    </div>
  );
}

interface CredentialCardProps {
  credential: TenantCredential;
  provider: LlmProvider;
  onEdit: () => void;
}

function CredentialCard({ credential, provider, onEdit }: CredentialCardProps) {
  const update = useUpdateCredential(provider);
  const validate = useValidateCredential();
  const deleteMut = useDeleteCredential(provider);
  const [validating, setValidating] = useState(false);

  const isAzure = provider === 'azure_openai';

  const handleToggle = async (on: boolean) => {
    try {
      await update.mutateAsync({
        credentialId: credential.id,
        body: { isEnabled: on },
      });
    } catch (err) {
      notificationService.error(
        err instanceof Error ? err.message : 'Toggle failed',
      );
    }
  };

  const handleValidate = async () => {
    setValidating(true);
    try {
      const result = await validate.mutateAsync(credential.id);
      if (result.validationStatus === 'ok') {
        notificationService.success('Credentials validated');
      } else {
        notificationService.warning(
          result.detail ? `Invalid: ${result.detail}` : 'Validation failed',
        );
      }
    } catch (err) {
      notificationService.error(
        err instanceof Error ? err.message : 'Validation failed',
      );
    } finally {
      setValidating(false);
    }
  };

  const handleDelete = async () => {
    const confirmed = window.confirm(
      `Delete credential "${credential.name}"? Any LLM Default referencing it will break until you remap.`,
    );
    if (!confirmed) return;
    try {
      await deleteMut.mutateAsync(credential.id);
      notificationService.success(`Credential "${credential.name}" deleted`);
    } catch (err) {
      notificationService.error(
        err instanceof Error ? err.message : 'Delete failed',
      );
    }
  };

  const statusBadge = (() => {
    if (!credential.isEnabled) return <Badge variant="neutral">Disabled</Badge>;
    if (credential.validationStatus === 'ok') {
      return (
        <Badge variant="success" icon={CheckCircle2}>
          Validated
        </Badge>
      );
    }
    if (credential.validationStatus === 'invalid') {
      return (
        <Badge variant="danger" icon={ShieldAlert}>
          Invalid
        </Badge>
      );
    }
    return (
      <Badge variant="neutral" icon={ShieldQuestion}>
        Untested
      </Badge>
    );
  })();

  const extra = credential.extraConfig ?? {};
  const endpoint = (extra.base_url as string | undefined) ?? '';
  const apiVersion = (extra.api_version as string | undefined) ?? '';
  const projectId = (extra.project_id as string | undefined) ?? '';
  const region = (extra.default_region as string | undefined) ?? '';

  return (
    <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="text-[13px] font-semibold text-[var(--text-primary)]">
              {credential.name}
            </h3>
            {statusBadge}
          </div>
          <div className="mt-1 space-y-0.5 text-[12px] text-[var(--text-muted)]">
            <div>
              <span className="text-[var(--text-secondary)]">Secret:</span>{' '}
              {credential.secretPreview ?? '— none stored —'}
            </div>
            {endpoint && (
              <div>
                <span className="text-[var(--text-secondary)]">Endpoint:</span>{' '}
                {endpoint}
              </div>
            )}
            {apiVersion && (
              <div>
                <span className="text-[var(--text-secondary)]">API version:</span>{' '}
                {apiVersion}
              </div>
            )}
            {projectId && (
              <div>
                <span className="text-[var(--text-secondary)]">Project:</span>{' '}
                {projectId}
              </div>
            )}
            {region && (
              <div>
                <span className="text-[var(--text-secondary)]">Region:</span>{' '}
                {region}
              </div>
            )}
            {credential.lastValidatedAt && (
              <div>
                <span className="text-[var(--text-secondary)]">Last validated:</span>{' '}
                {new Date(credential.lastValidatedAt).toLocaleString()}
              </div>
            )}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Switch
            checked={credential.isEnabled}
            onCheckedChange={handleToggle}
            aria-label={`Enable ${credential.name}`}
          />
          <Button
            variant="secondary"
            size="sm"
            disabled={validating}
            onClick={handleValidate}
          >
            {validating ? 'Testing…' : 'Test'}
          </Button>
          <Button variant="secondary" size="sm" onClick={onEdit}>
            Edit
          </Button>
          <Button
            variant="ghost"
            size="sm"
            icon={Trash2}
            onClick={handleDelete}
            aria-label={`Delete ${credential.name}`}
          />
        </div>
      </div>

      {isAzure && (
        <AzureDeploymentEditor
          credentialId={credential.id}
          credentialName={credential.name}
        />
      )}
    </div>
  );
}

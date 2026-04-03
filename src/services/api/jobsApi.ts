/**
 * Jobs API client — submit, track, and poll background jobs.
 *
 * Backend returns camelCase via Pydantic alias_generator.
 */
import { apiRequest } from './client';

export interface Job {
  id: string;
  jobType: string;
  status: 'queued' | 'running' | 'retryable_failed' | 'completed' | 'failed' | 'cancelled';
  appId?: string;
  queueClass?: 'interactive' | 'standard' | 'bulk';
  priority?: number;
  attemptCount?: number;
  maxAttempts?: number;
  params: Record<string, unknown>;
  result: Record<string, unknown> | null;
  progress: { current: number; total: number; message: string };
  errorMessage: string | null;
  createdAt: string;
  startedAt: string | null;
  completedAt: string | null;
  heartbeatAt?: string | null;
  leaseExpiresAt?: string | null;
  nextRetryAt?: string | null;
  deadLetteredAt?: string | null;
  deadLetterReason?: string | null;
  queuePosition?: number | null;
}

export const jobsApi = {
  async submit(jobType: string, params: Record<string, unknown>): Promise<Job> {
    return apiRequest<Job>('/api/jobs', {
      method: 'POST',
      body: JSON.stringify({ jobType, params }),
    });
  },

  async list(opts?: { status?: string; jobType?: string }): Promise<Job[]> {
    const params = new URLSearchParams();
    if (opts?.status) params.set('status', opts.status);
    if (opts?.jobType) params.set('job_type', opts.jobType);
    const qs = params.toString();
    return apiRequest<Job[]>(`/api/jobs${qs ? `?${qs}` : ''}`);
  },

  async get(jobId: string): Promise<Job> {
    return apiRequest<Job>(`/api/jobs/${jobId}`);
  },

  async cancel(jobId: string): Promise<void> {
    await apiRequest(`/api/jobs/${jobId}/cancel`, { method: 'POST' });
  },
};
